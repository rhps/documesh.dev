# SESSION HANDOFF — Documesh: Deep-Coverage Backfill (server-run workload)

**Written:** 2026-09-02 (~16:30 UTC)
**Purpose:** Run the vendor docs deep-crawl + D1 backfill on your server (laptop-independent).
Paste the "New session prompt" into a fresh Hermes session on the server.

---

## 0. New session prompt (paste this on the server)

> I'm working on Documesh at `/path/to/documesh.dev` (clone from `github:rhps/documesh.dev`,
> branch `main`). Read `SESSION_HANDOFF_BACKFILL.md` in this directory first, then run the
> deep-coverage backfill: deepen the thin vendors, rebuild D1, and report per-batch results
> as a Have/Available/Coverage table. Do NOT deploy anything — D1 is written directly via
> Cloudflare's API.

---

## 1. Goal

Raise per-vendor coverage (chunks) toward each vendor's available docs corpus.
Current state: **31,012 chunks / 47 vendors** in Cloudflare D1 (database `documesh-search`).

Priority order (highest-impact gaps first — from docs/COVERAGE_AUDIT.md):

| Batch | Vendors | Have now | Available (est.) | Why |
|---|---|---:|---:|---|
| 2 | digitalocean | 293 | ~4,000 | 7% coverage, huge tutorial corpus, llms.txt agent-permitted |
| 3 | ibmcloud | 199 | ~10,000 | 2% — huge catalog; prioritize popular services |
| 4 | opentelemetry | 73 | ~2,000 | 4% — spec + docs repos |
| 5 | pulumi | 34 | ~2,000 | 2% — fix: use docs/ subtree, skip 404ing marketing links |
| 6 | pytorch | 75 | ~6,000 | 1% — tutorials repo has hundreds of .md |
| 7 | sentry | 131 | ~1,500 | 9% — platform SDKs |
| 8 | langchain | 175 | ~2,500 | 7% — python docs slice |
| 9 | vercel | 719 | ~2,500 | 29% — raise page cap |
| 10 | hugo, docusaurus, upstash, bun | 60–72 each | 350–900 | quick wins, llms.txt crawls |

Batches 1 (aws, stripe, kubernetes, pytorch, ollama) are DONE — aws 1,188, kubernetes 794,
stripe 649, ollama 127 (100% complete), pytorch 75.

## 2. How ingestion works

- **Crawlers** live in `indexer/`:
  - `indexer/deepen_batch1.py` — pattern example: per-vendor crawl functions, writes
    `data/chunks/<vendor>_latest.jsonl` (REPLACES that file)
  - `indexer/deepen_aws_v2.py` — AWS pattern: root llms.txt → sub-llms.txt indexes → .md pages
  - `indexer/add_vendor.py --id <vendor> --cap 400` — generic single-vendor crawler with
    pattern library (llms.txt, git tree, sitemap). Check `VENDORS` dict for supported ids.
  - `indexer/batch2_docs.py` — prior batch script (cap already raised to 400)
- **Chunk format** (one JSON per line): `chunk_id, vendor, version:"latest", title,
  heading_path, path, content, source_url, license, license_url, attribution, last_updated`.
  Use `chunk_markdown()` + `make_chunk()` helpers from deepen_batch1.py — split on headings,
  chunk big sections at ~1,800 chars, ≥120-char body minimum.
- **Caps are already removed**: MAX=400 in batch2_docs.py / ingest_tier1_cloud.py /
  add_vendor.py default. Politeness delay 0.05–0.15 s between fetches — keep it.
- **Known crawler bugs already fixed**: stripe `.md.md` double-suffix; aws root-index
  landing pages (real depth is in sub-llms.txt).

## 3. After crawling a vendor — get it into D1

1. Rebuild shards (also used as a fallback search path): `python3 indexer/build_shards.py`
2. Backfill D1 (idempotent, parameterized, safe to re-run):
   ```
   export CLOUDFLARE_API_TOKEN=<token>       # on server: set once in env/shell profile
   export CLOUDFLARE_ACCOUNT_ID=bbcfb524d633f21f6a7888b0aade6f4f
   python3 indexer/load_d1.py                # reads ALL data/chunks/*.jsonl, upserts by chunk_id
   ```
   - ~15–17 min for the full corpus (29k+ rows, 8 parallel workers); re-runs only upsert deltas
   - D1 database id: `0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b` (name: documesh-search)
3. Verify:
   ```
   curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/d1/database/0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b/query" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
     -d '{"sql":"SELECT vendor, COUNT(*) n FROM chunks GROUP BY vendor ORDER BY n DESC"}'
   ```

**NO DEPLOY NEEDED.** Live search reads D1 directly (SEARCH_BACKEND=d1 is already deployed).
The site updates the moment D1 has the rows.

## 4. Reporting format (per batch)

After each batch, report a table like:

| Vendor | Have (new) | Before | Available (est.) | Coverage |
|---|---:|---:|---:|---:|

Then commit (`git add -A && git commit && git push origin main`) so the chunk files are
preserved. Run batches sequentially, not in parallel (politeness + API rate limits).

## 5. Ingestion criteria (do not violate)

- Official agent interface (llms.txt that permits agents) OR open-licensed docs repo
- Permissive licenses only: CC-BY / MIT / Apache / BSD. NO BUSL, GPL, AGPL, SSPL, NC.
- Every chunk carries license + attribution + canonical source_url
- Skip marketing/blog/changelog pages; skip pages whose .md returns HTML or <250 bytes

## 6. Gotchas

- D1 rejects `BEGIN/COMMIT` — load_d1.py already avoids them (use load_d1.py, don't hand-roll SQL files)
- FTS5 schema: `d1/schema.sql` + explicit statement list `d1/schema.statements.json`
  (apply via `indexer/d1_schema_apply.py` — only needed for a NEW database)
- Doc content containing "BEGIN TRANSACTION"/"PRAGMA" breaks naive SQL files →
  load_d1.py uses bound parameters; keep it that way
- `git pull --ff-only` before starting — other sessions may have pushed
- GitHub rate limits: unauthenticated = 60/hr for api.github.com; crawlers hitting
  raw.githubusercontent.com are unaffected
- The site: https://documesh.selatan.org (single deployment; staging env IS production path)

## 7. Reference docs in repo

- `docs/COVERAGE_AUDIT.md` — the Have/Available/Coverage table this work targets
- `docs/VENDOR_EXPANSION_RESEARCH.md` — llms.txt probe results for future vendors
- `docs/PLAN_D1_VECTORIZE.md` — search architecture (Phase 2/3 pending, not this task)
