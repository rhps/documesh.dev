/**
 * Docs Mesh API — Cloudflare Worker with lazy vendor-shard loading.
 * Each vendor's index is a gzipped JSON file in app/shards/ (static asset).
 * Worker loads only the shards needed per query — fits free-tier memory.
 */
import { loadIndex, search, explainError, VENDORS } from "./search-core.js";

// Registry — derived from actual shard files present
const VENDOR_IDS = [
  "argocd","bun","cilium","cloudflare","elasticsearch","electron","elysia","flux",
  "gitea","godot","helm","hono","hugo","kubernetes","moby","neovim","netlify",
  "nodejs","nuxt","ollama","opentelemetry","playwright","pytest","pytorch",
  "react","sentry","solid","stripe","tensorflow","terragrunt","turso",
  "upstash","vercel","vue-core-docs",
];

const VENDOR_META = {
  cloudflare: { name: "Cloudflare", license: "CC-BY-4.0", docs_origin: "llms.txt + .md" },
  netlify: { name: "Netlify", license: "llms.txt agent-permitted", docs_origin: "llms.txt" },
  vercel: { name: "Vercel", license: "llms.txt agent-permitted", docs_origin: "llms.txt + sitemap.md" },
  kubernetes: { name: "Kubernetes", license: "CC-BY-4.0", docs_origin: "git release branches" },
  bun: { name: "Bun", license: "MIT", docs_origin: "llms.txt" },
  elysia: { name: "ElysiaJS", license: "MIT", docs_origin: "llms.txt" },
  turso: { name: "Turso", license: "llms.txt agent-permitted", docs_origin: "llms.txt" },
  upstash: { name: "Upstash", license: "llms.txt agent-permitted", docs_origin: "llms.txt" },
  sentry: { name: "Sentry", license: "llms.txt agent-permitted", docs_origin: "llms.txt" },
  stripe: { name: "Stripe", license: "llms.txt agent-permitted", docs_origin: "llms.txt" },
  hono: { name: "Hono", license: "MIT", docs_origin: "llms.txt" },
  nuxt: { name: "Nuxt", license: "MIT", docs_origin: "llms.txt" },
  solid: { name: "SolidJS", license: "MIT", docs_origin: "llms.txt" },
  opentelemetry: { name: "OpenTelemetry", license: "CC-BY-4.0", docs_origin: "llms.txt" },
  argocd: { name: "Argo CD", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  helm: { name: "Helm", license: "Apache-2.0", docs_origin: "helm-www git-hosted docs" },
  flux: { name: "Flux CD", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  cilium: { name: "Cilium", license: "Apache-2.0", docs_origin: "Documentation/ RST→md" },
  react: { name: "React", license: "MIT", docs_origin: "reactjs/react.dev git-hosted docs" },
  pytorch: { name: "PyTorch", license: "BSD-style", docs_origin: "pytorch/pytorch git-hosted docs" },
  tensorflow: { name: "TensorFlow", license: "Apache-2.0", docs_origin: "tensorflow/docs git-hosted docs" },
  langchain: { name: "LangChain", license: "MIT", docs_origin: "langchain-ai git-hosted docs" },
  playwright: { name: "Playwright", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  clickhouse: { name: "ClickHouse", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  ollama: { name: "Ollama", license: "MIT", docs_origin: "git-hosted docs" },
  electron: { name: "Electron", license: "MIT", docs_origin: "git-hosted docs" },
  hugo: { name: "Hugo", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  docusaurus: { name: "Docusaurus", license: "MIT", docs_origin: "git-hosted docs" },
  pytest: { name: "pytest", license: "MIT", docs_origin: "git-hosted docs" },
  nodejs: { name: "Node.js", license: "MIT", docs_origin: "nodejs/node git-hosted docs" },
  "godot-docs": { name: "Godot", license: "MIT", docs_origin: "godot-docs git-hosted docs" },
  neovim: { name: "Neovim", license: "Apache-2.0", docs_origin: "neovim/neovim git-hosted docs" },
  terragrunt: { name: "Terragrunt", license: "MIT", docs_origin: "gruntwork-io/terragrunt git-hosted docs" },
  moby: { name: "Docker (Moby)", license: "Apache-2.0", docs_origin: "moby/moby git-hosted docs" },
  elasticsearch: { name: "Elasticsearch", license: "Apache-2.0", docs_origin: "elastic/elasticsearch git-hosted docs" },
  "svelte-core": { name: "Svelte", license: "MIT", docs_origin: "sveltejs/svelte git-hosted docs" },
  "vue-core-docs": { name: "Vue (core)", license: "MIT", docs_origin: "vuejs/core git-hosted docs" },
  gitea: { name: "Gitea", license: "MIT", docs_origin: "go-gitea/gitea git-hosted docs" },
};

// Per-vendor shard cache (lazy, isolate-level)
const shardCache = {};
const shardPromises = {};

/**
 * Load a single vendor shard via ASSETS binding.
 * Shards are raw JSON files at /shards/index_<vendor>.json
 */
async function getShard(vendor) {
  if (shardCache[vendor]) return shardCache[vendor];
  if (shardPromises[vendor]) return shardPromises[vendor];

  shardPromises[vendor] = (async () => {
    try {
      const res = await fetch(`https://internal/shards/index_${vendor}.json`);
      if (!res.ok) return null;
      const data = await res.json();
      const idx = {
        docs: data.docs.map(d => ({ ...d })),
        postings: data.postings,
        builtAt: data.built_at || "2026-08-30",
      };
      shardCache[vendor] = idx;
      return idx;
    } catch (e) {
      console.error(`shard load failed: ${vendor}`, e);
      return null;
    }
  })();
  return shardPromises[vendor];
}

/** Search across loaded vendors. Loads shards lazily for queried vendors. */
function searchInIndex(index, query, opts = {}) {
  const { vendors, limit = 5 } = opts;
  const toks = tokenize(query);
  if (!toks.length) return [];

  const scores = new Map();
  for (const tok of toks) {
    const pl = index.postings[tok];
    if (!pl) continue;
    for (const [docIdx, w] of pl) {
      scores.set(docIdx, (scores.get(docIdx) || 0) + w);
    }
  }

  let results = [];
  for (const [docIdx, score] of scores) {
    const d = index.docs[docIdx];
    if (vendors && vendors.length && !vendors.includes(d.vendor)) continue;
    const docToks = new Set(tokenize(d.title + " " + d.heading_path));
    let covered = 0;
    for (const t of toks) if (docToks.has(t)) covered++;
    results.push({
      chunk_id: d.chunk_id, vendor: d.vendor, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated,
      score: +(score * (1 + covered / toks.length)).toFixed(4),
    });
  }
  results.sort((a, b) => b.score - a.score);
  return results.slice(0, limit);
}

function tokenize(text) {
  const STOP = new Set("a an and are as at be by for from has have how in is it its of on or that the to was what when where which who why will with".split(" "));
  return (text.toLowerCase().match(/[a-z0-9]{2,}/g) || []).filter((t) => !STOP.has(t));
}

function extractSignatures(logExcerpt) {
  const sig = [];
  const patterns = [
    /([A-Z][a-zA-Z]+Exception)/g,
    /(CrashLoopBackOff|ImagePullBackOff|OOMKilled|ErrImagePull)/g,
    /(ECONNREFUSED|EACCES|ENOENT|ETIMEDOUT|EADDRINUSE|EPERM)/g,
    /(Error|error|ERROR):?\s+([a-zA-Z0-9 :'.\-_/]{10,90})/g,
  ];
  for (const p of patterns) {
    let m;
    while ((m = p.exec(logExcerpt)) !== null) {
      sig.push(m[0].length > 60 ? m[0].slice(0, 60) : m[0]);
    }
  }
  return sig;
}

export function buildVendorsResponse() {
  return VENDOR_IDS.map(id => ({
    id,
    ...(VENDOR_META[id] || {}),
    attribution_required: true,
  }));
}

export { shardCache, VENDOR_IDS, VENDOR_META, searchInIndex, extractSignatures, tokenize };
