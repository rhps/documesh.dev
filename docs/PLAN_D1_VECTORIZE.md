# Implementation Plan — Option C: D1 FTS5 + Vectorize Hybrid Search

**Goal:** Replace in-isolate static-shard search with D1 full-text search as the primary path,
plus optional semantic reranking via Vectorize. Memory per request drops from ~65 MB to ~0;
the 25 MiB/file asset ceiling and the 128 MB isolate wall stop being constraints.

**Current pipeline (what we're replacing):**
`indexer/*.py crawl → data/chunks/*.jsonl → indexer/build_shards.py → app/shards/index_<vendor>.json
→ Worker fetches shards per query → in-memory Maps → TF*IDF in isolate`

**Target pipeline:**
`indexer/*.py crawl → data/chunks/*.jsonl → indexer/load_d1.py → D1 (chunks + chunks_fts)
                                            ↘ indexer/embed_backfill.py → Vectorize (vectors)
Worker → ctx.env.DB.prepare("SELECT ... WHERE chunks_fts MATCH ? AND vendor IN (...)")  [always]
       → optional Vectorize rerank (explain_error / prefer.semantic)`

---

## Phase 0 — Preflight (30 min)

1. `wrangler d1 create documesh-search` → note `database_id`.
2. Add to `wrangler.jsonc`:
   ```jsonc
   "d1_databases": [
     { "binding": "DB", "database_name": "documesh-search", "database_id": "<id>" }
   ],
   "vectorize": [
     { "binding": "VEC", "index_name": "documesh-chunks", "index_name_prefix": "" }
   ],
   "ai": { "binding": "AI" }
   ```
   (Vectorize index created later in Phase 2; the binding can be added then to avoid
   deploy errors — D1 binding alone in Phase 1.)
3. Confirm plan: Workers Paid required for realistic D1 usage (free tier: 5 GB total /
   5 M rows read per day — fine for dev, tight for launch traffic).
4. Feature flag: add `env.SEARCH_BACKEND` secret/var (`"shards"` default, `"d1"` to switch).
   Keeps rollback instant during eval.

## Phase 1 — D1 + FTS5 (the core swap)

### 1a. Schema (`d1/schema.sql`)
```sql
CREATE TABLE IF NOT EXISTS chunks (
  rowid_alias INTEGER PRIMARY KEY,
  chunk_id    TEXT UNIQUE NOT NULL,
  vendor      TEXT NOT NULL,
  version     TEXT NOT NULL,
  title       TEXT NOT NULL,
  heading_path TEXT,
  path        TEXT,
  source_url  TEXT NOT NULL,
  license     TEXT NOT NULL,
  attribution TEXT,
  last_updated TEXT,
  snippet     TEXT,          -- prebuilt 280-char plaintext (reuse build_shards.make_snippet)
  content     TEXT NOT NULL
);
CREATE INDEX idx_chunks_vendor ON chunks(vendor);
CREATE INDEX idx_chunks_chunkid ON chunks(chunk_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  title, heading_path, content,
  content='chunks', content_rowid='rowid_alias',
  tokenize='porter unicode61'
);
-- triggers to keep FTS in sync
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid_alias, title, heading_path, content)
  VALUES (new.rowid_alias, new.title, new.heading_path, new.content);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid_alias, title, heading_path, content)
  VALUES ('delete', old.rowid_alias, old.title, old.heading_path, old.content);
END;
```
Design notes:
- `content='chunks'` external-content table avoids storing the text twice.
- porter stemming: "deploying" matches "deploy" — free relevance win over current tokenizer.
- `snippet` stays a real column (fast to return; no `snippet()` call needed per row).

### 1b. Backfill (`indexer/load_d1.py`)
- Read `data/chunks/*.jsonl` (existing source of truth), reuse `make_snippet()`.
- Batch 500-row `INSERT` statements; upsert by `chunk_id` (`INSERT ... ON CONFLICT DO UPDATE`)
  so re-runs are idempotent.
- Target: 18.5k rows ≈ 40 batches ≈ a few minutes over the HTTP API or `wrangler d1 execute --file`.
- Print per-vendor counts; verify against `data/snapshot.json`.

### 1c. Query module (`worker/src/search-d1.js`)
```js
export async function searchD1(env, query, { vendors, limit = 5, cursor, minScore = 0 }) {
  const match = ftsEscape(query);           // quote tokens: `aws` "edge functions" OR-style
  const bind = [match, limit + 1];          // +1 to compute next_cursor
  let vendorFilter = "";
  if (vendors?.length) {
    vendorFilter = `AND c.vendor IN (${vendors.map(() => "?").join(",")})`;
    bind.push(...vendors);
  }
  const cur = decodeCursor(cursor);         // {score, rowid} keyset pagination
  if (cur) { vendorFilter += ` AND (bm25(chunks_fts), c.rowid_alias) < (?, ?)`; bind.push(cur.score, cur.rowid); }
  const rows = await env.DB.prepare(
    `SELECT c.rowid_alias AS rowid, c.chunk_id, c.vendor, c.version, c.title,
            c.heading_path, c.path, c.source_url, c.license, c.attribution,
            c.last_updated, c.snippet,
            bm25(chunks_fts) AS score
     FROM chunks_fts f JOIN chunks c ON c.rowid_alias = f.rowid
     WHERE chunks_fts MATCH ?1 ${vendorFilter}
     ORDER BY score, c.rowid_alias LIMIT ?2`
  ).bind(...bind).all();
  // map rows → existing response shape: {results:[{chunk_id, vendor, version, title,
  //   heading_path, path, source_url, license, attribution, last_updated, score, snippet}],
  //   next_cursor, total?}  (score sign-flipped: bm25 returns negative = better)
}
```
- **Keep the exact response contract** consumers already get (`results[]` fields + `next_cursor`).
- `ftsEscape`: strip FTS operators from user input, wrap tokens in double quotes → prevents
  syntax errors and light FTS injection. Empty/stopword-only queries → return `[]` (or fall back).
- Keyset pagination on `(score, rowid)` — stable across pages.

### 1d. Wire into `worker/src/index.js`
- In `searchAcross` call sites (`/search` GET+POST, `/batch`, MCP `search_docs_across`):
  `if (env.SEARCH_BACKEND === "d1") return searchD1(env, ...) else legacy shards`.
- `runExplain` → same D1 query with error-text as MATCH input (signatures already extracted).
- Delete the shard-loading block once flag flips (keep code under the flag for one release).

### 1e. Eval & switchover
1. `SEARCH_BACKEND=shards` deploy → capture baseline outputs for the 5 eval queries + 20
   representative queries (script: dump JSON per query).
2. `SEARCH_BACKEND=d1` (preview URL or wrangler dev with local D1) → same dump.
3. Compare top-3 overlap; tune (bm25 weights `bm25(chunks_fts, 3.0, 2.0, 1.0)` to upweight
   title/heading — mirrors the current ×3 title boost).
4. Run `worker/eval.mjs` (gate ≥80%) with the flag on via a test harness.
5. Flip default to `d1` in production, keep `shards` fallback for one release, then delete
   shard code + `app/shards/` (Phase 2).

### 1f. Phase 1 exit criteria
- [ ] `/search` p95 < 150 ms (was variable/serial shard loads)
- [ ] Isolate memory flat regardless of query breadth (no shard loading)
- [ ] eval.mjs ≥ baseline
- [ ] 47/47 vendors return non-empty results for a smoke query each
- [ ] Rollback = set `SEARCH_BACKEND=shards` (still deployed)

## Phase 2 — Retire shards + deep-ingest unlock

1. Remove `app/shards/`, shard loading code, `build_shards.py` consumers.
2. Deep-ingest AWS top services (per-service llms.txt files), raise `MAX_PAGES`.
3. Re-run `load_d1.py` (idempotent upserts).
4. Update docs: coverage counts, architecture blurb, memory of 128 MB wall gone.
   Asset count drops by 47 files; total assets well under limits.

## Phase 3 — Vectorize semantic rerank (Option C's second stage)

### 3a. Vectorize setup
```bash
npx wrangler vectorize create documesh-chunks --dimensions=768 --metric=cosine
```
(768 = @cf/baai/bge-base-en-v1.5; check current model card for dims before creating.)

### 3b. Embedding backfill (`indexer/embed_backfill.py` or a Worker queue consumer)
- For each chunk: `env.AI.run("@cf/baai/bge-base-en-v1.5", { text: title + "\n" + snippet })`
  → vector; `env.VEC.upsert({ id: chunk_id, values, metadata: { vendor } })`.
- 18.5k chunks: batch 100/req → ~185 AI calls. Run via a queue consumer or a script loop
  with the Worker AI binding (script needs a Worker endpoint; simplest is a one-off
  `/admin/embed-backfill` route protected by a secret, invoked with `waitUntil` batches).
- Store `chunk_id ↔ vector id` 1:1 (ids are already unique).

### 3c. Query path
```
POST /search { query, prefer: { semantic: true } }
  → D1 FTS5 top-50 (fast, exact)               ── always
  → AI.embed(query) + VEC.query(topK=50)       ── only when semantic requested
  → RRF merge (reciprocal rank fusion, k=60)   ── no score normalization needed
  → return top-N
```
- `explain_error` defaults to semantic ON (its whole job is fuzzy matching).
- Response gains `reranked: "semantic"|"keyword"` field; contract otherwise unchanged.

### 3d. Phase 3 exit criteria
- [ ] explain_error eval set improves (define 10 error→expected-doc pairs before starting)
- [ ] semantic path p95 < 400 ms (embed ~50 ms + vector query ~20 ms + merge)
- [ ] Vectorize: 18.5k vectors vs 5 M limit — headroom ×250

## Rollout order & rollback
| Step | Action | Rollback |
|---|---|---|
| 1 | D1 created, schema + backfill | none needed (nothing reads it) |
| 2 | Worker dual-path behind `SEARCH_BACKEND` | flag flip |
| 3 | Default → `d1` | flag flip to `shards` |
| 4 | Shards deleted | git revert |
| 5 | Vectorize + backfill | `prefer.semantic` off by default |
| 6 | semantic on for explain_error | per-request opt-out already supported |

## Effort estimates
| Phase | Effort | Main risk |
|---|---|---|
| 0 | 0.5 h | account plan for D1 |
| 1 | 1–2 days | relevance re-baseline (BM25 vs TF-IDF) |
| 2 | 0.5 day + ingestion time | AWS corpus size (chunk the backfill) |
| 3 | 1 day | embedding quota; define eval set first |

## Open questions to settle before Phase 1 starts
1. **Version handling:** chunks carry `version: "latest"` today — single-version rows OK?
   (If multi-version later: add `version` to FTS filter, no schema change needed.)
2. **`/batch` concurrency:** D1 supports N sequential statements per request; 20 ops × 1 query
   is fine, but consider `Promise.all` batching limits (D1 = no true parallel sessions per
   invocation; sequential is fine at our scale).
3. **Eval baseline dump script** — write it *before* flipping the flag so before/after is
   comparable.
