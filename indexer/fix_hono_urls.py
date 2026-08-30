#!/usr/bin/env python3
"""
Fix Hono source_url: map each chunk to its real docs page on hono.dev.

Strategy: Hono's docs source is honojs/website/docs/<section>/<page>.md.
The llms-small.txt is generated from those pages — H1 boundaries = page titles.
We reconstruct: chunk title/heading → search the website repo's file tree →
map to https://hono.dev/<docs-path>.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS = BASE / "data" / "chunks" / "hono_latest.jsonl"
UA = {"User-Agent": "docs-mesh-fixer"}


def gh_tree():
    url = "https://api.github.com/repos/honojs/website/git/trees/main?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    return [t["path"] for t in d.get("tree", []) if t["path"].endswith(".md") and "/docs/" in t["path"]]


def title_to_slug(title):
    t = title.lower()
    t = re.sub(r"\{#[a-z0-9-]+\}", "", t)  # strip anchors
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t


def main():
    url = "https://api.github.com/repos/honojs/website/git/trees/main?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    paths = [t["path"] for t in d.get("tree", []) if t["path"].endswith(".md") and t["path"].startswith("docs/")]
    print(f"website repo: {len(paths)} docs md files")

    # Build lookup: slug of filename (without .md) -> full path
    by_file = {}
    for p in paths:
        fname = p.rsplit("/", 1)[-1].removesuffix(".md")
        by_file.setdefault(fname, p)

    # H1 page titles in llms file order → try match against docs dir listing order too
    # We'll match each chunk's top-level title to a docs file.
    chunks = [json.loads(l) for l in CHUNKS.open()]
    fixed, unresolved = 0, 0
    for c in chunks:
        # top-level title = first segment of heading_path
        top = c["heading_path"].split(" > ")[0] if c["heading_path"] else c["title"]
        cand = title_to_slug(top)
        hit = None
        # exact file slug match
        if cand in by_file:
            hit = by_file[cand]
        else:
            # partial: file slug contains candidate or vice versa
            for slug, p in by_file.items():
                if cand and (cand in slug or slug in cand):
                    hit = p
                    break
        if hit:
            rel = hit[len("docs/"):].rsplit(".", 1)[0]
            page = f"https://hono.dev/docs/{rel}"
            c["source_url"] = page
            fixed += 1
        else:
            # manual overrides for titles that don't slug-match filenames
            manual = {
                "node.js": "https://hono.dev/docs/getting-started/nodejs",
                "faq": "https://hono.dev/docs/guides/faq",
                "frequently asked questions": "https://hono.dev/docs/guides/faq",
                "webassembly (w/ wasi)": "https://hono.dev/docs/getting-started/webassembly-wasi",
                "next.js": "https://hono.dev/docs/getting-started/nextjs",
                "client components": "https://hono.dev/docs/guides/jsx",
                "supabase edge functions": "https://hono.dev/docs/getting-started/supabase-edge-functions",
                "alibaba cloud function compute": "https://hono.dev/docs/getting-started/ali-function-compute",
                "miscellaneous": "https://hono.dev/docs/",
                "getting started": "https://hono.dev/docs/",
                "wrangler.toml": "https://hono.dev/docs/getting-started/cloudflare-workers",
            }
            key = top.lower().strip()
            if key in manual:
                c["source_url"] = manual[key]
                fixed += 1
            else:
                unresolved += 1

    with CHUNKS.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    print(f"fixed: {fixed}, unresolved (keep llms-small.txt): {unresolved}")
    # rebuild index
    import subprocess
    subprocess.run(["python3", str(BASE / "indexer" / "build_index.py")], check=True)


if __name__ == "__main__":
    main()
