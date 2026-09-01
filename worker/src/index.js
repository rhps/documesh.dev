/**
 * Docs Mesh API — Cloudflare Worker
 * Loads per-vendor gzipped shards lazily from static assets.
 * Fits free-tier memory (no monolithic bundle).
 */
import { VENDOR_META, tokenize, searchInShard, extractSignatures } from "./search-core-lite.js";

const VENDOR_IDS = Object.keys(VENDOR_META);

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
      const idx = {
        docs: data.docs,
        postings: new Map(Object.entries(data.postings)),
        builtAt: data.built_at || "2026-08-30",
      };
      shardCache[vendor] = idx;
      return idx;
    } catch (e) {
      console.error(`shard load failed: ${vendor}`, e);
      shardPromises[vendor] = null; // allow retry
      return null;
    }
  })();
  return shardPromises[vendor];
}

async function loadVendors(env, vendors) {
  const list = vendors && vendors.length ? vendors : VENDOR_IDS;
  const loaded = {};
  for (const v of list) {
    const idx = await loadShard(env, v);
    if (idx) loaded[v] = idx;
  }
  return loaded;
}

function searchAcross(loaded, query, opts = {}) {
  const { limit = 5 } = opts;
  const toks = tokenize(query);
  if (!toks.length) return [];

  const scores = new Map(); // "vendor:docIdx" -> score
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
    const docIdx = parseInt(docIdxStr);
    const d = index.docs[docIdx];
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

function explainErrorFromShards(loaded, logExcerpt, opts = {}) {
  const { vendor, limit = 3 } = opts;
  const sigs = extractSignatures(logExcerpt);
  const searchText = [logExcerpt.slice(0, 400), ...sigs].join(" ");

  const filtered = {};
  for (const [v, idx] of Object.entries(loaded)) {
    if (!vendor || v === vendor) filtered[v] = idx;
  }

  // search across loaded shards
  const toks = tokenize(searchText);
  const scores = new Map(); // "vendor:docIdx" -> {score, covered}
  for (const [v, index] of Object.entries(filtered)) {
    for (const tok of toks) {
      const pl = index.postings.get(tok);
      if (!pl) continue;
      for (const [docIdx, w] of pl) {
        const key = `${v}:${docIdx}`;
        const prev = scores.get(key) || { score: 0, covered: new Set() };
        prev.score += w;
        prev.covered.add(tok);
        scores.set(key, prev);
      }
    }
  }

  const matches = [];
  for (const [key, s] of scores) {
    const [v, docIdxStr] = key.split(":");
    const index = filtered[v];
    if (!index) continue;
    const d = index.docs[parseInt(docIdxStr)];
    matches.push({
      chunk_id: d.chunk_id, vendor: v, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated, score: +s.score.toFixed(4),
    });
  }
  matches.sort((a, b) => b.score - a.score);

  // diversify: max 2 per vendor
  const vendorCount = {};
  const diversified = [];
  for (const m of matches) {
    vendorCount[m.vendor] = (vendorCount[m.vendor] || 0) + 1;
    if (vendorCount[m.vendor] <= 2) {
      diversified.push(m);
      if (diversified.length >= limit) break;
    }
  }
  return { extracted_signatures: sigs.slice(0, 6), matches: diversified };
}

// ─── HTTP handlers ───────────────────────────────────────────────────────────

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json", ...CORS },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    // Load shards lazily on first data request
    const shardsLoaded = new Set();

    async function ensureShards(vendors) {
      const list = vendors && vendors.length ? vendors : VENDOR_IDS;
      await Promise.all(list.map(v => loadShard(env, v)));
    }

    if (path === "/health") {
      return json({ ok: true, service: "documesh-api", vendors: VENDOR_IDS.length });
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

      await ensureShards(vendors);
      const loaded = {};
      for (const v of (vendors || VENDOR_IDS)) {
        const idx = await loadShard(env, v);
        if (idx) loaded[v] = idx;
      }

      const start = Date.now();
      const results = searchAcross(loaded, q, { limit });
      return json({ query: q, results, took_ms: Date.now() - start });
    }

    if (path === "/explain") {
      const err = url.searchParams.get("error") || "";
      const vendor = url.searchParams.get("vendor") || undefined;
      if (!err.trim()) return json({ error: "missing error" }, 400);

      // Load only a subset of vendors to stay within CPU limits on free tier.
      // Use cached shards first, then load up to 5 more.
      const priority = vendor ? [vendor] : ["cloudflare", "netlify", "vercel", "kubernetes", "nodejs"];
      const loaded = await loadVendors(env, priority);
      const sigs = extractSignatures(err);
      const searchText = [err.slice(0, 400), ...sigs].join(" ");

      // search across loaded shards
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

      // rank + diversify
      const ranked = [];
      for (const [key, score] of scores) {
        const [v, docIdxStr] = key.split(":");
        const shard = loaded[v];
        if (!shard) continue;
        const d = shard.docs[parseInt(docIdxStr)];
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
        if (vendorCount[m.vendor] <= 2) { matches.push(m); }
        if (matches.length >= 3) break;
      }

      return json({
        extracted_signatures: sigs.slice(0, 6),
        matches,
        disclaimer: "These are the closest documentation sections, not a diagnosis. Verify against the linked official docs.",
        snapshot_date: "2026-08-30",
      });
    }

    return json({ error: "not found", routes: ["/health", "/vendors", "/search", "/explain"] }, 404);
  },
};

// helper for explain — needs loaded shards
async function ensureShardsAndSearch(env, vendors, query, limit) {
  const loaded = {};
  for (const v of (vendors || VENDOR_IDS)) {
    const idx = await loadShard(env, v);
    if (idx) loaded[v] = idx;
  }
  return loaded;
}
