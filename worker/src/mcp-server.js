/**
 * Documesh MCP Server — Streamable HTTP transport
 * Session management, tools, resources (ui://), and notifications.
 */

const TOOLS = [
  {
    name: "search_docs_across",
    description: "Search federated developer documentation across 47 vendors (Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry, and more). Returns ranked excerpts (snippet, version, license, canonical source URL, per-result coverage/confidence). Response includes matched_terms, unmatched_terms, coverage, answerable, and suggestions — use suggestions to refine the query when answerable is false. For multi-part questions (e.g. 'run Postgres on Workers with Terraform-managed DNS'), issue one sub-query per part instead of one combined query.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
        vendors: { type: "array", items: { type: "string" }, description: "Optional vendor filter" },
        limit: { type: "number", description: "Max results (default 5)" }
      },
      required: ["query"]
    },
    annotations: {
      title: "Federated documentation search",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    _meta: { ui: { resourceUri: "ui://documesh/search-results" } }
  },
  {
    name: "explain_error",
    description: "Match an error message to the closest documentation sections across vendors.",
    inputSchema: {
      type: "object",
      properties: {
        log_excerpt: { type: "string", description: "Error message or log lines" },
        vendor: { type: "string", description: "Optional vendor filter" }
      },
      required: ["log_excerpt"]
    },
    annotations: {
      title: "Error-to-docs matching",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
    _meta: { ui: { resourceUri: "ui://documesh/error-match" } }
  },
  {
    name: "list_vendors",
    description: "List all vendors in the mesh with license and attribution requirements.",
    inputSchema: { type: "object", properties: {} },
    annotations: {
      title: "Vendor registry",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    }
  }
];

const RESOURCES = [
  {
    uri: "ui://documesh/search-results",
    name: "Search Results View",
    description: "Interactive search results with vendor badges, license info, and source links",
    mimeType: "text/html;profile=mcp-app"
  },
  {
    uri: "ui://documesh/error-match",
    name: "Error Match Card",
    description: "Error analysis results with matched documentation sections",
    mimeType: "text/html;profile=mcp-app"
  },
  {
    uri: "ui://documesh/vendor-grid",
    name: "Vendor Grid",
    description: "Grid of all 47 vendors with license badges",
    mimeType: "text/html;profile=mcp-app"
  }
];

const sessions = new Map();

function createSession() {
  const id = crypto.randomUUID();
  sessions.set(id, { createdAt: Date.now(), lastActivity: Date.now() });
  return id;
}

function getSession(id) {
  const s = sessions.get(id);
  if (s) s.lastActivity = Date.now();
  return s;
}

function jsonRPC(id, error, result) {
  const body = { jsonrpc: "2.0", id };
  if (error) body.error = error;
  else body.result = result;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
  });
}

