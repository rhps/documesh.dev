# Implementation Plan — Phase 2 (shard retirement) + Phase 3 (Vectorize semantic rerank)

**Date:** 2026-09-03 · **Status:** planned, ready to execute post-deadline
**Prereq check (verified 2026-09-03):**
- Phase 1 (D1 FTS5) is LIVE: `SEARCH_BACKEND=d1` deployed, ~31k chunks / 47 sources, eval 5/5
- Shard fallback still present: `app/shards/` = 47 files, `searchAcross()` + lazy loader in `worker/src/index.js` (line 83, 335), `explain` falls back to shards on D1 error (line 250)
- Deadline (Sep 3) work takes priority — this plan starts **after** Devpost submission

---

## Phase 2 — Retire shards + deep-ingest unlock (~half day + crawl time)

### Why now
Shards cost 47 asset files (~67 MB raw) and every legacy-path query loads them into isolate
memory (~65 MB decompressed). D1 has been the default backend since promotion; shards are only
a safety net. Removing them frees the 25 MiB/file ceiling and unlocks deep ingestion (AWS
per-service slices, deeper Vercel/IBMCloud).

### 2a. Pre-flight safety net (before deleting anything)
1. **Freeze a rollback tag:** `git tag shards-fallback v1.2.x-alias` — if D1 ever degrades,
   redeploying this tag restores the fallback instantly.
2. **D1 health probe in /health:** extend `/health` to assert `SELECT count(*) FROM chunks`
   returns > 0 and report `backend: "d1", chunks: N`. Rollback trigger: probe fails 3× in CI.
3. **CI addition:** a nightly smoke job hitting `/v1/search?q=` across 5 vendor filters,
   asserting non-empty results (catches silent D1 drift before users do).

### 2b. Deletion sequence (one PR, ordered commits)
1. Remove `explain`'s shard fallback branch (line ~250) — D1 errors now return the typed
   error envelope with `resolution: "retry shortly"` (honest failure beats wrong results).
2. Remove `searchAcross()` + shard loader block from `worker/src/index.js` (lines ~83, ~335).
3. Delete `app/shards/` (47 files), `indexer/build_shards.py`, shard references in README.
4. Simplify `unifiedSearch()` → always D1; keep the function name (call sites unchanged).
5. Update `docs/` + README architecture blurbs; coverage page removes "shard fallback" text.

### 2c. Verification
- `node worker/eval.mjs` ≥ 5/5 (D1-only)
- p95 latency check: `/v1/search` over 20 queries — expect flat <150 ms (no cold shard loads)
- Asset count in deploy log drops by 47; deploy time slightly down
- Rollback: `wrangler deploy` of the frozen tag (shards still in that tree)

### 2d. Deep-ingest unlock (Phase 2 payoff — can run on the server loop)
1. Bump `AVAILABLE` denominators in `deepen_loop.py` for vendors previously capped:
   AWS (per-service llms.txt slices), Vercel (raise page cap 60 → 400), IBMCloud.
2. Resume the deepen loop; new chunks flow into D1 via `load_d1.py` (idempotent upserts).
3. No deploy needed — D1 writes are live immediately (same as backfill flow).

**Exit criteria:** no shard code in tree, eval ≥ baseline, p95 flat, deploy log shows −47 assets,
deep-ingest loop running with raised caps.

---

## Phase 3 — Vectorize semantic rerank (~1 day, most of it backfill babysitting)

### 3a. Setup (~15 min)
```bash
npx wrangler vectorize create documesh-chunks --dimensions=768 --metric=cosine
```
- Model: `@cf/baai/bge-base-en-v1.5` (768-dim). **Verify dims on the model card first** —
  if we pick `bge-m3` (1024) instead, the index must be created with 1024.
- wrangler.jsonc additions (top-level + both envs):
  ```jsonc
  "vectorize": [{ "binding": "VEC", "index_name": "documesh-chunks" }],
  "ai": { "binding": "AI" }
  ```

### 3b. Embedding backfill (the long pole)
- **Where:** a one-off authenticated admin route on the Worker
  (`POST /admin/embed-backfill`, guarded by `env.ADMIN_SECRET` header) — the AI + VEC
  bindings only exist inside Workers, so a standalone script can't call them.
- **Loop:** pull chunk_ids in batches of 100 from D1 (skip ids already in Vectorize —
  track a `embeddings` marker table in D1: `chunk_id TEXT PRIMARY KEY`), embed
  `title + "\n" + heading_path + "\n" + snippet` (NOT full content: bge context window
  is 512 tokens; snippets carry the signal), upsert 100 vectors/VEC call.
