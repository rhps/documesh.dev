# Research: Scaling Search Beyond Static-Asset Shards

**Problem:** The search index ships as 47 static JSON shards (67 MB raw, ~40 MB gz on CF CDN).
The Worker lazily loads shards into **isolate memory** per query. Limits & pain points:

| Constraint | Value | Impact |
|---|---|---|
| Worker isolate memory | 128 MB | Each unfederated query loads ALL 47 shards (~40 MB gz → ~65+ MB decompressed Maps). A handful of concurrent cold queries can evict/kill the isolate. |
| Worker CPU time (free/paid) | 10 ms / 30 s | Decompress + `Object.entries()` → Map for big shards (Cloudflare 18 MB) is CPU-heavy on cold loads. |
| Static asset size per file | 25 MiB hard cap | Cloudflare shard (18 MB) is close; adding more vendors per vendor depth will hit it. |
| Total assets | 20,000 files / 10 GB paid tier | Fine today; blocks future "deep ingestion" (AWS has 1,236+ pages per service slice). |
| Startup/latency | cold queries load every shard serially | Federated queries get slower linearly with vendor count. |

**Root cause:** we ship the *inverted index* to compute at the edge. The alternative class of
solutions is: keep the index in a **queryable store** and push the query to the data, not the
data to the query.

---

## Option A — Cloudflare D1 (SQLite at the edge) ⭐ recommended first step

D1 is Cloudflare's serverless SQLite. FTS5 (full-text search) is supported.

- **Model:** one `chunks` table (`vendor, version, title, heading_path, path, source_url, license, attribution, last_updated, content`) + an FTS5 virtual table over it. The Worker issues `SELECT ... FROM chunks_fts WHERE chunks_fts MATCH ? AND vendor IN (...) LIMIT k`.
- **Why it fits:** search work moves *into* D1 — the Worker never loads an index into memory. Memory per request drops to ~0; vendor count stops mattering. federation = `vendor IN (...)`, cursor pagination = `WHERE rowid > ?`.
- **Limits (2026):** 10 GB per database (paid; free 5 GB), query rows read limits generous. Our corpus: 18.5k chunks ≈ 180 MB of text — **fits ~25× over even with 5× deeper ingestion.**
- **Ingestion path:** `wrangler d1 execute` with batched inserts, or a small script over the HTTP API. Rebuild = drop/recreate FTS table (deterministic from chunks JSONL we already have).
- **Effort:** ~1–2 days. Schema + indexer/loader swap + response-shape preservation (results already carry vendor/license/URL; scoring changes from TF-IDF to BM25 — eval gate may need re-baselining).
- **Risks:** BM25 relevance differs from current TF*IDF ranking → re-run `worker/eval.mjs`, tune `bm25()` weights; FTS5 tokenization is Unicode-aware but not identical to our tokenizer.

## Option B — Cloudflare Vectorize + Workers AI (semantic search)

- Vectorize = managed vector index; pair with `@cf/baai/bge-m3`-class embedding model.
- **Why:** upgrades matching from keyword to semantic ("my pod keeps restarting" → CrashLoopBackOff docs) — a genuine quality jump for the explain_error tool.
- **Limits:** 5 M vectors / index (paid) — 18.5k chunks is nothing; but **embedding 18.5k chunks costs Workers AI quota** and adds an embedding step to ingestion.
- **Verdict:** best as **Option C hybrid second stage**, not the first move. Keyword search stays the cheap baseline; semantic reranking of top-50 candidates keeps costs tiny.

## Option C — Hybrid two-stage (D1 FTS5 → Vectorize rerank) ⭐ end-state

1. D1 FTS5 fetches top-50 keyword candidates (cheap, exact).
2. Optional: embed query, Vectorize topK=50, merge/rerank (only when `prefer.semantic=true` or for explain_error).
- Keeps latency ~10–30 ms for the common path; semantic is opt-in. Both stores stay under limits forever.

## Option D — Precomputed compressed shards + smarter loading (no new infra)

Quick wins that extend the current architecture without D1:

| Tactic | Saving | Cost |
|---|---|---|
| Ship `.br`/`.gz` shards + `Cache-Control: immutable` (CF compresses JSON automatically today — verify clients get br) | 87% wire size (2.4 MB for the 18 MB shard) | ~0 — but **decompress still costs isolate CPU/memory**; doesn't fix the 128 MB wall |
| Split "postings" from "docs" (two files per vendor); load postings for filtering, fetch doc rows only for the final k results | ~40–60% memory (docs are the bulk) | Medium refactor |
| Merge per-vendor shards into ONE pre-bundled `index.bin` with a binary layout (typed arrays, not JSON Maps) | 5–10× memory vs Map-of-objects; much faster cold load | High refactor (custom binary format + reader) |
| Cache API: store decompressed Maps in `caches.default` keyed per vendor | avoids re-parse; still memory-bound | Small |
| Parallelize shard fetch with `Promise.all` (currently serial) | latency only | Trivial |

**Verdict:** Option D buys months, not a solution. The 128 MB ceiling + 25 MiB/file cap will bite again at ~80–100 vendors or with deeper AWS ingestion.

## Option E — External search service (Typesense/Meilisearch/Algolia/Turso-built-on-libSQL)

- **Self-hosted Typesense/Meilisearch** on a VPS/Fly/Railway: excellent BM25 + typo tolerance, one HTTP call from the Worker. ~$5–10/mo.
- **Algolia**: managed, generous free tier (10k records/mo) — we're at 18.5k, so paid from day one. Overkill.
- **Turso (libSQL)**: SQLite-at-edge with FTS5 support + `database per geography` replication; libSQL supports vector search too. Attractive because it's the same SQL model as D1 but multi-cloud — but it inserts a second vendor (dependency + egress) where D1 keeps everything in Cloudflare.

**Verdict:** viable fallback if D1's FTS5 relevance disappoints; otherwise extra moving parts.

## Option F — Docs-as-content via R2 + on-the-fly grep

Store raw markdown in R2, "search" = object listing + substring scan. **Rejected:** O(corpus) per query, no ranking, latency awful at 180 MB+.

---

## Recommendation (for later implementation)

1. **Phase 1 — D1 + FTS5 (Option A).** One weekend: schema, backfill script from `data/chunks/*.jsonl` (source of truth we already have), Worker query swap, keep static shards as fallback flag. Re-baseline eval.
2. **Phase 2 — kill the shards** once eval ≥ current baseline; frees 67 MB from the asset pipeline and removes the 25 MiB/file ceiling for deep AWS ingestion.
3. **Phase 3 — Vectorize rerank for explain_error** (Option C) when quality, not scale, is the next bottleneck.
4. Keep Option D's parallel-fetch trick regardless — it's a 5-line change.

### Cost model (paid Workers $5/mo — required for D1 at our write volume)
- D1: included (5 GB) → our 180 MB corpus is trivial; reads/writes well under paid allowances at hackathon traffic.
- No egress, no second vendor, everything stays in the current `wrangler deploy`.

### Key numbers to re-check at implementation time
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- FTS5 in D1: https://developers.cloudflare.com/d1/reference/features/full-text-search/
- Vectorize limits: https://developers.cloudflare.com/vectorize/platform/limits/
