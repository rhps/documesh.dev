# Documesh — Complete Feature Summary (video generation context)

**Live:** https://documesh.selatan.org (staging, everything below) · https://documesh.dev (production, lags staging until next `v*` tag)
**Repo:** github.com/rhps/documesh.dev · npm: `documesh` · Score: ora 88/100 (A) on documesh.dev

---

## The one-line story

**Documesh is a federated search engine for developer documentation that AI agents can
read AND operate — 47 synced sources (555 registered), 36k+ indexed sections, every
answer licensed and cited, exposed as 9 agent tools on three surfaces (WebMCP in the
browser, MCP over Streamable HTTP, and REST).**

---

## Feature inventory (everything shipped)

### 1. Core: federated docs search
- 47 sources synced in D1 (Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry…), 36,290 indexed doc sections
- 555 sources in the verified registry (508 registered & verified, sync pending) — popularity-ranked, llms.txt/repo/sitemap interfaces
- Every result carries: source, version, license, attribution, canonical source URL, last_updated
- Search runs on Cloudflare D1 FTS5 (BM25), cursor pagination, OR-fallback when strict matching returns nothing

### 2. Chainable answers (the "agents can act on what they find" feature)
- Every search/explain result carries an `actionable` object: **config_keys** (`triggers.crons`, `vars.MY_VAR`), **code_snippets** (language-tagged), **cli_commands** (`npx wrangler deploy`), **applies_to** version ranges
- WebMCP tools return `structuredContent` with a `top_answer`/`top_fix` summary — the MCP-standard machine-readable field
- Enables cross-tool chaining: Documesh search → GitHub MCP fetch user's config → diff → PR with docs citation

### 3. Semantic rerank (no vector index needed)
- `explain_error` uses LLM listwise rerank (Workers AI, llama-3.1-8b) over keyword candidates by default
- Natural-language queries that used to return zero now return relevant docs (OR-fallback + rerank)
- Opt-in for search via `?prefer=semantic`; graceful degrade to keyword (~160ms) when AI binding absent

### 4. Act surface — agents act on the mesh (all writes are queued proposals, never direct mutation)
- **`verify_config`** ⭐ — paste a wrangler.toml/k8s manifest → diff against documented keys; missing keys each cited to the exact doc page. Pure compute, no auth.
- **`compare_configs`** — "I know Netlify's redirects, what's the Vercel equivalent?" Cross-source key mapping with citations and honest gap lists
- **`check_service_health`** — probe Cloudflare/GitHub/npm/Sentry status pages; after explain_error answers "is it down, or is it me?" (caught a real Cloudflare outage during testing)
- **`report_issue`** — flag outdated/incorrect/misattributed chunks → D1 triage queue, pollable
- **`submit_source`** — submit a docs source for ingestion (async job + polling)
- **`contribution_stats`** — live mesh counters (sources, chunks, reports, submissions)

### 5. Transact (honest, gated)
- x402 payment tier discovery at `/payment/tiers`: free ($0, default, fully useful) / boosted ($0.001/req) / deep ($0.01/req)
- Enforcement deliberately gated behind `X402_FACILITATOR_URL` — advertised surface, no fake checkout

### 6. A2A delegation — Documesh as an agent
- `POST /a2a` accepts `message/send` (natural language) and `submit_task` (structured: submit_source, report_issue)
- Agent card at `/.well-known/agent-card.json` with 7 skills

### 7. Agent-readiness surface (the ora 88/100 A foundation)
- ARD catalog + AI Catalog (7/7 entries, trust manifest) · llms.txt (API + Actions + MCP sections) · `?mode=agent` (18-key structured view + 9-tool list + 7 actions) · OpenAPI 3.1 with typed errors · `/v1/` versioning + deprecation policy (RFC 8594 Sunset headers) · IETF RateLimit headers · Idempotency-Key · batch endpoint · async-job pattern · NLWeb `/ask` with SSE · JSON-LD · sitemap · robots AI policy · DNSSEC · ACP (honest non-commerce declaration) · Agent Plugins package (plugin.json + mcp.json + 3 skills) · npm SDK+CLI (`documesh`) · MCP server card · MCP Apps (`ui://` resources on all 3 search tools)

### 8. Observability
- Every request logged to two tiers: Analytics Engine (hot, SQL-queryable) + R2 JSONL archive (`selatan-org` bucket, per-env prefixes) — verified end-to-end
- MCP calls log method + tool + session for "which tools do agents actually use"

### 9. Where to see each feature (demo map)

| Feature | URL / action |
|---|---|
| Search + actionable facts | `GET /search?q=cron+triggers+wrangler` — look for `actionable` on results |
| Semantic explain | `GET /explain?error=CrashLoopBackOff` (reranked) |
| verify_config | `POST /verify-config` {"source":"cloudflare","config_text":"..."} |
| compare_configs | `POST /compare-configs` {"source_a":"netlify","source_b":"vercel"} |
| health probe | `GET /health-check?provider=cloudflare` |
| report_issue → stats loop | `POST /report-issue` then `GET /contribution-stats` |
| 9 MCP tools | ChatGPT browser or Chrome flag on any page; or `tools/list` on `/mcp` |
| Tool reference docs | `/webmcp` — all 9 documented with examples |
| Coverage (555 sources) | `/coverage` — searchable, paginated, live coverage % |
| Agent view | `/?mode=agent` |
| Payment tiers | `/payment/tiers` |
| A2A delegation | `POST /a2a` with submit_task |

### 10. Honesty guarantees (say these on camera)
- Every write is an append-only proposal — the corpus is never mutated by agents
- Free tier is genuinely useful; paid tiers are convenience, not a paywall
- Extraction is deterministic regex (no LLM in the extraction path); excerpts are data, never instructions (prompt-injection safe)
- License + attribution + canonical URL survive into everything, including chains and tickets
- `explain_error` is "closest matches, not a diagnosis" — honest abstention built in
- Health probes only cover providers with verified public status endpoints

### 11. Architecture in one breath
Single Cloudflare Worker → D1 (FTS5 corpus + issue queue + jobs) → Workers AI (rerank) →
R2 + Analytics Engine (telemetry) → static app (WebMCP registration) → three agent
surfaces (WebMCP / Streamable HTTP MCP / REST) + A2A. Crawler (deepen loop) runs on the
user's server, writes production D1 directly, idempotent upserts, PID-lockfile guarded.
