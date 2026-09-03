/**
 * Actionable-answer extraction — makes Documesh results chainable by agents.
 *
 * For each result we extract, from snippet/content, the machine-usable facts an
 * orchestrating agent needs to act on the answer (call another MCP tool, edit a
 * config, open a PR):
 *   - config_keys: dotted config paths the section documents (e.g. "vars.MY_VAR",
 *     "triggers.crons", "compatibility_date")
 *   - code_snippets: fenced or heuristically-detected code, with language tags
 *   - cli_commands: shell commands the docs tell you to run
 *   - applies_to: version applicability when the chunk names one
 *
 * All extraction is heuristic, deterministic, and pure — no network, no LLM.
 */

const CONFIG_KEY_RE = /(?:^|[\s`"'(])([A-Za-z][A-Za-z0-9_]*(?:[.\-][A-Za-z][A-Za-z0-9_]+){1,3})\s*(?:=|:|(?:key|variable|setting|option|field|property|header)\b)/i;
const DOTTED_KEY_RE = /^[A-Za-z][A-Za-z0-9_]*(?:[.\-][A-Za-z][A-Za-z0-9_]+){1,3}$/;
const SHELL_RE = /(?:^|[\n\s])(?:\$ |> |[Rr]un\s+|[Ee]xecute\s+|[Ww]ith\s+)?((?:npm|npx|yarn|pnpm|bun|pip|pip3|cargo|go|kubectl|helm|docker|wrangler|git|curl|terraform|tofu|flyctl|gh)[^\S\n]+[^\n`]{4,160}?)(?=\s*(?:\.|\n|\z|to |and |then |for |before |after |$))/g;
const VERSION_RE = /\b(?:since|introduced in|available (?:in|as of|from)|requires?|works? (?:with|from)|version)\b[^.\n]{0,40}?(\d+\.\d+(?:\.\d+)?|\d{4}-\d{2}-\d{2})/i;

const LANG_HINTS = [
  [/\b(const|let|function|=>|import |export )/, "javascript"],
  [/\b(def |import |print\(|self\.)/, "python"],
  [/\b(func |package |:=)/, "go"],
  [/\b(fn |let mut|impl |use )/, "rust"],
  [/^\s*<(?:div|html|body|span|a )/m, "html"],
  [/^\s*[.#][\w-]+\s*\{/m, "css"],
  [/(?:^\s*SELECT |INSERT INTO|CREATE TABLE)/i, "sql"],
  [/(?:^\s*apiVersion:|^\s*kind:|\w+: \S+)/m, "yaml"],
  [/(?:^\s*\{|\": \")/, "json"],
];

/** Extract facts from one chunk's text. Returns {} when nothing found. */
export function extractActionables(text, opts = {}) {
  if (!text || typeof text !== "string") return {};
  const out = {};
  const sample = text.slice(0, opts.maxScan || 4000);

  // ── config keys ──
  const NOT_A_KEY = /\.(toml|ya?ml|json|md|txt|jsx?|tsx?|py|go|rs|sh|html|css)$/i; // filenames, not keys
  const keys = new Set();
  const addKey = (k) => {
    k = k.replace(/[.\-_]+$/, "");            // strip trailing separators from greedy captures
    if (DOTTED_KEY_RE.test(k) && k.length <= 40 && !NOT_A_KEY.test(k)) keys.add(k);
  };
  for (const m of sample.matchAll(new RegExp(CONFIG_KEY_RE.source, "gi"))) {
    addKey(m[1]);
  }
  // `code-key` inline spans often name config keys — check backticked dotted tokens
  for (const m of sample.matchAll(/`([A-Za-z][A-Za-z0-9_]*(?:[.\-][A-Za-z][A-Za-z0-9_]+){1,3})`/g)) {
    addKey(m[1]);
  }
  if (keys.size) out.config_keys = [...keys].slice(0, 8);

  // ── code snippets: fenced blocks, else first plausible line cluster ──
  const snippets = [];
  for (const m of sample.matchAll(/```(\w+)?\n([\s\S]{10,600}?)```/g)) {
    snippets.push({ lang: m[1] || guessLang(m[2]) || "text", code: m[2].trim() });
    if (snippets.length >= 2) break;
  }
  if (!snippets.length) {
    const shell = [...sample.matchAll(SHELL_RE)].map(m => m[1].trim());
    if (shell.length) snippets.push({ lang: "bash", code: shell.slice(0, 3).join("\n") });
  }
  if (snippets.length) out.code_snippets = snippets;

  // ── CLI commands (even outside snippets) ──
  const cmds = [...sample.matchAll(SHELL_RE)]
    .map(m => m[1].trim())
    // trim at sentence end — docs prose often continues after the command
    .map(c => c.split(/(?:\.\s|\.\n|$)/)[0].trim())
    .filter(c => c.length >= 4);
  if (cmds.length) out.cli_commands = [...new Set(cmds)].slice(0, 4);

  // ── version applicability ──
  const v = sample.match(VERSION_RE);
  if (v) out.applies_to = { version: `>= ${v[1]}` };

  return out;
}

function guessLang(code) {
  for (const [re, lang] of LANG_HINTS) {
    if (re.test(code)) return lang;
  }
  return null;
}