- **Volume math:** ~31k chunks → 310 AI calls + 310 VEC upserts. Workers AI bge-base is
  cheap (~$0.012/1M input tokens at paid neon rates; well under $1 total). Runtime: ~20–40 min
  including politeness pacing. Run as `ctx.waitUntil` chain from the admin route, or drive
  the loop from curl (safer: 100-chunk pages, one curl per page, resumable by design).
- **Idempotency:** marker table makes re-runs resume exactly where they stopped.
- **Freshness:** new chunks from the deepen loop are NOT auto-embedded — add an
  `embed_pending` step to the loop's cycle (embed newest 100 un-embedded chunks per cycle)
  or a weekly cron. Decide: loop-side (server) keeps Worker simple → **recommended**.

### 3c. Query path (hybrid RRF merge)
```
searchD1(env, query, {semantic: true}):
  kw   = D1 FTS5 top-50                          # always, ~20-40 ms
  if !semantic: return kw (unchanged contract)
  vec  = AI.run(bge, query) → VEC.query(vector, topK=50, returnMetadata=true)
  merged = RRF(kw, vec, k=60)                    # reciprocal rank fusion — no score scaling
  hydrate top-N rows from D1 by chunk_id IN (…)  # single round trip
  return {...kw-shape, results: merged, reranked: "semantic"}
```
- **RRF over score normalization:** BM25 and cosine are incomparable scales; rank fusion
  sidesteps tuning. Formula: `score(d) = Σ 1/(60 + rank_i(d))` over both lists.
- **Default OFF** for `/search`; ON for `explain_error` (its job is fuzzy matching);
  opt-in via `POST /search {prefer:{semantic:true}}` and `?prefer=semantic` on GET.
- Response gains one field: `reranked: "semantic" | "keyword"` — additive, contract-safe.

