# Agent Readiness Improvement Plan — Prioritized by Score Impact

**Score:** 48/100 (C) · **Target:** 70+ (B)
**Source:** ora.ai detailed scan, Sep 1 2026

---

## Quick Wins (code-only, no new services)

| # | Fix | Points | Effort |
|---|-----|--------|--------|
| 1 | Fix ard.json format (specVersion + entries array) | 1 | 5 min |
| 2 | robots.txt AI crawler tiered policy | 2 | 5 min |
| 3 | AGENTS.md in repo root | 1 | 5 min |
| 4 | Sitemap lastmod dates | 1 | 5 min |
| 5 | Enhanced JSON-LD (sameAs, contactPoint, address, FAQPage, BreadcrumbList) | 1+2 | 15 min |
| 6 | Trust anchor: richer Contact page (500+ chars) | 1 | 10 min |
| 7 | llms.txt: fix dead links + add when-to-use guidance | 3 | 10 min |
| 8 | .md markdown endpoints for all pages | 2 | 20 min |
| 9 | HTTP Link headers (RFC 8288) | 1 | 10 min |
| 10 | Agent mode view (?mode=agent) | 2 | 15 min |
| 11 | NLWeb /ask endpoint | 1 | 15 min |
| 12 | 404 with markdown body | 1 | 5 min |
| 13 | Rate limit headers | 2 | 10 min |
| 14 | API versioning (/v1/) + typed error model | 3 | 20 min |
| 15 | OpenAPI: operationIds + full response schemas | 1 | 15 min |
| 16 | A2A agent card | 2 | 5 min |
| 17 | MCP server card | 2 | 5 min |
| 18 | Developer portal page (/developers) | 6 | 30 min |
| 19 | Public API/docs linked from homepage | 3 | 5 min |
| 20 | Agent auth metadata (oauth-protected-resource) | 2 | 10 min |
| 21 | Skills.sh registration | 1+2 | external |
| 22 | Idempotency-Key support | 3 | 15 min |
| 23 | Async job pattern | 2 | 15 min |
| 24 | Batch/bulk endpoint | 2 | 15 min |
| 25 | NLWeb SSE streaming | 1 | 10 min |
| 26 | Web Bot Auth directory | 2 | 10 min |
| 27 | Bot-UA markdown serving | 1 | 15 min |
| 28 | Agent-friendly 404s | 1 | 5 min |
| 29 | MCP server (Streamable HTTP) | 6 | 2 hrs |
| 30 | Agent auth WWW-Authenticate hint | 1 | 10 min |
| 31 | Content negotiation (Accept: text/markdown) | 1 | 15 min |
| 32 | Modular llms.txt per section | 1 | 10 min |
| 33 | Agent Plugins manifest | 1 | 5 min |
| 34 | Agent onboarding friction (sandbox) | 1 | 10 min |
| 35 | Function calling compatibility | 1 | 5 min |
| 36 | API schema complexity (operationIds) | 1 | included in #15 |
| 37 | MCP Apps support (ui://) | 4 | 1 hr |
| 38 | Product + docs MCP coverage | 2 | 1 hr |
| 39 | Pagination (cursor-based) | 1 | 10 min |
| 40 | Auth.md (WorkOS spec structure) | 2+2 | 20 min |
| 41 | agent_auth endpoints | 2 | included in auth.md |
| 42 | WWW-Authenticate hint | 1 | included in auth.md |

**Not code-fixable:**
- Wikipedia/Wikidata entity (needs notability + external press)
- Brand name discoverability (needs search engine indexing time)
- NPM/PyPI SDK (needs npm publish — can do but external)

---

## Batch Strategy

**Batch 1 (static files — highest points/effort ratio):**
Items 1, 2, 3, 4, 5, 16, 17 — all JSON/text files, ~30 min total, ~15 pts

**Batch 2 (Worker code changes):**
Items 7, 8, 9, 10, 11, 12, 13, 14, 22, 25, 28, 30 — Worker route/handler changes, ~2 hrs, ~15 pts

**Batch 3 (new pages + portal):**
Items 18, 19 — new HTML page + homepage links, ~30 min, ~9 pts

**Batch 4 (MCP server):**
Items 29, 37, 38 — new MCP server endpoint, ~2 hrs, ~12 pts

**Batch 5 (remaining):**
Items 6, 20, 21, 23, 24, 26, 27, 32, 33, 34, 39, 40, 41, 42 — incremental, ~2 hrs, ~15 pts

**Not fixable now:** Wikipedia (3.7), brand search (5.6), NPM (1.9) — external/time-dependent
