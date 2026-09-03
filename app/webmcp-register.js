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
      description: "Search federated developer documentation (Cloudflare, Netlify, Vercel, Kubernetes, Bun, Stripe, Sentry and more). Returns ranked excerpts with version, license, and canonical source URL. Results include `actionable` facts — config_keys, code_snippets, cli_commands — designed to chain with other tools (e.g. fetch the user's config via a GitHub MCP tool and compare against docs config_keys, or run cli_commands in a sandbox).",
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
        const results = (data.results || []).map(r => ({
          vendor: r.vendor, version: r.version, title: r.title,
          section: r.heading_path, excerpt_link: r.source_url,
          license: r.license, last_updated: r.last_updated, relevance: r.score,
          ...(r.actionable ? { actionable: r.actionable } : {})
        }));
        // structuredContent: machine-readable top answer for reliable tool chaining
        const top = results[0];
        const structured = {
          query: input.query,
          top_answer: top ? {
            source: top.vendor,
            title: top.title,
            section: top.section,
            canonical_url: top.excerpt_link,
            license: top.license,
            ...(top.actionable || {}),
          } : null,
          result_count: results.length,
        };
        return {
          structuredContent: structured,
          ...structured,
          results,
        };
      }
    }, { signal });

    ctx.registerTool({
      name: "explain_error",
      description: "Given a log excerpt or error message, find the closest matching documentation sections across mesh sources. Returns version-cited sections plus actionable fix facts (config_keys, code_snippets, cli_commands) and a disclaimer — not a diagnosis. Chain with execution tools (sandbox, GitHub MCP) to apply the suggested fix.",
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
        const data = await res.json();
        const matches = (data.matches || []).map(m => ({
          ...m,
          ...(m.actionable ? { actionable: m.actionable } : {})
        }));
        const top = matches[0];
        const structured = {
          error: input.log_excerpt.slice(0, 200),
          top_fix: top ? {
            source: top.vendor,
            title: top.title,
            canonical_url: top.source_url,
            license: top.license,
            ...(top.actionable || {}),
          } : null,
          match_count: matches.length,
        };
        return {
          structuredContent: structured,
          ...data,
          matches,
          structured,
        };
      }
    }, { signal });

    ctx.registerTool({
      name: "list_vendors",
      description: "List the documentation sources in the mesh with their license and attribution requirements.",
      inputSchema: { type: "object", properties: {} },
      execute: async (_input, options = {}) => await fetch("/vendors", { signal: options.signal ?? signal }).then(r => r.json())
    }, { signal });


// ── Act tools (browser surface) — same capabilities as the MCP server ──
try {
  // verify_config
  ctx.registerTool({
    name: "verify_config",
    description: "Diff the user's config file against the keys a source documents. Returns missing_keys (cited to docs) and unknown_keys (possible typos).",
    inputSchema: {
      type: "object",
      properties: {
        source: { type: "string", description: "Source id (e.g. 'cloudflare')" },
        config_text: { type: "string", description: "The config file contents" },
        config_query: { type: "string", description: "Optional docs query" },
      },
      required: ["source", "config_text"],
    },
    execute: async (input, options = {}) => {
      const res = await fetch("/verify-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
        signal: options.signal ?? signal,
      });
      return await res.json();
    },
  }, { signal });

  // compare_configs
  ctx.registerTool({
    name: "compare_configs",
    description: "Compare documented configuration keys between two sources (e.g. netlify vs vercel) — matched keys with citations, gaps listed.",
    inputSchema: {
      type: "object",
      properties: {
        source_a: { type: "string", description: "First source id" },
        source_b: { type: "string", description: "Second source id" },
        query_a: { type: "string" },
        query_b: { type: "string" },
      },
      required: ["source_a", "source_b"],
    },
    execute: async (input, options = {}) => {
      const res = await fetch("/compare-configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
        signal: options.signal ?? signal,
      });
      return await res.json();
    },
  }, { signal });

  // check_service_health
  ctx.registerTool({
    name: "check_service_health",
    description: "Probe a provider's public status page (cloudflare, github, npm, sentry). Answers 'is it down, or is it me?'",
    inputSchema: {
      type: "object",
      properties: { provider: { type: "string", enum: ["cloudflare", "github", "npm", "sentry"] } },
      required: ["provider"],
    },
    execute: async (input, options = {}) => {
      const res = await fetch(`/health-check?provider=${encodeURIComponent(input.provider)}`, { signal: options.signal ?? signal });
      return await res.json();
    },
  }, { signal });

  // report_issue
  ctx.registerTool({
    name: "report_issue",
    description: "Report a documentation problem (outdated/incorrect/misattributed). Queued as a proposal for review.",
    inputSchema: {
      type: "object",
      properties: {
        source_id: { type: "string" },
        chunk_id: { type: "string" },
        issue_type: { type: "string", enum: ["outdated", "incorrect", "misattributed", "license-mismatch", "broken-link"] },
        detail: { type: "string" },
        suggested_fix: { type: "string" },
        reporter: { type: "string" },
      },
      required: ["source_id", "chunk_id", "issue_type", "detail"],
    },
    execute: async (input, options = {}) => {
      const res = await fetch("/report-issue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
        signal: options.signal ?? signal,
      });
      return await res.json();
    },
  }, { signal });

  // submit_source
  ctx.registerTool({
    name: "submit_source",
    description: "Submit a documentation source for ingestion review (async job).",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string" },
        docs_origin: { type: "string" },
        license: { type: "string" },
      },
      required: ["name", "license"],
    },
    execute: async (input, options = {}) => {
      const res = await fetch("/submit-vendors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
        signal: options.signal ?? signal,
      });
      return await res.json();
    },
  }, { signal });

  // contribution_stats
  ctx.registerTool({
    name: "contribution_stats",
    description: "Mesh contribution counters: submissions, issue reports, sources indexed.",
    inputSchema: { type: "object", properties: {} },
    execute: async (_input, options = {}) =>
      await fetch("/contribution-stats", { signal: options.signal ?? signal }).then(r => r.json()),
  }, { signal });
} catch (e) {
  console.error("[webmcp] act tool registration failed:", e);
}

    if (typeof window !== "undefined") {
      window.__documeshWebMCPReady = true;
    }
    console.log("[webmcp] Documesh tools registered (9 tools: 3 core + 6 act)");
  } catch (e) {
    console.error("[webmcp] registration failed:", e);
  }
}

registerWebMCP();
