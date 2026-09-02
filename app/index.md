---
title: Documesh
description: Federated developer documentation search across 47 vendors. Powered by WebMCP.
canonical: https://documesh.selatan.org/
last-updated: 2026-09-01
---

# Documesh

Documentation that agents can not only read, but operate.

Documesh is an application powered by WebMCP — federated developer documentation
from 47 vendors, with version-cited, license-attributed answers.

## Vendors in the mesh

Cloudflare (CC-BY-4.0) · Netlify (llms.txt) · Vercel (llms.txt) · Kubernetes (CC-BY-4.0) ·
Bun (MIT) · ElysiaJS (MIT) · Turso (llms.txt) · Upstash (llms.txt) · Sentry (llms.txt) ·
Stripe (llms.txt) · Hono (MIT) · Nuxt (MIT) · SolidJS (MIT) · OpenTelemetry (CC-BY-4.0) ·
Argo CD (Apache-2.0) · Helm (Apache-2.0) · Flux CD (Apache-2.0) · Cilium (Apache-2.0) ·
React (MIT) · PyTorch (BSD) · TensorFlow (Apache-2.0) · LangChain (MIT) · Playwright (Apache-2.0) ·
ClickHouse (Apache-2.0) · Ollama (MIT) · Electron (MIT) · Hugo (Apache-2.0) · Docusaurus (MIT) ·
pytest (MIT) · Node.js (MIT) · Godot (MIT) · Neovim (Apache-2.0) · Terragrunt (MIT) ·
Moby (Apache-2.0) · Elasticsearch (Apache-2.0) · Svelte (MIT) · Vue (MIT) · Gitea (MIT)

## WebMCP Tools

- `search_docs_across` — federated search across all vendors
- `explain_error` — log excerpt → closest doc sections
- `list_vendors` — vendor registry with licenses

## API

- GET /search?q=&vendors=&limit=
- GET /explain?error=&vendor=
- GET /vendors
- GET /health

Built with ❤️ by [selatan.org](https://selatan.org)
