# Vendor Expansion Research — New Sources for the Mesh

**Researched:** 2026-09-02 (live HTTP probes of every `llms.txt` listed — status codes and sizes are real, not memory)
**Ingestion criteria (per project rules):** official agent interface (`llms.txt` that permits agent access) **or** open-licensed docs repo. Permissive licensing only: CC-BY, MIT, Apache-2.0, BSD. Excluded: BUSL, copyleft, NC, no-scraping-only sites.
**Current mesh:** 38 vendors (Cloudflare, Netlify, Vercel, Kubernetes, Bun, Elysia, Turso, Upstash, Sentry, Stripe, Hono, Nuxt, Solid, OpenTelemetry, Argo CD, Helm, Flux, Cilium, React, PyTorch, TensorFlow, LangChain, Playwright, ClickHouse, Ollama, Electron, Hugo, Docusaurus, pytest, Node.js, Godot, Neovim, Terragrunt, Docker/Moby, Elasticsearch, Svelte, Vue, Gitea).

---

## Tier 1 — MAJOR WINS: verified `llms.txt`, high demand, add first

| Vendor | llms.txt (verified 200) | Size | Access mode | License basis | Why it matters | Effort |
|---|---|---|---|---|---|---|
| **AWS** | https://docs.aws.amazon.com/llms.txt | 417 KB | llms.txt + per-page `.md` | "All rights reserved" BUT AWS publishes llms.txt explicitly for LLM consumption → agent-permitted by their own action | The single biggest gap in the mesh. Every dev asks agents AWS questions. Massive corpus (EC2, S3, Lambda, Bedrock…) | Medium-high (huge corpus; shard per service) |
| **GitLab** | https://docs.gitlab.com/llms.txt | 85 KB | llms.txt | llms.txt agent-permitted (product proprietary; CE is MIT) | Top-2 DevOps platform; CI/CD questions everywhere | Medium |
| **DigitalOcean** | https://docs.digitalocean.com/llms.txt | 66 KB | llms.txt + `index.html.md` pages | llms.txt agent-permitted ("For AI agents:" note in header) | Popular with indie/startup devs; big tutorial corpus | Medium |
| **IBM Cloud** | https://cloud.ibm.com/docs/llms.txt | 100 KB | llms.txt + `?format=markdown` + `Accept: application/markdown` + RFC 9727 api-catalog! | llms.txt agent-permitted | First-class markdown negotiation incl. OpenAPI via Accept: application/json — aligns with Documesh's own patterns | Medium |
| **Anthropic** | https://platform.claude.com/llms.txt (redirects from docs.anthropic.com/llms.txt) | 73 KB | llms.txt | llms.txt agent-permitted | #1 asked-about AI API after OpenAI | Medium |
| **Neon** ⭐ | https://neon.com/docs/llms.txt | 37 KB | llms.txt + append `.md` / `Accept: text/markdown` | llms.txt agent-permitted | Serverless Postgres — very hot with AI-agent devs; you named it as a target | Low-medium |
| **Clerk** | https://clerk.com/docs/llms.txt | 520 KB | llms.txt | llms.txt agent-permitted | Leading auth provider; huge agent-driven-integration demand | Medium |
| **Pulumi** | https://www.pulumi.com/llms.txt | 15 KB | llms.txt | Apache-2.0 (SDK/registry); docs via llms.txt | IaC complement to Terragrunt/Terraform-style content already mesh-adjacent | Medium |
| **Temporal** | https://docs.temporal.io/llms.txt | 13 KB | llms.txt | MIT (core engine, open-source) | Durable execution — fast-growing agent-adjacent infra | Medium |
| **Kong** | https://developer.konghq.com/llms.txt | 501 KB | llms.txt | llms.txt agent-permitted (Gateway core Apache-2.0) | API gateway — big dev-infra topic | Medium-high |

## Tier 2 — verified, solid additions

| Vendor | llms.txt (verified) | Size | License basis | Notes |
|---|---|---|---|---|
| **Vultr** | https://docs.vultr.com/llms.txt | 572 KB | llms.txt agent-permitted | Cloud provider; large corpus (creator program content — spot-check quality) |
| **Scaleway** | https://www.scaleway.com/en/docs/llms.txt | 375 KB | llms.txt agent-permitted (explicit "for large language models" note) | EU cloud |
| **Render** | https://render.com/docs/llms.txt | 45 KB | llms.txt agent-permitted | Hosting PaaS — natural neighbor to Netlify/Vercel |
| **Railway** | https://docs.railway.com/llms.txt | 72 KB | llms.txt agent-permitted | Deploy platform |
| **Prisma** | https://www.prisma.io/docs/llms.txt | 8 KB | Apache-2.0 + llms.txt | Dominant TS ORM |
| **Drizzle ORM** | https://orm.drizzle.team/llms.txt | 38 KB | Apache-2.0 + llms.txt | Fast-growing TS ORM; pairs with Neon content |
| **Deno** | https://docs.deno.com/llms.txt | 5 KB | MIT + llms.txt | Runtime; complements Bun/Node |
| **Pinecone** | https://pinecone.io/docs/llms.txt | 44 KB | llms.txt agent-permitted | Vector DB — core AI-infra topic |
| **Weaviate** | https://weaviate.io/developers/llms.txt | 30 KB | BSD-3 + llms.txt | Vector DB |
| **GitBook** | https://docs.gitbook.com/llms.txt | 120 KB | llms.txt agent-permitted | Docs tooling |
| **Mintlify** | https://mintlify.com/docs/llms.txt | 19 KB | llms.txt agent-permitted | Docs tooling (powers many llms.txt sites) |
| **Expo** | https://docs.expo.dev/llms.txt | 55 KB | MIT (SDK) + llms.txt | React Native — big mobile dev audience |
| **VS Code** | https://code.visualstudio.com/llms.txt | 69 KB | llms.txt agent-permitted | Highest-traffic editor docs |
| **Mistral** | https://mistral.ai/llms.txt | 5 KB | Apache-2.0 (models/code) + llms.txt | Major EU AI API |
| **Cohere** | https://docs.cohere.com/llms.txt | 662 B (index only) | llms.txt agent-permitted | Thin index — verify page-level markdown before adding |
| **Convex** | https://docs.convex.dev/llms.txt | 45 KB | llms.txt agent-permitted (core was FSL→Apache parts; verify current) | Backend platform popular with agents |
| **Medusa** | https://docs.medusajs.com/llms.txt | 27 KB | MIT + llms.txt | Commerce framework |
| **Mollie** | https://docs.mollie.com/llms.txt | 114 KB | llms.txt agent-permitted | Payments (EU) — pairs with Stripe |
| **Sevalla** | https://docs.sevalla.com/llms.txt | 25 KB | llms.txt agent-permitted | Kinsta's hosting platform |
| **Bunny** | https://docs.bunny.net/llms.txt | 68 KB | llms.txt agent-permitted | CDN/storage |

