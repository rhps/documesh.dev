#!/usr/bin/env python3
"""
Targeted ingest: Cloudflare Hyperdrive + Terraform sections.

Motivation (2026-09-02): compound agent questions like
  "Can I run Postgres on Cloudflare Workers with Terraform-managed DNS?"
score ZERO postings for 'postgres'/'hyperdrive' in the cloudflare shard,
so ranking degenerates to generic-token matches ("Customize cache behavior
with Workers"). This script adds the missing product sections using the
same CC-BY-4.0 .md-endpoint pipeline as fetch_docs.crawl_cloudflare.

Usage: python3 indexer/ingest_hyperdrive_terraform.py
Appends new chunks into data/chunks/cloudflare_latest.jsonl (dedup by path),
then run indexer/build_shards.py to rebuild shards.
"""
from __future__ import annotations

import json
import re
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_docs import (  # noqa: E402
    fetch, parse_llms_txt, strip_base, chunk_markdown, chunk_id,
    make_chunk, crawl_cloudflare,
)

BASE = Path(__file__).resolve().parent.parent
CHUNKS = BASE / "data" / "chunks" / "cloudflare_latest.jsonl"

LICENSE_INFO = {
    "license": "CC-BY-4.0",
    "license_url": "https://github.com/cloudflare/cloudflare-docs/blob/production/LICENSE",
    "attribution": "© Cloudflare, Inc., CC BY 4.0 — via documesh",
}

# (llms.txt URL, path prefix kept in rel paths)
TARGETS = [
    ("https://developers.cloudflare.com/hyperdrive/llms.txt", "hyperdrive"),
    ("https://developers.cloudflare.com/terraform/llms.txt", "terraform"),
]


def collect_pages(llms_url: str, prefix: str) -> list[dict]:
    """One-stage: product llms.txt -> page links ending in .md."""
    txt = fetch(llms_url)
    if not txt:
        print(f"  !! no llms.txt at {llms_url}")
        return []
    links = [l for l in parse_llms_txt(txt)
             if strip_base(l["url"]).endswith(".md")]
    print(f"  [{prefix}] {len(links)} .md pages listed")
    return links


def fetch_pages(links: list[dict], prefix: str) -> list[dict]:
    out = []
    for i, link in enumerate(links):
        md_url = strip_base(link["url"])
        md = fetch(md_url)
        if not md or len(md) < 200:
            time.sleep(0.1)
            continue
        page_url = md_url[:-3] if md_url.endswith(".md") else md_url
        rel = page_url.replace("https://developers.cloudflare.com", "").strip("/")
        rel = re.sub(r"/index$", "", rel) or "index"
        if not rel.startswith(prefix):
            rel = f"{prefix}/{rel}"
        for c in chunk_markdown(md, rel):
            c["lastmod"] = link.get("lastmod")
            out.append(make_chunk("cloudflare", "latest", LICENSE_INFO, page_url, c))
        if i % 10 == 0:
            print(f"    [{prefix}] {i + 1}/{len(links)} pages, {len(out)} chunks")
        time.sleep(0.1)
    return out


def main():
    existing: dict[str, dict] = {}
    if CHUNKS.exists():
        for line in open(CHUNKS):
            d = json.loads(line)
            existing.setdefault(d["path"], d)  # dedup key: page path
    print(f"existing cloudflare chunks: {sum(1 for _ in open(CHUNKS)) if CHUNKS.exists() else 0}")

    new_chunks = []
    for llms_url, prefix in TARGETS:
        print(f"\n=== {prefix} ===")
        links = collect_pages(llms_url, prefix)
        got = fetch_pages(links, prefix)
        added = 0
        for c in got:
            if c["path"] not in existing:
                existing[c["path"]] = c
                new_chunks.append(c)
                added += 1
        print(f"  [{prefix}] {len(got)} chunks fetched, {added} new (rest deduped)")

    if not new_chunks:
        print("\nnothing new — skipping write")
        return

    with CHUNKS.open("a") as f:
        for c in new_chunks:
            f.write(json.dumps(c) + "\n")
    print(f"\nappended {len(new_chunks)} chunks -> {CHUNKS.name}")
    print("next: python3 indexer/build_shards.py")


if __name__ == "__main__":
    main()
