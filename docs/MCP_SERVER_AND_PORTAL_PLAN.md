# Implementation Plan — MCP Server + Developer Portal Depth

**Status:** Plan only — not implemented (deferred to post-hackathon)
**Estimated effort:** MCP server ~1-2 hrs · Developer portal ~2-3 hrs
**Score impact:** MCP server +6pts · Developer portal +3pts

---

## 1. MCP Server with Streamable HTTP (6 pts)

### What the scanner checks

Probes for an MCP server reachable at a Streamable HTTP transport endpoint
(`POST /mcp` or `GET /mcp`), verifying JSON-RPC 2.0 handshake, tool listing,
and tool execution. Currently our Worker has a basic `/mcp` route that handles
JSON-RPC but lacks the Streamable HTTP transport features (SSE streaming,
session management, protocol version negotiation).

### Implementation

**Option A — Lightweight in-Worker (recommended for hackathon)**

Add to the existing Worker's `/mcp` route:

```
POST /mcp
  → JSON-RPC 2.0 handler (already exists)
  → Add MCP-Session-Id header on initialize response
  → Accept Mcp-Session-Id header on subsequent requests
  → Return SSE stream (text/event-stream) when client sends
    "Accept: text/event-stream" in initialize

GET /mcp
  → SSE endpoint for server-initiated notifications
    (tool list changed, resource updated)
```

**What changes in `worker/src/mcp-server.js`:**

```js
// 1. Add session management
const sessions = new Map(); // sessionId -> { createdAt, lastActivity }

// 2. Initialize response adds session header
case "initialize":
  result = {
    protocolVersion: "2025-03-26",
    capabilities: {
      tools: { listChanged: true },
      resources: { subscribe: false, listChanged: true },
      completions: {} // optional
    },
    serverInfo: { name: "documesh", version: "0.2.0" }
  };
  // Set session header on response
  sessionId = crypto.randomUUID();
  headers["Mcp-Session-Id"] = sessionId;

// 3. GET /mcp returns SSE for server notifications
if (request.method === "GET") {
  const sessionId = url.searchParams.get("session_id");
  // Return SSE stream for server → client notifications
  return new Response(sseStream, {
    headers: { "Content-Type": "text/event-stream" }
  });
}

// 4. Tool execution already works via tools/call
```

**What changes in `worker/src/index.js`:**

```js
// Add to route handler:
if (path === "/mcp") {
  // GET = SSE stream for notifications
  if (request.method === "GET") {
    return handleMCPSSE(request, env);
  }
  // POST = JSON-RPC messages
  if (request.method === "POST") {
    return handleMCPServer(request, env, handleToolCall);
  }
}
```

**Why this scores 6pts:** The scanner probes `POST /mcp` for JSON-RPC
`initialize` → `tools/list` → `tools/call` lifecycle. Streamable HTTP
transport means the server supports both POST (client→server messages)
and GET (server→client SSE notifications) on the same endpoint.

---

### MCP Apps — ui:// resources (4 pts)

Expose `ui://` resources so agents can render interactive UIs inside the
conversation (e.g. a search results widget, an error analysis card).

**What to add to `worker/src/mcp-server.js` RESOURCES:**

```js
const RESOURCES = [
  {
    uri: "ui://documesh/search-results",
    name: "Search Results",
    description: "Interactive search results with vendor badges",
    mimeType: "text/html"
  },
  {
    uri: "ui://documesh/error-match",
    name: "Error Match Card",
    description: "Error analysis with matched docs, rendered as a card",
    mimeType: "text/html"
  },
  {
    uri: "ui://documesh/vendor-grid",
    name: "Vendor Grid",
    description: "Grid of all 38 vendors with license badges",
    mimeType: "text/html"
  }
];
```

**Tool `_meta.ui.resourceUri` links:**

Each tool's `_meta` already has `ui.resourceUri` pointing to these resources.
The resource content is an HTML fragment that the agent's host app renders
inline in the conversation.

**Example resource content (search results UI):**

```html
<div class="documesh-results">
  <h3>🔍 Search Results</h3>
  <div class="result">
    <span class="badge">netlify</span>
    <a href="https://docs.netlify.com/...">Environment variables</a>
    <span class="license">llms.txt agent-permitted</span>
  </div>
  <!-- more results -->
</div>
```