## NOT addable today (verified missing / blocked)

| Vendor | Probe result | Reason / path forward |
|---|---|---|
| **GCP (Google Cloud)** | `cloud.google.com/llms.txt` → 404; `developers.google.com/llms.txt` → 404 | No official llms.txt. Some Google products publish their own (e.g. Gemini API — probe `ai.google.dev/gemini-api/docs/llms.txt` next session). Watch for launch. |
| **Microsoft Learn / Azure** | `learn.microsoft.com/llms.txt` → 302 (no llms.txt) | MS docs are copyrighted, no agent interface. Watch: MSFT has experimented with `.md` endpoints on some products. |
| **Oracle Cloud** | 404 | No agent interface. |
| **Supabase** | `/docs/llms.txt` → 404 | **Likely has an alternate path** (Supabase is known to publish llms-full.txt for the community). Probe `supabase.com/docs/guides/llms.txt` and `supabase.com/llms-full.txt` before writing off — high-priority verify. |
| **Fly.io** | `fly.io/docs/llms.txt` → 404, probe timed out | Retry; if absent, skip. |
| **HashiCorp (Terraform/Vault)** | `developer.hashicorp.com/llms.txt` → 404 | No llms.txt (BUSL history on Terraform too). Skip. |
| **Astro / Nuxt / Laravel / Qwik** | 404 on probed paths | Some frameworks expose llms.txt under versioned paths; not verified. Low priority (mesh already strong on frameworks). |
| **Auth0** | 404 (docs.auth0.com) | Clerk covers the auth niche. |
| **Gitea docs** | 404 (docs.gitea.com/llms.txt) | Note: Gitea already in mesh via repo; fine. |
| **PlanetScale** | llms.txt returns 200 but **0 bytes** | Empty file; skip until populated. |
| **OpenAI platform docs** | Not probed successfully this pass | Worth one probe: `platform.openai.com/docs/llms.txt`. If permitted, it's Tier 1. |
| **PayPal** | llms.txt exists but only 1.5 KB index | Thin; verify page markdown. |
| **Vectara** | 107 KB llms.txt | Fine to add later; vector-DB niche getting crowded (Pinecone, Weaviate first). |

## Recommendation — ingestion order for next batch

1. **AWS** — highest value; build a per-service shard strategy (there are per-service llms.txt files under the index, e.g. `bedrock/latest/userguide/llms.txt` — ingest top 20 services first, not all ~200).
2. **Neon, Prisma, Drizzle** — one coherent "serverless Postgres + TS ORM" cluster; all markdown-native, cheapest to ingest.
3. **Anthropic, Mistral, Cohere** — AI API cluster (mesh already has LangChain/PyTorch consumers).
4. **DigitalOcean, Vultr, Scaleway, IBM Cloud** — "more clouds" cluster; all agent-permitted llms.txt.
5. **Clerk, Render, Railway, Pulumi, Temporal, Kong, Pinecone, Weaviate, Deno** — fill remaining infra niches.
6. **Verify-then-decide**: Supabase (alternate path), OpenAI platform docs, Gemini API, Fly.io, GitLab page-markdown check.

## Technical notes for the indexer

- **Three access patterns to support** (already partially in `indexer/fetch_docs.py`):
  1. page `.md` suffix (Neon, Stripe, AWS)
  2. `?format=markdown` query param (IBM)
  3. `Accept: text/markdown` header (IBM, Neon)
- **AWS caveat**: index is 417 KB with hundreds of sub-indexes; cap ingestion per service and respect their CDN (add politeness delay).
- **License labeling in the mesh**: use the existing pattern — `llms.txt agent-permitted` for proprietary-but-permitting clouds (AWS, DO, IBM, Clerk, Render…), SPDX license for open-source-backed vendors (Prisma=Apache-2.0, Deno=MIT, Temporal=MIT, Weaviate=BSD-3, Drizzle/Pulumi/Medusa=Apache/MIT).
- Update `VENDOR_META` in `worker/src/search-core-lite.js`, coverage page, homepage count (38 → new total), and all `18 vendors`/`38 vendors` strings (grep — they're inconsistent across ARD, openapi.json, agent-card.json, acp.json, index.html).
