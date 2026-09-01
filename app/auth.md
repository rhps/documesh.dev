# Documesh API Authentication

Documesh uses an open API model — no authentication required for read-only access.

## Discover

The Documesh API is public. No API keys, tokens, or authentication are needed for any GET endpoint.

## Pick a method

| Method | When to use |
|--------|-------------|
| anonymous | All GET endpoints (/search, /explain, /vendors, /health) — no auth needed |
| service_auth | Future write operations (vendor submission API) — not yet implemented |

## Register

No registration required. The API is fully open for read access.

## Claim

No claims or tokens needed. All data is publicly accessible.

## Exchange

N/A — no token exchange required for read-only access.

## Use the access_token

N/A — no access tokens required. Simply call any GET endpoint directly:

```bash
curl "https://documesh.selatan.org/search?q=edge+functions"
```

## Errors

| Status | Meaning |
|--------|---------|
| 400 | Missing or invalid parameter |
| 404 | Resource not found (see response body for suggestions) |
| 429 | Rate limited (100 req/hour) — check X-RateLimit-Remaining header |
| 500 | Internal server error |

All errors return JSON: `{ "error": { "code": "...", "message": "...", "status": N } }`

## Revocation

N/A — no credentials to revoke. The API is fully open for read-only access.
