#!/usr/bin/env python3
"""Restore v2: the 4 vendors that need special handling.
- langchain: python.langchain.com/llms.txt (175 links)
- clickhouse: clickhouse.com/docs/llms.txt (145 links)
- svelte-core: svelte.dev/llms-full.txt (single-file full docs, MIT)
- docusaurus: git-tree probe with corrected prefixes, else honest failure
"""
import sys, re, json
sys.path.insert(0, "indexer")
import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def load_module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / "indexer" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

rg = load_module("reingest_gaps")
ti = load_module("tier_ingestion")
save_to = Path(BASE / "data" / "chunks")

def save(vendor, chunks):
    if not chunks:
        print(f"  !! {vendor}: 0 chunks")
        return 0
    out = save_to / f"{vendor}_latest.jsonl"
    with out.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"  -> {vendor}: {len(chunks)} chunks")
    return len(chunks)

# 1. langchain + clickhouse via catalogs
lic_l = rg.agent_permitted_lic("LangChain", "https://python.langchain.com/llms.txt")
save("langchain", rg.crawl_llms_catalog("langchain", "https://python.langchain.com/llms.txt", 175, lic_l))

lic_c = rg.agent_permitted_lic("ClickHouse", "https://clickhouse.com/docs/llms.txt")
save("clickhouse", rg.crawl_llms_catalog("clickhouse", "https://clickhouse.com/docs/llms.txt", 145, lic_c))

# 2. svelte-core: single-file full docs
print("=== svelte-core (llms-full.txt single-file) ===")
full = rg.fetch("https://svelte.dev/llms-full.txt", timeout=60)
if full:
    lic_s = rg.LIC_MIT("sveltejs/svelte")
    chunks = []
    for c in rg.chunk_markdown(full, "docs"):
        chunks.append(rg.make_chunk("svelte-core", lic_s, "https://svelte.dev/docs", c))
    save("svelte-core", chunks)
else:
    print("  !! svelte llms-full.txt fetch failed")

# 3. docusaurus: probe corrected git prefixes
print("=== docusaurus (git prefix probe) ===")
import urllib.request
found = None
for prefix in ["website/docs/", "packages/"]:
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/facebook/docusaurus/git/trees/main?recursive=1",
            headers={"User-Agent": "documesh"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        paths = [x["path"] for x in d.get("tree", []) if x["path"].endswith(".md") and x["path"].startswith(prefix)]
        print(f"  prefix {prefix}: {len(paths)} files")
        if len(paths) > 20:
            found = (prefix, paths)
            break
    except Exception as e:
        print(f"  prefix {prefix}: {str(e)[:80]}")
if found:
    prefix, paths = found
    lic_d = rg.LIC_MIT("facebook/docusaurus")
    out = []
    for rp in paths[:200]:
        raw = f"https://raw.githubusercontent.com/facebook/docusaurus/main/{rp}"
        md = rg.fetch(raw)
        if not md or len(md) < 250:
            continue
        rel = rp[len(prefix):].rstrip("/") if rp.startswith(prefix) else rp
        rel = re.sub(r"\.md$", "", rel) or "index"
        page = f"https://docusaurus.io/docs/{rel}"
        for c in rg.chunk_markdown(md, rel):
            out.append(rg.make_chunk("docusaurus", lic_d, page, c))
        import time as _t; _t.sleep(0.05)
    save("docusaurus", out)
else:
    print("  !! docusaurus: no usable in-repo docs tree — needs official docs crawl (deferred)")

print("\ndone.")
