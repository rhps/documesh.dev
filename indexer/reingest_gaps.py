#!/usr/bin/env python3
"""
Re-ingest with per-vendor page budgets to close coverage gaps found by
coverage_audit.py, while keeping shards deployable:
  - CF Workers static asset limit: 25 MB per file
  - searchAcross loads 1 shard per query'd vendor; unfiltered queries load ALL
Per-vendor PAGE_BUDGETS sized so the largest projected shard stays <20 MB.

Usage: python3 indexer/reingest_gaps.py [vendor ...]   (default: all budget vendors)
"""
from __future__ import annotations
import json, re, sys, time, hashlib, urllib.request, urllib.error
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (compatible; documesh-indexer/1.0)"}
CHUNK_TARGET = 1800
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)

# page budgets chosen so projected shard stays under ~20MB
PAGE_BUDGETS = {
    "cloudflare": 900,      # ~3k catalog pages; largest vendor
    "clerk": 500,
    "kong": 500,
    "aws": 400,
    "anthropic": 300,
    "stripe": 300,
    "neon": 244,            # full catalog
    "turso": 286,           # full
    "sentry": 125,          # full
    "temporal": 105,        # full
    "elysia": 89,           # full
    "pulumi": 33,           # full
    "digitalocean": 293,    # full
    "ibmcloud": 197,        # full
    "hono": 89,             # full
}

CATALOG_URLS = {
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
    "hono": "https://hono.dev/llms.txt",
}

EXCLUDE_RE = re.compile(r"/(blog|changelog|release-notes)(/|$)")

def fetch(url, timeout=30, redirects=5):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308) and redirects > 0:
            loc = e.headers.get("Location")
            if loc:
                return fetch(loc, timeout, redirects - 1)
        print(f"    !! {e.code} {url[:90]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url[:90]}")
        return None

def parse_llms(txt):
    out = []
    if not txt:
        return out
    for m in re.finditer(r"^\s*[-*]?\s*\[([^\]]+)\]\(([^)\s]+)\)", txt, re.M):
        out.append({"title": m.group(1).strip(), "url": m.group(2).strip()})
    return out

def chunk_markdown(md, rel_path):
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    matches = list(HEADING_RE.finditer(md))
    if not matches:
        return []
    sections = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sections.append((level, m.group(2).strip(), md[start:end].strip()))
    chunks = []
    current_parents = {}
    for level, title, body in sections:
        current_parents[level] = title
        for l in list(current_parents):
            if l > level:
                del current_parents[l]
        breadcrumb = " > ".join(current_parents[l] for l in sorted(current_parents))
        if len(body) < 120:
            continue
        pieces = []
        if len(body) > CHUNK_TARGET * 2:
            buf, cur = [], ""
            for para in body.split("\n\n"):
                if len(cur) + len(para) > CHUNK_TARGET and cur:
                    buf.append(cur)
                    cur = para
                else:
                    cur = f"{cur}\n\n{para}".strip()
            if cur:
                buf.append(cur)
            pieces = buf
        else:
            pieces = [body]
        for j, piece in enumerate(pieces):
            chunks.append({"path": rel_path, "heading_path": breadcrumb, "title": title,
                           "part": j + 1 if len(pieces) > 1 else None, "content": piece[:4000]})
    return chunks

def chunk_id(vendor, c):
    slug = re.sub(r"[^a-z0-9]+", "-", f"{c['path']}#{c['heading_path']}".lower()).strip("-")[:80]
    h = hashlib.sha1(c["content"].encode()).hexdigest()[:8]
    return f"{vendor}:latest:{slug}:{h}"

def make_chunk(vendor, lic, url, c):
    return {
        "chunk_id": chunk_id(vendor, c), "vendor": vendor, "version": "latest",
        "path": c["path"], "heading_path": c["heading_path"], "title": c["title"],
        "content": c["content"], "source_url": url,
        "license": lic["license"], "license_url": lic["license_url"],
        "attribution": lic["attribution"],
        "last_updated": c.get("lastmod") or SNAPSHOT_DATE,
    }

def agent_permitted_lic(name, llms_url):
    return {"license": f"{name} Docs (agent-permitted via llms.txt)",
            "license_url": llms_url,
            "attribution": f"© {name} — via llms.txt agent-permitted interface"}

def md_url_of(u):
    u = u.split("?")[0].split("#")[0].rstrip("/")
    return u + ".md" if not u.endswith(".md") else u

