import { readFileSync } from "node:fs";
import { loadIndex, search } from "./src/search-core.js";

const index = loadIndex(readFileSync("data/search-index.json", "utf8"));

// Reproduce EXACTLY what explainError does now
const log = `node:internal/modules/cjs/loader:1078 throw err; Error: Cannot find module 'express' Require stack: server.js`;
const sigs = ["Error: Cannot find module 'express' Require stack: server.js"];

const searchText = [log.slice(0, 400), ...sigs].join(" ");
const res = search(index, searchText, { limit: 12 });

// Apply the boost
const sigTerms = sigs.join(" ").toLowerCase().match(/[a-z]{3,}/g) || [];
console.log("sigTerms:", sigTerms);

for (const r of res.results) {
  const hay = `${r.title} ${r.heading_path}`.toLowerCase();
  let boost = 1;
  for (const term of sigTerms) {
    if (hay.includes(term)) { boost = 2.5; break; }
  }
  r.score = r.score * boost;
}
res.results.sort((a, b) => b.score - a.score);

console.log("\nAfter boost, top 8:");
for (const x of res.results.slice(0, 8)) {
  const hay = `${x.title} ${x.heading_path}`.toLowerCase();
  const hasKw = ["express", "module", "import"].some(kw => hay.includes(kw));
  console.log(`${x.score.toFixed(1).padStart(7)} ${x.vendor.padEnd(12)} kw=${hasKw ? "Y" : "N"} ${x.title.slice(0, 50)}`);
}

// Find where "Use Express..." lands
const express = res.results.findIndex(x => x.title.toLowerCase().includes("express"));
console.log(`\n"Use Express..." at position: ${express + 1}`);
