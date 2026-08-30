# Documesh 🕸

**Documentation that agents can not only read, but operate.**

Documesh is an agent-native web app that federates developer documentation from
**Cloudflare**, **Netlify**, **Vercel**, and **Kubernetes** into a single
version-cited, agent-operable interface built on [WebMCP](https://webmachinelearning.github.io/webmcp/).

Built for [The WebMCP Challenge](https://webmcp.devpost.com/) (Sep 2026).

## Why

Every dev already "chats with docs" via brittle scraped RAG — version-blind,
unattributed, each AI vendor crawling separately. Documesh turns docs into a
**declared, versioned, opt-in interface**: agents get structured tools; humans
see the same cited sources on screen (agent co-presence).

## WebMCP Tools

Registered via `document.modelContext.registerTool()` in `app/index.html`:

| Tool | Kind | What it does |
|------|------|--------------|
| `search_docs_across` | answer | Federated search across all vendors; every result carries vendor, version, license, canonical URL, last-updated |
| `explain_error` | answer | Paste a log excerpt → closest matching doc sections (top-3, cross-vendor) + honest disclaimer |
| `list_vendors` | answer | Vendors in the mesh with license + attribution requirements |

## Architecture

```
Browser (ChatGPT in-app browser / Chrome 149+ with WebMCP flag)
  └─ Web app (static) — registers WebMCP tools, chat UI + cited source viewer
        └─ CF Worker API — /search /explain /vendors /page (TF-IDF over prebuilt index)
              └─ Build-time indexer (Python) — pulls official markdown:
                   · developers.cloudflare.com llms.txt + .md endpoints (CC-BY-4.0)
                   · docs.netlify.com llms.txt + .md endpoints (agent-permitted)
                   · vercel.com/docs sitemap.md + llms.txt (agent-permitted)
                   · kubernetes/website GitHub release branches (CC-BY-4.0)
```

**No scraping.** Every source is an official vendor-published machine interface
(llms.txt / .md endpoints) or an open-licensed git repository. Terraform docs
were deliberately excluded (BUSL license) — the mesh is license-aware by design.

## Attribution (required by our sources)

- Cloudflare docs: © Cloudflare, Inc., [CC BY 4.0](https://github.com/cloudflare/cloudflare-docs/blob/production/LICENSE)
- Kubernetes docs: © The Kubernetes Authors, [CC BY 4.0](https://github.com/kubernetes/website/blob/main/LICENSE)
- Netlify docs: © Netlify, Inc. — consumed via their official [llms.txt](https://docs.netlify.com/llms.txt) agent interface
- Vercel docs: © Vercel, Inc. — consumed via their official [llms.txt](https://vercel.com/docs/llms.txt) agent interface
- Bun: MIT — via [bun.com/docs/llms.txt](https://bun.com/docs/llms.txt)
- ElysiaJS: MIT — via [elysiajs.com/llms.txt](https://elysiajs.com/llms.txt)
- Hono: MIT — via [hono.dev/llms.txt](https://hono.dev/llms.txt)
- Nuxt: MIT — via [nuxt.com/llms.txt](https://nuxt.com/llms.txt)
- SolidJS: MIT — via [docs.solidjs.com/llms.txt](https://docs.solidjs.com/llms.txt)
- Sentry docs: © Sentry — via [docs.sentry.io/llms.txt](https://docs.sentry.io/llms.txt)
- Stripe docs: © Stripe — via [docs.stripe.com/llms.txt](https://docs.stripe.com/llms.txt)
- Turso docs: © Turso — via [docs.turso.tech/llms.txt](https://docs.turso.tech/llms.txt)
- Upstash docs: © Upstash — via [docs.upstash.com/llms.txt](https://docs.upstash.com/llms.txt)
- OpenTelemetry docs: © OpenTelemetry contributors, [CC BY 4.0](https://github.com/open-telemetry/opentelemetry.io/blob/main/LICENSE) — via official llms.txt
- Argo CD docs: © Argo CD contributors, [Apache-2.0](https://github.com/argoproj/argo-cd/blob/master/LICENSE) — via git-hosted docs

All tool responses and UI cards display the source license + canonical link back
to the vendor's page.

**Deliberately excluded for legal reasons:** Terraform/HashiCorp (BUSL — no clear
third-party republication right), Grafana (AGPL copyleft), Shopify/Render (no
public doc repos or agent interfaces), Mayo/CDC/NIH (bot-blocked + copyrighted).

## Run locally

```bash
# 1. Build the index (fetches official docs, ~2 min)
python3 indexer/fetch_docs.py
python3 indexer/build_index.py
python3 indexer/verify.py

# 2. Start API (port 8787)
node worker/dev-server.mjs

# 3. Serve the app (port 8788)
python3 -m http.server 8788 --directory app

# 4. Open http://localhost:8788 — try:
#    "kubernetes restart policy backoff"
#    or paste an error log for explain_error
```

## Test

```bash
node worker/eval.mjs   # error→docs eval: 5 real-world errors, gate ≥80%
```

## Deploy (Cloudflare)

```bash
npx wrangler deploy   # serves app (static assets) + API from one Worker
```

## Project docs

See `../docs/` for the ideation history: challenge guide, ecosystem research
(322-site WebMCP directory survey), brainstorm, and MVP plan.
