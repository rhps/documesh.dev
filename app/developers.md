# Documesh API Docs: Developer Portal

Everything you need to integrate Documesh into your application or agent. The API is fully open for read-only access, so there is nothing to sign up for and no keys to manage. This page is the markdown twin of https://documesh.selatan.org/developers.html.

## Quickstart

Search documentation with a single HTTP request:

```bash
curl "https://documesh.selatan.org/search?q=edge+functions+env+vars"
```

Every match comes back ranked, with its source, version, license, and a canonical URL pointing at the original docs.

## Authentication

There is none. The API is completely open for read-only use: no API keys, no tokens, no registration. Rate limits still apply (100 requests per hour per IP) and are declared in the `RateLimit-*` response headers. See the [auth docs](https://documesh.selatan.org/auth.md) and the [versioning & deprecation policy](https://documesh.selatan.org/deprecation.md) for the details.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/search?q=&sources=&limit=&cursor= | Federated documentation search (cursor pagination) |
| POST | /search | JSON-body search; safe retries via Idempotency-Key header |
| POST | /batch | Up to 20 searches in one request (Idempotency-Key required) |
| GET | /v1/explain?error=&source= | Error or log excerpt → closest documentation sections |
| GET | /v1/vendors | Source registry with licenses |
| POST | /v1/submit-sources | Async submission → 202 + job_id (poll GET /v1/jobs/{job_id}) |
| GET/POST | /ask | NLWeb query; SSE streaming via prefer.streaming or Accept: text/event-stream |
| POST | /mcp | MCP Streamable HTTP (JSON-RPC 2.0); GET /mcp for SSE |
| GET | /health | Service health |

### Example response

```
{
  "query": "edge functions env vars",
  "results": [{
    "source": "netlify",
    "version": "latest",
    "title": "Environment variables at Netlify",
    "heading_path": "Build > Environment variables > Overview",
    "source_url": "https://docs.netlify.com/build/environment-variables/overview/",
    "license": "Netlify Docs (llms.txt agent-permitted)",
    "last_updated": "2026-08-30",
    "score": 274.66
  }],
  "took_ms": 12
}
```

## Agent Mode

Add `?mode=agent` to the root URL and you get a machine-readable view of all capabilities, endpoints, and sources instead of the marketing page.

```bash
curl "https://documesh.selatan.org/?mode=agent"
```

## Testing Against the Live API

Documesh is read-only, free, and open, so the live service doubles as its own sandbox. There are no destructive operations and no production data to put at risk, which is why there is no separate test host.

```bash
curl "https://documesh.selatan.org/search?q=test+query"
```

## SDKs & CLI

The official SDK and CLI ship together as one package:

```bash
npm install documesh
```

See [documesh on npm](https://www.npmjs.com/package/documesh). Prefer a different language? The API is plain REST, so it works with any HTTP client, and you can use the [OpenAPI spec](https://documesh.selatan.org/openapi.json) with [openapi-generator](https://openapi-generator.tech/) to produce a client for whatever you use.

## Rate Limits

100 requests per hour per IP on the free tier. Every response includes IETF rate limit headers (`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`) so clients can pace themselves without guessing.

## Versioning policy

URL path versioning (`/v1/`). Breaking changes ship under a new `/vN` prefix, and deprecated routes return `Deprecation` and `Sunset` (RFC 8594) headers at least 90 days before removal. Unversioned paths stay as live aliases of `/v1`. Full details: [versioning & deprecation policy](https://documesh.selatan.org/deprecation.md).

## Errors

All API paths return structured JSON errors: `{"error": {"code", "message", "status", "resolution"}}`.

## WebMCP Tools

When a Documesh page is open in a WebMCP-compatible browser, its tools are available through `document.modelContext.registerTool()`. The [tool reference](https://documesh.selatan.org/webmcp.html) covers the full inputSchema and examples.

## More

- OpenAPI contract: https://documesh.selatan.org/openapi.json
- Auth guide: https://documesh.selatan.org/auth.md
- Source repository: https://github.com/rhps/documesh.dev (MIT), including [AGENTS.md](https://github.com/rhps/documesh.dev/blob/main/AGENTS.md) for AI coding agents
- Contact: https://documesh.selatan.org/contact.html
