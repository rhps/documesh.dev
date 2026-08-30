/**
 * Documesh API — Cloudflare Worker entrypoint.
 * Routes: /search, /page, /vendors, /explain, /health
 */
import { loadIndex, search, explainError, VENDORS } from "./search-core.js";
import indexData from "../../data/search-index.json";

let index = null;
function getIndex() {
  if (!index) index = loadIndex(JSON.stringify(indexData));
  return index;
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

function excerpt(doc) {
  // content stored separately in chunks; Worker returns metadata + deep link.
  // Full content fetch via /page route.
  return doc;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (path === "/health") {
      return json({ ok: true, service: "documesh-api", snapshot: getIndex().builtAt });
    }

    if (path === "/vendors") {
      return json({ vendors: VENDORS, snapshot_date: getIndex().builtAt });
    }

    if (path === "/search") {
      const q = url.searchParams.get("q") || "";
      const vendorsParam = url.searchParams.get("vendors");
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "5", 10), 20);
      if (!q.trim()) return json({ error: "missing q parameter" }, 400);
      const result = search(getIndex(), q, {
        vendors: vendorsParam ? vendorsParam.split(",").map((s) => s.trim()) : undefined,
        limit,
      });
      return json(result);
    }

    if (path === "/explain") {
      const err = url.searchParams.get("error") || "";
      const vendor = url.searchParams.get("vendor") || undefined;
      if (!err.trim()) return json({ error: "missing error parameter" }, 400);
      return json(explainError(getIndex(), err, { vendor }));
    }

    if (path === "/page") {
      // metadata-only page info (content lives in chunks; page = deep link + heading path)
      const vendor = url.searchParams.get("vendor");
      const pathParam = url.searchParams.get("path");
      if (!vendor || !pathParam) return json({ error: "missing vendor or path" }, 400);
      const idx = getIndex();
      const matches = idx.docs.filter((d) => d.vendor === vendor && (d.path === pathParam || d.path.startsWith(pathParam)));
      if (!matches.length) return json({ error: "not found", vendor, path: pathParam }, 404);
      const headings = [...new Set(matches.map((m) => m.heading_path))];
      return json({
        vendor,
        path: pathParam,
        sections: matches.slice(0, 30).map((m) => ({
          chunk_id: m.chunk_id, title: m.title, heading_path: m.heading_path,
          source_url: m.source_url, license: m.license, last_updated: m.last_updated,
        })),
        heading_tree: headings,
        source_url: matches[0].source_url,
        license: matches[0].license,
        attribution: matches[0].attribution,
        snapshot_date: idx.builtAt,
      });
    }

    return json({ error: "not found", routes: ["/health", "/vendors", "/search?q=", "/explain?error=", "/page?vendor=&path="] }, 404);
  },
};