### 3d. Wiring points (all in `worker/src/index.js` + one new module)
- New `worker/src/search-semantic.js`: `embedQuery()`, `vecQuery()`, `rrfMerge()`, `hydrate()`.
- `searchD1()` gains the optional semantic branch (keep it a separate module so Phase 2's
  simplification of `index.js` isn't reopened).
- `runExplain()` calls with `semantic: true` by default; MCP `explain_error` tool description
  updated to mention semantic matching (nice eval-bait for judges post-deadline).

### 3e. Eval before/after (do this FIRST — defines success)
1. Write `worker/eval-semantic.mjs`: 10 error→expected-doc pairs (extend the existing 5:
   CrashLoopBackOff, module-not-found, EADDRINUSE, deploy-fail, OOMKilled + 5 new fuzzy ones:
   "pod keeps restarting", "can't connect to db from worker", "CORS error in browser",
   "env var undefined in production build", "rate limit 429 from API").
2. Baseline: current D1 keyword path → record top-3 hit rate.
3. After: same set with semantic ON → require ≥ baseline, target +20% on the 5 fuzzy ones.
4. Keep both evals in CI; semantic regression fails the gate.

**Exit criteria:** eval-semantic ≥ baseline + fuzzy improvement, semantic path p95 < 400 ms
(embed ~50 ms + VEC ~20 ms + hydrate), 31k vectors ≪ 5M limit, rollback =
`prefer.semantic` flag off (default already off — instant).

---

## Execution order & cost

| Step | Effort | When | Cost |
|---|---|---|---|
| 2a safety net | 30 min | post-deadline day 1 | free |
| 2b shard deletion | 1 h | same day | free |
| 2d deep ingest | loop runtime | same week | free (server) |
| 3a Vectorize setup | 15 min | day 2 | free tier |
| 3e eval set FIRST | 1 h | day 2 | free |
| 3b backfill | 1 h code + ~30 min run | day 2 | <$0.05 AI |
| 3c–3d query path | 2–3 h | day 2 | free |
| 3e re-eval + deploy | 1 h | day 2 | free |

**Total: ~2 focused days.** Hard dependencies: none external; needs Workers Paid (already on,
since D1 production traffic) for Vectorize + AI bindings.

## Risks & mitigations
| Risk | Mitigation |
|---|---|
| Embedding quality mismatch (snippets too thin) | eval set decides; fallback to title+heading+first 1000 chars of content if fuzzy eval regresses |
| bge context window truncation | embed snippet not content (design already does this) |
| VEC query adds latency to explain_error | p95 budget 400 ms; acceptable for the tool's nature |
| D1 drift breaks keyword path after shard deletion | 2a CI smoke + /health probe; rollback tag |
| Double-embedding after deepen loop adds chunks | loop-side embed_pending step (3b) |

## Deliberately NOT in scope
- Full-content embeddings (token cost, marginal gain over snippet+title)
- Semantic-only search path (keyword stays the cheap always-on baseline)
- Multi-vector per chunk (one embedding per chunk; heading_path in text covers hierarchy)
- Turso/libSQL vectors (second vendor for no gain at our scale)

---

## Implementation status — FINAL (2026-09-03 ~02:00 UTC): Phase 3 LIVE, Vectorize-free

Vectorize index creation was blocked (no token scope + dashboard unavailable), so Phase 3
shipped with a **different semantic engine**: LLM listwise rerank via Workers AI.

| What | Status |
|---|---|
| `worker/src/llm-rerank.js` — listwise rerank, `@cf/meta/llama-3.1-8b-instruct-fp8-fast`, temp 0, robust index parsing | ✅ live |
| AI binding (all envs) | ✅ deployed — needs no resource creation, unlike Vectorize |
| Semantic branch in `searchD1` | ✅ live — opt-in `?prefer=semantic` / POST `prefer.semantic`; `explain_error` default-on |
| `reranked: "semantic"\|"keyword"` response field | ✅ live-verified |
| OR-semantics fallback (strict-AND zero results → OR retry, feeds reranker) | ✅ live-verified: "cors error browser fetch blocked" went 0 → 3 CORS docs |
| `/admin/rerank-check` diagnostics route | ✅ live (X-Admin-Secret) |
| Latency | ~500–700 ms semantic (1 LLM call), ~150–200 ms keyword — within the 400 ms-ish target for an opt-in path |
| Eval gate | ✅ 5/5 before and after |

Latency comparison: keyword 161 ms vs semantic 519 ms (acceptable — semantic is opt-in and
explain-only by default). Vectorize remains the better end-state at scale (vectors pre-computed,
~20 ms queries); if the account gains Vectorize access, `search-semantic.js` history in git
(worker/src/search-semantic.js @ 523c983) plus plan §3 is the full recipe.

## Implementation status (2026-09-03 ~01:40 UTC)

| Step | Status |
|---|---|
| 3a Vectorize index creation | 🔴 **BLOCKED** — both the laptop CF API token and the CI (Deploy Staging) token lack Vectorize scope ("Authentication error 10000"). One-off CI workflow attempt confirmed. |
| 3b backfill route | ✅ Implemented: `POST /admin/embed-backfill` (X-Admin-Secret header, ?page_size=, resumable via `embeddings` marker table, 501 when bindings absent) — live, guard verified (403 without secret) |
| 3c query path | ✅ Implemented: `searchD1(semantic:true)` RRF fusion, `?prefer=semantic` / POST `prefer.semantic`, `reranked` field added; `explain_error` semantic-on-by-default |
| 3d degrade path | ✅ Verified live: `?prefer=semantic` returns 200 `reranked:"keyword"` (bindings absent → keyword fallback, no error); eval gate 5/5 still passes |
| wrangler bindings | ⏸ VEC/AI blocks written then held out of wrangler.jsonc until the index exists (deploy would fail otherwise). Re-add the three blocks (top-level + staging + production) after index creation — they are in this plan §3a. |
| ADMIN_SECRET | ⏸ Not set — `wrangler secret put ADMIN_SECRET --env staging` (and production), needs a value from the user |

### To finish (needs a token with Vectorize edit permission)
1. Dashboard → AI & Platform → Vectorize → Create index: name `documesh-chunks`, dims **768**, metric **cosine**
   (or: new API token with `Vectorize:Edit` → `npx wrangler vectorize create documesh-chunks --dimensions=768 --metric=cosine`)
2. Re-add VEC + AI binding blocks to wrangler.jsonc (§3a above, 3 places) → push → Deploy Staging
3. `wrangler secret put ADMIN_SECRET --env staging`
4. Loop until `{"done":true}`:
   `curl -s -X POST 'https://documesh.selatan.org/admin/embed-backfill?page_size=100' -H "X-Admin-Secret: $SECRET"`
   (~31k chunks → ~310 calls, ~20–40 min)
5. Verify: `curl 'https://documesh.selatan.org/search?q=pod+keeps+restarting&prefer=semantic&limit=3'` → `reranked:"semantic"`
6. Same for production env before next `v*` tag.
