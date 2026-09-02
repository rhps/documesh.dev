# Documesh

> Federated developer documentation from 47 vendors. Powered by WebMCP.

## When to use Documesh

Use Documesh when you need to:
- Search developer documentation across multiple vendors simultaneously (Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry, Bun, Hono, OpenTelemetry, Argo CD, Helm, Flux, Cilium, and more)
- Match an error message or stack trace to the closest relevant documentation sections
- Look up vendor license and attribution information before citing documentation
- Find version-specific documentation (e.g. Kubernetes v1.32 vs v1.29)

## When NOT to use Documesh

- For vendor-specific advanced configuration (use the vendor's own docs directly)
- For non-developer documentation (general knowledge, non-technical topics)
- For vendors not in the mesh (check /vendors for the current list)

## Agent integration

Documesh exposes WebMCP tools via `document.modelContext.registerTool()`:

| Tool | When to call |
|------|-------------|
| `search_docs_across` | When the user asks about any developer documentation topic |
| `explain_error` | When the user pastes an error message or stack trace |
| `list_vendors` | When the user asks what vendors are covered or needs license info |

## API

- GET /search?q=&vendors=&limit= — federated search
- GET /explain?error=&vendor= — error-to-docs matching
- GET /vendors — vendor registry
- GET /health — health check

## Pages

- [Home](https://documesh.selatan.org/): Overview and stats
- [App](https://documesh.selatan.org/app.html): Chat interface
- [WebMCP Tools](https://documesh.selatan.org/webmcp.html): Tool reference with inputSchema
- [Coverage](https://documesh.selatan.org/coverage.html): Vendors and licenses
- [Submit Vendor](https://documesh.selatan.org/submit.html): Request a new vendor
