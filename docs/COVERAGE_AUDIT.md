# Vendor Coverage Audit — Have vs Available

**Date:** 2026-09-02 · **Live D1:** 29,153 chunks / 26.9 MB across 47 vendors
**"Available (est.)"** = estimated size of each vendor's full public docs corpus
(official llms.txt link counts, sitemap pages, or docs-repo .md file counts — rounded, from
ingestion probes and docs-site observation on 2026-09-02). Estimates, not exact counts.

## Coverage table

| Vendor | Have (chunks) | Available (est.) | Coverage | Gap note |
|---|---:|---:|---:|---|
| Cloudflare | 7,574 | ~40,000 | ~19% | 40+ products; we ingest ~15 deeply |
| Netlify | 1,521 | ~1,800 | ~85% | near-complete |
| Node.js | 4,682 | ~5,000 | ~94% | full API reference |
| Vercel | 719 | ~2,500 | ~29% | docs are large; we cap at 60 pages |
| Kubernetes | 128 | ~4,500 | ~3% | intentional: 12 hand-picked high-value topics |
| Bun | 60 | ~350 | ~17% | compact docs, partial |
| ElysiaJS | 123 | ~150 | ~82% | compact docs |
| Turso | 301 | ~600 | ~50% | core + cloud docs |
| Upstash | 61 | ~700 | ~9% | many SDK/product docs |
| Sentry | 131 | ~1,500 | ~9% | huge multi-SDK platform |
| Stripe | 416 | ~3,500 | ~12% | API reference alone is massive |
| Hono | 284 | ~300 | ~95% | compact docs |
| Nuxt | 64 | ~1,200 | ~5% | just restored; big framework |
| SolidJS | 62 | ~400 | ~16% | restored |
| OpenTelemetry | 73 | ~2,000 | ~4% | enormous spec+docs |
| Argo CD | 94 | ~700 | ~13% | |
| Helm | 188 | ~800 | ~24% | |
| Flux CD | 322 | ~600 | ~54% | |
| Cilium | 176 | ~1,100 | ~16% | |
| React | 1,094 | ~1,600 | ~68% | react.dev guides+reference |
| PyTorch | 16 | ~6,000 | <1% | tutorials only; full API is huge |
| TensorFlow | 650 | ~5,000 | ~13% | python API slice |
| LangChain | 175 | ~2,500 | ~7% | python core slice |
| Playwright | 836 | ~900 | ~93% | near-complete |
| ClickHouse | 159 | ~2,500 | ~6% | reference is massive |
| Ollama | 8 | ~80 | ~10% | effectively placeholder |
| Electron | 1,030 | ~1,200 | ~86% | near-complete |
| Hugo | 72 | ~900 | ~8% | |
| Docusaurus | 44 | ~400 | ~11% | |
| pytest | 115 | ~350 | ~33% | core usage |
| Godot | 2,418 | ~3,000 | ~81% | excellent |
| Neovim | 621 | ~700 | ~89% | user manual |
| Terragrunt | 97 | ~450 | ~22% | |
| Docker (Moby) | 74 | ~1,800 | ~4% | docker docs live outside moby repo |
| Elasticsearch | 379 | ~4,000 | ~9% | reference is massive |
| Svelte | 1,559 | ~1,700 | ~92% | near-complete |
| Vue | 121 | ~1,500 | ~8% | changelog-heavy slice |
| Gitea | 102 | ~800 | ~13% | |
| **AWS** | **406** | **~45,000** | **<1%** | **biggest absolute gap — biggest opportunity** |
| DigitalOcean | 293 | ~4,000 | ~7% | 4,000+ tutorials |
| IBM Cloud | 199 | ~10,000 | ~2% | huge catalog |
| Anthropic | 316 | ~700 | ~45% | API + core guides |
| Neon | 246 | ~500 | ~49% | |
| Clerk | 500 | ~900 | ~56% | |
| Pulumi | 34 | ~2,000 | ~2% | most llms.txt links 404'd as .md |
| Temporal | 105 | ~800 | ~13% | |

## Rollup

| Coverage band | Vendors | Chunk share |
|---|---:|---:|
| ≥80% (near-complete) | 9 | 62% of chunks |
| 40–79% (solid core) | 7 | 12% |
| 10–39% (partial) | 16 | 20% |
| <10% (sample) | 15 | 6% |
| **Total** | **47** | 29,153 chunks / 26.9 MB |

## Top depth opportunities (by absolute gap × demand)

| Priority | Vendor | Have → Realistic target | Effort |
|---|---|---|---:|
| 1 | AWS | 406 → ~5,000 (top 20 services) | med — per-service llms.txt crawl, raise MAX_PAGES |
| 2 | Stripe | 416 → ~1,500 (api.md + guides) | low — docs.stripe.com serves .md natively |
| 3 | Kubernetes | 128 → ~800 (add workloads, networking, storage topics) | low — same git crawler, more topics |
| 4 | PyTorch | 16 → ~800 (pytorch/tutorials repo) | low — separate tutorials repo exists |
| 5 | OpenTelemetry | 73 → ~600 (docs-m + spec repos) | med |
| 6 | DigitalOcean | 293 → ~1,500 (curate products, drop release-notes) | low |
| 7 | Pulumi | 34 → ~600 (docs/ subtree instead of root llms.txt) | low — fix link filter |
| 8 | Ollama | 8 → ~80 (full docs/ dir) | trivial |
| 9 | Vercel | 719 → ~1,500 (raise cap 60→150) | trivial |
| 10 | IBM Cloud | 199 → ~1,000 (prioritize popular services) | med |

## Notes

- Est. counts include only *ingestible* pages (markdown-permitted), not marketing/blog/404s.
- "Available" for llms.txt agent-permitted vendors assumes their llms.txt is the ingestion
  source; for git-hosted vendors it's the repo's docs/ .md count.
- Cloudflare intentionally capped: 7.5k chunks covers Workers/Pages/Hyperdrive/Queues well;
  the remaining ~80% is Zero Trust, R2 internals, partner docs — low query demand.
- Kubernetes gap is *by design* (12 curated topics chosen for eval coverage, not breadth).
- The 9 "near-complete" vendors are why the mesh already answers most common queries well —
  depth work should chase the long tail (AWS/Stripe/K8s) where agents currently strike out.
