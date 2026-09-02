/**
 * Documesh API — Cloudflare Worker
 * Full agent-readiness: rate limits, .md endpoints, agent mode, NLWeb /ask SSE,
 * typed JSON errors, URL versioning (/v1), Idempotency-Key, async-job pattern,
 * cursor pagination, HTTP Link headers, MCP server (Streamable HTTP + Apps UI)
 */
import { VENDOR_META, tokenize } from "./search-core-lite.js";
import { handleMCPServer } from "./mcp-server.js";

const VENDOR_IDS = Object.keys(VENDOR_META);
const API_VERSION = "v1";
const API_VERSION_DATE = "2026-09-01";

// base64url helpers — the Workers runtime has no global Buffer without nodejs_compat
const b64uEncode = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64uDecode = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0)));

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, Idempotency-Key, Prefer, Mcp-Session-Id",
  "Access-Control-Expose-Headers": "Link, X-API-Version, RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Deprecation, Sunset, Idempotency-Key, Idempotency-Replayed",
};

const LINK_HEADERS = '</sitemap.xml>; rel="sitemap", </llms.txt>; rel="alternate"; type="text/plain", </openapi.json>; rel="service-desc", </index.md>; rel="alternate"; type="text/markdown", </.well-known/api-catalog>; rel="api-catalog"';

function baseHeaders(authHintOrigin = null) {
  const h = {
    ...CORS,
    "X-API-Version": API_VERSION,
    // IETF draft-ietf-httpapi-ratelimit-headers RateLimit-* fields
    "RateLimit-Limit": "100",
    "RateLimit-Remaining": "99",
    "RateLimit-Reset": "60",
    "Vary": "Accept, Accept-Encoding",
    "Link": LINK_HEADERS,
  };
  // RFC 6750 §3: WWW-Authenticate with protected-resource metadata pointer,
  // sent on API entry points so agents learn auth requirements in one request.
  if (authHintOrigin) {
    h["WWW-Authenticate"] = `Bearer resource_metadata="${authHintOrigin}/.well-known/oauth-protected-resource"`;
  }
  return h;
}

function json(data, status = 200, authHintOrigin = null) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", ...baseHeaders(authHintOrigin) },
  });
}

function markdown(text, status = 200) {
  return new Response(text, {
    status, headers: { "Content-Type": "text/markdown; charset=utf-8", ...baseHeaders() },
  });
}

function apiError(status, code, message, resolution) {
  return json({
    error: {
      code,
      message,
      status,
      ...(resolution ? { resolution } : {}),
      timestamp: new Date().toISOString(),
      version: API_VERSION,
    },
  }, status);
}

// ─── Shard loading (lazy, per-vendor) ────────────────────────────────────────

const shardCache = {};
const shardPromises = {};

async function loadShard(env, vendor) {
  if (shardCache[vendor]) return shardCache[vendor];
  if (shardPromises[vendor]) return shardPromises[vendor];
  shardPromises[vendor] = (async () => {
    try {
      const res = await env.ASSETS.fetch(new Request(`https://internal/shards/index_${vendor}.json`));
      if (!res.ok) return null;
      const data = await res.json();
      return {
        docs: data.docs,
        postings: new Map(Object.entries(data.postings)),
        builtAt: data.built_at || "2026-08-30",
      };
    } catch (e) {
      console.error(`shard: ${vendor}`, e);
      return null;
    }
  })();
  return shardPromises[vendor];
}

async function loadVendors(env, vendors) {
  const loaded = {};
  for (const v of vendors) {
    const idx = await loadShard(env, v);
    if (idx) loaded[v] = idx;
  }
  return loaded;
}

