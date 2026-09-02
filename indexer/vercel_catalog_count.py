#!/usr/bin/env python3
"""
Vercel catalog count — vercel.com has no llms.txt; its docs index is a
markdown sitemap at /docs/sitemap.md with "- [title](/docs/path) Lastmod: date"
lines. Count unique doc pages and write it into coverage-catalog.json.

Usage: python3 indexer/vercel_catalog_count.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverage_audit import fetch, norm

BASE = Path(__file__).resolve().parent.parent

VERCEL_SITEMAP_RE = re.compile(
    r"-\s+\[([^\]]+)\]\((/docs/[^\s)]+)\)", re.M)

def main():
    txt = fetch("https://vercel.com/docs/sitemap.md")
    if not txt:
        print("FAILED to fetch vercel sitemap.md")
        return
    pages = set()
    for m in VERCEL_SITEMAP_RE.finditer(txt):
        pages.add(norm("https://vercel.com" + m.group(2)))
    print(f"vercel catalog pages: {len(pages)}")

    cat_path = BASE / "app" / "stats" / "coverage-catalog.json"
    cat = json.loads(cat_path.read_text())
    entry = cat.get("vercel", {})
    catalog_n = len(pages)
    # ingested page count for vercel: derive from chunks data (unique paths)
    ingested = set()
    chunks_path = BASE / "data" / "chunks" / "vercel_latest.jsonl"
    if chunks_path.exists():
        for line in open(chunks_path):
            d = json.loads(line)
            u = d["source_url"].split("?")[0].rstrip("/")
            u = re.sub(r"\.(md|mdx)$", "", u)
            u = re.sub(r"/index$", "", u)
            ingested.add(u.lower())
    covered = sum(1 for p in ingested if p in pages)
    pct = round(100 * covered / catalog_n, 1) if catalog_n else None
    cat["vercel"] = {"catalog": catalog_n, "pct": pct}
    cat_path.write_text(json.dumps(cat, indent=1))
    print(f"vercel: ingested {len(ingested)} pages, {covered} in catalog -> {pct}%")
    print(f"updated {cat_path}")

if __name__ == "__main__":
    main()
