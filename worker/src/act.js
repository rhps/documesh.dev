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
  netlify: { status_url: "https://netlifystatus.net/api/v2/status.json", name: "Netlify" },
  github: { status_url: "https://www.githubstatus.com/api/v2/status.json", name: "GitHub" },
  npm: { status_url: "https://status.npmjs.org/api/v2/status.json", name: "npm" },
  aws: { status_url: "https://health.aws.amazon.com/public/currentstatus", name: "AWS" },
  vercel: { status_url: "https://www.vercelstatus.com/api/v2/status.json", name: "Vercel" },
  stripe: { status_url: "https://status.stripe.com/api/v2/status.json", name: "Stripe" },
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
  // Aggregate documented keys per source from search results
  const docByKey = new Map();
  for (const r of docEntries) {
    for (const k of r?.actionable?.config_keys || []) {
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
