# Research: Logging MCP + API Activity on Cloudflare

**Question:** How to record all incoming MCP and API traffic for Documesh (Cloudflare Worker).
**Current stack:** single Worker (`documesh-api`), D1 (`documesh-search`), static assets, no logging pipeline today.

---

## Option A — Cloudflare Workers Analytics Engine ⭐ recommended for this use case

Workers Analytics Engine (AE) is Cloudflare's built-in, high-volume, low-cost telemetry store designed
exactly for "write many small event rows from a Worker, query later".

- **How it works:** `env.AE.writeDataPoint({ blobs, doubles, indexes })` — one line per request.
  Query via SQL API (or Grafana integration).
- **Cost:** effectively free at this scale. Free tier: **100k writes/day**; paid ($5/mo Workers Paid):
  **10M writes/day**, 1 GB total storage, 90-day retention for sampled data (3-month query window).
- **Latency:** write is non-blocking (fire-and-forget), no D1 write contention.
- **Cardinality:** 1 index (e.g. route) + up to 20 blobs (query strings, source list, session id, UA)
  + doubles (took_ms, result count). Perfect fit for "who called what with which params".

### Fit for Documesh
- MCP JSON-RPC calls: log method, tool name, session id, params summary.
- REST: path, query, source filter, status, took_ms.
- No schema migration, no cleanup jobs (retention is automatic).
- **Caveat:** retention window; it's analytics, not an audit archive. If you need
  months of raw request bodies, pair with Option B.

## Option B — Logpush to R2 (structured archive)

- Wrap the Worker fetch in `ctx.waitUntil()` and `PUT` a JSON line to an R2 bucket
  (partitioned `dt=/hour=/...`), or use **Workers Logs → Logpush** (paid) to push
  Worker invocations to R2 automatically.
- **Cost:** R2 ~$0.015/GB-month storage, zero egress. At ~1 KB/event and 100k events/day
  that's ~3 GB/month ≈ **$0.05/month**. Cheapest long-term archive.
- **Query:** R2 SQL bindings (newer) or periodic export to D1 DuckDB-style analysis.
- **Fit:** good as the *cold* tier — raw body capture, compliance-grade history.

## Option C — Tail Workers (live stream of every invocation)

- `wrangler tail` in production, or attach a **Tail Worker** via API: consumes
  `trace` events (console logs, exceptions, request metadata) for every invocation.
- **Fit:** debugging/live watch, not storage. Pairs with A or B: Tail Worker can
  also *forward* events to AE/R2/D1 without touching main worker code.

## Option D — Log to D1 (what we already have)

- Tempting since D1 exists, but **wrong tool for request logs**: every request becomes
  a DB write (rows-read quota burn, write latency in request path, table bloat, manual
  pruning). D1 is fine for *derived* aggregates (e.g. "popular queries" materialized
  hourly), not raw event streams.

## Option E — Third-party (Axiom/Tinybird/Datadog via fetch)

- Worker fetches to an HTTP ingestion endpoint inside `waitUntil()`.
- Generous free tiers (Axiom 500 GB/mo, Tinybird free queries), great dashboards.
- **Caveat:** external dependency + egress; fine for a hackathon dashboard, adds vendor risk.

---

## Recommended architecture (2 tiers)

```
Request → Worker
   ├─ (always)   Analytics Engine writeDataPoint   [hot tier: 90d, SQL queries, dashboards]
   └─ (sampled or all, via ctx.waitUntil)  R2 JSONL append  [cold tier: permanent, cheap]
   └─ (existing) D1 stays for corpus + derived aggregates only
```

## Implementation sketch (Option A, ~60 lines)

1. wrangler.jsonc: add `"analytics_engine_datasets": [{"binding": "AE"}]` (both envs).
2. `worker/src/logging.js`:
   ```js
   export function logRequest(ctx, env, e) {
     if (!env.AE) return;                       // graceful no-op locally
     ctx.waitUntil(env.AE.writeDataPoint({
       blobs:   [e.route, e.method, e.status, e.backend, e.sessionId ?? '', e.query ?? '', e.ua ?? ''],
       doubles: [e.tookMs, e.results],
       index:   e.route,                        // coarse index for grouping
     }));
   }
   ```
3. Call it once per request in `index.js` fetch() just before returning (both MCP + REST paths),
   with MCP JSON-RPC method/tool extracted in `mcp-server.js` return path.
4. Query:
   ```
   POST /accounts/{account}/analytics_engine/sql
       SELECT blob1 AS route, count(*), avg(double1)
       FROM documesh_api WHERE timestamp > NOW() - 24h GROUP BY route
   ```

## Key numbers to re-check at build time

- AE limits: https://developers.cloudflare.com/analytics-engine/platform/limits/
- Logpush from Workers: https://developers.cloudflare.com/workers/observability/logs/workers-logs/#logpush
- R2 SQL: https://developers.cloudflare.com/r2/api/super-slurp/ (or r2sql bindings)
