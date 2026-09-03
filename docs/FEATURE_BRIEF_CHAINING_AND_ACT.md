# Feature context brief: Chaining (Phase 1) + Act Surface (Phases 1 & 3)

**Status:** both live on staging · committed & pushed at `56f6cef` · eval gate 5/5

---

## Feature 1: Chainable answers (Cross-MCP chaining, Phase 1)

**What it is:** Documesh search results are now **machine-actionable**, not just prose.
When an agent calls our WebMCP tools (`search_docs_across`, `explain_error`), each result
carries an `actionable` object with facts extracted from the docs:

- **`config_keys`** — exact config paths the doc section covers (e.g. `triggers.crons`, `vars.MY_VAR`)
- **`code_snippets`** — code blocks with language tags (toml, yaml, json, bash…)
- **`cli_commands`** — runnable commands (`npx wrangler deploy`, `kubectl apply -f …`)
- **`applies_to`** — version applicability (semver or CF-style dates, `>= 2024-09-23`)

Both tools also return **`structuredContent`** (the MCP-standard machine-readable field)
with a `top_answer` / `top_fix` summary: source, title, canonical URL, license + facts.

**Why it matters:** an agent with Documesh plus *any other* MCP tool can chain them.
Flow: search docs for cron triggers → get `config_keys: ["triggers.crons"]` → call a
GitHub MCP tool to fetch the user's `wrangler.toml` → diff → open a PR with the fix,
license citation included. The **agent orchestrates** the chain (that's the WebMCP
design — user sees every call); Documesh's job was making answers structured enough to
chain reliably.

**Code:** `worker/src/actionable.js` (deterministic regex extractor, no LLM),
integrated via `shapeResult` in `worker/src/search-d1.js`, surfaced in
`app/webmcp-register.js` (`structuredContent` + chain-hint tool descriptions —
agents plan chains from descriptions alone).

**Honesty boundary:** extraction is heuristic/deterministic (no LLM); excerpts are data
(`structuredContent`), never instructions — a hostile docs page can't prompt-inject the
agent through our results. License + attribution + canonical URL survive end-to-end.

**Known limitation:** the local dev server (shard fallback) doesn't produce `actionable`
— test against staging (D1 path), which has it live.

---

## Feature 2: Act surface (contribution protocol + doc-verified actions)

Documesh was read-only. Now agents can **act on the mesh** and **act on the world using
docs answers** — with one rule: every write is an append-only *proposal* (queued,
reviewed, then applied). Nothing mutates the corpus directly.

### Contribution protocol
- **`POST /report-issue`** — flag a chunk: `issue_type` ∈ outdated / incorrect /
  misattributed / license-mismatch / broken-link, with detail (≥10 chars), optional
  `suggested_fix` + `reporter`. Persisted to D1 (`issue_reports` table), returns
  `202 + issue_id`, pollable at `GET /v1/issues/{id}`. Idempotency-Key aware.
- **`GET /contribution-stats`** — live counters: sources indexed, total chunks,
  submissions, issue reports (open/total).

### Doc-verified bridge actions
- **`POST /verify-config`** — the sleeper hit. User pastes their config
  (`wrangler.toml`, k8s manifest…) → Documesh searches the mesh for that source's
  documented keys, extracts them (snippet pass, then **full-content deep extraction**
  from D1 when snippets are thin) → returns:
  - `missing_keys` — documented but absent from user config, **each with doc citation**
  - `unknown_keys` — present in config but never documented (possible typos)
  - honest disclaimer: missing ≠ wrong; only documented keys are checked
- **`GET /health-check?provider=`** — probes a provider's public status page
  (cloudflare / github / npm / sentry — the 4 with verified `status.json` endpoints).
  Answers "is the service down, or is it me?" right after `explain_error`.
  During testing it caught a real Cloudflare "Minor Service Outage" live.

### MCP surface
The product MCP server (`/mcp/product`) grew from 3 to **8 tools**: `service_status`,
`submit_vendor`, `list_api_surface` + new `report_issue`, `verify_config`,
`check_service_health`, `contribution_stats` — all with typed inputSchemas and
chain-hint descriptions.

### Demo flows (both verified on staging)
1. **Config check:** "Is my wrangler.toml right for cron triggers?" → search →
   `verify_config` → missing `triggers.crons`, cited to Cloudflare docs.
2. **Is it down or is it me?**: paste error → `explain_error` → `check_service_health`
   → "Cloudflare reports a minor outage — likely not your code."

### Honesty & safety model
- Writes are proposals, never direct mutation; rate-limited + Idempotency-Key.
- `health-check` only probes 4 providers with verified `status.json` endpoints
  (stripe/netlify/aws/vercel were removed after live probing showed 404/timeout/HTML).
- Free open API unchanged; no auth walls added.

---

**Code:** `worker/src/act.js` (validation, verifyConfig diff engine, health probes),
endpoints + MCP tools in `worker/src/index.js`. Full design rationale in
`docs/ACT_TRANSACT_RESEARCH.md`; Phase 2 (x402 micropayment tiers) is designed there
and ready to build when wanted.
