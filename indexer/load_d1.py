#!/usr/bin/env python3
"""
Backfill D1 (documesh-search) from data/chunks/*.jsonl.

Uses D1 HTTP API with BOUND PARAMETERS — doc content containing quotes,
semicolons, or SQL keywords is safe.

Idempotent: upserts by chunk_id.

Usage:
  python3 indexer/load_d1.py            # remote; needs CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID
  python3 indexer/load_d1.py --dry      # parse & count only
Env: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, optional D1_DATABASE_ID
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
DB_ID = os.environ.get("D1_DATABASE_ID", "0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b")
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
WORKERS = 8            # parallel HTTP calls
RETRY = 3

URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query"

UPSERT = ("INSERT INTO chunks (chunk_id, vendor, version, title, heading_path, path, "
          "source_url, license, attribution, last_updated, snippet, content) "
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
          "ON CONFLICT(chunk_id) DO UPDATE SET "
          "vendor=excluded.vendor, version=excluded.version, title=excluded.title, "
          "heading_path=excluded.heading_path, path=excluded.path, "
          "source_url=excluded.source_url, license=excluded.license, "
          "attribution=excluded.attribution, last_updated=excluded.last_updated, "
          "snippet=excluded.snippet, content=excluded.content")


def make_snippet(content: str, max_chars: int = 280) -> str:
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", content)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    snippet = next((p for p in paras
                    if len(p) > 80 and not re.match(r"^(last updated|copy as markdown|\|)", p, re.I)),
                   paras[0] if paras else "")
    snippet = snippet.replace("\n", " ").strip()
    if len(snippet) <= max_chars:
        return snippet
    return snippet[:max_chars].rsplit(" ", 1)[0] + "…"


def load_rows():
    rows = []
    for f in sorted(CHUNKS_DIR.glob("*.jsonl")):
        for line in f.open():
            c = json.loads(line)
            rows.append([
                c["chunk_id"], c["vendor"], c.get("version", "latest"), c["title"],
                c.get("heading_path"), c.get("path"), c["source_url"], c["license"],
                c.get("attribution"), c.get("last_updated"),
                make_snippet(c.get("content", "")), c["content"],
            ])
    return rows


def upsert_one(params):
    body = json.dumps({"sql": UPSERT, "params": params})
    req = urllib.request.Request(URL, data=body.encode(), headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }, method="POST")
    for attempt in range(RETRY):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
            if d.get("success"):
                return True
            err = str(d.get("errors"))[:150]
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read().decode()[:120]}"
        except Exception as e:
            err = str(e)[:120]
        time.sleep(1.5 * (attempt + 1))
    print(f"    !! row failed after {RETRY} tries: {err}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if not args.dry and (not TOKEN or not ACCOUNT_ID):
        print("need CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID")
        sys.exit(1)

    rows = load_rows()
    hist: dict[str, int] = {}
    for r in rows:
        hist[r[1]] = hist.get(r[1], 0) + 1
    print(f"loaded {len(rows)} rows, {len(hist)} vendors")

    if args.dry:
        print("dry run — nothing executed")
        return

    t0 = time.time()
    ok = 0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(upsert_one, r): i for i, r in enumerate(rows)}
        done = 0
        for fut in cf.as_completed(futures):
            done += 1
            if fut.result():
                ok += 1
            if done % 2000 == 0:
                print(f"  {done}/{len(rows)} ({ok} ok, {done - ok} failed) — {time.time()-t0:.0f}s")

    print(f"\nDONE: {ok}/{len(rows)} rows in {time.time()-t0:.0f}s")
    if ok != len(rows):
        print("!! some rows FAILED — re-run to retry (idempotent)")
        sys.exit(1)


if __name__ == "__main__":
    main()
