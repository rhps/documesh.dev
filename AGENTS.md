# AGENTS.md — Documesh

Instructions for AI coding agents working with this codebase.

## What is Documesh?

Documesh is an agent-native developer-documentation search engine built on WebMCP.
It federates documentation from **47 vendors** (Cloudflare, Netlify, Vercel, AWS,
Kubernetes, Stripe, Anthropic, Neon, and more — full list: `/vendors` or
`docs/COVERAGE_AUDIT.md`) into a single version-cited, license-attributed interface.

- **Live:** https://documesh.selatan.org (also https://documesh.dev)
- **API:** open, read-only, no auth — `/search`, `/explain`, `/vendors`, `/health`, `/mcp`
- **API contract:** `app/openapi.json`
- **Machine-readable site index:** `app/llms.txt` (also served at `/llms.txt`)
- **License:** MIT (code). Ingested docs carry per-vendor licenses — attribution is mandatory.

## Architecture

```
app/            → static assets served by the Worker (pages, .well-known/, shards)
app/shards/     → per-vendor JSON index shards (legacy fallback search path)
worker/         → Cloudflare Worker: index.js (routing), search-d1.js (D1 FTS5,
                  primary search), search-core-lite.js (shard fallback + VENDOR_META),
                  mcp-server.js (MCP Streamable HTTP, 3 tools + ui:// apps)
indexer/        → Python ingestion pipeline: crawlers → data/chunks/*.jsonl → D1
d1/             → D1 schema (FTS5 external-content table + sync triggers)
data/chunks/    → source of truth for all ingested docs (one JSON per line)
docs/           → research, audits, plans (COVERAGE_AUDIT.md, PLAN_D1_VECTORIZE.md)
evals/          → webmcp-evals JSON test suites
sdk/            → documesh npm package (SDK + CLI)
```

## Non-negotiable rules

1. Every search result carries `license`, `attribution`, `source_url`,
   `last_updated` — never break this response contract (additive changes only).
2. Ingestion uses **official agent interfaces (llms.txt) or open-licensed git
   repos only** — no scraping. Permissive licenses only (CC-BY / MIT / Apache /
   BSD); never BUSL, GPL/AGPL/SSPL, or NC.
3. Config validation is deterministic (schema-based), never LLM judgment.
4. The index is a dated snapshot — state freshness honestly (`last_updated`).
5. Read-only operations against vendor docs; no mutations.
6. Vendor count (currently 47) must stay consistent across `app/openapi.json`,
   `app/.well-known/ard.json`, `app/.well-known/agent-card.json`, `app/llms.txt`,
   and page copy — a mismatch is a regression. Grep before changing.

## Deploy model

- `documesh.selatan.org` is THE site. Merge to `main` → "Deploy Staging"
  workflow → live automatically.
- Production promotion = push a `v*` tag → "Deploy Production" workflow
  (adds documesh.dev + www). Never deploy manually.
- Search backend: `SEARCH_BACKEND=d1|shards` in `wrangler.jsonc` (d1 = primary,
  shards = instant-rollback fallback).

## Verification before pushing

```bash
python3 indexer/verify.py     # chunk integrity: 0 missing fields
node worker/eval.mjs          # eval gate: ≥80%
```

## Common tasks

```bash
# deepen a vendor's coverage (no caps; politeness-delayed)
python3 indexer/deepen_batch1.py <vendor>        # aws/stripe/kubernetes/pytorch/ollama
python3 indexer/add_vendor.py --id <vendor> ...  # generic crawler (see crawl_sources.json)

# rebuild indexes + D1 (idempotent; needs CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID)
python3 indexer/build_shards.py
python3 indexer/load_d1.py

# local worker with local D1
SEARCH_BACKEND=d1 npx wrangler dev --local
```

## Where to look first

- Coverage/attribution per vendor: `docs/COVERAGE_AUDIT.md`, `/coverage.html`
- Search architecture: `docs/PLAN_D1_VECTORIZE.md`
- Backfill runbook: `docs/BACKFILL_GUIDE.md`
- Agent capabilities catalog: `/.well-known/ard.json`
