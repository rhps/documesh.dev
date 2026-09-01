/**
 * Documesh API — shared search logic (framework-free, runs on CF Workers & Node)
 *
 * Search: TF-IDF-weighted token intersection over the prebuilt index.
 * Deterministic; every result carries license + source + last_updated.
 */

export function loadIndex(indexJson) {
  const { docs, postings, built_at } = JSON.parse(indexJson);
  return { docs, postings, builtAt: built_at };
}

function tokenize(text) {
  const STOP = new Set("a an and are as at be by for from has have how in is it its of on or that the to was what when where which who why will with".split(" "));
  return (text.toLowerCase().match(/[a-z0-9]{2,}/g) || []).filter((t) => !STOP.has(t));
}

/**
 * @param {object} index  loaded index
 * @param {string} query  natural language query
 * @param {object} opts   { vendors?: string[], limit?: number }
 */
export function search(index, query, opts = {}) {
  const { vendors, limit = 5 } = opts;
  const toks = tokenize(query);
  if (!toks.length) return { results: [], query, took_ms: 0 };

  const started = Date.now();
  const scores = new Map();
  for (const tok of toks) {
    const pl = index.postings[tok];
    if (!pl) continue;
    for (const [docIdx, w] of pl) {
      scores.set(docIdx, (scores.get(docIdx) || 0) + w);
    }
  }

  // Coverage bonus: reward docs matching more distinct query tokens
  let results = [];
  for (const [docIdx, score] of scores) {
    const d = index.docs[docIdx];
    if (vendors && vendors.length && !vendors.includes(d.vendor)) continue;
    const docToks = new Set(tokenize(d.title + " " + d.heading_path));
    let covered = 0;
    for (const t of toks) if (docToks.has(t)) covered++;
    results.push({
      chunk_id: d.chunk_id,
      vendor: d.vendor,
      version: d.version,
      title: d.title,
      heading_path: d.heading_path,
      path: d.path,
      source_url: d.source_url,
      license: d.license,
      attribution: d.attribution,
      last_updated: d.last_updated,
      score: +(score * (1 + covered / toks.length)).toFixed(4),
    });
  }
  results.sort((a, b) => b.score - a.score);
  results = results.slice(0, limit);
  return { query, results, took_ms: Date.now() - started, snapshot_date: index.builtAt };
}

