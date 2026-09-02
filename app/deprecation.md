# Documesh API Versioning & Deprecation Policy

**Status:** active · **Current version:** `v1` · **Stable since:** 2026-09-01
**Machine-readable copy:** [`/openapi.json`](https://documesh.selatan.org/openapi.json) → `x-api-versioning`

## Versioning strategy

- **URL path versioning.** All endpoints are available under `/v1/...`
  (e.g. `/v1/search`, `/v1/explain`, `/v1/vendors`).
- **Unversioned paths are live aliases** of the current version (`/search` ≡
  `/v1/search`). They are not deprecated — they are a permanent convenience and
  are supported through at least **2027-09-01**.
- New breaking versions ship under a **new path prefix** (`/v2/...`). The
  previous prefix keeps serving, unchanged, through its sunset date.

## What counts as breaking

- Removing or renaming a response field
- Changing a field's type or meaning
- Removing an endpoint or query parameter
- Changing authentication requirements

## What is NOT breaking (may change without notice inside a version)

- Adding new response fields (including the additive `source` field and
  `sources` response key)
- Adding new endpoints, query parameters, or vendors to the mesh
- Relevance/ranking improvements
- Bug fixes

## Deprecation signaling

When an endpoint, field, or version is deprecated, responses carry:

| Header | Meaning |
|---|---|
| `Deprecation: @<unix-ts>` or `Deprecation: true` (draft-ietf-httpapi-deprecation-header) | Present from the day the deprecation is decided |
| `Sunset: <HTTP-date>` (RFC 8594) | Present once a removal date is committed — **always at least 90 days out** |
| `Link: <...>; rel="sunset"` (optional) | Points to this policy / the changelog entry |

Both header names are declared in `Access-Control-Expose-Headers` on every
response, so browser and agent clients can read them mechanically.

**Current deprecations:** none. `vendor` as a response-field alias for `source`
is deprecated in naming only (same value, both always returned; no removal date).

## Removal rules

- No endpoint, field, or version is ever removed silently.
- Minimum 90 days between `Sunset` publication and actual removal.
- After sunset, removed paths return `410 Gone` with a JSON error envelope
  (same shape as all Documesh errors) pointing at the replacement.

## Changelog

- **2026-09-01** — `v1` declared stable. `/v1` prefixes added for all endpoints;
  unversioned paths kept as permanent aliases. No deprecations.
