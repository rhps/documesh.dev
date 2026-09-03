/**
 * Request logging for MCP + API traffic.
 *
 * Hot tier:  Cloudflare Analytics Engine (env.AE) — SQL-queryable, 90d retention.
 * Cold tier: R2 (env.LOGS) — permanent JSONL archive, one object per 15-min window.
 *
 * Both are best-effort: absence of bindings (local dev) or write errors are
 * swallowed so logging can never break a request. All writes go through
 * ctx.waitUntil() — zero added latency.
 */

const LOG_SAMPLE_RATE = 1.0;          // 1.0 = log everything
const R2_FLUSH_INTERVAL_MS = 15 * 60 * 1000;  // one R2 object per 15-minute window

const r2Buffer = [];
let r2Key = null;   // "dt=2026-09-03/hour=14/part-<minute-block>.jsonl"

function windowKey(now = new Date()) {
  const blockMin = Math.floor(now.getUTCMinutes() / 15) * 15;
  const dt = now.toISOString().slice(0, 10);
  const hour = String(now.getUTCHours()).padStart(2, "0");
  return `dt=${dt}/hour=${hour}/part-${String(blockMin).padStart(2, "0")}.jsonl`;
}

/**
 * Extract request-level facts shared by REST + MCP paths.
 * Never reads or stores request bodies (privacy: only query string + MCP method).
 */
export function collectRequestEvent(request, url, startedMs) {
  const ua = request.headers.get("user-agent") || "";
  return {
    method: request.method,
    route: url.pathname,
    query: url.search.slice(0, 300),
    ua: ua.slice(0, 120),
    tookMs: Math.round(performance.now() - startedMs),
    cf: request.cf?.country || "",
  };
}

/** Write one event to both tiers. */
export function logRequest(ctx, env, ev, extra = {}) {
  if (Math.random() > LOG_SAMPLE_RATE) return;

  const status = extra.status ?? 0;
  const backend = extra.backend ?? "";
  const sessionId = (extra.sessionId || "").slice(0, 40);
  const mcpMethod = (extra.mcpMethod || "").slice(0, 40);
  const mcpTool = (extra.mcpTool || "").slice(0, 40);
  const results = extra.results ?? 0;

  // ── hot tier: Analytics Engine ──
  if (env.AE) {
    try {
      ctx.waitUntil(env.AE.writeDataPoint({
        // index must be low-cardinality (route)
        index: ev.route,
        // blobs (strings, max 20): method, status, backend, mcpMethod, mcpTool, sessionId, query, ua, country
        blobs: [ev.method, String(status), backend, mcpMethod, mcpTool, sessionId, ev.query, ev.ua, ev.cf],
        // doubles: tookMs, results
        doubles: [ev.tookMs, results],
      }));
    } catch { /* never break a request over logging */ }
  }

  // ── cold tier: R2 JSONL buffer ──
  if (env.LOGS) {
    try {
      const now = new Date();
      r2Key = r2Key || windowKey(now);
      r2Buffer.push(JSON.stringify({
        ts: now.toISOString(),
        method: ev.method,
        route: ev.route,
        status,
        backend,
        mcp_method: mcpMethod || undefined,
        mcp_tool: mcpTool || undefined,
        session: sessionId || undefined,
        query: ev.query || undefined,
        took_ms: ev.tookMs,
        results: results || undefined,
        country: ev.cf || undefined,
        ua: ev.ua || undefined,
      }));
      flushR2(ctx, env);
    } catch { /* never break a request over logging */ }
  }
}

/** Append buffered lines to R2; rollover to a new key each 15-min window. */
function flushR2(ctx, env) {
  if (!r2Buffer.length) return;

  const now = new Date();
  const currentKey = windowKey(now);
  if (currentKey !== r2Key) {
    // window rolled over — flush under the old key immediately
    const key = r2Key;
    const lines = r2Buffer.splice(0);
    r2Key = currentKey;
    ctx.waitUntil(putR2(env, key, lines));
    return;
  }

  // Same window: debounce ~2 s so bursts coalesce into fewer PUTs
  if (flushR2._timer) return;
  flushR2._timer = setTimeout(() => {
    flushR2._timer = null;
    if (!r2Buffer.length || !env.LOGS) return;
    const lines = r2Buffer.splice(0);
    ctx.waitUntil(putR2(env, r2Key, lines));
  }, 2000);
}

async function putR2(env, key, lines) {
  try {
    const body = lines.join("\n") + "\n";
    const existing = await env.LOGS.get(key);
    const finalBody = existing ? (await existing.text()) + body : body;
    await env.LOGS.put(key, finalBody, {
      httpMetadata: { contentType: "application/x-ndjson" },
    });
  } catch { /* best-effort archive */ }
}
