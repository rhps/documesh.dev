/**
 * Documesh MCP Server — Streamable HTTP transport
 * Exposes Documesh capabilities as MCP tools for Claude, ChatGPT, and other agents.
 * Also includes MCP Apps (ui:// resources) for in-agent UI rendering.
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
    _meta: {
      ui: { resourceUri: "ui://documesh/search-results" }
    }
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
    _meta: {
      ui: { resourceUri: "ui://documesh/error-match" }
    }
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
    name: "Error Match View",
    description: "Error analysis results with matched documentation sections",
    mimeType: "text/html"
  }
];

export function handleMCPServer(request, env, handleToolCall) {
  return handleStreamableHTTP(request, env, handleToolCall);
}

async function handleStreamableHTTP(request, env, handleToolCall) {
  // Parse JSON-RPC
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonRPC(null, { code: -32700, message: "Parse error" }, null);
  }

  const { id, method, params } = body;

  try {
    let result;

    switch (method) {
      case "initialize":
        result = {
          protocolVersion: "2025-03-26",
          capabilities: {
            tools: { listChanged: true },
            resources: { subscribe: false, listChanged: true }
          },
          serverInfo: {
            name: "documesh",
            version: "0.2.0",
            description: "Federated developer documentation search across 18 vendors"
          }
        };
        break;

      case "notifications/initialized":
        return new Response(null, { status: 204 });

      case "tools/list":
        result = { tools: TOOLS };
        break;

      case "tools/call": {
        const toolName = params?.name;
        const toolArgs = params?.arguments || {};
        result = await handleToolCall(toolName, toolArgs, env);
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
            text: "<html><body><p>Documesh UI resource</p></body></html>"
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

    return jsonRPC(id, null, result);
  } catch (e) {
    return jsonRPC(id, { code: -32603, message: e.message }, null);
  }
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