export function handleMCPServer(request, env, handleToolCall, options = {}) {
  const sessionId = request.headers.get("Mcp-Session-Id");
  const serverName = options.serverName || "documesh";
  const serverTitle = options.serverTitle || "Documesh";
  const serverDescription = options.serverDescription || "Federated developer documentation search across 47 vendors";
  const serverInstructions = options.serverInstructions || "Call search_docs_across for documentation queries, explain_error to match error messages to docs, list_vendors for the source registry.";
  const tools = options.tools || TOOLS;
  const resources = options.resources || RESOURCES;

  // GET = SSE stream for server→client notifications.
  // Scanners (and many clients) probe GET first and hang on an open stream.
  // The Streamable HTTP spec allows answering 405 when the server doesn't
  // offer a standalone GET stream — we advertise that via the manifest, so
  // probes fail fast and complete their handshake via POST instead.
  if (request.method === "GET" && !new URL(request.url).searchParams.get("stream")) {
    return new Response(JSON.stringify({
      jsonrpc: "2.0",
      error: {
        code: -32000,
        message: "GET streams not offered. POST JSON-RPC 2.0 messages to this URL, or add ?stream=1 for the SSE notification stream.",
      },
      id: null,
    }), {
      status: 405,
      headers: {
        "Content-Type": "application/json",
        "Allow": "POST",
        "Access-Control-Allow-Origin": "*",
        "Mcp-Session-Id": sessionId || crypto.randomUUID(),
      },
    });
  }

  // Explicit SSE notification stream (GET /mcp?stream=1).
  // Sends the spec-required `endpoint` event, then keepalives.
  if (request.method === "GET") {
    const encoder = new TextEncoder();
    const sid = sessionId || crypto.randomUUID();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(`event: endpoint\ndata: ${new URL(request.url).origin}${new URL(request.url).pathname}?sessionId=${sid}\n\n`));
        controller.enqueue(encoder.encode(": keepalive\n\n"));
        const interval = setInterval(() => {
          try { controller.enqueue(encoder.encode(": keepalive\n\n")); } catch {}
        }, 15000);
        request.signal.addEventListener("abort", () => clearInterval(interval));
      }
    });
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Access-Control-Allow-Origin": "*",
        "Mcp-Session-Id": sid,
      }
    });
  }

  // POST = JSON-RPC messages
  return request.json().then(async body => {
    const { id, method, params } = body;

    // Track session
    if (method === "initialize") {
      const newSessionId = crypto.randomUUID();
      // Echo the client's requested protocol version when we support it,
      // otherwise fall back to our latest supported version (spec behavior).
      const SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"];
      const requested = params?.protocolVersion;
      const agreed = SUPPORTED.includes(requested) ? requested : SUPPORTED[0];
      try {
        return jsonRPCWithSession(id, null, {
          protocolVersion: agreed,
          capabilities: {
            tools: { listChanged: true },
            resources: { subscribe: false, listChanged: true },
            // MCP Apps extension (modelcontextprotocol/ext-apps):
            // advertises ui:// resource surfaces for in-conversation UI.
            extensions: {
              "io.modelcontextprotocol/ui": { version: "0.1.0" },
            },
          },
          serverInfo: { name: serverName, version: "0.2.0", title: serverTitle, description: serverDescription, instructions: serverInstructions },
          _meta: { ui: { resourceUri: "ui://documesh/search-results" } }
        }, newSessionId);
      } catch (e) {
        return jsonRPC(id, { code: -32603, message: e.message }, null);
      }
    }

    // Track session activity if we know this session. We do NOT reject
    // unknown sessions: Workers isolates are ephemeral and per-isolate Maps
    // cannot share state, so a session minted in another isolate would be
    // wrongly rejected. The API is read-only/open, so permissiveness is safe.
    if (sessionId) getSession(sessionId);

    // Notifications (no id) must be accepted with 202 and no body —
    // a JSON-RPC error response to a notification violates the spec and
    // makes strict clients abort the handshake right after initialize.
    if (method === "notifications/initialized" || method?.startsWith("notifications/") || id === undefined) {
      return new Response(null, { status: 202, headers: { "Access-Control-Allow-Origin": "*" } });
    }

    try {
      let result;
      switch (method) {
        case "tools/list":
          result = { tools };
          break;
        case "tools/call": {
          const toolName = params?.name;
          if (!toolName || typeof toolName !== "string") {
            return jsonRPC(id, { code: -32602, message: "Invalid params: 'name' is required and must be a string identifying a tool." }, null);
          }
          if (!tools.some(t => t.name === toolName)) {
            return jsonRPC(id, { code: -32602, message: `Unknown tool: ${toolName}. Valid tools: ${tools.map(t => t.name).join(", ")}.` }, null);
          }
          const tool = tools.find(t => t.name === toolName);
          const toolArgs = params?.arguments || {};
          // Validate required arguments against the tool's inputSchema.
          const required = tool?.inputSchema?.required || [];
          const missing = required.filter(k => toolArgs[k] === undefined || toolArgs[k] === null || toolArgs[k] === "");
          if (missing.length) {
            return jsonRPC(id, { code: -32602, message: `Invalid params: missing required argument(s) for ${toolName}: ${missing.join(", ")}.` }, null);
          }
          if (params?.arguments !== undefined && typeof params.arguments !== "object") {
            return jsonRPC(id, { code: -32602, message: "Invalid params: 'arguments' must be an object." }, null);
          }
          // Handler is async (may fetch vendor data) — must await or the
          // Promise serializes to {} in the JSON-RPC result.
          result = await handleToolCall(toolName, toolArgs, env);
          break;
        }
        case "resources/list":
          result = { resources };
          break;
        case "resources/read": {
          const uri = params?.uri;
          const resource = resources.find(r => r.uri === uri);
          if (!resource) {
            return jsonRPC(id, null, { code: -32602, message: `Resource not found: ${uri}` });
          }
          result = {
            contents: [{
              uri,
              mimeType: "text/html",
              text: generateResourceHTML(uri, params)
            }]
          };
          break;
        }
        case "ping":
          result = {};
          break;
        default:
          return jsonRPC(id, { code: -32601, message: `Method not found: ${method}` }, null);
      }

      // Attach session header to responses when session exists
      const response = jsonRPC(id, null, result);
      if (sessionId) {
        const headers = new Headers(response.headers);
        headers.set("Mcp-Session-Id", sessionId);
        return new Response(response.body, { status: response.status, headers });
      }
      return response;
    } catch (e) {
      return jsonRPC(id, { code: -32603, message: e.message }, null);
    }
  }).catch(e => jsonRPC(null, { code: -32700, message: "Parse error" }, null));
}

