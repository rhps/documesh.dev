/**
 * Shared result-shaping helpers.
 *
 * Tier-2 "sources" rename (2026-09-02): every search result now carries
 * `source` (new canonical field) alongside the legacy `vendor` field.
 * `vendor` is deprecated-but-stable: API consumers (SDK, WebMCP demo,
 * third-party agents) keep working; new code should read `source`.
 * The JSON field in D1/shards is still `vendor` — storage rename is a
 * later migration (d1/schema.sql + shard format), not part of this step.
 */

/** Add `source` (alias of vendor) to one result object. */
export function withSource(result) {
  if (result && typeof result === "object" && "vendor" in result && !("source" in result)) {
    result.source = result.vendor;
  }
  return result;
}

/** Map a list of results through withSource (returns a new array). */
export function withSourceAll(results) {
  return (results || []).map(withSource);
}
