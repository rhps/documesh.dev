/**
 * Local dev server — identical routes/logic to the CF Worker, for testing without wrangler.
 * Usage: node worker/dev-server.mjs  (port 8787)
 */
import http from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { loadIndex, search, explainError, VENDORS } from "./src/search-core.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const indexData = readFileSync(path.join(__dirname, "../data/search-index.json"), "utf8");
const index = loadIndex(indexData);

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const server = http.createServer((req, res) => {
  console.log(`[req] ${new Date().toISOString().slice(11, 19)} ${req.method} ${req.url} (from ${req.headers.origin || "same-origin"})`);
  const url = new URL(req.url, `http://localhost:${process.env.PORT || 8787}`);
  const p = url.pathname;
  const send = (data, status = 200) => {
    res.writeHead(status, { "Content-Type": "application/json", ...CORS });
    res.end(JSON.stringify(data));
  };

  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS);
    return res.end();
  }

  if (p === "/health") return send({ ok: true, service: "documesh-api", snapshot: index.builtAt });

  if (p === "/vendors") return send({ vendors: VENDORS, snapshot_date: index.builtAt });

  if (p === "/search") {
    const q = url.searchParams.get("q") || "";
    const vendorsParam = url.searchParams.get("vendors");
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "5", 10), 20);
    if (!q.trim()) return send({ error: "missing q parameter" }, 400);
    return send(search(index, q, {
      vendors: vendorsParam ? vendorsParam.split(",").map((s) => s.trim()) : undefined,
      limit,
    }));
  }

  if (p === "/explain") {
    const err = url.searchParams.get("error") || "";
    const vendor = url.searchParams.get("vendor") || undefined;
    if (!err.trim()) return send({ error: "missing error parameter" }, 400);
    return send(explainError(index, err, { vendor }));
  }

  if (p === "/page") {
    const vendor = url.searchParams.get("vendor");
    const pathParam = url.searchParams.get("path");
    if (!vendor || !pathParam) return send({ error: "missing vendor or path" }, 400);
    const matches = index.docs.filter((d) => d.vendor === vendor && (d.path === pathParam || d.path.startsWith(pathParam)));
    if (!matches.length) return send({ error: "not found", vendor, path: pathParam }, 404);
    const headings = [...new Set(matches.map((m) => m.heading_path))];
    return send({
      vendor, path: pathParam,
      sections: matches.slice(0, 30).map((m) => ({
        chunk_id: m.chunk_id, title: m.title, heading_path: m.heading_path,
        source_url: m.source_url, license: m.license, last_updated: m.last_updated,
      })),
      heading_tree: headings,
      source_url: matches[0].source_url,
      license: matches[0].license,
      attribution: matches[0].attribution,
      snapshot_date: index.builtAt,
    });
  }

  return send({ error: "not found", routes: ["/health", "/vendors", "/search?q=", "/explain?error=", "/page?vendor=&path="] }, 404);
});

const PORT = process.env.PORT || 8787;
server.listen(PORT, () => console.log(`documesh dev API on http://localhost:${PORT} (snapshot ${index.builtAt})`));
