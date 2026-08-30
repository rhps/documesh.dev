#!/usr/bin/env python3
"""Verify chunk quality: license fields, content sanity, spot checks."""
import json
from pathlib import Path

data = Path(__file__).resolve().parent.parent / "data" / "chunks"
required = ["chunk_id", "vendor", "version", "path", "heading_path", "title",
            "content", "source_url", "license", "attribution", "last_updated"]

fail = 0
total = 0
for f in sorted(data.glob("*.jsonl")):
    good, bad = 0, 0
    samples = []
    with f.open() as fh:
        for line in fh:
            total += 1
            c = json.loads(line)
            missing = [k for k in required if k not in c or not c[k]]
            if missing:
                bad += 1
                if bad <= 2:
                    print(f"  MISSING {missing} in {c.get('chunk_id','?')}")
            else:
                good += 1
                if len(samples) < 2:
                    samples.append(c)
    print(f"{f.name}: {good} good, {bad} bad")
    fail += bad
    for s in samples:
        print(f"   sample: [{s['vendor']}|{s['version']}] {s['title'][:50]} | lic={s['license'][:30]} | {s['source_url'][:60]}")

print(f"\nTOTAL: {total} chunks, {fail} missing fields")
exit(0 if fail == 0 and total > 1000 else 1)
