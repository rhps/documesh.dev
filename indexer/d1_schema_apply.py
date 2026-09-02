#!/usr/bin/env python3
"""Apply d1/schema.statements.json to remote D1 via HTTP API."""
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

ACCOUNT = os.environ["CLOUDFLARE_ACCOUNT_ID"]
TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
DB = os.environ.get("D1_DATABASE_ID", "0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b")

def api(sql):
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DB}/query"
    req = urllib.request.Request(url, data=json.dumps({"sql": sql}).encode(), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}\nSQL was: {sql[:150]}")
    if not d.get("success"):
        raise RuntimeError(f"{str(d.get('errors'))[:300]}\nSQL was: {sql[:150]}")
    return d

stmts = json.load(open(BASE / "d1" / "schema.statements.json"))
print(f"{len(stmts)} statements")
for i, s in enumerate(stmts):
    api(s)
    print(f"  ok [{i+1}]: {s.splitlines()[0][:60]}")
print("schema applied")
