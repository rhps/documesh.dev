#!/usr/bin/env python3
"""
Rebrand: Docs Mesh → Documesh across all app/worker/indexer files.
Also: hero/fallback vendor list uses the API at runtime (already dynamic),
so only literal names need updating.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

REPLACEMENTS = [
    # product name
    ("Docs Mesh", "Documesh"),
    ("docs-mesh", "documesh"),           # worker names / identifiers stay lowercase
    ("Docs-Mesh", "Documesh"),
    # footer credit
]

FILES = [
    "app/index.html",
    "app/app.html",
    "app/capabilities.html",
    "app/webmcp.html",
    "app/coverage.html",
    "worker/src/index.js",
    "worker/src/search-core.js",
    "worker/dev-server.mjs",
    "worker/eval.mjs",
    "indexer/fetch_docs.py",
    "indexer/enrich_docs.py",
    "indexer/foundation_docs.py",
    "README.md",
    "LICENSE",
    "package.json",
    "wrangler.jsonc",
]

for rel in FILES:
    p = BASE / rel
    if not p.exists():
        continue
    text = p.read_text()
    orig = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != orig:
        p.write_text(text)
        n = sum(orig.count(o) for o, _ in REPLACEMENTS)
        print(f"✅ {rel}: {n} replacements")
    else:
        print(f"–  {rel}: no changes")