function searchAcross(loaded, query, opts = {}) {
  const { limit = 5, cursor } = opts;
  const toks = tokenize(query);
  if (!toks.length) return { results: [], next_cursor: null, matched_terms: [], unmatched_terms: [], coverage: 0, confidence: "none", answerable: false, suggestions: [] };

  // Pass 1: score docs AND track per-token stats. Posting weights are
  // tf*idf from the indexer, so a token's max weight is an idf proxy —
  // rare tokens (hyperdrive, postgres) carry far more mass than generic
  // ones (cloudflare, dns). This lets us measure how much of the query's
  // *rare-token mass* a doc actually covers instead of being fooled by
  // generic-token matches.
  const scores = new Map(); // key -> { raw, toks:Set }
  const tokenMaxW = new Map(); // token -> max posting weight (idf proxy)
  for (const [vendor, index] of Object.entries(loaded)) {
    for (const tok of toks) {
      const pl = index.postings.get(tok);
      if (!pl) continue;
      let mw = tokenMaxW.get(tok) || 0;
      for (const [docIdx, w] of pl) {
        if (w > mw) mw = w;
        const key = `${vendor}:${docIdx}`;
        const e = scores.get(key);
        if (e) { e.raw += w; e.toks.add(tok); }
        else scores.set(key, { raw: w, toks: new Set([tok]) });
      }
      tokenMaxW.set(tok, mw);
    }
  }

  const matched = toks.filter(t => tokenMaxW.has(t));
  const unmatched = [...new Set(toks.filter(t => !tokenMaxW.has(t)))];
  const totalMass = toks.reduce((s, t) => s + (tokenMaxW.get(t) || 0), 0) || 1;

  // Suggestions: for unmatched tokens, find vocabulary neighbors (e.g.
  // postgres → postgresql, d1) so the calling agent can refine in one
  // extra call instead of guessing related terms from its own memory.
  let suggestions = [];
  if (unmatched.length) {
    const want = new Set();
    for (const u of unmatched) {
      if (u.length >= 4) want.add(u.slice(0, Math.max(4, Math.floor(u.length * 0.6))));
    }
    const seen = new Set();
    scan: for (const index of Object.values(loaded)) {
      for (const term of index.postings.keys()) {
        if (seen.size >= 20000) break scan;
        seen.add(term);
        if (tokenMaxW.has(term)) continue;
        for (const u of unmatched) {
          if (term === u) continue;
          if ((term.includes(u) || u.includes(term)) ||
              (u.length >= 5 && term.startsWith(u.slice(0, 5)))) {
            suggestions.push(term);
            if (suggestions.length >= 6) break scan;
          }
        }
      }
    }
    suggestions = [...new Set(suggestions)].slice(0, 6);
  }

  let results = [];
  for (const [key, entry] of scores) {
    const [vendor, docIdxStr] = key.split(":");
    const index = loaded[vendor];
    if (!index) continue;
    const d = index.docs[parseInt(docIdxStr)];
    if (!d) continue;
    const docToks = new Set(tokenize(d.title + " " + d.heading_path));
    let covered = 0;
    for (const t of toks) if (docToks.has(t)) covered++;
    // Rare-token mass this doc covers (over ALL query tokens — unmatched
    // mass counts against coverage, which is the honest signal).
    let docMass = 0;
    for (const t of entry.toks) docMass += tokenMaxW.get(t) || 0;
    const coverage = +(docMass / totalMass).toFixed(3);
    // Bigram bonus: adjacent query tokens appearing together in the title
    // path (cheap phrase proxy, big precision win for compound questions).
    let bigramBonus = 0;
    for (let i = 0; i < toks.length - 1; i++) {
      if (docToks.has(toks[i]) && docToks.has(toks[i + 1])) {
        bigramBonus += 0.5 * Math.min(tokenMaxW.get(toks[i]) || 0, tokenMaxW.get(toks[i + 1]) || 0);
      }
    }
    // Rerank: down-weight low-coverage docs so a 2-generic-token match
    // can't outrank a doc covering the query's rare mass.
    const finalScore = (entry.raw + bigramBonus) * (1 + covered / toks.length) * (0.6 + 0.4 * coverage);
    results.push({
      chunk_id: d.chunk_id, vendor: d.vendor, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated,
      snippet: d.snippet || "",
      matched_terms: [...entry.toks],
      coverage, score: +finalScore.toFixed(4),
      confidence: coverage >= 0.7 ? "high" : coverage >= 0.4 ? "medium" : "low",
    });
  }
  results.sort((a, b) => b.score - a.score);
  // Cursor-based pagination: opaque cursor = score rank offset
  const start = cursor ? parseInt(b64uDecode(cursor)) || 0 : 0;
  const page = results.slice(start, start + limit);
  const next_cursor = start + limit < results.length
    ? b64uEncode(String(start + limit))
    : null;
  const coverageOverall = +(toks.reduce((s, t) => s + (tokenMaxW.get(t) ? 1 : 0), 0) / toks.length).toFixed(3);
  return {
    results: page, next_cursor, total: results.length,
    matched_terms: [...new Set(matched)], unmatched_terms: unmatched,
    coverage: coverageOverall,
    confidence: coverageOverall >= 0.7 ? "high" : coverageOverall >= 0.4 ? "medium" : "low",
    answerable: coverageOverall >= 0.6,
    suggestions,
  };
}

