#!/usr/bin/env python3
"""
Restore the 6 advertised-but-unsearchable vendors whose chunk files were
never committed (data lost between machines). Reuses the original per-vendor
ingestion code by importing it:
  - nuxt, solid          <- indexer/enrich_docs.py VENDORS
  - langchain, clickhouse, docusaurus <- indexer/tier_ingestion.py JOBS
  - svelte-core          <- svelte.dev/llms.txt via reingest_gaps crawler
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS = BASE / "data" / "chunks"
sys.path.insert(0, str(BASE / "indexer"))

def load_module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / "indexer" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def save(vendor, chunks):
    if not chunks:
        print(f"  !! {vendor}: 0 chunks")
        return
    out = CHUNKS / f"{vendor}_latest.jsonl"
    with out.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"  -> {vendor}: {len(chunks)} chunks")

def main():
    # 1. enrich_docs vendors: nuxt, solid
    en = load_module("enrich_docs")
    for vendor, lic, fn in en.VENDORS:
        if vendor in ("nuxt", "solid"):
            print(f"=== {vendor} (enrich_docs) ===")
            try:
                save(vendor, fn())
            except Exception as e:
                print(f"  !! {vendor} FAILED: {str(e)[:100]}")

    # 2. tier_ingestion vendors: langchain, clickhouse, docusaurus
    ti = load_module("tier_ingestion")
    want = {"langchain", "clickhouse", "docusaurus"}
    for vendor, lic, fn in ti.JOBS:
        if vendor in want:
            print(f"=== {vendor} (tier_ingestion) ===")
            try:
                save(vendor, fn())
            except Exception as e:
                print(f"  !! {vendor} FAILED: {str(e)[:100]}")

    # 3. svelte-core via svelte.dev llms.txt
    rg = load_module("reingest_gaps")
    print("=== svelte-core (svelte.dev/llms.txt) ===")
    lic = rg.LIC_MIT("sveltejs/svelte")
    try:
        save("svelte-core", rg.crawl_llms_catalog("svelte-core", "https://svelte.dev/llms.txt", 250, lic))
    except Exception as e:
        print(f"  !! svelte-core FAILED: {str(e)[:100]}")

    print("\ndone. next: python3 indexer/build_shards.py && python3 indexer/coverage_audit.py")

if __name__ == "__main__":
    main()
