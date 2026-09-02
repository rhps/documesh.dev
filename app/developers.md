# Documesh — Developer Portal

Federated developer documentation search across 47 vendors. Open API — no keys. This page is the markdown twin of https://documesh.selatan.org/developers.html.

## Quickstart

```bash
# Search across vendors (versioned path)
curl "https://documesh.selatan.org/v1/search?q=edge+functions+env+vars&limit=5"

# Unversioned alias of /v1/search
curl "https://documesh.selatan.org/search?q=edge+functions&limit=5"

# Match an error to docs
curl "https://documesh.selatan.org/v1/explain?error=CrashLoopBackOff+in+pod+docs-api"

# Vendor registry
curl "https://documesh.selatan.org/v1/vendors"

# MCP handshake
curl -X POST https://documesh.selatan.org/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"me","version":"1"}}}'
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/search?q=&vendors=&limit=&cursor= | Federated documentation search (cursor pagination) |
| POST | /search | JSON-body search; safe retries via Idempotency-Key header |
| POST | /batch | Up to 20 searches in one request (Idempotency-Key required) |
| GET | /v1/explain?error=&vendor= | Error/log excerpt → closest documentation sections |
| GET | /v1/vendors | Source registry with licenses |
| POST | /v1/submit-vendors | Async submission → 202 + job_id (poll GET /v1/jobs/{job_id}) |
| GET/POST | /ask | NLWeb query; SSE streaming via prefer.streaming or Accept: text/event-stream |
| POST | /mcp | MCP Streamable HTTP (JSON-RPC 2.0); GET /mcp for SSE |
| GET | /health | Service health |

## Authentication

None. The API is fully open for read-only use.

## Rate limits

100 requests/minute per IP. Advertised via IETF `RateLimit-Limit` / `RateLimit-Remaining` / `RateLimit-Reset` response headers.

## Versioning policy

URL path versioning (`/v1/`). Breaking changes ship under a new `/vN` prefix; deprecated routes return `Deprecation` and `Sunset` (RFC 8594) headers at least 90 days before removal. Unversioned paths are live aliases of `/v1`.

## SDKs

- **JavaScript/TypeScript:** `npm install documesh` — [npmjs.com/package/documesh](https://www.npmjs.com/package/documesh) (includes the `documesh` CLI)
- CLI: `documesh search "edge functions env vars"`

## Errors

All API paths return structured JSON: `{"error": {"code", "message", "status", "resolution"}}`.

## Sandbox

Staging environment: https://documesh-beta.selatan.org — same API surface, no production impact.

## More

- OpenAPI contract: https://documesh.selatan.org/openapi.json
- Auth guide: https://documesh.selatan.org/auth.md
- Contact: https://documesh.selatan.org/contact.html
