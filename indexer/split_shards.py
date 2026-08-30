#!/usr/bin/env python3
"""
Split the index into per-vendor shards so the Worker loads only what it needs,
OR compress it for bundling. Simplest robust fix for CF free-tier 1MB/10MB limits:
gzip-compressed JSON loaded via fetch from static assets, decompressed in-stream.

Actually simplest: keep ONE file but check if CF Workers paid startup limit applies.
Free plan: Worker size limit 10MB (with assets separate). Our 34MB is too big.
Solution: split index into shards by vendor; worker loads lazily per query.
"""
import json
import gzip
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
idx = json.load(open(BASE / "data" / "search-index.json"))

docs = idx["docs"]
postings = idx["postings"]

# Per-vendor doc indices
from collections import defaultdict
vendor_docs = defaultdict(list)
vendor_doc_idx = defaultdict(dict)

for i, d in enumerate(docs):
    v = d["vendor"]
    new_i = len(vendor_docs[v])
    vendor_doc_idx[v][i] = new_i
    vendor_docs[v].append(d)

# Re-index postings per vendor with remapped indices
import math
vendor_postings = defaultdict(dict)
for tok, pl in postings.items():
    for old_i, w in pl:
        d = docs[old_i]
        v = d["vendor"]
        new_i = vendor_doc_idx[v][old_i]
        vendor_postings[v].setdefault(tok, []).append([new_i, w])

# Write per-vendor files
outdir = BASE / "data" / "shards"
outdir.mkdir(exist_ok=True)
total = 0
for v in vendor_docs:
    n_docs = len(vendor_docs[v])
    n_toks = len(vendor_postings.get(v, {}))
    payload = {"docs": vendor_docs[v], "postings": vendor_postings.get(v, {}), "built_at": idx["built_at"]}
    f = outdir / f"index_{v}.json.gz"
    with gzip.open(f, "wt", compresslevel=9) as fh:
        json.dump(payload, fh)
    sz = f.stat().st_size / 1e6
    total += sz
    print(f"  {v:15s} {n_docs:5d} docs, {n_toks:6d} tokens, {sz:.2f} MB gz")

print(f"\ntotal gzipped: {total:.1f} MB across {len(vendor_docs)} shards")
