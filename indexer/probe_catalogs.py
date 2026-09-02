#!/usr/bin/env python3
"""Probe llms.txt catalogs for the 4 remaining failed vendors."""
import sys
sys.path.insert(0, "indexer")
from reingest_gaps import fetch

CANDIDATES = {
    "svelte-core": [
        "https://svelte.dev/docs/llms.txt",
        "https://svelte.dev/llms-full.txt",
    ],
    "langchain": [
        "https://python.langchain.com/llms.txt",
        "https://docs.langchain.com/llms.txt",
        "https://langchain-ai.github.io/langchain/llms.txt",
    ],
    "clickhouse": [
        "https://clickhouse.com/docs/llms.txt",
        "https://clickhouse.com/llms.txt",
    ],
    "docusaurus": [
        "https://docusaurus.io/llms.txt",
        "https://docusaurus.io/docs/llms.txt",
    ],
}

for vendor, urls in CANDIDATES.items():
    print(f"\n=== {vendor} ===")
    for u in urls:
        t = fetch(u, timeout=20)
        n_links = 0
        if t:
            import re
            n_links = len(re.findall(r"^\s*[-*]\s*\[([^\]]+)\]\((https?://[^)]+)\)", t, re.M))
        status = f"{len(t)} chars, {n_links} md-links" if t else "FAILED"
        print(f"  {u} -> {status}")
        if t and n_links:
            print(f"    WINNER: {u}")
            break