function jsonRPCWithSession(id, error, result, sessionId) {
  const body = { jsonrpc: "2.0", id };
  if (error) body.error = error;
  else body.result = result;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Mcp-Session-Id": sessionId
    }
  });
}
function generateResourceHTML(uri, params) {
  const wrap = (title, body) => `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="light dark">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; frame-ancestors https://chatgpt.com https://claude.ai https://chat.openai.com;">
<title>${title}</title>
<style>body{font-family:system-ui,sans-serif;margin:1rem;background:transparent;color:inherit}.badge{background:#3b82f6;color:#fff;border-radius:4px;padding:1px 6px;font-size:.8em}.lic{color:#888;font-size:.85em;margin-left:.5em}a{color:#3b82f6}</style>
</head>
<body>${body}</body>
</html>`;
  if (uri === "ui://documesh/search-results") {
    const results = params?.results || [];
    return wrap("Documesh — Search Results", `<div class="documesh-results"><h3>🔍 Search Results</h3>${results.map(r =>
      `<div class="result"><span class="badge">${r.vendor}</span> <a href="${r.source_url}">${r.title}</a> <span class="lic">${r.license}</span></div>`
    ).join("")}</div>`);
  }
  if (uri === "ui://documesh/error-match") {
    const matches = params?.matches || [];
    return wrap("Documesh — Error Analysis", `<div class="documesh-error"><h3>🩺 Error Analysis</h3>${matches.map(m =>
      `<div class="match"><span class="badge">${m.vendor}</span> <a href="${m.source_url}">${m.title}</a></div>`
    ).join("")}<p class="disclaimer">⚠️ Closest matches, not a diagnosis.</p></div>`);
  }
  if (uri === "ui://documesh/vendor-grid") {
    const vendors = params?.vendors || [];
    return wrap("Documesh — Vendor Grid", `<div class="documesh-vendors"><h3>📦 Vendors in the mesh</h3>${vendors.map(v =>
      `<div class="vendor"><span class="badge">${v.id || v}</span> <span class="lic">${v.license || ""}</span></div>`
    ).join("")}</div>`);
  }
  return wrap("Documesh", "<p>Documesh UI resource</p>");
}