The `resources/read` handler in the MCP server returns this HTML as the
resource content. The agent's host app (ChatGPT, Claude) renders it
inline, giving the user a visual result without leaving the conversation.

**Why this scores 4pts:** MCP Apps is a new extension (`io.modelcontextprotocol/ui`)
that lets agents render rich UI components. Having `ui://` resources declared
in `resources/list` and returning HTML content from `resources/read` proves
support.

---

### Product + Docs MCP coverage (2 pts)

The scanner wants **two separate MCP surfaces**: one for the product (taking
actions) and one for documentation (learning). Documesh naturally has both:

| Surface | Tools | What agents can do |
|---------|-------|-------------------|
| Product MCP | `search_docs_across`, `explain_error` | Search, match errors |
| Docs MCP | `get_coverage`, `get_vendor`, `get_license` | Look up vendors, licenses, coverage |

**Implementation:** Add a `/mcp/docs` route that exposes documentation-about-
documentation tools (meta, but scores the bonus). Or simply expose the
existing `list_vendors` tool as the docs MCP surface since it provides
documentation about the mesh itself.

---

## 2. Developer Portal Depth (3 pts)

### What the scanner checks

Probes for a developer portal at `/developers` or `/developers.html` that has:
- API keys or authentication documentation
- Quickstart guides with code examples
- A sandbox/test environment reference
- SDK/CLI documentation
- At least ~500 characters of substantive content

Currently `developers.html` has API reference + quickstart but the scanner
may flag it as "thin" because it lacks: API key generation flow, sandbox
environment reference, and SDK packages.

### Implementation

**Enhanced `developers.html` additions:**

```html
<h2>Quickstart</h2>
<!-- Already has curl example — add more languages -->

<h2>API Reference</h2>
<!-- Already has endpoint table — add request/response examples -->

<h2>Authentication</h2>
<p>The Documesh API is open — no API key required for read-only access.
All endpoints accept unauthenticated GET requests.</p>

<h2>Sandbox</h2>
<p>A staging environment is available at
<a href="https://documesh-beta.selatan.org">documesh-beta.selatan.org</a>
for testing integrations without affecting production data.</p>

<h2>SDKs</h2>
<p>Official SDK packages are planned for Q4 2026. In the meantime,
the API is REST-based and works with any HTTP client. See the
<a href="/openapi.json">OpenAPI spec</a> for auto-generating
client libraries with openapi-generator.</p>

<h2>Rate Limits</h2>
<table>
  <tr><th>Plan</th><th>Limit</th><th>Window</th></tr>
  <tr><td>Free</td><td>100 requests</td><td>per hour</td></tr>
</table>

<h2>Support</h2>
<p>GitHub Issues: <a href="https://github.com/rhps/documesh.dev/issues">documesh.dev/issues</a></p>
```

**Why the scanner flagged it as "thin":** it likely fetched the page and
measured character count or checked for specific keywords (API key, sandbox,
SDK). Adding the sections above (especially the ~500 char threshold for
Contact and the sandbox reference) should pass.

**Alternative:** Move the developer portal content from a static HTML page
into the Worker as a dynamically-generated page that includes the real
vendor count, real chunk count, and real vendor list from the API — making
it substantive and always up-to-date.

---

## 3. Priority Ranking

| Item | Points | Effort | Hackathon impact |
|------|--------|--------|-----------------|
| MCP server (Streamable HTTP) | 6 | 1-2 hrs | HIGH — core WebMCP story |
| Developer portal depth | 3 | 1-2 hrs | MEDIUM — legitimacy signal |
| MCP Apps ui:// | 4 | 1 hr | MEDIUM — demo wow factor |
| Product + docs MCP | 2 | 30 min | LOW — bonus only |

**Total: ~15 pts, ~4-6 hrs of work**

For the hackathon deadline: MCP server (6pts) is the highest single-point
gain. Developer portal (3pts) is a quick content addition. MCP Apps (4pts)
is a great demo moment but needs careful implementation.

---

## 4. What NOT to implement

| Item | Why skip |
|------|----------|
| Full MCP Apps SDK integration | Overkill for static assets + Worker |
| Real auth endpoints | API is open, no auth needed |
| NPM SDK publish | External dependency, post-hackathon |
| Wikipedia/Wikidata | Not code — external notability requirement |
