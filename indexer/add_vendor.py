#!/usr/bin/env python3
"""
Documesh — Add Vendor Tool (L1: Admin CLI)

Adds a new documentation vendor to the mesh without code changes.
Detects the ingestion pattern automatically, crawls, chunks, and
updates the vendor registry.

Usage:
  python3 indexer/add_vendor.py \
    --name "Kubernetes" \
    --id "kubernetes" \
    --repo "kubernetes/website" \
    --docs-path "content/en/docs/" \
    --license "CC-BY-4.0" \
    --branch "main" \
    [--llms "https://example.com/llms.txt"] \
    [--include "getting-started/,concepts/"] \
    [--exclude "changelog,_test"] \
    [--cap 60]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
SHARDS_DIR = BASE / "data" / "shards"
REGISTRY = BASE / "data" / "vendors.json"
UA = {"User-Agent": "Mozilla/5.0 (documesh indexer)"}
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
CHUNK_TARGET = 1800
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")


# ─── fetch ───────────────────────────────────────────────────────────────────

def fetch(url, timeout=25, redirects=5):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308) and redirects > 0:
            loc = e.headers.get("Location") or ""
            if loc:
                from urllib.parse import urljoin
                return fetch(urljoin(url, loc), timeout, redirects - 1)
        print(f"    !! {e.code} {url[:80]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url[:80]}")
        return None


# ─── pattern detection ───────────────────────────────────────────────────────

def detect_pattern(llms_url=None, repo=None, docs_path=None, branch="main"):
    """Return the best ingestion pattern for this vendor."""
    if llms_url:
        txt = fetch(llms_url)
        if not txt:
            return None, "llms_url_unreachable"
        links = parse_llms_links(txt)
        md_links = [l for l in links if ".md" in l["url"].split("/")[-1]]
        if md_links:
            return {"type": "P1", "links": links, "llms_url": llms_url,
                    "base": llms_url.rsplit("/llms.txt", 1)[0]}, "P1:llms.txt→per-page.md"
        # check for single-file
        full = re.findall(r'\((https?://[^\s)]+llms-full\.txt)\)', txt)
        if full:
            return {"type": "P2", "file_url": full[0]}, "P2:llms-full.txt"
        # check for sitemap.md
        sm = re.findall(r'\((https?://[^\s)]+sitemap\.md)\)', txt)
        if sm:
            return {"type": "P3", "sitemap_url": sm[0]}, "P3:sitemap.md"
        # links that serve markdown via query param (e.g. IBM: ?format=markdown)
        fmt_md = [l for l in links if "format=markdown" in l["url"]]
        if fmt_md:
            return {"type": "P1", "links": links, "llms_url": llms_url,
                    "base": llms_url.rsplit("/llms.txt", 1)[0]}, "P1b:llms.txt→?format=markdown"
        return None, "llms.txt exists but no usable links"

    if repo and docs_path:
        return {"type": "P4", "repo": repo, "branch": branch, "path": docs_path}, "P4:git-repo"

    return None, "no pattern detected"


def parse_llms_links(text):
    return [{"title": m.group(1).strip(), "url": m.group(2).strip()}
            for m in re.finditer(r"^-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text or "", re.M)]


# ─── crawl: P1 (llms.txt → .md pages) ───────────────────────────────────────

def crawl_p1(vendor, pattern, lic, cap=60):
    txt = fetch(pattern["llms_url"])
    links = parse_llms_links(txt)
    base = pattern.get("base", "")
    default_base = base or pattern["llms_url"].rsplit("/", 1)[0]
    out = []
    for i, link in enumerate(links[:cap * 3]):  # scan more links (some lack .md)
        if len(out) >= cap:
            break
        url = link["url"]
        if not url.startswith("http"):
            url = default_base + (url if url.startswith("/") else "/" + url)
        if ".md" not in url.split("/")[-1]:
            # try appending .md; for ?format=markdown URLs the URL itself
            # already serves markdown, so try it as-is first
            if "format=markdown" in url:
                md_url = url
            else:
                md_url = url.rstrip("/") + ".md"
        else:
            md_url = url
        md = fetch(md_url)
        if (not md or len(md) < 200) and md_url != url:
            # fallback: try the bare URL too (some CMSs ignore .md suffix)
            md = fetch(url)
            md_url_used = url if md and len(md) >= 200 else md_url
        else:
            md_url_used = md_url
        if not md or len(md) < 200:
            time.sleep(0.08)
            continue
        page = md_url_used[:-3] if md_url_used.endswith(".md") else md_url_used
        page = page.split("?")[0]  # strip ?format=markdown from canonical URL
        rel = re.sub(r"^https?://[^/]+/", "", page).strip("/")
        rel = re.sub(r"\.md$", "", rel) or "index"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 15 == 0:
            print(f"    [{vendor}] {i}/{min(len(links), cap*3)} links, {len(out)} chunks")
        time.sleep(0.08)
    return out


def crawl_p2(vendor, pattern, lic, cap=40):
    """Single llms-full.txt file, split on H1."""
    txt = fetch(pattern["file_url"])
    if not txt:
        return []
    parts = re.split(r"^# ", txt, flags=re.M)[1:]
    out = []
    for p in parts[:cap]:
        title = p.split("\n", 1)[0].strip()[:80]
        body = f"# {p}"
        rel = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        for c in chunk_markdown(body, rel):
            c["title"] = c["title"] or title
            out.append(make_chunk(vendor, lic, pattern["file_url"], c))
    return out


def crawl_p3(vendor, pattern, lic, sitemap_url, base_url, cap=60):
    """Sitemap.md with title/path/Lastmod lines."""
    txt = fetch(sitemap_url)
    if not txt:
        return []
    entries = []
    for m in re.finditer(r"-\s+\[([^\]]+)\]\((/?[^\s)]+)\).*?Lastmod:\s*(\d{4}-\d{2}-\d{2})", txt):
        title, path, lastmod = m.group(1).strip(), m.group(2).rstrip("/"), m.group(3)
        url = base_url + path if path.startswith("/") else path
        entries.append({"title": title, "url": url, "lastmod": lastmod})
    print(f"    [{vendor}] sitemap: {len(entries)} pages")
    out = []
    for i, e in enumerate(entries[:cap]):
        md_url = e["url"] + ".md" if not e["url"].endswith(".md") else e["url"]
        md = fetch(md_url)
        if not md or len(md) < 200:
            time.sleep(0.08)
            continue
        rel = e["url"].replace(base_url, "").strip("/") or "index"
        rel = re.sub(r"\.md$", "", rel) or "index"
        for c in chunk_markdown(md, rel):
            c["lastmod"] = e["lastmod"]
            out.append(make_chunk(vendor, lic, e["url"], c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(entries), cap)} pages, {len(out)} chunks")
        time.sleep(0.08)
    return out


def crawl_p4(vendor, pattern, lic, cap=60, include=(), exclude=()):
    """Git repo tree-walk, raw.githubusercontent fetch."""
    repo, branch, content_path = pattern["repo"], pattern.get("branch", "main"), pattern["path"]
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        print(f"    !! tree fetch failed: {e}")
        return []
    paths = sorted(t["path"] for t in d.get("tree", [])
                   if t["path"].startswith(content_path) and t["path"].endswith(".md"))
    if include:
        paths = [p for p in paths if any(inc in p for inc in include)]
    for ex in exclude:
        paths = [p for p in paths if ex not in p]
    print(f"    [{vendor}] {len(paths)} md files matched")
    out = []
    for i, rp in enumerate(paths[:cap]):
        raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{rp}"
        md = fetch(raw)
        if not md or len(md) < 200:
            time.sleep(0.06)
            continue
        rel = rp[len(content_path):].lstrip("/")
        rel = re.sub(r"\.md$", "", rel)
        rel = re.sub(r"/_index$", "", rel)
        rel = re.sub(r"/index$", "", rel) or "index"
        page = f"https://{repo.split('/')[0]}.io/{rel}/" if "kube" in vendor else f"https://github.com/{repo}/tree/{branch}/{rp}"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(paths), cap)} pages, {len(out)} chunks")
        time.sleep(0.06)
    return out


# ─── shared utilities ────────────────────────────────────────────────────────

def chunk_markdown(md, rel):
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    matches = list(HEADING_RE.finditer(md))
    if not matches:
        return []
    chunks, parents = [], {}
    for i, m in enumerate(matches):
        level, title = len(m.group(1)), m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        body = md[m.start():end].strip()
        parents[level] = title
        for l in [l for l in list(parents) if l > level]:
            del parents[l]
        crumb = " > ".join(parents[l] for l in sorted(parents))
        if len(body) < 120:
            continue
        pieces = [body]
        if len(body) > CHUNK_TARGET * 2:
            pieces, cur = [], ""
            for para in body.split("\n\n"):
                if len(cur) + len(para) > CHUNK_TARGET and cur:
                    pieces.append(cur)
                    cur = para
                else:
                    cur = f"{cur}\n\n{para}".strip()
            if cur:
                pieces.append(cur)
        for j, piece in enumerate(pieces):
            chunks.append({"path": rel, "heading_path": crumb, "title": title,
                           "part": j + 1 if len(pieces) > 1 else None,
                           "content": piece[:4000]})
    return chunks


def make_chunk(vendor, lic, url, c):
    slug = re.sub(r"[^a-z0-9]+", "-", f"{c['path']}#{c['heading_path']}".lower()).strip("-")[:80]
    h = hashlib.sha1(c["content"].encode()).hexdigest()[:8]
    return {"chunk_id": f"{vendor}:latest:{slug}:{h}", "vendor": vendor, "version": "latest",
            "path": c["path"], "heading_path": c["heading_path"], "title": c["title"],
            "content": c["content"], "source_url": url,
            "license": lic["license"], "license_url": lic["license_url"],
            "attribution": lic["attribution"], "last_updated": c.get("lastmod") or SNAPSHOT_DATE}


# ─── registry update ─────────────────────────────────────────────────────────

REGISTRY_FILE = BASE / "data" / "vendors.json"


def update_registry(vendor_id, name, lic, origin):
    reg = {}
    if REGISTRY_FILE.exists():
        reg = json.load(open(REGISTRY_FILE))
    reg[vendor_id] = {
        "name": name,
        "license": lic["license"],
        "license_url": lic["license_url"],
        "docs_origin": origin,
        "attribution_required": True,
        "added": SNAPSHOT_DATE,
    }
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, indent=1))
    print(f"  registry updated: {vendor_id}")


def load_registry():
    if REGISTRY_FILE.exists():
        return json.load(open(REGISTRY_FILE))
    return {}


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Add a documentation vendor to Documesh")
    p.add_argument("--name", required=True, help="Display name (e.g. 'Kubernetes')")
    p.add_argument("--id", required=True, help="Vendor ID (e.g. 'kubernetes')")
    p.add_argument("--repo", help="GitHub repo (e.g. 'kubernetes/website') for P4")
    p.add_argument("--docs-path", help="Docs content path in repo for P4")
    p.add_argument("--branch", default="main", help="Git branch for P4")
    p.add_argument("--llms", help="llms.txt URL for P1/P2/P3")
    p.add_argument("--sitemap", help="sitemap.md URL for P3")
    p.add_argument("--base-url", help="Base URL for P1/P3 page links")
    p.add_argument("--license", required=True, help="License SPDX (e.g. 'MIT', 'Apache-2.0', 'llms.txt agent-permitted')")
    p.add_argument("--license-url", default="", help="URL to license file")
    p.add_argument("--cap", type=int, default=400, help="Max pages to crawl")
    p.add_argument("--include", default="", help="Comma-separated include filters for P4")
    p.add_argument("--exclude", default="changelog,_test,cmdref", help="Comma-separated exclude filters")
    args = p.parse_args()

    lic = {"license": args.license, "license_url": args.license_url,
           "attribution": f"© {args.name} — {args.license}, via Documesh"}

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # detect pattern
    if args.llms:
        pattern, ptype = detect_pattern(llms_url=args.llms)
    elif args.repo and args.docs_path:
        pattern, ptype = detect_pattern(repo=args.repo, docs_path=args.docs_path, branch=args.branch)
    elif args.sitemap:
        pattern = {"type": "P3", "sitemap_url": args.sitemap, "base_url": args.base_url or ""}
        ptype = "P3:sitemap"
    else:
        print("❌ Need --llms OR (--repo + --docs-path) OR --sitemap")
        sys.exit(1)

    print(f"pattern: {ptype}")

    # crawl
    if ptype.startswith("P1"):
        chunks = crawl_p1(args.id, pattern, lic, cap=args.cap)
    elif ptype.startswith("P2"):
        chunks = crawl_p2(args.id, pattern, lic)
    elif ptype.startswith("P3"):
        chunks = crawl_p3(args.id, pattern, lic, pattern["sitemap_url"],
                          pattern.get("base_url", ""), cap=args.cap)
    elif ptype.startswith("P4"):
        inc = [x.strip() for x in args.include.split(",") if x.strip()] if args.include else ()
        exc = [x.strip() for x in args.exclude.split(",") if x.strip()]
        chunks = crawl_p4(args.id, pattern, lic, cap=args.cap, include=inc, exclude=exc)
    else:
        chunks = []

    if not chunks:
        print(f"❌ {args.id}: 0 chunks — aborting")
        sys.exit(1)

    # write chunk file
    outp = CHUNKS_DIR / f"{args.id}_latest.jsonl"
    with outp.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"\n✅ {args.id}: {len(chunks)} chunks → {outp.name}")

    # update registry
    update_registry(args.id, args.name, lic, ptype)

    print(f"\nNext: python3 indexer/build_index.py && node worker/eval.mjs")


if __name__ == "__main__":
    main()
