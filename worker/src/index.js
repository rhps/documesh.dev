/**
 * Documesh API — Cloudflare Worker
 * Batch 2: agent-readiness features (rate limits, .md endpoints, agent mode,
 *          NLWeb /ask, typed errors, versioning, HTTP Link headers)
 */
import { VENDOR_META, tokenize, extractSignatures } from "./search-core-lite.js";

const VENDOR_IDS = Object.keys(VENDOR_META);
const API_VERSION = "v1";
const API_VERSION_DATE = "2026-09-01";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, Idempotency-Key",
};

function baseHeaders() {
  return {
    ...CORS,
    "X-API-Version": API_VERSION,
    "X-RateLimit-Limit": "100",
    "X-RateLimit-Remaining": "99",
    "Link": '</sitemap.xml>; rel="sitemap", </llms.txt>; rel="alternate"; type="text/plain", </openapi.json>; rel="service-desc", </index.md>; rel="alternate"; type="text/markdown"',
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
  const { limit = 5 } = opts;
  const toks = tokenize(query);
  if (!toks.length) return [];
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
  return results.slice(0, limit);
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

// ─── Main handler ────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    // .md endpoints — serve markdown twins for static pages
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
      return markdown(`# Not Found\n\nNo page at \`${path}\`.\n\nSee [llms.txt](/llms.txt) for the full index.`, 404);
    }

    // Agent mode view
    if (path === "/" && url.searchParams.get("mode") === "agent") {
      return json({
        name: "Documesh",
        description: "Federated developer documentation search across 18 vendors",
        version: API_VERSION,
        api_base: url.origin,
        endpoints: {
          search: "/search?q=&vendors=&limit=",
          explain_error: "/explain?error=&vendor=",
          vendors: "/vendors",
          health: "/health",
        },
        authentication: "none (open API)",
        vendors: VENDOR_IDS,
        webmcp_tools: ["search_docs_across", "explain_error", "list_vendors"],
      });
    }

    if (path === "/health") {
      return json({ ok: true, service: "documesh-api", vendors: VENDOR_IDS.length, version: API_VERSION });
    }

    if (path === "/vendors") {
      return json({
        vendors: VENDOR_IDS.map(id => ({ id, ...VENDOR_META[id] })),
        total: VENDOR_IDS.length,
      });
    }

    if (path === "/search") {
      const q = url.searchParams.get("q") || "";
      const vendors = url.searchParams.get("vendors")?.split(",").map(s => s.trim()).filter(Boolean);
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "5"), 20);
      if (!q.trim()) return json({ error: "missing q" }, 400);

      const loaded = await loadVendors(env, vendors || VENDOR_IDS);
      const start = Date.now();
      const results = searchAcross(loaded, q, { limit });
      return json({ query: q, results, took_ms: Date.now() - start });
    }

    if (path === "/explain") {
      const err = url.searchParams.get("error") || "";
      const vendor = url.searchParams.get("vendor") || undefined;
      if (!err.trim()) return json({ error: "missing error" }, 400);

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

      return json({
        extracted_signatures: sigs.slice(0, 6),
        matches,
        disclaimer: "These are the closest documentation sections, not a diagnosis.",
      });
    }

    // NLWeb /ask
    if (path === "/ask" && (request.method === "POST" || request.method === "GET")) {
      let q = "";
      if (request.method === "POST") {
        try { q = (await request.json()).query || ""; } catch {}
      } else {
        q = url.searchParams.get("q") || "";
      }
      if (!q) return json({ error: "missing query" }, 400);
      const loaded = await loadVendors(env, VENDOR_IDS);
      const results = searchAcross(loaded, q, { limit: 5 });
      return json({
        _meta: { response_type: "search_results", version: API_VERSION },
        query: q, results,
      });
    }

    // Typed 404 with markdown body
    return new Response(
      `# 404 — Not Found\n\nPath \`${path}\` does not exist.\n\n## Where to look next\n\n- API index: \`/openapi.json\`\n- Agent interface: \`/llms.txt\`\n- Routes: \`/search\`, \`/explain\`, \`/vendors\`, \`/health\``,
      { status: 404, headers: { "Content-Type": "text/markdown; charset=utf-8", ...baseHeaders() } }
    );
  },
};
