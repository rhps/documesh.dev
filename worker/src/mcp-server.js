/**
 * Documesh MCP Server — Streamable HTTP transport
 * Session management, tools, resources (ui://), and notifications.
 */

const TOOLS = [
  {
    name: "search_docs_across",
    description: "Search federated developer documentation across 38 vendors (Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry, and more). Returns ranked excerpts with version, license, and canonical source URL.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
        vendors: { type: "array", items: { type: "string" }, description: "Optional vendor filter" },
        limit: { type: "number", description: "Max results (default 5)" }
      },
      required: ["query"]
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
    _meta: { ui: { resourceUri: "ui://documesh/error-match" } }
  },
  {
    name: "list_vendors",
    description: "List all vendors in the mesh with license and attribution requirements.",
    inputSchema: { type: "object", properties: {} }
  }
];

const RESOURCES = [
  {
    uri: "ui://documesh/search-results",
    name: "Search Results View",
    description: "Interactive search results with vendor badges, license info, and source links",
    mimeType: "text/html"
  },
  {
    uri: "ui://documesh/error-match",
    name: "Error Match Card",
    description: "Error analysis results with matched documentation sections",
    mimeType: "text/html"
  },
  {
    uri: "ui://documesh/vendor-grid",
    name: "Vendor Grid",
    description: "Grid of all 38 vendors with license badges",
    mimeType: "text/html"
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

export function handleMCPServer(request, env, handleToolCall) {
  const sessionId = request.headers.get("Mcp-Session-Id");

  // GET = SSE stream for server→client notifications
  if (request.method === "GET") {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(": keepalive\n\n"));
        const interval = setInterval(() => {
          try { controller.enqueue(encoder.encode(": keepalive\n\n")); } catch {}
        }, 15000);
        request.signal.addEventListener("abort", () => clearInterval(interval));
      }
    });
    return new Response(stream, {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*" }
    });
  }

  // POST = JSON-RPC messages
  return request.json().then(body => {
    const { id, method, params } = body;

    // Track session
    if (method === "initialize") {
      const newSessionId = crypto.randomUUID();
      try {
        return jsonRPCWithSession(id, null, {
          protocolVersion: "2025-03-26",
          capabilities: { tools: { listChanged: true }, resources: { subscribe: false, listChanged: true } },
          serverInfo: { name: "documesh", version: "0.2.0", description: "Federated developer documentation search across 18 vendors" }
        }, newSessionId);
      } catch (e) {
        return jsonRPC(id, { code: -32603, message: e.message }, null);
      }
    }

    // Validate session for non-initialize requests
    if (sessionId && !getSession(sessionId)) {
      return jsonRPC(id, { code: -32001, message: "Session not found or expired" }, null);
    }

    try {
      let result;
      switch (method) {
        case "tools/list":
          result = { tools: TOOLS };
          break;
        case "tools/call": {
          const toolName = params?.name;
          const toolArgs = params?.arguments || {};
          result = handleToolCall(toolName, toolArgs, env);
          break;
        }
        case "resources/list":
          result = { resources: RESOURCES };
          break;
        case "resources/read": {
          const uri = params?.uri;
          const resource = RESOURCES.find(r => r.uri === uri);
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
          return jsonRPC(id, { code: -32601, message: `Method not found: ${method}` }, id);
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
  if (uri === "ui://documesh/search-results") {
    const results = params?.results || [];
    return `<div class="documesh-results"><h3>🔍 Search Results</h3>${results.map(r =>
      `<div class="result"><span class="badge">${r.vendor}</span> <a href="${r.source_url}">${r.title}</a> <span class="lic">${r.license}</span></div>`
    ).join("")}</div>`;
  }
  if (uri === "ui://documesh/error-match") {
    const matches = params?.matches || [];
    return `<div class="documesh-error"><h3>🩺 Error Analysis</h3>${matches.map(m =>
      `<div class="match"><span class="badge">${m.vendor}</span> <a href="${m.source_url}">${m.title}</a></div>`
    ).join("")}<p class="disclaimer">⚠️ Closest matches, not a diagnosis.</p></div>`;
  }
  return "<p>Documesh UI resource</p>";
}
