/**
 * Documesh — WebMCP registration for the landing page.
 * Registers all 3 tools so agents discover Documesh immediately on page load.
 * The tools call the same API endpoints as app.html.
 */
const TOOL_VENDORS = ["cloudflare","netlify","vercel","kubernetes","bun","elysia","turso","upstash","sentry","stripe","hono","nuxt","solid","opentelemetry","argocd","helm","flux","cilium","react","pytorch","tensorflow","langchain","playwright","clickhouse","ollama","electron","hugo","docusaurus","pytest","nodejs","godot-docs","neovim","terragrunt","moby","elasticsearch","svelte-core","vue-core-docs","gitea"];

async function registerWebMCP() {
  const ctx = document.modelContext ?? createShim();
  try {
    ctx.registerTool({
      name: "search_docs_across",
      description: "Search federated developer documentation (Cloudflare, Netlify, Vercel, Kubernetes, Bun, Stripe, Sentry and more). Returns ranked excerpts with version, license, and canonical source URL for every result.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query, e.g. 'edge functions environment variables'" },
          vendors: { type: "array", items: { type: "string", enum: TOOL_VENDORS }, description: "Optional vendor filter" },
          limit: { type: "number", description: "Max results (default 5)" }
        },
        required: ["query"]
      },
      execute: async (input) => {
        const params = new URLSearchParams({ q: input.query, limit: String(input.limit ?? 5) });
        if (input.vendors?.length) params.set("vendors", input.vendors.join(","));
        const data = await fetch(`/search?${params}`).then(r => r.json());
        return {
          snapshot_date: data.snapshot_date,
          results: data.results.map(r => ({
            vendor: r.vendor, version: r.version, title: r.title,
            section: r.heading_path, excerpt_link: r.source_url,
            license: r.license, last_updated: r.last_updated, relevance: r.score
          }))
        };
      }
    });

    ctx.registerTool({
      name: "explain_error",
      description: "Given a log excerpt or error message, find the closest matching documentation sections across mesh vendors. Returns version-cited sections and a disclaimer — not a diagnosis.",
      inputSchema: {
        type: "object",
        properties: {
          log_excerpt: { type: "string", description: "The error message or log lines" },
          vendor: { type: "string", enum: TOOL_VENDORS, description: "Optional vendor filter" }
        },
        required: ["log_excerpt"]
      },
      execute: async (input) => {
        const params = new URLSearchParams({ error: input.log_excerpt });
        if (input.vendor) params.set("vendor", input.vendor);
        return await fetch(`/explain?${params}`).then(r => r.json());
      }
    });

    ctx.registerTool({
      name: "list_vendors",
      description: "List the documentation vendors in the mesh with their license and attribution requirements.",
      inputSchema: { type: "object", properties: {} },
      execute: async () => await fetch("/vendors").then(r => r.json())
    });

    console.log("[webmcp] Documesh tools registered on landing page");
  } catch (e) {
    console.error("[webmcp] registration failed:", e);
  }
}

function createShim() {
  const tools = {};
  const shim = {
    registerTool: (t) => {
      tools[t.name] = t;
      if (typeof window !== "undefined") {
        window.__documeshTools = window.__documeshTools || {};
        window.__documeshTools[t.name] = t;
      }
    }
  };
  if (!("modelContext" in document)) {
    Object.defineProperty(document, "modelContext", {
      get() { return shim; },
      configurable: true,
    });
  }
  return shim;
}

registerWebMCP();
