#!/usr/bin/env python3
"""
Backfill LOCAL D1 (wrangler dev / miniflare) directly via its SQLite file or
the local d1 execute. Faster than remote; used for verification before touching prod.
"""
from __future__ import annotations
import json, re, subprocess, sys, tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "indexer"))
from load_d1 import load_rows, upsert_sql  # reuse

def run_local(sql: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as tf:
        tf.write(sql)
        path = tf.name
    try:
        res = subprocess.run(
            ["npx", "wrangler", "d1", "execute", "documesh-search", "--local", "--file", path, "-y"],
            capture_output=True, text=True, timeout=300,
        )
        return res.returncode == 0
    finally:
        Path(path).unlink(missing_ok=True)

rows = load_rows()
print(f"loaded {len(rows)} rows")
BATCH = 200
batches = [rows[i:i+BATCH] for i in range(0, len(rows), BATCH)]
ok = 0
for i, b in enumerate(batches):
    if run_local(upsert_sql(b)):
        ok += 1
        if (i+1) % 20 == 0 or i+1 == len(batches):
            print(f"  {i+1}/{len(batches)} batches")
    else:
        print(f"  batch {i+1} FAILED")
        sys.exit(1)
print(f"DONE: {ok}/{len(batches)} batches into LOCAL documesh-search")
