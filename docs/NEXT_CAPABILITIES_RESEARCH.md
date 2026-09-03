# Research: Next capability candidates for Documesh

**Date:** 2026-09-03 · **Context:** shipped so far — chainable answers (Phase 1), act
surface (contribution protocol + verify_config + health-check), semantic rerank,
source expansion to 547. This doc ranks what's next, honest about effort and value.

---

## Tier 1 — High value, natural fit (build next)

### 1. `/digest` — version-aware "what changed" feed ⭐⭐⭐
Docs sources update constantly; agents (and humans) need deltas, not just search.
- `GET /digest?source=cloudflare&since=2026-08-01` → new/changed/deprecated pages since a date,
  built from `last_updated` + content-hash diffs already computed during deepen crawls.
- WebMCP tool `get_doc_changes` — "what changed in Cloudflare Workers docs since last month?"
- Feeds A2A delegation and scheduled-agent workflows (cron an agent to watch vendor docs).
- **Effort:** 2–3 days (hash comparison at crawl time + one endpoint). Data mostly exists.

### 2. `compare_configs(source_a, source_b)` — cross-vendor config mapping ⭐⭐⭐
Extends `verify_config` beyond a single source: "I know Netlify's redirect syntax — what's
the Vercel equivalent?" Maps documented keys across sources via co-occurrence of concepts.
- v1 honest scope: side-by-side of documented keys with citations, plus a gap list
  ("Vercel docs here don't document an equivalent — verify manually").
- **Effort:** 2 days. Pure compute on existing actionable data.

### 3. MCP Apps UI for the app page ⭐⭐ (also ora +2)
The 3 search tools have `_meta.ui` pointing at `ui://` resources — but resource quality
is scored (correct MIME `text/html;profile=mcp-app`, dark-mode meta, CSP for ChatGPT/Claude
sandboxes). Shipping one polished interactive result-card UI lifts both UX and the ora
"act for user" goal (currently 0/100).
- **Effort:** 1–2 days. Also fixes `mcp-apps-ui-quality` + `mcp-view-csp` checks.

### 4. Scheduled watch / webhook subscriptions ⭐⭐
"Watch kubernetes docs for 'storage' changes and POST to my webhook" — agent-native
monitoring. Builds on digest (needs #1 first).
- **Effort:** 3–4 days (KV-backed subscriptions + worker cron + webhook signing).

## Tier 2 — Good, slightly heavier

### 5. Multi-language SDK generation (PyPI first)
ora flagged: npm SDK exists, PyPI missing. openapi-generator from our spec → `documesh`
PyPI package with repository/homepage pointing at the domain. Closes the multi-SDK check (+0.5).
- **Effort:** half a day mostly CI.

### 6. Registry listings (Smithery + skills.sh) ⭐ low effort, pure discoverability
MCP registry entry (server-card already exists) + publish the 3 skills on skills.sh
(`npx skills add`). Both are ~1-hour tasks, both flip ora checks.

### 7. Doc quality scores per source
From issue_reports + freshness + coverage: a per-source "freshness/trust score" shown on
/coverage. Makes the contribution loop visible and gives agents a quality signal when
choosing sources.

### 8. `ask_docs` composite tool
One tool that does search → extract → (optional verify_config) and returns a direct
answer with citations. Fewer agent round-trips for simple questions. Risk: overlaps with
what the agent does well already; keep as convenience layer.

## Tier 3 — Strategic bets (post-hackathon)

### 9. x402 Boosted/Deep tiers — designed in ACT_TRANSACT_RESEARCH Phase 2 (3–4 days)
### 10. A2A delegation — Documesh as an agent that executes tasks (2 days on existing A2A endpoint)
### 11. NLWeb full feed — schemamap.xml exists; add JSONL structured feeds per source
### 12. Private meshes / team spaces — "your org's internal docs, searchable by agent" (the commercial evolution; pairs with x402 or real billing)

---

## Recommendation

**Next build: #1 `/digest`** — it's the only capability that turns the mesh from
"searchable" into "watchable", compounds with everything shipped (deepen loop updates,
A2A, scheduled agents), and is mostly assembling data we already collect.
Then #3 (MCP Apps polish) as the quick ora win, then #6 (registry listings) as an hour
of pure discoverability.
