#!/usr/bin/env python3
"""
Coverage audit v2 — exact-URL matching against each vendor's own catalog.
- Expands two-stage catalogs (cloudflare: root llms.txt -> product llms.txt -> pages)
- Excludes /blog/ and obvious non-docs sections from the catalog denominator
- Exact match on normalized URL (host + path), no tail heuristics
"""
from __future__ import annotations
import json, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "documesh-coverage-audit/0.2"}

TWO_STAGE = {"cloudflare": "https://developers.cloudflare.com/llms.txt"}
ONE_STAGE = {
    "netlify": "https://docs.netlify.com/llms.txt",
    "aws": "https://docs.aws.amazon.com/llms.txt",
    "digitalocean": "https://docs.digitalocean.com/llms.txt",
    "ibmcloud": "https://cloud.ibm.com/docs/llms.txt",
    "anthropic": "https://platform.claude.com/llms.txt",
    "neon": "https://neon.com/docs/llms.txt",
    "clerk": "https://clerk.com/docs/llms.txt",
    "pulumi": "https://www.pulumi.com/llms.txt",
    "temporal": "https://docs.temporal.io/llms.txt",
    "kong": "https://developer.konghq.com/llms.txt",
    "elysia": "https://elysiajs.com/llms.txt",
    "turso": "https://docs.turso.tech/llms.txt",
    "sentry": "https://docs.sentry.io/llms.txt",
    "stripe": "https://docs.stripe.com/llms.txt",
    "bun": "https://bun.com/docs/llms.txt",
    "upstash": "https://docs.upstash.com/llms.txt",
    "hono": "https://hono.dev/llms.txt",
}

EXCLUDE = re.compile(r"/(blog|changelog|release-notes|whats-new|newsletter)(/|$)")

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return None

def norm(u: str) -> str:
    u = u.split("?")[0].split("#")[0].rstrip("/")
    u = re.sub(r"\.(md|mdx)$", "", u)
    u = re.sub(r"/index$", "", u)
    return u.lower()

def links(txt):
    return [m.group(1) for m in re.finditer(r"\((https?://[^)\s]+)\)", txt)]

def catalog_pages(vendor, llms_url):
    txt = fetch(llms_url)
    if not txt:
        return None
    pages = set()
    if vendor in TWO_STAGE:  # root -> product llms.txt -> pages
        products = [u for u in links(txt) if u.rstrip("/").endswith("llms.txt")]
        for p in products[:60]:
            ptxt = fetch(p)
            time.sleep(0.05)
            if not ptxt:
                continue
            for u in links(ptxt):
                nu = norm(u)
                if nu.endswith("/llms") or nu.endswith("/llms.txt"):
                    continue
                if not EXCLUDE.search(nu):
                    pages.add(nu)
    else:
        for u in links(txt):
            nu = norm(u)
            if nu.endswith("/llms") or nu.endswith("/llms.txt"):
                continue
            if not EXCLUDE.search(nu):
                pages.add(nu)
    return pages

def our_pages(vendor):
    f = BASE / "data" / "chunks" / f"{vendor}_latest.jsonl"
    if not f.exists():
        f = BASE / "data" / "chunks" / f"{vendor}_multi.jsonl"
    pages = set()
    if not f.exists():
        return pages
    for line in open(f):
        d = json.loads(line)
        pages.add(norm(d["source_url"]))
    return pages

def main():
    print(f"{'vendor':<14} {'catalog':>8} {'ours':>6} {'cov%':>7}  status")
    print("-" * 60)
    report = {}
    cats = dict(ONE_STAGE)
    for vendor, llms_url in TWO_STAGE.items():
        cats[vendor] = llms_url
    for vendor, llms_url in cats.items():
        cat = catalog_pages(vendor, llms_url)
        ours = our_pages(vendor)
        if cat is None:
            print(f"{vendor:<14} {'unreach':>8} {len(ours):>6} {'----':>7}  llms.txt unreachable")
            report[vendor] = {"catalog": None, "ours": len(ours)}
            continue
        covered = cat & ours
        missing = sorted(cat - ours)
        pct = 100 * len(covered) / len(cat) if cat else 0
        flag = "OK" if pct >= 90 else ("PARTIAL" if pct >= 50 else "GAPS")
        print(f"{vendor:<14} {len(cat):>8} {len(ours):>6} {pct:>6.1f}%  {flag}")
        report[vendor] = {"catalog": len(cat), "ours": len(ours),
                          "pct": round(pct, 1), "missing": missing}
        time.sleep(0.3)
    out = BASE / "data" / "coverage_audit.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nfull gap lists -> {out}")

if __name__ == "__main__":
    main()
