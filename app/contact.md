# Contact Documesh

Documesh is a federated developer documentation search engine that indexes official, openly licensed documentation from 38 software sources — Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry, and more — and serves it to AI agents and human developers through a REST API, an MCP server, and a WebMCP-powered web app.

## Getting in touch

- **General inquiries:** rhps@selatan.org — we aim to reply within 2 business days.
- **Documentation corrections:** if you spot an error in a doc section we serve, email us with the `chunk_id` and `source_url` from the API response and we will investigate against the upstream source.
- **Source inclusion requests:** to propose adding a documentation source to the mesh, include the source name, docs origin URL, and its license. We only ingest official agent interfaces (llms.txt-permitted sources) or open-licensed repositories — we never scrape. Use the API path `POST /v1/submit-vendors` for programmatic submission (async-job pattern; you receive a `job_id` to poll).
- **Security reports:** responsible disclosure welcome at rhps@selatan.org; please allow 90 days before public disclosure.
- **Privacy requests:** see the [privacy policy](https://documesh.selatan.org/privacy.html) for data practices, and the [about page](https://documesh.selatan.org/about.html) for project background.

## Project links

- **Live service:** https://documesh.selatan.org
- **Source code:** https://github.com/rhps/documesh.dev (MIT licensed)
- **API contract:** https://documesh.selatan.org/openapi.json
- **Developer portal:** https://documesh.selatan.org/developers.html
- **Coverage & licensing:** https://documesh.selatan.org/coverage.html

Documesh is maintained by the selatan.org organization and runs on Cloudflare's global network. There is no phone support; email is the fastest channel. When reporting an issue, include the endpoint, request parameters, and full response — it lets us reproduce in one pass.
