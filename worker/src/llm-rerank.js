/**
 * LLM listwise rerank — Vectorize-free semantic reranking via Workers AI.
 *
 * Why not Vectorize (docs/PHASE2_PHASE3_PLAN.md §3): account API tokens (laptop + CI)
 * lack Vectorize scope and the dashboard path was unavailable — so instead of a vector
 * index we rerank with an instruct LLM in a single call:
 *
 *   D1 FTS5 top-20 → one @cf/meta/llama-3.1-8b-instruct call:
 *   "rank these doc chunks by relevance to the query" → reordered ids
 *
 * Costs 1 AI call (~200–500 ms), no embeddings, no index, no new permissions.
 * Graceful degrade: any AI error → original keyword order, reranked:"keyword".
 */

const RERANK_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8-fast";
const MAX_CANDIDATES = 20;

/**
 * Rerank D1 rows against a query using an instruct LLM.
 * rows: [{chunk_id, title, heading_path, snippet}] — keyword-ordered.
 * Returns array of chunk_ids in (possibly new) best-first order; on any
 * failure returns the input order (caller keeps keyword ranking).
 */
export async function llmRerank(env, query, rows) {
  const candidates = rows.slice(0, MAX_CANDIDATES);
  if (candidates.length < 2 || !env.AI) return null;

  const list = candidates.map((r, i) =>
    `[${i}] ${r.title}${r.heading_path ? " — " + r.heading_path : ""}: ${(r.snippet || "").slice(0, 220)}`
  ).join("\n");

  const prompt =
    `Rank these documentation snippets by relevance to the query.\n` +
    `Query: ${JSON.stringify(query.slice(0, 300))}\n\n` +
    `Snippets:\n${list}\n\n` +
    `Reply with ONLY the indices, best first, comma-separated (e.g. "3,0,7,1,..."). ` +
    `Use every index exactly once.`;

  try {
    const res = await env.AI.run(RERANK_MODEL, {
      messages: [{ role: "user", content: prompt }],
      max_tokens: 120,
      temperature: 0,
    });
    const text = (res?.response || "").trim();
    // Parse "3,0,7,1..." — tolerate stray text by extracting all integers,
    // keep only valid unique indices, append any missing ones in keyword order.
    const picked = [];
    const seen = new Set();
    for (const m of text.matchAll(/\d+/g)) {
      const idx = parseInt(m[0], 10);
      if (idx < candidates.length && !seen.has(idx)) {
        seen.add(idx);
        picked.push(idx);
      }
    }
    for (let i = 0; i < candidates.length; i++) {
      if (!seen.has(i)) picked.push(i);
    }
    return picked.map(i => candidates[i].chunk_id);
  } catch (e) {
    console.error("llmRerank failed, keeping keyword order:", e.message);
    return null;
  }
}
