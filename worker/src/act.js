/**
 * Act surface — contribution & verification tools.
 *
 * Everything here is a queued PROPOSAL: nothing mutates the corpus directly.
 * - report_issue: flag a chunk as wrong/outdated/misattributed → triage queue
 * - contribution_stats: aggregate contribution counters (per-source)
 * - verify_config: diff a user's config text against a source's documented
 *   config_keys (pure compute, no external auth — the sleeper-hit bridge tool)
 * - check_service_health: probe a vendor's public status page/health endpoint
 *   (read-only, auth-free) — "is it down, or is it me?"
 *
 * All writes are rate-limited (same RateLimit budget) and Idempotency-Key aware.
 */

/** Issue types accepted by report_issue. */
export const ISSUE_TYPES = ["outdated", "incorrect", "misattributed", "license-mismatch", "broken-link"];

/** Public provider status pages (read-only health probes). */
export const KNOWN_PROVIDERS = {
  cloudflare: { status_url: "https://www.cloudflarestatus.com/api/v2/status.json", name: "Cloudflare" },
  github: { status_url: "https://www.githubstatus.com/api/v2/status.json", name: "GitHub" },
  npm: { status_url: "https://status.npmjs.org/api/v2/status.json", name: "npm" },
  sentry: { status_url: "https://status.sentry.io/api/v2/status.json", name: "Sentry" },
};

/**
 * Validate + normalize a correction report.
 * Returns { ok, report } or { ok: false, error }.
 */
export function normalizeIssueReport({ source_id, chunk_id, issue_type, detail, suggested_fix, reporter }) {
  if (!source_id || typeof source_id !== "string") return { ok: false, error: "source_id is required" };
  if (!chunk_id || typeof chunk_id !== "string") return { ok: false, error: "chunk_id is required" };
  if (!ISSUE_TYPES.includes(issue_type)) {
    return { ok: false, error: `issue_type must be one of: ${ISSUE_TYPES.join(", ")}` };
  }
  if (!detail || typeof detail !== "string" || detail.trim().length < 10) {
    return { ok: false, error: "detail is required (≥10 chars) — explain what is wrong" };
  }
  return {
    ok: true,
    report: {
      source_id,
      chunk_id,
      issue_type,
      detail: detail.trim().slice(0, 2000),
      suggested_fix: (suggested_fix || "").toString().slice(0, 2000) || undefined,
      reporter: (reporter || "").toString().slice(0, 120) || undefined,
    },
  };
}

/**
 * verify_config — diff a user's config text against a source's documented config keys.
 * docKeys: config_keys aggregated from the source's indexed chunks (via search).
 * Returns missing keys (documented but absent from user config), unknown keys
 * (present in config but never documented — possible typos), and cited evidence.
 */
