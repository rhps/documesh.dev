# Research: Cross-MCP Tool Chaining for Documesh — "search → act" workflows

**Date:** 2026-09-03 · **Question:** Can WebMCP tools interact with other MCP servers so the
answer of a Documesh docs search feeds another MCP's tool (and vice versa) to solve a problem
end-to-end?

---

## 1. The landscape — who orchestrates the chain?

The key architectural insight: **in WebMCP, the agent is already the orchestrator.**
Tools don't call each other directly; the agent sees all registered tools (from all pages
and all MCP servers) in one flat tool list and chains them itself.

Three integration topologies exist:

### Topology A — Agent-orchestrated chaining (WebMCP-native) ⭐ zero infra
```
User: "My Cloudflare Worker throws CRON env error — fix my repo"
Agent plan:
  1. search_docs_across(query="worker cron trigger environment variables", vendors=["cloudflare"])
  2. ← docs answer (excerpt + canonical URL)
  3. github MCP: get_file(repo, path)          ← another page/MCP server's tool
  4. LLM diff: docs answer vs user's code
  5. github MCP: create_pull_request(...)
```
The agent already does this today — ChatGPT/Claude with multiple tools calls them in
sequence. **Documesh's job is to make step 2 maximally machine-actionable**, which it
mostly is (structured results with source_url, version, license).

**Gap:** our tool returns prose excerpts. For chaining, an agent needs
*structured, actionable* answers: exact config keys, code snippets with language tags,
version applicability ("this answer applies to Workers runtime 2025-05-05+").

### Topology B — Documesh server-side tool calls other MCP servers (MCP client role)
Documesh's Worker becomes an MCP **client**: when `search_docs_across` answers, it can
optionally forward a follow-up call to another MCP server (e.g., call GitHub MCP's
`get_file_contents` to pull the user's actual config and check it against the docs answer).

- MCP spec supports this: any HTTP client can be an MCP client — handshake, tools/list,
  tools/call against another Streamable HTTP server.
- **Cost:** outbound fetch per chain step, auth management for third-party servers
  (GitHub tokens etc.), latency, and an trust/consent question (WebMCP principle:
  side effects need user approval — server-side calls bypass the browser consent surface).
- **Verdict:** powerful but heavy; only worth it for 1–2 high-value chains.

### Topology C — Documesh registers "bridge" tools that wrap other servers' capabilities
Register tools like `check_deployment_health` that internally hit a vendor's REST API
(not their MCP server) *using the docs context*:
```js
search_docs_across → returns docs for "deploy hooks netlify"
check_netlify_deploy(site_id) → new tool, calls Netlify API directly
```
No MCP-client complexity — just REST calls from the Worker. This is how most
"multi-tool" products actually work.

---

## 2. What the spec says (WebMCP + MCP)

- **WebMCP** (WICG draft, 2026): tools registered per-page via
  `navigator.modelContext.registerTool()`. Tools from multiple pages coexist;
  the agent (browser side) picks and chains. No spec mechanism for tool→tool calls —
  chaining is the agent's job by design. Tool results may include `structuredContent`
  (JSON) which is what makes chaining reliable.
- **MCP** (2025-06-18 spec): servers can expose **sampling** (ask the *client's* LLM),
  **roots**, and **elicitation**. A server acting as MCP *client* to other servers is
  allowed and common (aggregators like mcp-gateway, mcphub.io do exactly this).
- **Auth:** MCP now has OAuth 2.1 resource-server semantics; Streamable HTTP servers
  advertise `401 + WWW-Authenticate` for protected resources. Documesh is open/read-only,
  so it's the *easy* server in any chain.

## 3. Concrete high-value chains for Documesh (ranked by feasibility × demo value)

| # | Chain | Direction | Effort | Demo value |
|---|---|---|---|---|
| 1 | **docs → error reproduction:** search_docs_across → explain_error (already internal) → user pastes log | internal | done | medium |
| 2 | **docs → code fix (GitHub):** search docs → fetch user's config from GitHub MCP → flag mismatch | A (agent) | ~0 (just improve output shape) | **high** |
| 3 | **docs → live check:** explain_error → `check_service_status`-style REST probes (status.cloudflare.com, k8s cluster via kubeconfig-less API) | C | 1–2 days | high |
| 4 | **docs → docs:** Cloudflare answer references Kubernetes concept → auto-suggest cross-mesh search | A | 1 day (cross-ref extraction) | medium |
| 5 | **docs → ticket:** explain_error → Linear/Jira MCP `create_issue` with docs citations attached | A | ~0 (agent does it) | **high for demo** |
| 6 | **server-side aggregation:** /search transparently calls 2–3 other MCP servers to enrich answers | B | 1 week + auth | medium (risky) |

## 4. Recommended implementation path (post-deadline)

### Phase 1 — Make answers chainable (1–2 days, pure output shaping)
1. **`structuredContent` in WebMCP tool returns** (spec field for machine-readable
   results): `search_docs_across` returns
   `{ structuredContent: { query, top_answer: {config_keys[], code_snippets[{lang,code}], applies_to_version, canonical_url}, results[...] } }`.
2. **Actionable fields in API responses:** extract `config_keys` (e.g. `cron`,
   `vars.MY_VAR`) and fenced code blocks (with language) at index time or query time —
   chunks already carry heading_path which usually names the config key.
3. **`applies_to` metadata:** map vendor+version to a concrete "this applies to X ≥ Y" hint.
4. Document the chain recipes in the tool `description` itself — agents read descriptions
   to plan: *"Pairs well with GitHub MCP get_file_contents to verify user config against docs."*

### Phase 2 — One bridge tool (2–3 days)
Pick the single highest-value live check: `check_status_health(provider)` hitting
status pages / health endpoints (read-only, no auth) — turns "docs say X" into
"and here's the live state relevant to X". Register alongside existing tools; the agent
chains it after explain_error automatically.

### Phase 3 — MCP-client mode (optional, gated)
`/search?enrich=github` — Worker performs MCP handshake to user-designated MCP server
(URL + token supplied per-request, never stored) and merges results. Per-request creds
avoid the trust problem; latency ~+300–800 ms.

## 5. Risks & guardrails
- **Trust/consent:** server-side actions (Topology B) bypass the browser consent model —
  keep all side-effectful actions in Topology A (agent does them, user sees each call).
- **Prompt injection via docs content:** a malicious docs page could try to instruct the
  agent. Mitigate: mark excerpts as data (`structuredContent` not concatenated prose),
  keep the honest-disclaimer pattern, never auto-execute anything from search results.
- **Latency budget:** every chain hop adds a turn; keep Documesh responses fast (<300 ms)
  so chains stay snappy.
- **License:** chains that carry excerpts into third-party systems (tickets, PRs) must
  keep the license + attribution fields — our chunks already carry them end-to-end.

## 6. Effort summary
| Phase | Effort | New infra | Unblocks |
|---|---|---|---|
| 1. Chainable outputs | 1–2 days | none | all Topology-A chains (2,4,5) |
| 2. Bridge tool | 2–3 days | none (REST) | chain 3 (live checks) |
| 3. MCP-client enrich | ~1 week | outbound auth | chain 6 |
