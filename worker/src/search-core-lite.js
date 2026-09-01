/**
 * Minimal TF-IDF search core for Documesh Worker.
 * Works on per-vendor shards loaded lazily from static assets.
 */

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
  elasticsearch: { name: "Elasticsearch", license: "Apache-2.0", docs_origin: "git-hosted docs" },
  "svelte-core": { name: "Svelte", license: "MIT", docs_origin: "sveltejs/svelte git-hosted docs" },
  "vue-core-docs": { name: "Vue (core)", license: "MIT", docs_origin: "vuejs/core git-hosted docs" },
  gitea: { name: "Gitea", license: "MIT", docs_origin: "go-gitea/gitea git-hosted docs" },
};

const VENDOR_IDS = Object.keys(VENDOR_META);

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

function searchInShard(index, query, opts = {}) {
  const toks = tokenize(query);
  if (!toks.length) return { results: [] };
  const scores = new Map();
  for (const tok of toks) {
    const pl = index.postings.get(tok);
    if (!pl) continue;
    for (const [docIdx, w] of pl) {
      scores.set(docIdx, (scores.get(docIdx) || 0) + w);
    }
  }
  let results = [];
  for (const [docIdx, score] of scores) {
    const d = index.docs[docIdx];
    if (opts.vendors && opts.vendors.length && !opts.vendors.includes(d.vendor)) continue;
    results.push({
      chunk_id: d.chunk_id, vendor: d.vendor, version: d.version,
      title: d.title, heading_path: d.heading_path, path: d.path,
      source_url: d.source_url, license: d.license, attribution: d.attribution,
      last_updated: d.last_updated, score: +score.toFixed(4),
    });
  }
  results.sort((a, b) => b.score - a.score);
  return { results: results.slice(0, opts.limit || 5) };
}

export { VENDOR_META, VENDOR_IDS, tokenize, extractSignatures, searchInShard };