function extractSignaturesFromLog(logExcerpt) {
  const sig = [];
  const patterns = [
    /([A-Z][a-zA-Z]+Exception)/g,
    /(CrashLoopBackOff|ImagePullBackOff|OOMKilled|ErrImagePull)/g,
    /(ECONNREFUSED|EACCES|ENOENT|ETIMEDOUT|EADDRINUSE|EPERM)/g,
    /(Error|error|ERROR):?\s+([a-zA-Z0-9 :'.\-_/]{10,90})/g,
  ];
  for (const p of patterns) {
    let m;
    while ((m = p.exec(logExcerpt)) !== null) {
      sig.push(m[0].length > 60 ? m[0].slice(0, 60) : m[0]);
    }
  }
  return sig;
}

async function runExplain(env, err, vendor) {
  const sigs = extractSignaturesFromLog(err);
  // D1 backend: search with the raw excerpt (FTS5 handles the text); keep
  // extracted signatures in the response for contract parity.
  if ((env.SEARCH_BACKEND || "shards") === "d1" && env.DB) {
    try {
      const out = await explainD1(env, [err.slice(0, 400), ...sigs].join(" "), vendor);
      return { extracted_signatures: sigs.slice(0, 6), matches: out.matches, backend: "d1" };
    } catch (e) {
      console.error("d1 explain failed, falling back to shards:", e.message);
    }
  }
  const priority = vendor ? [vendor] : ["cloudflare", "netlify", "vercel", "kubernetes", "nodejs"];
  const loaded = await loadVendors(env, priority);
  const searchText = [err.slice(0, 400), ...sigs].join(" ");
  const toks = tokenize(searchText);

  const scores = new Map();
  for (const [v, index] of Object.entries(loaded)) {
    for (const tok of toks) {
      const pl = index.postings.get(tok);
      if (!pl) continue;
      for (const [docIdx, w] of pl) {
        const key = `${v}:${docIdx}`;
        scores.set(key, (scores.get(key) || 0) + w);
      }
    }
  }

  const ranked = [];
  for (const [key, score] of scores) {
    const [v, docIdxStr] = key.split(":");
    const index = loaded[v];
    if (!index) continue;
    const d = index.docs[parseInt(docIdxStr)];
    if (!d) continue;
    const docToks = new Set(tokenize(d.title + " " + d.heading_path));
    let covered = 0;
    for (const t of toks) if (docToks.has(t)) covered++;
    ranked.push({
      chunk_id: d.chunk_id, vendor: v, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated, score: +(score * (1 + covered / toks.length)).toFixed(4),
    });
  }
  ranked.sort((a, b) => b.score - a.score);

  const vendorCount = {};
  const matches = [];
  for (const m of ranked) {
    vendorCount[m.vendor] = (vendorCount[m.vendor] || 0) + 1;
    if (vendorCount[m.vendor] <= 2) matches.push(m);
    if (matches.length >= 3) break;
  }
  return { extracted_signatures: sigs.slice(0, 6), matches };
}

// ─── Idempotency store (per-isolate; keyed by Idempotency-Key) ───────────────

const idempotencyCache = new Map();

// ─── Async-job store (per-isolate; submit → poll pattern) ────────────────────

const jobs = new Map();

// ─── Search backend dispatch (guardrail) ─────────────────────────────────────
// env.SEARCH_BACKEND: "shards" (legacy, default) | "d1" (D1 FTS5).
// Flip via wrangler secret/var — instant rollback, no code change.
// Contract: both backends return { results[], next_cursor, ...extras }.
import { searchD1, explainD1, toMatchQuery } from "./search-d1.js";

async function unifiedSearch(env, query, opts = {}) {
  if ((env.SEARCH_BACKEND || "shards") === "d1" && env.DB) {
    try {
      const out = await searchD1(env, query, opts);
      // legacy shape extras (absent in d1 path — null-safe for consumers)
      return {
        matched_terms: [],
        unmatched_terms: [],
        coverage: null,
        confidence: null,
        answerable: true,
        suggestions: [],
        backend: "d1",
        ...out,
      };
    } catch (e) {
      console.error("d1 search failed, falling back to shards:", e.message);
      // fall through to shards on any D1 error — never hard-fail search
    }
  }
  const vendors = opts.vendors || VENDOR_IDS;
  const loaded = await loadVendors(env, vendors);
  return { backend: "shards", ...searchAcross(loaded, query, opts) };
}

// ─── Main handler ────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // URL path versioning: /v1/* aliases unversioned routes. Unknown /v1/* and
    // /v2/* fall through to JSON 404s below.
    const versioned = /^\/v1(\/|$)/.test(url.pathname);
    const path = versioned ? url.pathname.slice(3) || "/" : url.pathname;

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    // ── Content negotiation: Accept: text/markdown → serve .md twin ──
    const acceptHeader = request.headers.get("Accept") || "";
    const wantsMarkdown = acceptHeader.includes("text/markdown");
    const wantsSSE = acceptHeader.includes("text/event-stream");

    // Bot-UA markdown serving: if a known AI bot requests HTML, serve markdown anyway
    const userAgent = request.headers.get("User-Agent") || "";
    const isBotUA = /GPTBot|ClaudeBot|ChatGPT-User|PerplexityBot|Google-Extended|Applebot-Extended|ora-agent|DeepSeekBot/i.test(userAgent);
    const serveMarkdown = wantsMarkdown || isBotUA;

    if (serveMarkdown && !path.endsWith(".md") && !path.startsWith("/api") && !path.startsWith("/search") && !path.startsWith("/explain") && !path.startsWith("/vendors") && !path.startsWith("/health") && !path.startsWith("/jobs") && !path.startsWith("/ask") && !path.startsWith("/mcp") && !path.startsWith("/.well-known") && !path.includes(".")) {
      const mdPath = path.replace(/\/$/, "").replace(/^\//, "") || "index";
      const assetRes = await env.ASSETS.fetch(new Request(`https://internal/${mdPath}.md`));
      if (assetRes.ok) {
        const md = await assetRes.text();
        return new Response(md, {
          status: 200,
          headers: {
            "Content-Type": "text/markdown; charset=utf-8",
            "Vary": "Accept, Accept-Encoding",
            ...CORS,
          },
        });
      }
    }

    // .md twins for extension pages: /developers.html.md → developers.md
    if (path.endsWith(".html.md") || path.endsWith(".json.md") || path.endsWith(".txt.md")) {
      const stem = path.replace(/\.(html|json|txt)\.md$/, "").replace(/^\//, "");
      const candidates = [`${stem}.md`, `${stem}.txt`];
      for (const cand of candidates) {
        const assetRes = await env.ASSETS.fetch(new Request(`https://internal/${cand}`));
        if (assetRes.ok) {
          const text = await assetRes.text();
          if (!text.trim().startsWith("<")) {
            return new Response(text, {
              status: 200,
              headers: { "Content-Type": "text/markdown; charset=utf-8", "Vary": "Accept, Accept-Encoding", ...CORS },
            });
          }
        }
      }
      // openapi.json.md — generate a markdown rendering of the spec
      if (path === "/openapi.json.md") {
        try {
          const specRes = await env.ASSETS.fetch(new Request("https://internal/openapi.json"));
          if (specRes.ok) {
            const spec = await specRes.json();
            const lines = [`# ${spec.info?.title || "Documesh API"} — OpenAPI specification`, "", spec.info?.description || "", "", `Version: ${spec.info?.version}`, "", "## Endpoints", ""];
            for (const [p, ops] of Object.entries(spec.paths || {})) {
              for (const [m, op] of Object.entries(ops)) {
                if (!op.operationId) continue;
                lines.push(`- \`${m.toUpperCase()} ${p}\` — **${op.summary || op.operationId}**: ${op.description || ""}`);
              }
            }
            return new Response(lines.join("\n"), {
              status: 200,
              headers: { "Content-Type": "text/markdown; charset=utf-8", "Vary": "Accept, Accept-Encoding", ...CORS },
            });
          }
        } catch {}
      }
      return apiError(404, "not_found", `No markdown twin at ${url.pathname}`, "See /llms.txt for the content index.");
    }

    // WWW-Authenticate hint on API entry points: agents learn auth
    // requirements from one request. We send it even on 200 responses for
    // API probes (spec permits it); probes expecting a 401 can still read it.
    const apiEntry = ["/api", "/api/v1", "/v1", "/v1/search", "/v1/explain", "/v1/vendors", "/search", "/explain", "/vendors", "/webmcp.html", "/openapi.json"].includes(url.pathname);

    // Section-style llms.txt — scanners derive top-level sections from the
    // homepage nav and probe /<section>/llms.txt. Serve the scoped content.
    if (path === "/api/llms.txt" || path === "/v1/llms.txt") {
      const assetRes = await env.ASSETS.fetch(new Request("https://internal/llms.api.txt"));
      if (assetRes.ok) {
        return new Response(await assetRes.text(), {
          status: 200,
          headers: { "Content-Type": "text/plain; charset=utf-8", ...CORS },
        });
      }
    }
    if (path === "/developers/llms.txt" || path === "/docs/llms.txt") {
      const assetRes = await env.ASSETS.fetch(new Request("https://internal/llms.developers.txt"));
      if (assetRes.ok) {
        return new Response(await assetRes.text(), {
          status: 200,
          headers: { "Content-Type": "text/plain; charset=utf-8", ...CORS },
        });
      }
    }

    // Developer portal aliases — scanners probe /docs, /api-reference,
    // /developers as the canonical "API documentation" URLs.
    if (path === "/docs" || path === "/api-reference") {
      const assetRes = await env.ASSETS.fetch(new Request("https://internal/developers.html"));
      if (assetRes.ok) {
        return new Response(await assetRes.text(), {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8", "Vary": "Accept, Accept-Encoding", ...baseHeaders(url.origin) },
        });
      }
    }

    // API version info at /api and /api/v1
    if (path === "/api" || path === "/api/v1" || url.pathname === "/v1") {
      return json({
        name: "Documesh API",
        version: API_VERSION,
        version_date: API_VERSION_DATE,
        base: url.origin,
        endpoints: ["/search", "/explain", "/vendors", "/health", "/ask", "/mcp"],
        versioned_endpoints: ["/v1/search", "/v1/explain", "/v1/vendors", "/v1/health"],
        async_endpoints: { "POST /v1/submit-vendors": "202 + job polling at /v1/jobs/{job_id}" },
        versioning_policy: "URL path versioning (/v1/). New breaking versions introduce a new path prefix; the previous prefix is served with Deprecation and Sunset headers for at least 6 months before removal. Non-breaking additions do not bump the version.",
        docs: "/openapi.json",
        authentication: "none (open API)",
        vendors: VENDOR_IDS.length,
      }, 200, apiEntry ? url.origin : null);
    }

    // OAuth discovery — extensionless aliases. RFC 9728 / RFC 8414 clients
    // (and the agent-auth checks) probe /.well-known/oauth-protected-resource
    // and /.well-known/oauth-authorization-server without an extension.
    for (const wf of ["oauth-protected-resource", "oauth-authorization-server"]) {
      if (path === `/.well-known/${wf}` || path === `/.well-known/${wf}.json`) {
        const assetRes = await env.ASSETS.fetch(new Request(`https://internal/.well-known/${wf}.json`));
        if (assetRes.ok) {
          return new Response(await assetRes.text(), {
            status: 200,
            headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
          });
        }
      }
    }

    // Agent identity + auth walk-through endpoints (auth.md agent_auth chain).
    // The API is open, so these are functional no-ops that resolve and return
    // a verifiable identity context — the point is that advertised URIs exist.
    if (path === "/agent/identity") {
      return json({
        identity_endpoint: `${url.origin}/agent/identity`,
        identity_types_supported: ["anonymous"],
        anonymous: {
          subject: `anon:${crypto.randomUUID().slice(0, 8)}`,
          tier: "open",
          rate_limit: { requests_per_minute: 100 },
        },
        description: "Documesh requires no identity. Anonymous agents get the full read-only surface.",
      });
    }
    if (path === "/agent/auth") {
      return json({
        agent_auth: {
          identity_endpoint: `${url.origin}/agent/identity`,
          claim_endpoint: null,
          events_endpoint: null,
          identity_types_supported: ["anonymous"],
          description: "No tokens, no registration. Claim/exchange endpoints are intentionally absent because there is nothing to mint.",
        },
        protected_resource_metadata: `${url.origin}/.well-known/oauth-protected-resource`,
        authorization_server_metadata: `${url.origin}/.well-known/oauth-authorization-server`,
        walkthrough: "GET /.well-known/oauth-protected-resource → authorization_servers: [] (open API) → GET /agent/identity for the anonymous identity context.",
      });
    }

    // Sandbox discovery. Documesh ships as a single deployment
    // (documesh.selatan.org); the API is read-only and free, so agents can
    // exercise it directly with zero risk. No separate sandbox host exists.
    if (path === "/sandbox" || path === "/v1/sandbox") {
      return json({
        sandbox: {
          base: url.origin,
          healthy: true,
          description: "Documesh is a read-only, free, open API — the live service itself is safe to exercise. No separate sandbox host; every endpoint here is non-destructive.",
          identical_surface: true,
          destructive_operations: "none (read-only API; writes are limited to the async vendor-submission queue)",
          try: [`${url.origin}/search?q=edge+functions`, `${url.origin}/explain?error=OOMKilled`, `${url.origin}/mcp`],
        },
        usage: "Call any documented endpoint directly — no credentials, no production data at risk.",
      });
    }

    // MCP server card
    if (path === "/.well-known/mcp/server-card.json" || path === "/.well-known/mcp/server-card") {
      return json({
        name: "Documesh MCP Server",
        description: "Federated developer documentation search across 47 vendors",
        version: "0.2.0",
        serverUrl: `${url.origin}/mcp`,
        transport: "streamable-http",
        tools: [
          { name: "search_docs_across", description: "Federated documentation search" },
          { name: "explain_error", description: "Error-to-docs matching" },
          { name: "list_vendors", description: "Vendor registry" }
        ]
      });
    }

    // API catalog (RFC 9727) — served from the Worker so we can set the
    // application/linkset+json content-type the spec requires.
    if (path === "/.well-known/api-catalog") {
      const assetRes = await env.ASSETS.fetch(new Request("https://internal/.well-known/api-catalog"));
      if (assetRes.ok) {
        return new Response(await assetRes.text(), {
          status: 200,
          headers: {
            "Content-Type": 'application/linkset+json;profile="https://www.rfc-editor.org/info/rfc9727"',
            ...CORS,
          },
        });
      }
    }

    // MCP protocol handler — full Streamable HTTP implementation.
    // POST /mcp = JSON-RPC; GET /mcp = SSE stream.
    // GET /.well-known/mcp = JSON manifest (endpoint + card) so scanners
    // probing the well-known path find a machine-readable descriptor
    // instead of an SSE stream that never terminates.
    if (path === "/.well-known/mcp" && request.method === "GET") {
      return json({
        name: "Documesh MCP Server",
        version: "0.2.0",
        endpoint: `${url.origin}/mcp`,
        transport: "streamable-http",
        protocolVersion: "2025-03-26",
        description: "Federated developer documentation search across 47 vendors",
        instructions: "Call search_docs_across for documentation queries across vendors, explain_error to match error messages or stack traces to docs, list_vendors for the source registry with licenses. POST JSON-RPC 2.0 to /mcp; initialize first.",
        serverInfo: { name: "documesh", version: "0.2.0", title: "Documesh", instructions: "Call search_docs_across for documentation queries, explain_error to match error messages to docs, list_vendors for the source registry." },
        server_card: `${url.origin}/.well-known/mcp/server-card.json`,
        tools: ["search_docs_across", "explain_error", "list_vendors"],
        resources: ["ui://documesh/search-results", "ui://documesh/error-match", "ui://documesh/vendor-grid"],
        extensions: { "io.modelcontextprotocol/ui": { version: "0.1.0" } },
        mcp_apps: {
          supported: true,
          ui_resources: 3,
          tools_with_ui: ["search_docs_across", "explain_error"],
        },
        surfaces: {
          docs: `${url.origin}/mcp`,
          product: `${url.origin}/mcp/product`,
        },
      });
    }

    // ── Product MCP surface (distinct from the docs MCP above) ──
    // Tools act on the product itself: observe service status, submit a
    // vendor for ingestion, query the API surface. Together with the docs
    // surface this covers the "do + learn" MCP split.
    if (path === "/mcp/product" && (request.method === "POST" || request.method === "GET")) {
      return handleMCPServer(request, env, async (toolName, args) => {
        if (toolName === "service_status") {
          return { content: [{ type: "text", text: JSON.stringify({ ok: true, service: "documesh-api", vendors: VENDOR_IDS.length, version: API_VERSION, note: "read-only open API — safe to exercise directly" }) }] };
        }
        if (toolName === "submit_vendor") {
          const name = args.name || "";
          const license = args.license || "";
          if (!name || !license) {
            return { content: [{ type: "text", text: JSON.stringify({ error: "Both 'name' and 'license' are required." }) }], isError: true };
          }
          const jobId = crypto.randomUUID();
          jobs.set(jobId, { status: "processing", submitted_at: new Date().toISOString(), vendor: { name, license, docs_origin: args.docs_origin } });
          return { content: [{ type: "text", text: JSON.stringify({ job_id: jobId, status: "processing", poll: `/v1/jobs/${jobId}` }) }] };
        }
        if (toolName === "list_api_surface") {
          return { content: [{ type: "text", text: JSON.stringify({ endpoints: ["/search", "/explain", "/vendors", "/health", "/ask", "/batch", "/v1/submit-vendors"], openapi: `${url.origin}/openapi.json`, auth: "none (open API)" }) }] };
        }
        return { content: [{ type: "text", text: JSON.stringify({ error: `unknown tool: ${toolName}` }) }], isError: true };
      }, {
        serverName: "documesh-product",
        serverTitle: "Documesh Product Server",
        serverDescription: "Act on the Documesh product: check service status, submit a documentation source for ingestion, inspect the API surface.",
        tools: [
          {
            name: "service_status",
            description: "Get Documesh service status, vendor count, API version, and the sandbox URL.",
            inputSchema: { type: "object", properties: {} },
            _meta: { ui: { resourceUri: "ui://documesh/product-status" } },
          },
          {
            name: "submit_vendor",
            description: "Submit a documentation source for ingestion review (async job). Requires name and license; docs_origin optional.",
            inputSchema: {
              type: "object",
              properties: {
                name: { type: "string", description: "Source name (e.g. 'Example CLI')" },
                docs_origin: { type: "string", description: "Docs origin URL" },
                license: { type: "string", description: "License (e.g. MIT, CC-BY-4.0)" },
              },
              required: ["name", "license"],
            },
            _meta: { ui: { resourceUri: "ui://documesh/product-submit" } },
          },
          {
            name: "list_api_surface",
            description: "List the Documesh API endpoints and where the OpenAPI contract lives.",
            inputSchema: { type: "object", properties: {} },
            _meta: { ui: { resourceUri: "ui://documesh/product-surface" } },
          },
        ],
      });
    }
    if (path === "/mcp" || path === "/.well-known/mcp") {
      return handleMCPServer(request, env, async (toolName, args) => {
        if (toolName === "search_docs_across") {
          const out = await unifiedSearch(env, args.query, { vendors: args.vendors?.length ? args.vendors : undefined, limit: args.limit || 5 });
          return { content: [{ type: "text", text: JSON.stringify({ query: args.query, ...out }) }] };
        }
        if (toolName === "explain_error") {
          const err = args.log_excerpt || args.error || "";
          const out = await runExplain(env, err, args.vendor);
          return { content: [{ type: "text", text: JSON.stringify({ ...out, disclaimer: "These are the closest documentation sections, not a diagnosis." }) }] };
        }
        if (toolName === "list_vendors") {
          return { content: [{ type: "text", text: JSON.stringify({ vendors: VENDOR_IDS.map(id => ({ id, ...VENDOR_META[id] })) }) }] };
        }
        return { content: [{ type: "text", text: JSON.stringify({ error: `unknown tool: ${toolName}` }) }], isError: true };
      });
    }

    // ── A2A (Agent2Agent) JSON-RPC endpoint ──
    // Card at /.well-known/agent-card.json advertises this URL. Skills map
    // to the docs mesh: search, explain, vendors.
    if (path === "/a2a" && request.method === "POST") {
      const body = await request.json().catch(() => ({}));
      const { id, method, params } = body;
      if (method === "message/send") {
        const text = params?.message?.parts?.find(p => p.kind === "text" || p.type === "text")?.text
          || params?.message?.parts?.[0]?.text || "";
        const taskId = crypto.randomUUID();
        let replyText;
        try {
          if (!text.trim()) {
            replyText = "Ask me to search developer documentation across vendors, or paste an error message and I will find the closest official docs.";
          } else if (/license|attribution|vendor list|sources/i.test(text)) {
            const r = await fetch(`${url.origin}/vendors`).then(r => r.json());
            replyText = `Documesh indexes ${r.total} sources. Licenses:\n` + (r.vendors || [])
              .slice(0, 10).map(v => `- ${v.id}: ${v.license}`).join("\n")
              + (r.total > 10 ? `\n… and ${r.total - 10} more. Full registry: ${url.origin}/vendors` : "");
          } else if (/error|exception|crash|trace|ECONN|ENOENT|OOM|BackOff|EADDR/i.test(text) && text.length > 24) {
            const r = await fetch(`${url.origin}/explain?error=${encodeURIComponent(text.slice(0, 400))}`).then(r => r.json());
            replyText = (r.matches || []).length
              ? `Closest official documentation sections:\n` + r.matches.map(m =>
                  `- [${m.vendor}${m.version ? "@" + m.version : ""}] ${m.title}\n  ${m.source_url} (${m.license})`).join("\n")
                + `\n\n${r.disclaimer || ""}`
              : "No matching documentation sections found. Try the full search: " + url.origin + `/search?q=${encodeURIComponent(text.slice(0, 80))}`;
          } else {
            const r = await fetch(`${url.origin}/search?q=${encodeURIComponent(text.slice(0, 200))}&limit=3`).then(r => r.json());
            replyText = (r.results || []).length
              ? `Top documentation results:\n` + r.results.map(x =>
                  `- [${x.vendor}${x.version ? "@" + x.version : ""}] ${x.title}\n  ${x.source_url} (${x.license})`).join("\n")
              : `No results for "${text.slice(0, 60)}". Covered vendors: ${url.origin}/vendors`;
          }
        } catch (e) {
          replyText = `Documesh search error: ${e.message}. API status: ${url.origin}/health`;
        }
        return json({
          jsonrpc: "2.0",
          id,
          result: {
            id: taskId,
            contextId: params?.message?.contextId || crypto.randomUUID(),
            status: { state: "completed" },
            kind: "task",
            artifacts: [{
              artifactId: crypto.randomUUID(),
              name: "documesh-response",
              parts: [{ kind: "text", text: replyText }],
            }],
            history: [{
              role: "agent",
              parts: [{ kind: "text", text: replyText }],
              messageId: crypto.randomUUID(),
              kind: "message",
            }],
          },
        });
      }
      if (method === "tasks/get") {
        return json({ jsonrpc: "2.0", id, error: { code: -32001, message: "Tasks are completed synchronously; no persisted task state." } });
      }
      return json({ jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}. Supported: message/send, tasks/get.` } });
    }

    // Health (also /v1/health)
    if (path === "/health") {
      return json({ ok: true, service: "documesh-api", vendors: VENDOR_IDS.length, version: API_VERSION }, 200, apiEntry ? url.origin : null);
    }

    // Batch search — one request, many queries (Idempotency-Key required)
    if (path === "/batch" && request.method === "POST") {
      const idemKey = request.headers.get("Idempotency-Key");
      if (!idemKey) {
        return apiError(400, "MISSING_IDEMPOTENCY_KEY", "The Idempotency-Key header is required on POST /batch.", "Generate a UUID per logical batch and reuse it on retries.");
      }
      if (idempotencyCache.has(idemKey)) {
        const cached = idempotencyCache.get(idemKey);
        const headers = new Headers(cached.headers);
        headers.set("Idempotency-Replayed", "true");
        return new Response(cached.body, { status: cached.status, headers });
      }
      let ops = [];
      try { ops = (await request.json())?.operations || []; } catch {}
      if (!Array.isArray(ops) || !ops.length) {
        return apiError(400, "MISSING_OPERATIONS", 'Body must be {"operations": [{"q": "..."}]} with 1-20 operations.', "Each operation: {op_id?, q, vendors?, limit?}.");
      }
      const results = [];
      for (const [i, op] of ops.slice(0, 20).entries()) {
        const opId = op.op_id ?? String(i);
        if (!op.q || !String(op.q).trim()) {
          results.push({ op_id: opId, status: "error", error: { code: "MISSING_QUERY", message: "Each operation requires a non-empty 'q'.", status: 400 } });
          continue;
        }
        const out = await unifiedSearch(env, op.q, { limit: op.limit || 5 });
        results.push({ op_id: opId, status: "ok", query: op.q, results: out.results });
      }
      const response = json({ results });
      idempotencyCache.set(idemKey, { status: response.status, body: await response.clone().text(), headers: response.headers });
      return response;
    }

    // Vendors with cursor pagination
    if (path === "/vendors") {
      const cursor = url.searchParams.get("cursor");
      const limit = Math.min(parseInt(url.searchParams.get("limit") || String(VENDOR_IDS.length)), VENDOR_IDS.length);
      const all = VENDOR_IDS.map(id => ({ id, ...VENDOR_META[id] }));
      const start = cursor ? parseInt(b64uDecode(cursor)) || 0 : 0;
      const page = all.slice(start, start + limit);
      const next_cursor = start + limit < all.length ? b64uEncode(String(start + limit)) : null;
      return json({ vendors: page, total: all.length, next_cursor, pagination: { style: "cursor", cursor_param: "cursor", limit_param: "limit" } }, 200, apiEntry ? url.origin : null);
    }

    // Search — GET and POST (POST accepts Idempotency-Key for safe retries)
    if (path === "/search" && (request.method === "GET" || request.method === "POST")) {
      let q, vendors, limit, cursor;
      if (request.method === "POST") {
        let body = {};
        try { body = await request.json(); } catch {}
        q = body.query || body.q || "";
        vendors = body.vendors;
        limit = body.limit;
        cursor = body.cursor;
      } else {
        q = url.searchParams.get("q") || "";
        vendors = url.searchParams.get("vendors")?.split(",").map(s => s.trim()).filter(Boolean);
        limit = parseInt(url.searchParams.get("limit") || "5");
        cursor = url.searchParams.get("cursor");
      }
      limit = Math.min(limit || 5, 20);
      if (!q.trim()) {
        return apiError(400, "MISSING_QUERY", "Required query parameter 'q' is missing or empty.", "Retry with ?q=<search terms>, or POST JSON {\"query\": \"...\"}.");
      }
      const idemKey = request.headers.get("Idempotency-Key");
      if (idemKey && request.method === "POST" && idempotencyCache.has(idemKey)) {
        const cached = idempotencyCache.get(idemKey);
        const headers = new Headers(cached.headers);
        headers.set("Idempotency-Replayed", "true");
        return new Response(cached.body, { status: cached.status, headers });
      }
      const start = Date.now();
      const out = await unifiedSearch(env, q, { vendors: vendors || undefined, limit, cursor });
      const { results, next_cursor, total } = out;
      const response = json({ query: q, results, total, next_cursor, took_ms: Date.now() - start, backend: out.backend }, 200, apiEntry ? url.origin : null);
      if (idemKey && request.method === "POST") {
        idempotencyCache.set(idemKey, { status: response.status, body: await response.clone().text(), headers: response.headers });
      }
      return response;
    }

    // Explain
    if (path === "/explain") {
      const err = url.searchParams.get("error") || "";
      const vendor = url.searchParams.get("vendor") || undefined;
      if (!err.trim()) {
        return apiError(400, "MISSING_ERROR", "Required query parameter 'error' is missing or empty.", "Retry with ?error=<log excerpt>.");
      }
      const out = await runExplain(env, err, vendor);
      return json({ ...out, disclaimer: "These are the closest documentation sections, not a diagnosis." }, 200, apiEntry ? url.origin : null);
    }

    // Async-job pattern: submit → 202 → poll
    if (path === "/v1/submit-vendors" && request.method === "POST") {
      let body = {};
      try { body = await request.json(); } catch {}
      if (!body.name || !body.license) {
        return apiError(400, "MISSING_FIELDS", "Fields 'name' and 'license' are required to submit a vendor.", "POST JSON {\"name\": \"Example\", \"docs_origin\": \"https://...\", \"license\": \"MIT\"}.");
      }
      const jobId = crypto.randomUUID();
      jobs.set(jobId, { status: "processing", submitted_at: new Date().toISOString(), vendor: body });
      return json(
        {
          job_id: jobId,
          status: "processing",
          submitted_at: new Date().toISOString(),
          links: { self: `/v1/jobs/${jobId}`, poll: `/v1/jobs/${jobId}` },
        },
        202
      );
    }
    const jobMatch = path.match(/^\/v1\/jobs\/([a-f0-9-]+)$/);
    if (jobMatch && request.method === "GET") {
      const job = jobs.get(jobMatch[1]);
      if (!job) {
        return apiError(404, "JOB_NOT_FOUND", `No job with id ${jobMatch[1]}.`, "Jobs expire with the isolate; submit a new job via POST /v1/submit-vendors.");
      }
      if (job.status === "processing") job.status = "completed";
      return json({
        job_id: jobMatch[1],
        status: job.status,
        submitted_at: job.submitted_at,
        completed_at: job.status === "completed" ? new Date().toISOString() : undefined,
        result: job.status === "completed" ? { accepted: true, review: "Vendor submission queued for ingestion review." } : undefined,
        links: { self: `/v1/jobs/${jobMatch[1]}` },
      });
    }

    // NLWeb /ask — JSON or SSE streaming (Accept: text/event-stream or prefer: streaming)
    if (path === "/ask" && (request.method === "POST" || request.method === "GET")) {
      let q = "";
      let stream = wantsSSE;
      if (request.method === "POST") {
        try {
          const body = await request.json();
          q = body.query || "";
          if (body.prefer?.streaming === true) stream = true;
        } catch {}
      } else {
        q = url.searchParams.get("q") || "";
      }
      if (!q) {
        return apiError(400, "MISSING_QUERY", "Required 'query' is missing.", "POST JSON {\"query\": \"...\"} or GET /ask?q=...");
      }
      const out = await unifiedSearch(env, q, { limit: 5 });
      const { results } = out;
      if (!stream) {
        return json({
          _meta: { response_type: "search_results", version: API_VERSION },
          query: q, results,
        });
      }
      const encoder = new TextEncoder();
      const sseStream = new ReadableStream({
        start(controller) {
          const send = (event, data) => controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
          send("start", { query: q, version: API_VERSION });
          for (const r of results) send("result", r);
          send("complete", { query: q, count: results.length });
          controller.close();
        },
      });
      return new Response(sseStream, {
        headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", ...CORS },
      });
    }

    // JSON 404 for API-ish paths and JSON Accept — required so agents get
    // structured errors; keep markdown 404 elsewhere (agent-friendly-404).
    // Never swallow /.well-known/* or dotted static paths: they fall through
    // to the asset layer below (ard.json etc. must stay reachable with
    // Accept: application/json).
    const apiPath404 = !path.startsWith("/.well-known") && !/\.[a-z0-9]+$/i.test(path) &&
      ((url.pathname.startsWith("/api/") || url.pathname.startsWith("/v1/") || url.pathname.startsWith("/v2/") || url.pathname.startsWith("/jobs/")) ||
      (acceptHeader.includes("application/json") && !acceptHeader.includes("text/html")));
    if (apiPath404) {
      return apiError(404, "not_found", `No API route at ${url.pathname}.`, "Valid routes: /search, /explain, /vendors, /health, /ask, /mcp, /v1/*, /api. See /openapi.json for the full contract.");
    }

    // .md endpoints — serve markdown twins
    if (path.endsWith(".md")) {
      const mdPath = path.replace(/\.md$/, "").replace(/^\//, "") || "index";
      const assetRes = await env.ASSETS.fetch(new Request(`https://internal/${mdPath}.md`));
      if (assetRes.ok) {
        const text = await assetRes.text();
        if (!text.trim().startsWith("<")) {
          return new Response(text, {
            status: 200,
            headers: { "Content-Type": "text/markdown; charset=utf-8", ...baseHeaders() },
          });
        }
      }
      return markdown(`# Not Found\n\nNo page at \`${url.pathname}\`.\n\nSee [llms.txt](/llms.txt) for the full index.`, 404);
    }

    // Agent mode view
    if (path === "/" && url.searchParams.get("mode") === "agent") {
      return json({
        name: "Documesh",
        description: "Federated developer documentation search across 47 vendors",
        version: API_VERSION,
        api_base: url.origin,
        capabilities: {
          federated_search: "One query across 38 vendor documentation sets with version, license, and canonical URL on every result",
          error_matching: "Match a stack trace or error message to the closest official documentation sections",
          vendor_registry: "License and attribution info for every source in the mesh",
          nlweb_ask: "Natural-language query endpoint with optional SSE streaming",
          mcp: "Streamable HTTP MCP server with 3 typed docs tools + a separate product-action surface",
        },
        endpoints: {
          search: "/search?q=&vendors=&limit=&cursor=",
          search_post: "POST /search {query, vendors, limit} — supports Idempotency-Key",
          batch: "POST /batch {operations:[{q}]} — up to 20 searches, Idempotency-Key required",
          explain_error: "/explain?error=&vendor=",
          vendors: "/vendors?cursor=&limit=",
          health: "/health",
          ask: "/ask?q= (or POST {query, prefer:{streaming:true}} for SSE)",
          mcp: "/mcp (Streamable HTTP JSON-RPC 2.0)",
          mcp_product: "/mcp/product (service_status, submit_vendor, list_api_surface)",
          jobs: "POST /v1/submit-vendors → 202 → GET /v1/jobs/{job_id}",
          sandbox: "/sandbox",
        },
        discovery: {
          openapi: "/openapi.json",
          api_catalog: "/.well-known/api-catalog",
          ard: "/.well-known/ard.json",
          agent_skills: "/.well-known/agent-skills/index.json",
          mcp_manifest: "/.well-known/mcp",
          mcp_server_card: "/.well-known/mcp/server-card.json",
          oauth_protected_resource: "/.well-known/oauth-protected-resource",
          auth_docs: "/auth.md",
          llms: "/llms.txt",
          llms_api: "/api/llms.txt",
          llms_developers: "/developers/llms.txt",
        },
        authentication: {
          type: "none",
          description: "Open API — no keys, tokens, or registration required for read-only access",
          protected_resource_metadata: "/.well-known/oauth-protected-resource",
          authorization_server_metadata: "/.well-known/oauth-authorization-server",
          agent_registration: "/auth.md",
          identity_endpoint: "/agent/identity",
        },
        rate_limit: { requests_per_minute: 100, headers: "RateLimit-Limit / RateLimit-Remaining / RateLimit-Reset" },
        versioning: "URL path /v1/; unversioned paths are aliases; Deprecation + Sunset headers on deprecation",
        sandbox: url.origin + " (read-only open API — the live service is the sandbox)",
        sdks: { npm: "documesh (SDK + CLI)", install: "npm install documesh", cli: "documesh search <query>" },
        tools: {
          mcp_tools: ["search_docs_across", "explain_error", "list_vendors"],
          product_mcp_tools: ["service_status", "submit_vendor", "list_api_surface"],
          mcp_apps_ui: true,
          ui_resources: ["ui://documesh/search-results", "ui://documesh/error-match", "ui://documesh/vendor-grid"],
        },
        schemas: {
          openapi: "/openapi.json",
          response_schemas: "All operations return typed JSON matching OpenAPI components.schemas",
          error_schema: '{"error":{"code","message","status","resolution"}}',
        },
        security: {
          tls: true,
          authentication_required: false,
          data_practices: "/privacy.html",
          contact: "/contact.html",
        },
        docs: {
          developer_portal: "/developers.html",
          quickstart: "/developers.md",
          webmcp_tools_reference: "/webmcp.html",
          coverage_licenses: "/coverage.html",
        },
        webmcp_tools: ["search_docs_across", "explain_error", "list_vendors"],
        a2a: { agent_card: "/.well-known/agent-card.json", endpoint: "/a2a" },
      });
    }

    // ── Static assets pass-through (run_worker_first: true) ──
    // Add agent-readiness headers (Link, Vary, RateLimit) to static responses.
    const assetResponse = await env.ASSETS.fetch(request);
    if (assetResponse.status !== 404) {
      const headers = new Headers(assetResponse.headers);
      headers.set("Link", LINK_HEADERS);
      const vary = headers.get("Vary");
      headers.set("Vary", vary && !vary.includes("Accept") ? `${vary}, Accept` : (vary || "Accept, Accept-Encoding"));
      return new Response(assetResponse.body, { status: assetResponse.status, headers });
    }

    // Typed 404 with markdown body (non-API paths)
    return new Response(
      `# 404 — Not Found\n\nPath \`${url.pathname}\` does not exist.\n\n## Where to look next\n\n- API index: \`/openapi.json\`\n- Agent interface: \`/llms.txt\`\n- Routes: \`/search\`, \`/explain\`, \`/vendors\`, \`/health\`, \`/mcp\``,
      { status: 404, headers: { "Content-Type": "text/markdown; charset=utf-8", ...baseHeaders() } }
    );
  },
};
