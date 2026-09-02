#!/usr/bin/env python3
"""Diagnose the 4 failed vendor restores (svelte, langchain, clickhouse, docusaurus)."""
import sys, json, urllib.request
sys.path.insert(0, "indexer")
from reingest_gaps import fetch

# 1. svelte llms.txt
t = fetch("https://svelte.dev/llms.txt")
print("svelte llms.txt:", f"{len(t)} chars" if t else "FAILED")
if t:
    print("  head:", t[:150].replace("\n", " | "))

# 2. langchain tree structure
for repo, branch in [("langchain-ai/langchain", "master"), ("langchain-ai/langchain", "main")]:
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1",
            headers={"User-Agent": "documesh"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        paths = [x["path"] for x in d.get("tree", []) if x["path"].endswith(".md")]
        docs = [p for p in paths if p.startswith("docs/")]
        print(f"langchain {branch}: {len(paths)} .md total, {len(docs)} under docs/")
        for p in docs[:5]:
            print("   ", p)
        break
    except Exception as e:
        print(f"langchain {branch}: {str(e)[:80]}")

# 3. clickhouse + docusaurus docs paths
for repo, branch, pref in [("clickhouse/clickhouse", "master", "docs/"),
                           ("facebook/docusaurus", "main", "docs/")]:
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1",
            headers={"User-Agent": "documesh"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        paths = [x["path"] for x in d.get("tree", []) if x["path"].endswith(".md") and x["path"].startswith(pref)]
        print(f"{repo} {branch}: {len(paths)} .md under {pref}")
        for p in paths[:5]:
            print("   ", p)
    except Exception as e:
        print(f"{repo}: {str(e)[:80]}")
