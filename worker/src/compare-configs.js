/**
 * Act surface extensions — Tier1 #2 (compare_configs) + Tier 3 (x402 tiers, A2A delegation).
 */

/**
 * compare_configs — map documented config keys between two sources.
 * "I know Netlify's redirect syntax — what's the Vercel equivalent?"
 *
 * v1 honest scope: side-by-side of documented keys (each with doc citation) using
 * concept-overlap matching on key segments + titles; explicit gap lists for
 * unmatched keys. No LLM, no claims of semantic equivalence beyond name overlap.
 */

const CONCEPT_SYNONYMS = [
  // [canonical concept, [synonym tokens]] — key-segment level
  ["redirect", ["redirect", "redirects", "rewrite", "rewrites"]],
  ["environment-variables", ["vars", "env", "environment", "variables", "environment-variables"]],
  ["headers", ["headers", "header"]],
  ["cache", ["cache", "caching", "headers-cache"]],
  ["cron", ["cron", "crons", "triggers-crons", "schedule", "schedules"]],
  ["auth", ["auth", "authentication", "auth-token", "api-key", "api-keys", "token"]],
  ["cors", ["cors"]],
  ["build", ["build", "builds", "build-command", "builds-command"]],
  ["deploy", ["deploy", "deployment", "deployments", "deploys"]],
  ["rate-limit", ["rate-limit", "rate-limits", "ratelimit", "limits"]],
];

function conceptOf(segment) {
  const s = segment.toLowerCase().replace(/[^a-z]/g, "");
  for (const [canon, syns] of CONCEPT_SYNONYMS) {
    if (syns.some(syn => s === syn || s.includes(syn) || syn.includes(s) && s.length > 3)) return canon;
  }
  return null;
}

function keyConcepts(key) {
  const concepts = new Set();
  for (const seg of key.toLowerCase().split(/[.\-_]/)) {
    const c = conceptOf(seg);
    if (c) concepts.add(c);
  }
  // whole-key concept match (e.g. "redirects" file key)
  const whole = conceptOf(key);
  if (whole) concepts.add(whole);
  return concepts;
}

/**
 * Compare documented config keys from two sources.
 * entriesA/entriesB: search results with .actionable.config_keys (like verify_config input).
 * Returns { common: [...], only_a: [...], only_b: [...], disclaimer }.
 * common entries pair keys whose concept sets overlap, each side with citation.
 */
export function compareConfigs(entriesA, entriesB, sourceA, sourceB) {
  const NOT_A_KEY = /\.(toml|ya?ml|json|md|txt|jsx?|tsx?|py|go|rs|sh|html|css)$/i;
  const collect = (entries) => {
    const map = new Map(); // key -> citation
    for (const r of entries) {
      for (const raw of r?.actionable?.config_keys || []) {
        const k = raw.replace(/[.\-_]+$/, "");
        if (!k || NOT_A_KEY.test(k)) continue;
        if (!map.has(k)) map.set(k, { title: r.title, source_url: r.source_url, vendor: r.vendor || r.source });
      }
    }
    return map;
  };
  const mapA = collect(entriesA);
  const mapB = collect(entriesB);
  if (!mapA.size || !mapB.size) {
    return { ok: false, error: "no documented config keys found for one or both sources — broaden the config_query for each" };
  }

  const common = [];
  const onlyA = [];
  for (const [keyA, citeA] of mapA) {
    const conceptsA = keyConcepts(keyA);
    let best = null;
    for (const [keyB, citeB] of mapB) {
      const conceptsB = keyConcepts(keyB);
      const overlap = [...conceptsA].filter(c => conceptsB.has(c));
      // exact key match outranks concept overlap
      const score = keyA.toLowerCase() === keyB.toLowerCase() ? 100 : overlap.length;
      if (score > 0 && (!best || score > best.score)) {
        best = { key: keyB, score, concepts: [...overlap], documented_in: citeB };
      }
    }
    if (best) {
      common.push({ key_a: keyA, key_b: best.key, match: best.score >= 100 ? "exact" : "concept", via_concepts: best.concepts, a: citeA, b: best.documented_in });
    } else {
      onlyA.push({ key: keyA, documented_in: citeA });
    }
  }
  const matchedB = new Set(common.map(c => c.key_b));
  const onlyB = [...mapB.keys()].filter(k => !matchedB.has(k)).map(k => ({ key: k, documented_in: mapB.get(k) }));

  return {
    ok: true,
    source_a: sourceA,
    source_b: sourceB,
    common: common.sort((x, y) => (x.match === y.match ? 0 : x.match === "exact" ? -1 : 1)),
    only_a: onlyA,
    only_b: onlyB,
    disclaimer: "Key mapping is heuristic (name + concept overlap), not semantic proof. 'No equivalent found' means none documented under a matching name — verify against the cited docs before relying on it.",
  };
}
