# About Documesh

Documesh is a federated developer documentation search engine. It indexes official, openly licensed documentation from 38 software sources — including Cloudflare, Netlify, Vercel, Kubernetes, Bun, Stripe, Sentry, React, PyTorch, Node.js, Godot, and Neovim — roughly 17,000 indexed sections, and serves it to both human developers and AI agents through one contract.

## Why Documesh exists

Today an AI agent that wants to use your documentation must scrape HTML, guess at structure, and cite whatever blog post ranked first — often the wrong version, often without a source. That is slow, fragile, and blind to licensing. Documesh flips this: the site publishes tools; the agent reads the contract and calls exactly what it needs. Humans keep the visual web; agents get first-class access.

## How it works

- **Ingestion:** every source is ingested via official agent interfaces (llms.txt-permitted origins, `.md` endpoints) or open-licensed git repositories. No scraping, ever. BUSL and strong-copyleft sources are deliberately excluded.
- **Indexing:** content is chunked by heading structure, each chunk carrying source, version, license, attribution, and canonical source URL.
- **Serving:** three WebMCP tools (`search_docs_across`, `explain_error`, `list_vendors`) are registered on the web app via `document.modelContext.registerTool()`, and a REST API plus an MCP server (Streamable HTTP at `/mcp`) expose the same capability to non-browser agents.

## Licensing stance

Coverage is a legal statement, not an accident. CC-BY and MIT sources are ingested; every response names its license and canonical link. See the [coverage page](https://documesh.selatan.org/coverage.html) for the full attribution table.

## Project

Documesh was built for the WebMCP Challenge (Devpost × OpenAI, September 2026). It is MIT-licensed open source at [github.com/rhps/documesh.dev](https://github.com/rhps/documesh.dev), maintained by the selatan.org organization. See the [contact page](https://documesh.selatan.org/contact.html) for how to reach the maintainers, and the [privacy policy](https://documesh.selatan.org/privacy.html) for data practices.