/** Error-signature extraction: pull likely-identifying tokens from a log line. */
export function errorSignature(logExcerpt) {
  const sig = [];
  const patterns = [
    /([A-Z][a-zA-Z]+Exception)/g,
    /([A-Z]{2,}[_-][A-Za-z-]+)/g,                  // ERROR_CODES
    /(ECONNREFUSED|EACCES|ENOENT|ETIMEDOUT|EPERM|EADDRINUSE)/g,
    /(CrashLoopBackOff|ImagePullBackOff|OOMKilled|ErrImagePull|CreateContainerConfigError)/g,
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

/** explain_error: match error signature tokens against the index. */
export function explainError(index, logExcerpt, opts = {}) {
  const { vendor, limit = 3 } = opts;
  const sigs = errorSignature(logExcerpt);
  // search with the raw excerpt + extracted signatures combined
  const searchText = [logExcerpt.slice(0, 400), ...sigs].join(" ");
  const res = search(index, searchText, { vendors: vendor ? [vendor] : undefined, limit: limit * 4 });

  // Boost results whose title/heading contains a distinctive signature keyword
  // (skip generic words that appear in most error contexts)
  const GENERIC = new Set(["error", "cannot", "find", "stack", "trace", "failed", "module", "require", "server", "code", "exit", "listen"]);
  const sigTerms = (sigs.join(" ").toLowerCase().match(/[a-z]{3,}/g) || [])
    .filter(t => !GENERIC.has(t));
  for (const r of res.results) {
    const hay = `${r.title} ${r.heading_path}`.toLowerCase();
    let boost = 1;
    for (const term of sigTerms) {
      if (hay.includes(term)) { boost = 2.5; break; }
    }
    r.score = +(r.score * boost).toFixed(4);
  }
  res.results.sort((a, b) => b.score - a.score);

  // diversify across vendors for the top-N
  const seenVendors = new Map();
  const diversified = [];
  for (const r of res.results) {
    const n = seenVendors.get(r.vendor) || 0;
    if (n < 2) {
      diversified.push(r);
      seenVendors.set(r.vendor, n + 1);
    }
    if (diversified.length >= limit) break;
  }
  return {
    extracted_signatures: sigs.slice(0, 6),
    matches: diversified,
    disclaimer: "These are the closest documentation sections, not a diagnosis. Verify against the linked official docs.",
    snapshot_date: index.builtAt,
  };
}

/** Vendor metadata (license attribution — constitution requirement). */
export const VENDORS = [
  {
    id: "cloudflare", name: "Cloudflare Developers",
    license: "CC-BY-4.0",
    license_url: "https://github.com/cloudflare/cloudflare-docs/blob/production/LICENSE",
    docs_origin: "developers.cloudflare.com (official llms.txt agent interface)",
    attribution_required: true,
  },
  {
    id: "netlify", name: "Netlify Docs",
    license: "Netlify Docs — agent use permitted via official llms.txt",
    license_url: "https://docs.netlify.com/llms.txt",
    docs_origin: "docs.netlify.com (official llms.txt agent interface)",
    attribution_required: true,
  },
  {
    id: "vercel", name: "Vercel Docs",
    license: "Vercel Docs — agent use permitted via official llms.txt",
    license_url: "https://vercel.com/docs/llms.txt",
    docs_origin: "vercel.com/docs (official llms.txt + sitemap.md agent interface)",
    attribution_required: true,
  },
  {
    id: "kubernetes", name: "Kubernetes",
    license: "CC-BY-4.0",
    license_url: "https://github.com/kubernetes/website/blob/main/LICENSE",
    docs_origin: "kubernetes/website GitHub (release branches)",
    attribution_required: true,
  },
  // ---- enrichment tier (2026-08-30) ----
  { id: "bun", name: "Bun", license: "MIT (Bun core)", license_url: "https://github.com/oven-sh/bun/blob/main/LICENSE", docs_origin: "bun.com official llms.txt", attribution_required: true },
  { id: "elysia", name: "ElysiaJS", license: "MIT", license_url: "https://github.com/elysiajs/elysia/blob/main/LICENSE", docs_origin: "elysiajs.com official llms.txt", attribution_required: true },
  { id: "turso", name: "Turso", license: "Turso Docs (agent-permitted via llms.txt)", license_url: "https://docs.turso.tech/llms.txt", docs_origin: "docs.turso.tech llms.txt", attribution_required: true },
  { id: "upstash", name: "Upstash", license: "Upstash Docs (agent-permitted via llms.txt)", license_url: "https://docs.upstash.com/llms.txt", docs_origin: "docs.upstash.com llms.txt", attribution_required: true },
  { id: "sentry", name: "Sentry", license: "Sentry Docs (agent-permitted via llms.txt)", license_url: "https://docs.sentry.io/llms.txt", docs_origin: "docs.sentry.io llms.txt", attribution_required: true },
  { id: "stripe", name: "Stripe", license: "Stripe Docs (agent-permitted via llms.txt)", license_url: "https://docs.stripe.com/llms.txt", docs_origin: "docs.stripe.com llms.txt", attribution_required: true },
  { id: "hono", name: "Hono", license: "MIT", license_url: "https://github.com/honojs/hono/blob/main/LICENSE", docs_origin: "hono.dev official llms.txt", attribution_required: true },
  { id: "nuxt", name: "Nuxt", license: "MIT", license_url: "https://github.com/nuxt/nuxt/blob/main/LICENSE", docs_origin: "nuxt.com llms.txt", attribution_required: true },
  { id: "solid", name: "SolidJS", license: "MIT", license_url: "https://github.com/solidjs/solid/blob/main/LICENSE", docs_origin: "docs.solidjs.com llms.txt", attribution_required: true },
  { id: "opentelemetry", name: "OpenTelemetry", license: "CC-BY-4.0", license_url: "https://github.com/open-telemetry/opentelemetry.io/blob/main/LICENSE", docs_origin: "opentelemetry.io official llms.txt", attribution_required: true },
  { id: "argocd", name: "Argo CD", license: "Apache-2.0", license_url: "https://github.com/argoproj/argo-cd/blob/master/LICENSE", docs_origin: "argoproj/argo-cd git-hosted docs", attribution_required: true },
  { id: "helm", name: "Helm", license: "Apache-2.0", license_url: "https://github.com/helm/helm-www/blob/main/LICENSE", docs_origin: "helm/helm-www git-hosted docs", attribution_required: true },
  { id: "flux", name: "Flux CD", license: "Apache-2.0", license_url: "https://github.com/fluxcd/flux2/blob/main/LICENSE", docs_origin: "fluxcd/website git-hosted docs", attribution_required: true },
  { id: "cilium", name: "Cilium", license: "Apache-2.0", license_url: "https://github.com/cilium/cilium/blob/main/LICENSE", docs_origin: "cilium/cilium Documentation (RST→md)", attribution_required: true },
  // ---- wiki FOSS tier (2026-08-31) ----
  { id: "react", name: "React", license: "MIT", license_url: "https://github.com/facebook/react/blob/main/LICENSE", docs_origin: "facebook/react git-hosted docs", attribution_required: true },
  { id: "pytorch", name: "PyTorch", license: "BSD-style (permissive)", license_url: "https://github.com/pytorch/pytorch/blob/main/LICENSE", docs_origin: "pytorch/pytorch git-hosted docs", attribution_required: true },
  { id: "tensorflow", name: "TensorFlow", license: "Apache-2.0", license_url: "https://github.com/tensorflow/tensorflow/blob/master/LICENSE", docs_origin: "tensorflow/tensorflow git-hosted docs", attribution_required: true },
  { id: "langchain", name: "LangChain", license: "MIT", license_url: "https://github.com/langchain-ai/langchain/blob/master/LICENSE", docs_origin: "langchain-ai/langchain git-hosted docs", attribution_required: true },
  { id: "playwright", name: "Playwright", license: "Apache-2.0", license_url: "https://github.com/microsoft/playwright/blob/main/LICENSE", docs_origin: "microsoft/playwright git-hosted docs", attribution_required: true },
  { id: "clickhouse", name: "ClickHouse", license: "Apache-2.0", license_url: "https://github.com/ClickHouse/ClickHouse/blob/master/LICENSE", docs_origin: "ClickHouse/ClickHouse git-hosted docs", attribution_required: true },
  { id: "ollama", name: "Ollama", license: "MIT", license_url: "https://github.com/ollama/ollama/blob/main/LICENSE", docs_origin: "ollama/ollama git-hosted docs", attribution_required: true },
  { id: "electron", name: "Electron", license: "MIT", license_url: "https://github.com/electron/electron/blob/main/LICENSE", docs_origin: "electron/electron git-hosted docs", attribution_required: true },
  { id: "hugo", name: "Hugo", license: "Apache-2.0", license_url: "https://github.com/gohugoio/hugo/blob/master/LICENSE", docs_origin: "gohugoio/hugo git-hosted docs", attribution_required: true },
  { id: "docusaurus", name: "Docusaurus", license: "MIT", license_url: "https://github.com/facebook/docusaurus/blob/main/LICENSE", docs_origin: "facebook/docusaurus git-hosted docs", attribution_required: true },
  { id: "pytest", name: "pytest", license: "MIT", license_url: "https://github.com/pytest-dev/pytest/blob/main/LICENSE", docs_origin: "pytest-dev/pytest git-hosted docs", attribution_required: true },
  { id: "nodejs", name: "Node.js", license: "MIT", license_url: "https://github.com/nodejs/node/blob/main/LICENSE", docs_origin: "nodejs/node git-hosted docs", attribution_required: true },
  { id: "godot-docs", name: "Godot", license: "MIT", license_url: "https://github.com/godotengine/godot/blob/master/LICENSE", docs_origin: "godotengine/godot git-hosted docs", attribution_required: true },
  { id: "neovim", name: "Neovim", license: "Apache-2.0", license_url: "https://github.com/neovim/neovim/blob/master/LICENSE", docs_origin: "neovim/neovim git-hosted docs", attribution_required: true },
  { id: "terragrunt", name: "Terragrunt", license: "MIT", license_url: "https://github.com/gruntwork-io/terragrunt/blob/main/LICENSE", docs_origin: "gruntwork-io/terragrunt git-hosted docs", attribution_required: true },
  { id: "moby", name: "Docker (Moby)", license: "Apache-2.0", license_url: "https://github.com/moby/moby/blob/master/LICENSE", docs_origin: "moby/moby git-hosted docs", attribution_required: true },
  { id: "elasticsearch", name: "Elasticsearch", license: "Apache-2.0", license_url: "https://github.com/elastic/elasticsearch/blob/main/LICENSE", docs_origin: "elastic/elasticsearch git-hosted docs", attribution_required: true },
  { id: "svelte-core", name: "Svelte", license: "MIT", license_url: "https://github.com/sveltejs/svelte/blob/main/LICENSE", docs_origin: "sveltejs/svelte git-hosted docs", attribution_required: true },
  { id: "vue-core-docs", name: "Vue (core)", license: "MIT", license_url: "https://github.com/vuejs/core/blob/main/LICENSE", docs_origin: "vuejs/core git-hosted docs", attribution_required: true },
  { id: "gitea", name: "Gitea", license: "MIT", license_url: "https://github.com/go-gitea/gitea/blob/main/LICENSE", docs_origin: "go-gitea/gitea git-hosted docs", attribution_required: true },
];
