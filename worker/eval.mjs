/**
 * Eval harness — held-out real-world errors → expect relevant doc section in top-3.
 * Gate: ≥80% (4/5) for MVP. Run: node worker/eval.mjs
 */
import { readFileSync } from "node:fs";
import { loadIndex, explainError } from "./src/search-core.js";

const index = loadIndex(readFileSync(new URL("../data/search-index.json", import.meta.url), "utf8"));

// 5 curated real-world errors (MVP gate).
// ok = at least one top-3 match is vendor-correct OR matches the expected topic keyword.
const CASES = [
  {
    name: "k8s CrashLoopBackOff",
    log: `Warning Failed 3m kubelet Back-off restarting failed container my-app. Error: CrashLoopBackOff: container failed to start, exit code 1`,
    expect: { topic: ["restart", "container", "pod"], vendor: "kubernetes" },
  },
  {
    name: "node ERR_MODULE_NOT_FOUND (express)",
    log: `node:internal/modules/cjs/loader:1078 throw err; Error: Cannot find module 'express' Require stack: server.js`,
    expect: { topic: ["express", "module", "import"], vendor: null },
  },
  {
    name: "port already in use (EADDRINUSE)",
    log: `Error: listen EADDRINUSE: address already in use 0.0.0.0:3000 at Server.setupListenListen`,
    expect: { topic: ["port", "listener", "listen", "error"], vendor: null },
  },
  {
    name: "deploy failed build command",
    log: `Deploy did not build: build.command failed with exit code 1: command not found: npm run build. Failed deploy.`,
    expect: { topic: ["deploy", "build"], vendor: null },
  },
  {
    name: "k8s OOMKilled",
    log: `State: Waiting Reason: OOMKilled Last State: Terminated Reason: Error Exit Code: 137 container exceeded memory limit`,
    expect: { topic: ["terminated", "memory", "container", "resource"], vendor: "kubernetes" },
  },
];

let pass = 0;
for (const c of CASES) {
  const out = explainError(index, c.log, { limit: 3 });
  const haystacks = out.matches.map((m) => `${m.title} ${m.heading_path} ${m.source_url}`.toLowerCase());
  const topicHit = c.expect.topic.some((kw) => haystacks.some((h) => h.includes(kw.toLowerCase())));
  const vendorHit = c.expect.vendor ? out.matches.some((m) => m.vendor === c.expect.vendor) : true;
  const ok = topicHit && vendorHit && out.matches.length > 0;
  if (ok) pass++;
  console.log(`${ok ? "✅" : "❌"} ${c.name}`);
  console.log(`   vendors: ${out.matches.map((m) => m.vendor).join(",") || "none"}`);
  console.log(`   top: ${out.matches[0]?.title?.slice(0, 60) || "NO MATCH"}`);
}

console.log(`\nEVAL RESULT: ${pass}/${CASES.length} = ${((pass / CASES.length) * 100).toFixed(0)}% (gate: ≥80%)`);
process.exit(pass / CASES.length >= 0.8 ? 0 : 1);