def crawl_llms_catalog(vendor, index_url, cap, lic, exclude=r"/(blog|changelog)(/|$)", prioritize=None):
    """Generic llms.txt crawler: exact-URL dedupe, optional prioritization."""
    print(f"    [{vendor}] fetching catalog {index_url}")
    links = parse_llms(fetch(index_url))
    if prioritize:
        links.sort(key=lambda l: 0 if prioritize(l["url"]) else 1)
    seen, out = set(), []
    for i, link in enumerate(links):
        if len(out) >= cap:
            break
        url = link["url"].split("?")[0].split("#")[0].rstrip("/")
        if url.endswith(".txt") or url.endswith("/llms") or EXCLUDE_RE.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        md = fetch(md_url_of(url))
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.08)
            continue
        page = md_url_of(url)[:-3]
        rel = re.sub(r"^https?://[^/]+/", "", page).strip("/") or "index"
        for c in chunk_markdown(md, rel):
            c["lastmod"] = None
            out.append(make_chunk(vendor, lic, page, c))
        if i % 25 == 0:
            print(f"    [{vendor}] {i+1}/{len(links)} scanned, {len(out)} pages, {len(out)}+ chunks")
        time.sleep(0.08)
    return out

def crawl_cloudflare_two_stage(cap, lic):
    """Root llms.txt -> product llms.txt pages, prioritized: workers, hyperdrive,
    d1, terraform, dns, workers-kv, r2, durable-objects first; then breadth."""
    root = "https://developers.cloudflare.com/llms.txt"
    products = [l["url"] for l in parse_llms(fetch(root))
                if l["url"].rstrip("/").endswith("llms.txt")]
    priority = ("workers", "hyperdrive", "d1", "terraform", "dns", "workers-kv",
                "r2", "durable-objects", "queues", "vectorize", "pages", "streams")
    def rank(u):
        for i, p in enumerate(priority):
            if f"/{p}/" in u or u.rstrip("/").endswith(p):
                return i
        return len(priority)
    products.sort(key=rank)
    PRIORITY_PRODUCT_PAGES = 120   # deep on priority products
    REST_PRODUCT_PAGES = 6         # breadth over the rest
    pages, seen = [], set()
    for idx, purl in enumerate(products):
        budget = PRIORITY_PRODUCT_PAGES if rank(purl) < len(priority) else REST_PRODUCT_PAGES
        plinks = [l for l in parse_llms(fetch(purl)) if not l["url"].rstrip("/").endswith("llms.txt")]
        taken = 0
        for l in plinks:
            if taken >= budget or len(pages) >= cap:
                break
            u = l["url"].split("?")[0].split("#")[0].rstrip("/")
            if u in seen or EXCLUDE_RE.search(u):
                continue
            seen.add(u)
            pages.append(l)
            taken += 1
        if len(pages) >= cap:
            break
    print(f"    [cloudflare] {len(products)} product indexes -> {len(pages)} pages queued")
    out = []
    for i, link in enumerate(pages[:cap]):
        md = fetch(md_url_of(link["url"]))
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.08)
            continue
        page = md_url_of(link["url"])[:-3]
        rel = re.sub(r"^https?://developers\.cloudflare\.com/", "", page).strip("/") or "index"
        rel = re.sub(r"/index$", "", rel) or "index"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("cloudflare", lic, page, c))
        if i % 25 == 0:
            print(f"    [cloudflare] {i+1}/{min(len(pages), cap)} pages, {len(out)} chunks")
        time.sleep(0.08)
    return out

LIC_MIT = lambda repo: {"license": "MIT", "license_url": f"https://github.com/{repo}/blob/main/LICENSE",
                        "attribution": f"© {repo.split('/')[0]} contributors — MIT, via {repo}"}

def main():
    requested = [a for a in sys.argv[1:] if not a.startswith("-")]
    vendors = requested or list(PAGE_BUDGETS)
    for v in vendors:
        cap = PAGE_BUDGETS[v]
        if v == "cloudflare":
            lic = {"license": "CC-BY-4.0",
                   "license_url": "https://github.com/cloudflare/cloudflare-docs/blob/production/LICENSE",
                   "attribution": "© Cloudflare, Inc., CC BY 4.0 — via documesh"}
            chunks = crawl_cloudflare_two_stage(cap, lic)
        else:
            lic = agent_permitted_lic(v.capitalize(), CATALOG_URLS[v])
            chunks = crawl_llms_catalog(v, CATALOG_URLS[v], cap, lic)
        if not chunks:
            print(f"  !! {v}: 0 chunks — keeping existing file")
            continue
        outp = CHUNKS_DIR / f"{v}_latest.jsonl"
        with outp.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {v}: {len(chunks)} chunks -> {outp.name}")
        time.sleep(0.3)
    print("\nnext: python3 indexer/build_shards.py && python3 indexer/coverage_audit.py")

if __name__ == "__main__":
    main()
