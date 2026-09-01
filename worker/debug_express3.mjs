import { readFileSync } from "node:fs";
import { loadIndex, search } from "../src/search-core.js";

const index = loadIndex(readFileSync(new URL("../data/search-index.json", import.meta.url), "utf8"));

const log = `node:internal/modules/cjs/loader:1078 throw err; Error: Cannot find module 'express' Require stack: server.js`;
const sigs = ["Error: Cannot find module 'express' Require stack: server.js"];
const searchText = [log.slice(0, 400), ...sigs].join(" ");
const res = search(index, searchText, { limit: 12 });

const sigTerms = sigs.join(" ").toLowerCase().match(/[a-z]{3,}/g) || [];
for (const r of res.results) {
  const hay = (r.title + " " + r.heading_path).toLowerCase();
  for (const term of sigTerms) { if (hay.includes(term)) { r.score *= 2.5; break; } }
}
res.results.sort((a, b) => b.score - a.score);

const vendorCount = {};
const top3 = [];
for (const r of res.results) {
  vendorCount[r.vendor] = (vendorCount[r.vendor] || 0) + 1;
  if (vendorCount[r.vendor] <= 2) { top3.push(r); }
  if (top3.length >= 3) break;
}
console.log("top-3:");
for (const m of top3) {
  const hay = (m.title + " " + m.heading_path).toLowerCase();
  const hasKw = ["express","module","import"].some(kw => hay.includes(kw));
  console.log(" ", m.vendor.padEnd(12), "kw=" + (hasKw?"Y":"N"), m.title.slice(0,45));
}
