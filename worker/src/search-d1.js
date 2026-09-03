/**
 * Documesh search — D1 FTS5 backend (Phase 1, Option C).
 *
 * Replaces in-isolate shard loading: search runs inside D1 via MATCH + bm25().
 * Response contract matches the legacy shard path exactly:
 *   { results: [{chunk_id, vendor, version, title, heading_path, path,
 *                source_url, license, attribution, last_updated, score, snippet}],
 *     next_cursor: string|null, total: number }
 */

import { withSource, withSourceAll } from "./result-shape.js";
import { extractActionables } from "./actionable.js";

const FTS_COLS_WEIGHTED = "bm25(chunks_fts, 3.0, 2.0, 1.0)"; // title, heading_path, content — mirrors legacy title-boost

/**
 * Convert a raw user query into a safe FTS5 MATCH expression.
 * - strips FTS operators and syntax characters
 * - wraps each token in double quotes (exact token match; porter stemmer still applies)
 * - ANDs tokens together (legacy behavior: all tokens should hit)
 * Returns null when nothing searchable remains.
 */
export function toMatchQuery(raw) {
  if (!raw) return null;
  const tokens = String(raw)
    .toLowerCase()
    .replace(/["'`*():^{}[\]/\\~!@#$%&+=|<>?;,.-]/g, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
  if (!tokens.length) return null;
  return tokens.map((t) => `"${t}"`).join(" ");
}

export function toTokens(raw) {
  if (!raw) return [];
  return String(raw)
    .toLowerCase()
    .replace(/["'`*():^{}[\]/\\~!@#$%&+=|<>?;,.-]/g, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
}

export function encodeCursor(score, rowid) {
  return btoa(JSON.stringify({ s: score, r: rowid })).replace(/=+$/, "");
}

export function decodeCursor(cursor) {
  if (!cursor) return null;
  try {
    const pad = cursor + "=".repeat((4 - (cursor.length % 4)) % 4);
    const o = JSON.parse(atob(pad));
    if (typeof o.s !== "number" || typeof o.r !== "number") return null;
    return o;
  } catch {
    return null;
  }
}

/**
 * FTS5 + keyset-paginated search.
 * @param {object} env Worker env (needs env.DB bound to D1)
 * @param {string} query raw user query
 * @param {{vendors?: string[], limit?: number, cursor?: string}} opts
 */
export async function searchD1(env, query, opts = {}) {
  const { vendors, limit = 5, cursor, semantic = false } = opts;
  const match = toMatchQuery(query);
  if (!match) {
    return { results: [], next_cursor: null, total: 0 };
  }

  const lim = Math.min(Math.max(1, limit | 0 || 5), 50);
  const cur = decodeCursor(cursor);

  // Semantic mode needs a wider keyword candidate pool to fuse against.
  // (Not combined with cursor pagination — semantic returns a fused top-N,
  //  there is no keyset to continue from.)
  const fetchLim = semantic ? Math.max(lim, 50) : lim + 1;

  // All-positional placeholders (?): D1 bind() maps them in order.
  const where = ["chunks_fts MATCH ?"];
  const bind = [match];
  if (vendors?.length) {
    const placeholders = vendors.map((v) => { bind.push(String(v)); return "?"; });
    where.push(`c.vendor IN (${placeholders.join(",")})`);
  }
  if (cur) {
    bind.push(cur.s, cur.s, cur.r);
    where.push(`(${FTS_COLS_WEIGHTED} < ? OR (${FTS_COLS_WEIGHTED} = ? AND c.id < ?))`);
  }
  bind.push(fetchLim);

  const sql = `
    SELECT c.id AS rowid, c.chunk_id, c.vendor, c.version, c.title,
           c.heading_path, c.path, c.source_url, c.license, c.attribution,
           c.last_updated, c.snippet,
           ${FTS_COLS_WEIGHTED} AS score
    FROM chunks_fts f
    JOIN chunks c ON c.id = f.rowid
    WHERE ${where.join(" AND ")}
    ORDER BY score ASC, c.id DESC
    LIMIT ?`;

  const { results } = await env.DB.prepare(sql).bind(...bind).all();

  // AND-semantics fallback: strict MATCH (all terms) can zero out natural-language
  // queries. When empty and not paginated, retry with OR so the reranker (and the
  // user) still get candidates; BM25 ordering puts best partial matches first.
  let rows = results;
  if (!rows.length && !cur) {
    const toks = toTokens(query);
    if (toks.length > 1) {
      const orWhere = ["chunks_fts MATCH ?"];
      const orBind = [toks.map((t) => `"${t}"`).join(" OR ")];
      if (vendors?.length) {
        orWhere.push(`c.vendor IN (${vendors.map(() => "?").join(",")})`);
        orBind.push(...vendors.map(String));
      }
      orBind.push(fetchLim);
      const orSql = `
    SELECT c.id AS rowid, c.chunk_id, c.vendor, c.version, c.title,
           c.heading_path, c.path, c.source_url, c.license, c.attribution,
           c.last_updated, c.snippet,
           ${FTS_COLS_WEIGHTED} AS score
    FROM chunks_fts f
    JOIN chunks c ON c.id = f.rowid
    WHERE ${orWhere.join(" AND ")}
    ORDER BY score ASC, c.id DESC
    LIMIT ?`;
      const { results: orRows } = await env.DB.prepare(orSql).bind(...orBind).all();
      rows = orRows;
    }
  }

  // ── Semantic rerank (Phase 3, Vectorize-free variant) ──────────────────
  // LLM listwise rerank of keyword candidates via Workers AI (no vector
  // index needed — see worker/src/llm-rerank.js header). Gracefully
  // degrades to keyword order when the AI binding is absent or fails.
  if (semantic && !cur && rows.length) {
    try {
      const { llmRerank } = await import("./llm-rerank.js");
      const order = await llmRerank(env, query, rows);
      if (order) {
        const byId = new Map(rows.map(r => [r.chunk_id, r]));
        const fused = order.map(id => byId.get(id)).filter(Boolean).slice(0, lim);
        return {
          results: fused.map(shapeResult),
          next_cursor: null,
          total: fused.length,
          reranked: "semantic",
        };
      }
    } catch (e) {
      console.error("semantic rerank failed, using keyword:", e.message);
    }
  }

  const hasMore = rows.length > lim;
  const page = hasMore ? rows.slice(0, lim) : rows;
  const last = page[page.length - 1];
  const next_cursor = hasMore && last ? encodeCursor(last.score, last.rowid) : null;

  return {
    results: page.map(shapeResult),
    next_cursor,
    total: page.length,
  };
}

function shapeResult(r) {
  // Actionable facts extracted from snippet + heading (chainable by agents).
  const actionable = extractActionables([r.title, r.heading_path, r.snippet].filter(Boolean).join("\n"));
  return withSource({
    chunk_id: r.chunk_id,
    vendor: r.vendor,
    version: r.version,
    title: r.title,
    heading_path: r.heading_path || "",
    path: r.path || "",
    source_url: r.source_url,
    license: r.license,
    attribution: r.attribution || "",
    last_updated: r.last_updated || "",
    score: r.score == null ? 0 : Math.abs(Number(r.score.toFixed(4))),
    snippet: r.snippet || "",
    ...(Object.keys(actionable).length ? { actionable } : {}),
  });
}

/**
 * Explain-flavored search: same engine, log-excerpt text as the query.
 * Signatures are pre-extracted by the caller; here we just search.
 */
export async function explainD1(env, errText, vendor) {
  // explain_error's whole job is fuzzy matching → semantic ON by default
  // (gracefully degrades to keyword when VEC/AI bindings are absent).
  const out = await searchD1(env, errText, { vendors: vendor ? [vendor] : undefined, limit: 6, semantic: true });
  const seen = new Set();
  const matches = [];
  for (const r of out.results) {
    if (seen.has(r.vendor)) continue;
    seen.add(r.vendor);
    matches.push(r);
    if (matches.length >= 3) break;
  }
  return { extracted_signatures: [], matches };
}