export function verifyConfig(docEntries, configText) {
  if (!configText || typeof configText !== "string" || !configText.trim()) {
    return { ok: false, error: "config_text is required" };
  }
  // Aggregate documented keys per source from search results.
  // Skip filenames (wrangler.toml etc.) — they are files, not config keys.
  const NOT_A_KEY = /\.(toml|ya?ml|json|md|txt|jsx?|tsx?|py|go|rs|sh|html|css)$/i;
  const docByKey = new Map();
  for (const r of docEntries) {
    for (const rawKey of r?.actionable?.config_keys || []) {
      const k = rawKey.replace(/[.\-_]+$/, "");
      if (NOT_A_KEY.test(k)) continue;
      if (!docByKey.has(k)) docByKey.set(k, { title: r.title, source_url: r.source_url, vendor: r.vendor || r.source });
    }
  }
  if (!docByKey.size) {
    return { ok: false, error: "no documented config keys found for this source/query — try a broader config_query" };
  }

  // Extract keys present in the user's config: dotted tokens, [section] headers,
  // and "key:" YAML/JSON-style entries.
  const userKeys = new Set();
  for (const m of configText.matchAll(/(?:^|\n)\s*\[([A-Za-z][\w.\-"]+)\]/g)) {
    userKeys.add(m[1].replace(/"/g, ""));
  }
  for (const m of configText.matchAll(/(?:^|\n)\s*"?([A-Za-z][\w]*(?:\.[\w]+)+)"?\s*[:=]/g)) {
    userKeys.add(m[1]);
  }
  // bare top-level words in TOML/INI style (name = value)
  for (const m of configText.matchAll(/(?:^|\n)\s*([A-Za-z][\w]*)\s*=\s*\S/g)) {
    userKeys.add(m[1]);
  }

  const missing = [];
  for (const [key, evidence] of docByKey) {
    // match exact, or as a suffix segment (user config may scope keys: [triggers] crons = ...)
    const segments = key.split(".");
    const covered =
      userKeys.has(key) ||
      segments.some(seg => userKeys.has(seg)) ||
      [...userKeys].some(uk => key.endsWith(uk) || uk.endsWith(key));
    if (!covered) missing.push({ key, documented_in: evidence });
  }

  const unknown = [...userKeys].filter(uk => {
    if (docByKey.has(uk)) return false;
    // a user key is "known" if any documented key contains it as a segment
    for (const dk of docByKey.keys()) {
      const segs = dk.split(".");
      if (segs.includes(uk) || dk === uk) return false;
    }
    return true;
  });

  return {
    ok: true,
    documented_keys: [...docByKey.keys()],
    missing_keys: missing,
    unknown_keys: unknown,
    disclaimer: "Heuristic diff of your config against documented keys. Missing ≠ wrong — only keys this source documents are checked. Verify against the cited docs.",
  };
}

/**
 * check_service_health — probe a known provider's public status endpoint.
 * Returns normalized { provider, indicator, description } or fetch error.
 */
export async function checkServiceHealth(env, provider) {
  const p = KNOWN_PROVIDERS[provider];
  if (!p) {
    return {
      ok: false,
      error: `unknown provider: ${provider}`,
      known_providers: Object.keys(KNOWN_PROVIDERS),
    };
  }
  try {
    const res = await fetch(p.status_url, { headers: { "User-Agent": "documesh-health/1.0" }, signal: AbortSignal.timeout(6000) });
    if (!res.ok) return { ok: false, error: `status endpoint returned ${res.status}` };
    const data = await res.json();
    return {
      ok: true,
      provider,
      name: p.name,
      indicator: data.status?.indicator || "unknown",
      description: data.status?.description || "",
      checked_at: new Date().toISOString(),
      status_url: p.status_url,
    };
  } catch (e) {
    return { ok: false, error: `status probe failed: ${e.message}` };
  }
}

/**
 * x402 payment tiers — metered mesh capacity.
 *
 * Free tier stays genuinely useful (100 req/hr); exceeding it returns an x402
 * challenge (HTTP 402 + WWW-Authenticate: Payment). A request carrying a valid
 * PAYMENT-SIGNATURE header (verified via the hosted facilitator) gets boosted.
 *
 * The facilitator verify call is external — controlled by env.X402_FACILITATOR_URL.
 * Without it (local dev / not yet enabled), all requests fall through as free tier.
 */

export const PAYMENT_TIERS = {
  free:   { requests_per_hour: 100,  max_results: 5,  price_usd: 0 },
  boosted:{ requests_per_hour: 1000, max_results: 20, price_usd: 0.001 },
  deep:   { requests_per_hour: 5000, max_results: 50, price_usd: 0.01 },
};

/** Build an x402 challenge response for a paid tier. */
export function x402Challenge(env, tier = "boosted") {
  const t = PAYMENT_TIERS[tier];
  return {
    status: 402,
    headers: {
      "WWW-Authenticate": `Payment realm="documesh", tier="${tier}", price="${t.price_usd} USD", description="Documesh ${tier} capacity", facilitator="${env.X402_FACILITATOR_URL || "https://facilitator.x402.io"}"`,
    },
  };
}

/**
 * Tier/quota check for a request.
 * - Free tier: enforced via RateLimit headers (existing middleware) — this only
 *   handles the PAID escalation path.
 * - Returns { tier, boosted } or { tier:"free", challenge } when free quota is
 *   exhausted and the caller hasn't paid.
 */
export function resolveTier(request, env, quotaExceeded) {
  if (!quotaExceeded) return { tier: "free", boosted: false };
  // caller claims a paid tier via header; real verification happens through the facilitator
  const sig = request.headers.get("PAYMENT-SIGNATURE");
  if (sig && env.X402_FACILITATOR_URL) {
    return { tier: "boosted", boosted: true, payment_signature: sig };
  }
  return { tier: "free", boosted: false, challenge: x402Challenge(env, "boosted") };
}
