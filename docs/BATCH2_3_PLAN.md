# Batch 2 & 3 Implementation Plan

## Batch 2 — Worker Code Changes (~15 pts)

| Fix | Implementation |
|-----|---------------|
| HTTP Link headers (RFC 8288) | Add `Link:` headers to all API responses |
| Agent mode view (`?mode=agent`) | Worker route: `/?mode=agent` returns structured JSON |
| .md endpoints | Worker serves `.md` files from `app/` for all pages |
| Markdown alternate link | Add `<link rel="alternate" type="text/markdown">` to HTML |
| 404 with markdown body | Custom 404 that returns markdown for agents |
| Rate limit headers | Add `X-RateLimit-Limit`, `X-RateLimit-Remaining` |
| NLWeb /ask endpoint | POST /ask returning JSON with _meta |
| Content negotiation | Accept: text/markdown → serve .md version |
| Bot-UA markdown serving | Detect GPTBot/ClaudeBot UA → serve .md |

## Batch 3 — Developer Portal (~9 pts)

Create `/developers.html` with:
- API documentation (endpoints, parameters, examples)
- Quickstart guide (curl examples)
- API keys (placeholder — no auth required in v1)
- Sandbox info (point to staging URL)
- OpenAPI spec link
- SDK/CLI info

## Implementation

All Worker changes go in `worker/src/index.js` — no new files needed.
Developer portal goes in `app/developers.html`.
