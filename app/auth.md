# Documesh auth.md — Agent Registration & Authentication

auth.md — how AI agents register with and authenticate to the Documesh API.

## TL;DR

Documesh is a **fully open, read-only API**. No API keys, no tokens, no registration. Start calling endpoints immediately. Agents that want a machine-verified identity context can use the anonymous identity flow below.

## Discover

- **Audience:** AI agents and automated developer tools consuming the documentation search API.
- **API surface:** `/search`, `/explain`, `/vendors`, `/health`, `/ask`, `/batch`, `/mcp` — all open.
- **OpenAPI contract:** https://documesh.selatan.org/openapi.json
- **Protected Resource Metadata (RFC 9728):** https://documesh.selatan.org/.well-known/oauth-protected-resource
  - `resource`: https://documesh.selatan.org
  - `authorization_servers`: `[]` (open resource — no authorization server required)
  - `scopes_supported`: `[]`
  - `bearer_methods_supported`: `["header"]`
- **Authorization Server metadata:** https://documesh.selatan.org/.well-known/oauth-authorization-server (issuer matches the resource above)

## Pick a method

| Method | When to use |
|--------|-------------|
| `anonymous` | Everything. All endpoints are open for read-only use — no credentials needed. |
| `service_auth` | Reserved for future write operations (source submission API). Not yet issued; see the async submission endpoint for the current flow. |

## Register

**Complete registration flow (anonymous, self-contained):**

1. **Audience:** any AI agent or automated tool that needs developer documentation search. No approval, allowlist, or human step exists.
2. **Registration endpoint:** `GET https://documesh.selatan.org/agent/identity` — call it to provision an anonymous identity context. It returns immediately with a `subject` (e.g. `anon:4f2a91c3`), `tier: "open"`, and the rate limit.
3. **Method:** `anonymous` — the returned subject is informational; you do not need to present it back on subsequent calls.
4. **Credential use:** none. All API endpoints accept unauthenticated requests. Keep the subject for your own logging/retry accounting if desired.

**Example — register and query in two calls:**

```bash
# Step 1: register (provision anonymous identity)
curl https://documesh.selatan.org/agent/identity
# => {"identity_endpoint":"...","identity_types_supported":["anonymous"],
#     "anonymous":{"subject":"anon:4f2a91c3","tier":"open",
#                 "rate_limit":{"requests_per_minute":100}}}

# Step 2: use the API — no credential header required
curl "https://documesh.selatan.org/v1/search?q=edge+functions"
```

Formal registration discovery is also published in the Authorization Server metadata:

- **`agent_auth.skill`**: `https://documesh.selatan.org/auth.md` (this document)
- **`agent_auth.register_uri`**: `https://documesh.selatan.org/agent/identity`

## Agent identity (optional, anonymous flow)

Agents that want an identity context can call the anonymous identity endpoint:

- **identity_endpoint:** `https://documesh.selatan.org/agent/identity`
- **identity_types_supported:** `["anonymous"]`
- **anonymous.credential_types_supported:** `["none"]`
- **claim_uri:** `https://documesh.selatan.org/agent/identity` — returns an anonymous subject, open tier, and rate-limit info. No credentials needed.
- **claim_endpoint / events_endpoint:** intentionally absent — there are no tokens to claim and no auth events on an open API.

Walkthrough: `GET /.well-known/oauth-protected-resource` → `authorization_servers: []` (open API) → `GET /agent/identity` for the anonymous identity context. API entry-point responses also carry `WWW-Authenticate: Bearer resource_metadata="..."` pointing at the protected-resource metadata.

## Use the access_token

N/A — no access tokens required. Call any endpoint directly:

```bash
curl "https://documesh.selatan.org/v1/search?q=edge+functions"
```

## Errors

| Status | Meaning |
|--------|---------|
| 400 | Missing or invalid parameter |
| 404 | Resource not found (see response body for suggestions) |
| 429 | Rate limited (100 req/min) — check RateLimit-Remaining header |
| 500 | Internal server error |

All errors return JSON: `{ "error": { "code", "message", "status", "resolution" } }`

## Revocation

N/A — no credentials to revoke. The API is fully open for read-only access.
