/**
 * Semantic rerank — Vectorize + Workers AI hybrid over the D1 keyword path.
 *
 * Design (docs/PHASE2_PHASE3_PLAN.md §3):
 *   kw  = D1 FTS5 top-K                    (always — cheap, exact)
 *   vec = AI.embed(query) → VEC.topK       (only when semantic requested)
 *   merged = RRF(kw, vec, k=60)            (reciprocal rank fusion — no score scaling)
 *   hydrate merged ids from D1 in one round trip
 *
 * Binding-optional: if env.AI or env.VEC is missing (local dev / not yet deployed),
 * semantic requests degrade gracefully to the keyword path with reranked:"keyword".
 */

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";
const RRF_K = 60;
const CANDIDATES = 50;

/** Embed a query string → Float32Array-ish vector (768 dims). */
export async function embedQuery(env, text) {
  const out = await env.AI.run(EMBED_MODEL, { text: [text] });
  // Workers AI returns { shape:[1,768], data:[[...]] }
  const v = out?.data?.[0];
  if (!Array.isArray(v) || v.length !== 768) {
    throw new Error(`unexpected embedding shape: ${out?.shape}`);
  }
  return v;
}

/** Vectorize top-K lookup; returns [{id, score}] */
export async function vecQuery(env, vector, topK = CANDIDATES) {
  const res = await env.VEC.query(vector, { topK, returnValues: false });
  return (res?.matches || []).map(m => ({ id: m.id, score: m.score }));
}

/**
 * Reciprocal Rank Fusion of two ranked id lists.
 * lists: [ [{id}...], [{id}...] ] — order = rank. Returns Map(id → rrfScore).
 */
export function rrfMerge(lists, k = RRF_K) {
  const scores = new Map();
  for (const list of lists) {
    list.forEach((item, idx) => {
      const cur = scores.get(item.id) || 0;
      scores.set(item.id, cur + 1 / (k + idx + 1));
    });
  }
  return scores;
}

/**
 * Hybrid search: keyword candidates from D1 fused with vector neighbors.
 * kwRows: rows already returned by searchD1 (top CANDIDATES, superset of limit).
 * Returns ranked chunk_ids (best first).
 */
export function fuse(kwRows, vecMatches, limit) {
  const kwList = kwRows.map(r => ({ id: r.chunk_id }));
  const vecList = vecMatches.map(m => ({ id: m.id }));
  const scores = rrfMerge([kwList, vecList]);
  return [...scores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id]) => id);
}

/** Batch-embed texts and upsert vectors. Returns count embedded. */
export async function embedBatch(env, rows) {
  // rows: [{chunk_id, text}]
  if (!rows.length) return 0;
  const texts = rows.map(r => r.text);
  const out = await env.AI.run(EMBED_MODEL, { text: texts });
  const vectors = out?.data;
  if (!Array.isArray(vectors) || vectors.length !== rows.length) {
    throw new Error(`embed batch shape mismatch: got ${vectors?.length}, want ${rows.length}`);
  }
  await env.VEC.upsert(rows.map((r, i) => ({
    id: r.chunk_id,
    values: vectors[i],
    metadata: { vendor: r.vendor || "" },
  })));
  return rows.length;
}
