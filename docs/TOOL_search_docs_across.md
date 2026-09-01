# search_docs_across — Design Reference

**The core WebMCP tool that makes Documesh "agent-operable."**
This is the tool agents discover and call when they need documentation.

---

## 1. What It Does (one sentence)

> Fans a single search query across all vendor documentation shards simultaneously,
> merges results by relevance, and returns them with mandatory provenance
> (license, canonical URL, version, last-updated) on every result.

---

## 2. Tool Contract (what the agent sees)

```json
{
  "name": "search_docs_across",
  "kind": "answer",
  "description": "Search federated developer documentation (Cloudflare, Netlify, Vercel, Kubernetes, Bun, Stripe, Sentry and more). Returns ranked excerpts with version, license, and canonical source URL for every result.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query":   { "type": "string",  "description": "Search query" },
      "vendors": { "type": "array",   "items": { "type": "string" },
                   "description": "Optional vendor filter (e.g. ['cloudflare','kubernetes'])" },
      "limit":   { "type": "number",  "description": "Max results (default 5)" }
    },
    "required": ["query"]
  }
}
```

**Design decisions in the schema:**
- `vendors` is optional → agent can search everything OR narrow to one vendor
- `limit` is optional → sensible default of 5
- `required` is only `query` → lowest friction for agent adoption
- Kind = `answer` (read-only, safe, no confirmation needed)

---

## 3. How It Works Internally

```
Agent calls: search_docs_across({ query: "edge functions env vars" })
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Worker: ensureShards(vendors)                              │
│  ─────────────────────────────                              │
│  For each vendor in the mesh:                               │
│    if shard cached in isolate → use it (0ms)                │
│    else → env.ASSETS.fetch("/shards/index_<v>.json")        │
│           → parse JSON → cache in isolate                   │
│  Result: 32 vendor indices loaded lazily                    │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Worker: searchAcross(loaded, query)                        │
│  ─────────────────────────────                              │
│  1. tokenize(query) → ["edge","functions","env","vars"]     │
│  2. For each vendor shard:                                  │
│       for each token → postings.get(token) → [[docIdx, w]]  │
│       → accumulate scores in a Map (vendor:docIdx → score)  │
│  3. Coverage bonus: +boost if doc title matches more tokens │
│  4. Sort by score descending                                │
│  5. Return top `limit` results                              │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Response to agent                                          │
│  ─────────────────                                          │
│  {                                                          │
│    "query": "edge functions env vars",                      │
│    "snapshot_date": "2026-08-30",                           │
│    "took_ms": 12,                                           │
│    "results": [                                             │
│      {                                                      │
│        "vendor": "netlify",                                 │
│        "version": "latest",                                 │
│        "title": "Environment variables at Netlify",         │
│        "section": "Build > Environment variables",          │
│        "excerpt_link": "https://docs.netlify.com/…",       │
│        "license": "Netlify Docs (llms.txt agent-permitted)",│
│        "last_updated": "2026-08-30",                        │
│        "score": 274.66                                      │
│      },                                                     │
│      …                                                      │
│    ]                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

### Scoring formula
```
score(doc) = Σ(token_weight) × (1 + covered_tokens / total_query_tokens)
```
- `token_weight` = TF-IDF (precomputed at build time, stored in shard postings)
- Coverage bonus rewards docs matching more distinct query terms

---

## 4. What Makes It Special (vs a regular search API)

| Feature | Why it matters for agents |
|---------|--------------------------|
| **Cross-vendor by default** | "Can I run Postgres on Workers with TF DNS?" — no single vendor answers this |
| **Version-cited** | Agent knows it's looking at k8s v1.32 docs, not a 2021 blog post |
| **License-cited** | Agent can tell its user "this is CC-BY-4.0, attribution required" |
| **Deterministic** | Same query → same results (no LLM hallucination in the ranking) |
| **Lazy shard loading** | Worker only loads what's needed; no monolithic bundle |
| **38 vendors, one call** | Agent doesn't need to know which vendor has the answer |

---

## 5. Example Agent Conversations

### Cross-vendor question
```
User: "Can I run Postgres on Cloudflare Workers with Terraform managing DNS?"

Agent calls: search_docs_across({ query: "Postgres on Workers" })
           + search_docs_across({ query: "Terraform DNS provider Cloudflare" })

Agent synthesizes: "Based on Cloudflare docs (Hyperdrive), you can connect to
external Postgres. For DNS, Terraform's Cloudflare provider supports it…
Sources: developers.cloudflare.com/…, registry.terraform.io/…"
```

### Vendor-filtered question
```
User: "How do Netlify edge functions handle environment variables?"

Agent calls: search_docs_across({ query: "edge functions environment variables",
                                  vendors: ["netlify"] })

Agent answers: "Netlify edge functions access env vars via Netlify.env.get()…
Source: docs.netlify.com/build/environment-variables/ (license: llms.txt agent-permitted)"
```

---

## 6. Comparison: Why Not Just Use a Regular Search?

| | Regular search API | `search_docs_across` |
|---|---|---|
| Discovers sources | ❌ caller must know where to search | ✅ agent queries the mesh without knowing vendors |
| Version awareness | ❌ | ✅ every result carries version |
| License transparency | ❌ | ✅ every result carries license |
| Agent integration | needs custom code per API | ✅ WebMCP standard — any agent discovers it |
| Cross-vendor | ❌ per-vendor only | ✅ single call fans out |
| Attribution | ❌ | ✅ structural (enforced by indexer) |

---

## 7. Implementation Files

| File | Role |
|------|------|
| `app/app.html` | WebMCP registration (inputSchema + execute → calls /search) |
| `worker/src/index.js` | HTTP route → ensureShards → searchAcross |
| `worker/src/search-core-lite.js` | VENDOR_META registry (38 vendors) |
| `indexer/fetch_docs.py` | P1 crawlers (Cloudflare, Netlify, K8s) |
| `indexer/enrich_docs.py` | P1/P3 crawlers (Vercel + 6 others) |
| `indexer/foundation_docs.py` | CNCF crawlers (OTel, Argo CD) |
| `indexer/foundation_docs_r2.py` | P4 crawlers (Helm, Flux, Cilium) |
| `indexer/tier_ingestion.py` | Wikipedia tier crawlers (React, PyTorch, etc.) |
| `indexer/batch2_docs.py` | Batch 2 crawlers (TF, React, pytest, Godot, Neovim) |
| `indexer/build_index.py` | Monolithic index builder (local dev / eval) |
| `indexer/build_shards.py` | Per-vendor shard builder (for deploy) |
