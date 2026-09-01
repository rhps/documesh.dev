import { readFileSync } from "node:fs";
import { loadIndex, search } from "./src/search-core.js";

const index = loadIndex(readFileSync("data/search-index.json", "utf8"));

const log = `node:internal/modules/cjs/loader:1078 throw err; Error: Cannot find module 'express' Require stack: server.js`;

const sigs = [];
const pats = [
  /([A-Z][a-zA-Z]+Exception)/g,
  /(CrashLoopBackOff|ImagePullBackOff|OOMKilled|ErrImagePull)/g,
  /(ECONNREFUSED|EACCES|ENOENT|ETIMEDOUT|EADDRINUSE|EPERM)/g,
  /(Error|error|ERROR):?\s+([a-zA-Z0-9 :'.\-_/]{10,90})/g,
];
for (const p of pats) {
  let m;
  while ((m = p.exec(log)) !== null) sigs.push(m[0].length > 60 ? m[0].slice(0, 60) : m[0]);
}
console.log("sigs:", sigs);

const searchText = [log.slice(0, 400), ...sigs].join(" ");
const r = search(index, searchText, { limit: 20 });
console.log("\nTop 20:");
for (const x of r.results) {
  const hay = `${x.title} ${x.heading_path}`.toLowerCase();
  const hasKw = ["express", "module", "import"].some(kw => hay.includes(kw));
  console.log(`${x.score.toFixed(1).padStart(7)} ${x.vendor.padEnd(12)} kw=${hasKw ? "Y" : "N"} ${x.title.slice(0, 50)}`);
}
