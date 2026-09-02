/**
 * Documesh — WebMCP registration (landing page + app).
 * Registers all 3 tools so agents discover Documesh immediately on page load.
 *
 * Per the WebMCP spec the ModelContext lives on `navigator.modelContext`.
 * Some early implementations exposed `document.modelContext`, so we register
 * on whichever exists (navigator preferred) and install a discovery shim on
 * both when the API is absent, so scanners can enumerate registered tools.
 */
const TOOL_VENDORS = ["cloudflare","netlify","vercel","kubernetes","bun","elysia","turso","upstash","sentry","stripe","hono","nuxt","solid","opentelemetry","argocd","helm","flux","cilium","react","pytorch","tensorflow","langchain","playwright","clickhouse","ollama","electron","hugo","docusaurus","pytest","nodejs","godot-docs","neovim","terragrunt","moby","elasticsearch","svelte-core","vue-core-docs","gitea"];

function createShim() {
  const tools = {};
  const shim = {
    registerTool: (t, options = {}) => {
      tools[t.name] = t;
      if (typeof window !== "undefined") {
        window.__documeshWebMCPTools = window.__documeshWebMCPTools || {};
        window.__documeshWebMCPTools[t.name] = {
          name: t.name,
          description: t.description,
          inputSchema: t.inputSchema,
        };
      }
      return t;
    },
    unregisterTool: (name) => { delete tools[name]; },
    getTool: (name) => tools[name],
  };
  return shim;
}

async function registerWebMCP() {
  // navigator.modelContext is the spec location; document.modelContext is
  // the early-implementation fallback. Install the shim on both if absent.
  const ctx = navigator.modelContext ?? document.modelContext ?? (() => {
    const shim = createShim();
    try {
      if (!("modelContext" in navigator)) {
        Object.defineProperty(navigator, "modelContext", { get() { return shim; }, configurable: true });
      }
      if (!("modelContext" in document)) {
        Object.defineProperty(document, "modelContext", { get() { return shim; }, configurable: true });
      }
    } catch {}
    return shim;
  })();

  const controller = new AbortController();
  const { signal } = controller;
  if (typeof window !== "undefined") window.__documeshWebMCPAbort = controller;

  try {
    ctx.registerTool({
      name: "search_docs_across",
      description: "Search federated developer documentation (Cloudflare, Netlify, Vercel, Kubernetes, Bun, Stripe, Sentry and more). Returns ranked excerpts with version, license, and canonical source URL for every result.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query, e.g. 'edge functions environment variables'" },
          vendors: { type: "array", items: { type: "string", enum: TOOL_VENDORS }, description: "Optional source filter (accepts the legacy 'vendors' name; each value is a documentation source id)" },
          limit: { type: "number", description: "Max results (default 5)" }
        },
        required: ["query"]
      },
      execute: async (input, options = {}) => {
        const params = new URLSearchParams({ q: input.query, limit: String(input.limit ?? 5) });
        if (input.vendors?.length) params.set("vendors", input.vendors.join(","));
        const res = await fetch(`/search?${params}`, { signal: options.signal ?? signal });
        const data = await res.json();
        return {
          snapshot_date: data.snapshot_date,
          results: (data.results || []).map(r => ({
            vendor: r.vendor, version: r.version, title: r.title,
            section: r.heading_path, excerpt_link: r.source_url,
            license: r.license, last_updated: r.last_updated, relevance: r.score
          }))
        };
      }
    }, { signal });

    ctx.registerTool({
      name: "explain_error",
      description: "Given a log excerpt or error message, find the closest matching documentation sections across mesh sources. Returns version-cited sections and a disclaimer — not a diagnosis.",
      inputSchema: {
        type: "object",
        properties: {
          log_excerpt: { type: "string", description: "The error message or log lines" },
          vendor: { type: "string", enum: TOOL_VENDORS, description: "Optional vendor filter" }
        },
        required: ["log_excerpt"]
      },
      execute: async (input, options = {}) => {
        const params = new URLSearchParams({ error: input.log_excerpt });
        if (input.vendor) params.set("vendor", input.vendor);
        const res = await fetch(`/explain?${params}`, { signal: options.signal ?? signal });
        return await res.json();
      }
    }, { signal });

    ctx.registerTool({
      name: "list_vendors",
      description: "List the documentation sources in the mesh with their license and attribution requirements.",
      inputSchema: { type: "object", properties: {} },
      execute: async (_input, options = {}) => await fetch("/vendors", { signal: options.signal ?? signal }).then(r => r.json())
    }, { signal });

    if (typeof window !== "undefined") {
      window.__documeshWebMCPReady = true;
    }
    console.log("[webmcp] Documesh tools registered (navigator.modelContext)");
  } catch (e) {
    console.error("[webmcp] registration failed:", e);
  }
}

registerWebMCP();
