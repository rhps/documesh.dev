# Research: "Act & Transact" — capabilities for Documesh beyond search

**Date:** 2026-09-03 · **Question:** Documesh is read-only today. What act-and-transact
capabilities fit the product, the Cloudflare stack, and the agent ecosystem?

**Current foundations to build on:**
- Read-only REST + MCP (Streamable HTTP) + WebMCP (3 browser tools)
- `/v1/submit-sources` async-job pattern (202 + job polling) — the only write op today
- ACP discovery doc published as an *honest non-commerce declaration*
- All agent-payment protocols (x402/MPP/UCP/ACP/AP2) currently N/A
- Idempotency-Key support, batch endpoint, RateLimit headers — the plumbing agents need for safe writes already exists

---

## The product question first: what would anyone *act on* or *pay for*?

Documesh is a free, open docs mesh. Honesty rules out fake checkout endpoints. So
"act & transact" must map to real value. Three honest value axes:

1. **Act on the mesh itself** — contribute to it, correct it, grow it (contribution economy)
2. **Act on the world using docs answers** — chain docs → vendor APIs (delegated ops)
3. **Transact for mesh capacity** — pay for rate limits, deep corpus, priority sync (x402 micropayments — native fit)

---

## Capability 1 — ACT: Mesh Contribution Protocol ⭐ recommended first

Turn "submit a source" into a full agent-operable contribution surface. Agents (and the
humans steering them) can grow the mesh without a dashboard.

**Tools/endpoint additions:**

| Operation | Surface | Idempotent | State |
|---|---|---|---|
| `submit_source` (exists) | MCP tool + REST | Idempotency-Key | async job |
| `get_job_status` | MCP tool + REST | read | — |
| `report_issue` — "this chunk is wrong/outdated/misattributed" | NEW | yes | async triage queue |
| `claim_source` — "I'm maintaining vendor X's docs, here's the official llms.txt" | NEW | yes | verification workflow |
| `contribution_stats` — leaderboard, per-contributor sync counts | NEW | read | — |

**Why it's honest & safe:** every write is a *proposal* (queue → human/auto review → sync),
never a direct mutation of the corpus. Nothing destructive. Read-only mesh stays read-only;
contributions are append-only intents.

**Trust model:** unauthenticated writes are rate-limited + reviewed; `claim_source` with a
DNS/llms.txt verification step (the claimed source's own llms.txt must reference the claim —
same pattern as domain verification).

**Agent story:** "My team just launched docs.example.io — add it to Documesh" → agent calls
`submit_source` → polls job → reports back with sync ETA. Real act-and-transact-with-the-product.

**Effort:** 2–3 days. All Cloudflare-native (D1 queue table + existing job pattern).

---

## Capability 2 — TRANSACT: x402 micropayments for mesh capacity ⭐ best protocol fit

x402 (Coinbase, HTTP-native) is the cleanest payment protocol for Documesh because it
requires *no accounts, no API keys, no checkout UI* — an agent pays per-request with a
signed header when it hits an HTTP 402.

**Honest product tiers:**

| Tier | Price | What the agent gets |
|---|---|---|
| Free (current) | 0 | 100 req/hr, top-5 results, standard corpus |
| Boosted | $0.001/req via x402 | 1,000 req/hr, top-20 results, semantic rerank always-on |
| Deep | $0.01/req | + full-chunk content (not snippets), batch×50, priority queue |

**Implementation (Cloudflare-native):**
1. `/discovery/resources` endpoint advertising paid resources (x402 discovery convention)
2. Middleware on `/v1/search`: if request exceeds free quota → respond `402 Payment Required`
   with `WWW-Authenticate: Payment ...` challenge (x402 shape)
