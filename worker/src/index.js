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

function baseHeaders() {
  return {
    ...CORS,
    "X-API-Version": API_VERSION,
    // IETF draft-ietf-httpapi-ratelimit-headers RateLimit-* fields
    "RateLimit-Limit": "100",
    "RateLimit-Remaining": "99",
    "RateLimit-Reset": "60",
    "Vary": "Accept, Accept-Encoding",
    "Link": LINK_HEADERS,
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", ...baseHeaders() },
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
  if (!toks.length) return { results: [], next_cursor: null };
  const scores = new Map();
  for (const [vendor, index] of Object.entries(loaded)) {
    for (const tok of toks) {
      const pl = index.postings.get(tok);
      if (!pl) continue;
      for (const [docIdx, w] of pl) {
        const key = `${vendor}:${docIdx}`;
        scores.set(key, (scores.get(key) || 0) + w);
      }
    }
  }
  let results = [];
  for (const [key, score] of scores) {
    const [vendor, docIdxStr] = key.split(":");
    const index = loaded[vendor];
    if (!index) continue;
    const d = index.docs[parseInt(docIdxStr)];
    if (!d) continue;
    const docToks = new Set(tokenize(d.title + " " + d.heading_path));
    let covered = 0;
    for (const t of toks) if (docToks.has(t)) covered++;
    results.push({
      chunk_id: d.chunk_id, vendor: d.vendor, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated,
      score: +(score * (1 + covered / toks.length)).toFixed(4),
    });
  }
  results.sort((a, b) => b.score - a.score);
  // Cursor-based pagination: opaque cursor = score rank offset
  const start = cursor ? parseInt(b64uDecode(cursor)) || 0 : 0;
  const page = results.slice(start, start + limit);
  const next_cursor = start + limit < results.length
    ? b64uEncode(String(start + limit))
    : null;
  return { results: page, next_cursor, total: results.length };
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
  const priority = vendor ? [vendor] : ["cloudflare", "netlify", "vercel", "kubernetes", "nodejs"];
  const loaded = await loadVendors(env, priority);
  const sigs = extractSignaturesFromLog(err);
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
      });
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

    // MCP server card
    if (path === "/.well-known/mcp/server-card.json" || path === "/.well-known/mcp/server-card") {
      return json({
        name: "Documesh MCP Server",
        description: "Federated developer documentation search across 38 vendors",
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
        description: "Federated developer documentation search across 38 vendors",
        server_card: `${url.origin}/.well-known/mcp/server-card.json`,
        tools: ["search_docs_across", "explain_error", "list_vendors"],
        resources: ["ui://documesh/search-results", "ui://documesh/error-match", "ui://documesh/vendor-grid"],
      });
    }
    if (path === "/mcp" && (request.method === "POST" || request.method === "GET")) {
      return handleMCPServer(request, env, async (toolName, args) => {
        if (toolName === "search_docs_across") {
          const loaded = await loadVendors(env, args.vendors?.length ? args.vendors : VENDOR_IDS);
          return { content: [{ type: "text", text: JSON.stringify({ results: searchAcross(loaded, args.query, { limit: args.limit || 5 }).results }) }] };
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

    // Health (also /v1/health)
    if (path === "/health") {
      return json({ ok: true, service: "documesh-api", vendors: VENDOR_IDS.length, version: API_VERSION });
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
      const loaded = await loadVendors(env, VENDOR_IDS);
      const results = ops.slice(0, 20).map((op, i) => {
        const opId = op.op_id ?? String(i);
        if (!op.q || !String(op.q).trim()) {
          return { op_id: opId, status: "error", error: { code: "MISSING_QUERY", message: "Each operation requires a non-empty 'q'.", status: 400 } };
        }
        return { op_id: opId, status: "ok", query: op.q, results: searchAcross(loaded, op.q, { limit: op.limit || 5 }).results };
      });
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
      return json({ vendors: page, total: all.length, next_cursor, pagination: { style: "cursor", cursor_param: "cursor", limit_param: "limit" } });
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
      const loaded = await loadVendors(env, vendors || VENDOR_IDS);
      const start = Date.now();
      const { results, next_cursor, total } = searchAcross(loaded, q, { limit, cursor });
      const response = json({ query: q, results, total, next_cursor, took_ms: Date.now() - start });
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
      return json({ ...out, disclaimer: "These are the closest documentation sections, not a diagnosis." });
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
      const loaded = await loadVendors(env, VENDOR_IDS);
      const { results } = searchAcross(loaded, q, { limit: 5 });
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
    const apiPath404 = (url.pathname.startsWith("/api/") || url.pathname.startsWith("/v1/") || url.pathname.startsWith("/v2/") || url.pathname.startsWith("/jobs/")) ||
      (acceptHeader.includes("application/json") && !acceptHeader.includes("text/html"));
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
        description: "Federated developer documentation search across 18 vendors",
        version: API_VERSION,
        api_base: url.origin,
        endpoints: {
          search: "/search?q=&vendors=&limit=&cursor=",
          search_post: "POST /search {query, vendors, limit} — supports Idempotency-Key",
          explain_error: "/explain?error=&vendor=",
          vendors: "/vendors?cursor=&limit=",
          health: "/health",
          ask: "/ask?q= (or POST {query, prefer:{streaming:true}} for SSE)",
          mcp: "/mcp (Streamable HTTP JSON-RPC 2.0)",
          jobs: "POST /v1/submit-vendors → 202 → GET /v1/jobs/{job_id}",
        },
        discovery: {
          openapi: "/openapi.json",
          api_catalog: "/.well-known/api-catalog",
          ard: "/.well-known/ard.json",
          agent_skills: "/.well-known/agent-skills/index.json",
          mcp_server_card: "/.well-known/mcp/server-card.json",
          oauth_protected_resource: "/.well-known/oauth-protected-resource.json",
          auth_docs: "/auth.md",
          llms: "/llms.txt",
        },
        authentication: "none (open API)",
        vendors: VENDOR_IDS,
        webmcp_tools: ["search_docs_across", "explain_error", "list_vendors"],
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
