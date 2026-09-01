# AGENTS.md — Documesh

Instructions for AI coding agents working with this codebase.

## What is Documesh?

Documesh is an agent-native documentation search engine built on WebMCP.
It federates developer documentation from 18 vendors into a single
version-cited, license-attributed interface.

## Architecture

```
app/          → static HTML pages (landing, chat app, docs, coverage)
worker/       → Cloudflare Worker API (/search, /explain, /vendors, /health)
indexer/      → Python ingestion pipeline (crawls vendor docs, builds index)
data/         → committed chunks (.jsonl) + search index (.json) + shards (.gz)
evals/        → webmcp-evals JSON test suites
```

## Non-negotiable rules

1. Every tool response must carry `license`, `source_url`, and `last_updated`
2. Config validation is deterministic (schema-based), never LLM judgment
3. The index is a dated snapshot — state freshness honestly
4. No scraping — only official llms.txt / .md endpoints / open-licensed repos
5. Read-only operations only — no mutations to vendor docs

## Key files

- `indexer/fetch_docs.py` — primary crawler (Cloudflare, Netlify, K8s)
- `indexer/build_index.py` — builds TF-IDF search index
- `worker/src/search-core.js` — search engine (TF-IDF scoring)
- `app/app.html` — WebMCP tool registration + chat UI

## Testing

```bash
python3 indexer/verify.py   # chunk field audit
node worker/eval.mjs        # API eval (5 errors, gate ≥80%)
```