3. Agent retries with `PAYMENT-SIGNATURE` header → Worker verifies via x402 facilitator
   (Coinbase's hosted facilitator; no wallet infra needed server-side) → serve boosted
4. Advertise in OpenAPI (`x-payment-info`) + llms.txt + agent-mode view

**Why x402 over ACP/UCP/AP2:** those are *checkout* protocols (buying goods); x402 is
*per-request metering* — exactly the "pay for more capacity" model. Also: Cloudflare
ecosystem alignment (Coinbase facilitator has first-class CF Worker support).

**Honesty guardrails:** free tier stays genuinely useful (never cripple it to force payment).
The ACP discovery doc flips from "non-commerce" to a real x402 profile — still honest, now
with an actual payment surface.

**Effort:** 3–4 days (facilitator integration, tier middleware, docs, discovery).

---

## Capability 3 — ACT: Doc-Verified Actions (bridge tools)

From the chaining research (Topology C): tools that *act on the world* using docs context.
Ranked by feasibility:

| Tool | Acts on | Auth needed | Value |
|---|---|---|---|
| `check_service_health(provider)` | vendor status pages | none | "is it down, or is it me?" after explain_error |
| `fetch_source_page(source, path)` | original docs | none | full page (licensed excerpt + link) |
| `verify_config(source, config)` | user-supplied config text | none | diff config_keys vs user's config, no external auth |
| `submit_docs_correction(source, chunk_id, correction)` | Documesh mesh | rate-limit | closes the loop on stale docs |

**`verify_config` is the sleeper hit:** user pastes their wrangler.toml/k8s manifest, agent
calls `verify_config("cloudflare", config_text)` → gets `missing_keys: [triggers.crons]`,
`invalid_values: [...]`, each with the doc citation. Pure compute, no external auth, works
in the sandbox. High demo value.

**Effort:** 1–2 days each; `verify_config` + `check_service_health` first.

---

## Capability 4 — TRANSACT: Sponsored Sync (B2B, post-hackathon)

Vendors *pay Documesh* (inverse of ads) to deep-ingest their docs with priority. UCP/ACP
profile exposes "sync packages" as purchasable services. Honest: it's a real service with
real pricing (`/pricing.md`). Heavier lift: invoicing, SLA. **Post-hackathon.**

---

## Capability 5 — ACT: A2A delegation (experimental)

The A2A agent-card already advertises skills. Add *delegation*: an external agent can hand
Documesh a task ("index this sitemap, report when done") via `/a2a message/send` → Documesh
executes as a job and replies. This makes Documesh an agent that *acts*, not just a tool.
**Effort:** 2 days on top of existing A2A endpoint. Interesting but the contribution
protocol (Capability 1) covers most of the same ground with a simpler model.

---

## Recommended sequence

| Phase | Capability | Effort | Depends on |
|---|---|---|---|
| 1 | `verify_config` + `report_issue` + `contribution_stats` | 2–3 days | nothing |
| 2 | x402 Boosted/Deep tiers | 3–4 days | nothing (facilitator is hosted) |
| 3 | `check_service_health` + `fetch_source_page` | 2 days | nothing |
| 4 | `claim_source` with DNS verification | 2 days | contribution queue from 1 |
| 5 | Sponsored Sync / A2A delegation | post-hackathon | real demand |

**Phases 1+2 together = a complete act-and-transact story:** agents *act* on the mesh
(contribute, verify configs) and *transact* for capacity (x402) — both honest, both
Cloudflare-native, both demo-able in ChatGPT/Chrome.

## Key risks & guardrails
- **Never fake commerce:** payment surfaces go live only with a working facilitator; until
  then the ACP doc stays non-commerce (current state is already honest).
- **Write abuse:** all contributions are queued proposals; rate limits + Idempotency-Key;
  no direct corpus mutation.
- **x402 wallet UX:** agents need a funded wallet; keep free tier sufficient that paying is
  optional convenience, never a paywall.
- **Scope creep:** each vendor-bridge tool multiplies maintenance; prefer read-only,
  auth-free actions.

## Protocol references
- x402: HTTP 402 + PAYMENT-* headers, facilitator verify/settle (coinbase.com/x402)
- MPP: WWW-Authenticate: Payment challenge parameters
- UCP: /.well-known/ucp profile + checkout-sessions (checkout-shaped — wrong fit for metering)
- ACP: /checkout_sessions flow (ChatGPT instant checkout — goods-shaped, wrong fit)
- AP2: signed mandates (heavy; revisit if invoices become real)
