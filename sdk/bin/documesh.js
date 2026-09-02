#!/usr/bin/env node
/**
 * Documesh CLI — search federated developer documentation from the terminal.
 * Requires Node 18+. Zero dependencies.
 */
import { DocumeshClient } from "../documesh-sdk.js";

const [, , cmd, ...args] = process.argv;

const usage = `documesh — federated developer documentation search

Usage:
  documesh search "<query>" [--vendors a,b] [--limit N]
  documesh explain "<error or log excerpt>" [--vendor name]
  documesh vendors [--limit N]
  documesh health

Global:
  --base <url>   API base (default https://documesh.selatan.org)
  --json         Raw JSON output (pretty-printed)
  --version      Print version
  --help         This help

Examples:
  documesh search "edge functions env vars" --vendors cloudflare,vercel
  documesh explain "CrashLoopBackOff in pod docs-api"
`;

const flag = (name) => {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : undefined;
};
const has = (name) => process.argv.includes(name);

const client = new DocumeshClient({ base: flag("--base") || process.env.DOCUMESH_BASE || undefined });

async function main() {
  if (has("--help") || has("-h") || !cmd) {
    console.log(usage);
    return;
  }
  if (has("--version")) {
    const { createRequire } = await import("node:module");
    console.log(createRequire(import.meta.url)("../package.json").version);
    return;
  }

  const jsonOut = has("--json");

  if (cmd === "search") {
    const query = args.filter((a) => !a.startsWith("--")).join(" ");
    if (!query) { console.error('Usage: documesh search "<query>" [--vendors a,b] [--limit N]'); process.exit(1); }
    const r = await client.search(query, {
      vendors: flag("--vendors")?.split(",").map((s) => s.trim()).filter(Boolean),
      limit: flag("--limit") ? parseInt(flag("--limit")) : 5,
    });
    if (jsonOut) { console.log(JSON.stringify(r, null, 2)); return; }
    if (!r.results.length) { console.log("No results."); return; }
    for (const [i, res] of r.results.entries()) {
      console.log(`${i + 1}. [${res.vendor}${res.version ? `@${res.version}` : ""}] ${res.title}  (${res.score})`);
      console.log(`   ${res.heading_path || ""}`);
      console.log(`   ${res.source_url}  — license: ${res.license}`);
    }
    if (r.next_cursor) console.log(`\nMore: --cursor ${r.next_cursor} (pass as ?cursor=)`);
    return;
  }

  if (cmd === "explain") {
    const text = args.filter((a) => !a.startsWith("--")).join(" ");
    if (!text) { console.error('Usage: documesh explain "<error>" [--vendor name]'); process.exit(1); }
    const r = await client.explainError(text, { vendor: flag("--vendor") });
    if (jsonOut) { console.log(JSON.stringify(r, null, 2)); return; }
    console.log("Signatures:", r.extracted_signatures?.join(", ") || "(none)");
    for (const m of r.matches || []) {
      console.log(`\n• [${m.vendor}] ${m.title}`);
      console.log(`  ${m.source_url} — license: ${m.license}`);
    }
    console.log(`\n${r.disclaimer || ""}`);
    return;
  }

  if (cmd === "vendors") {
    const r = await client.listVendors({ limit: flag("--limit") ? parseInt(flag("--limit")) : undefined });
    if (jsonOut) { console.log(JSON.stringify(r, null, 2)); return; }
    for (const v of r.vendors) console.log(`${v.id.padEnd(16)} ${v.name || ""}  ${v.license || ""}`);
    if (r.next_cursor) console.log(`\nMore: --limit flag + cursor pagination via API`);
    return;
  }

  if (cmd === "health") {
    const r = await client.health();
    console.log(JSON.stringify(r, null, jsonOut ? 2 : 0));
    return;
  }

  console.error(`Unknown command: ${cmd}\n`);
  console.log(usage);
  process.exit(1);
}

main().catch((e) => {
  console.error(`error: ${e.message}`);
  process.exit(1);
});
