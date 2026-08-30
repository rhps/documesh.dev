#!/usr/bin/env python3
"""
Documesh Indexer — Loop 1
Fetches markdown docs from legally-verified sources, chunks by heading,
stamps license/attribution metadata on every chunk.

Sources (verified 2026-08-30, see docs/MVP_PLAN.md):
  - Cloudflare:  .md endpoints, CC-BY-4.0, CORS *
  - Netlify:     .md endpoints via llms.txt index, docs (c) Netlify, agent-invited
  - Vercel:      llms.txt index (+ linked md pages), docs (c) Vercel, agent-invited
  - Kubernetes:  raw.githubusercontent.com (CC-BY-4.0), version branches
"""

from __future__ import annotations

import json
import re
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
CHUNKS_DIR = BASE / "chunks"
SNAPSHOT = BASE / "snapshot.json"
UA = {"User-Agent": "documesh-indexer/0.1 (hackathon; contact: devpost)"}
MAX_PAGES_PER_VENDOR = 120        # v1 cap to keep build fast
CHUNK_TARGET_CHARS = 1800         # ~450 tokens

SNAPSHOT_DATE = time.strftime("%Y-%m-%d")


def fetch(url: str, timeout: int = 30, redirects: int = 5) -> str | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        # Python 3.9 urllib does not follow 308 — handle manually
        if e.code in (301, 302, 307, 308) and redirects > 0:
            loc = e.headers.get("Location")
            if loc:
                return fetch(loc, timeout, redirects - 1)
        print(f"    !! fetch failed {url}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"    !! fetch failed {url}: {e}")
        return None


# ---------------------------------------------------------------- llms.txt
def parse_llms_txt(text: str) -> list[dict]:
    """Extract links from llms.txt format: - [title](url): desc"""
    links = []
    for m in re.finditer(r"^-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text, re.M):
        title, url, desc = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip()
        links.append({"title": title, "url": url, "desc": desc})
    return links


# ---------------------------------------------------------------- chunking
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)


def chunk_markdown(md: str, rel_path: str) -> list[dict]:
    """Split markdown into heading-scoped chunks, keeping heading breadcrumb."""
    # strip frontmatter
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
    # build breadcrumb: merge small sections into parents when too short
    current_parents: dict[int, str] = {}
    for level, title, body in sections:
        current_parents[level] = title
        # clear deeper levels
        for l in list(current_parents):
            if l > level:
                del current_parents[l]
        breadcrumb = " > ".join(current_parents[l] for l in sorted(current_parents))

        if len(body) < 120:
            continue  # skip tiny fragments (indexes, anchors)

        # if body is huge, split on paragraphs
        pieces = []
        if len(body) > CHUNK_TARGET_CHARS * 2:
            buf, cur = [], ""
            for para in body.split("\n\n"):
                if len(cur) + len(para) > CHUNK_TARGET_CHARS and cur:
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
            chunks.append({
                "path": rel_path,
                "heading_path": breadcrumb,
                "title": title,
                "part": j + 1 if len(pieces) > 1 else None,
                "content": piece[:4000],
            })
    return chunks


def chunk_id(vendor: str, version: str, c: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{c['path']}#{c['heading_path']}".lower()).strip("-")[:80]
    h = hashlib.sha1(c["content"].encode()).hexdigest()[:8]
    return f"{vendor}:{version}:{slug}:{h}"


# ---------------------------------------------------------------- vendors
def strip_base(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def make_chunk(vendor: str, version: str, license_info: dict, url: str, c: dict) -> dict:
    return {
        "chunk_id": chunk_id(vendor, version, c),
        "vendor": vendor,
        "version": version,
        "path": c["path"],
        "heading_path": c["heading_path"],
        "title": c["title"],
        "content": c["content"],
        "source_url": url,
        "license": license_info["license"],
        "license_url": license_info["license_url"],
        "attribution": license_info["attribution"],
        "last_updated": c.get("lastmod") or SNAPSHOT_DATE,
    }


def crawl_md_endpoint(base_url: str, links: list[dict], vendor: str, version: str,
                      license_info: dict, max_pages: int) -> list[dict]:
    """Fetch each link's page with .md suffix."""
    out = []
    for i, link in enumerate(links[:max_pages]):
        url = strip_base(link["url"])
        if not url.startswith("http"):
            continue
        md_url = url + ".md" if not url.endswith(".md") else url
        md = fetch(md_url)
        if not md or len(md) < 200:
            time.sleep(0.15)
            continue
        rel = url.replace(base_url, "").strip("/") or "index"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, version, license_info, url, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(links), max_pages)} pages, {len(out)} chunks")
        time.sleep(0.12)
    return out


def crawl_cloudflare() -> tuple[str, str, list[dict]]:
    vendor, version = "cloudflare", "latest"
    license_info = {
        "license": "CC-BY-4.0",
        "license_url": "https://github.com/cloudflare/cloudflare-docs/blob/production/LICENSE",
        "attribution": "© Cloudflare, Inc., CC BY 4.0 — via documesh",
    }
    base = "https://developers.cloudflare.com"
    txt = fetch(f"{base}/llms.txt")
    product_llms = parse_llms_txt(txt or "")
    # Two-stage: root llms.txt -> product llms.txt -> page links (which END in index.md/.md)
    page_links: dict[str, dict] = {}
    for pl in product_llms[:40]:
        purl = strip_base(pl["url"])
        if not purl.startswith("http"):
            continue
        # purl already IS the product llms.txt URL (e.g. .../workers/llms.txt)
        ptxt = fetch(purl)
        if not ptxt:
            continue
        for link in parse_llms_txt(ptxt):
            lurl = strip_base(link["url"])
            if lurl.startswith("http") and ".md" in lurl.split("/")[-1]:
                page_links[lurl] = link
        time.sleep(0.08)
    # Fetch pages: product llms.txt links point directly to .md pages
    def cf_fetch_pages(links, base, vendor, version, license_info, max_pages):
        out = []
        for i, link in enumerate(links[:max_pages]):
            md_url = strip_base(link["url"])  # already ends with .md
            md = fetch(md_url)
            if not md or len(md) < 200:
                time.sleep(0.1)
                continue
            page_url = md_url[:-3] if md_url.endswith(".md") else md_url
            rel = page_url.replace(base, "").strip("/")
            rel = re.sub(r"/index$", "", rel) or "index"
            for c in chunk_markdown(md, rel):
                out.append(make_chunk(vendor, version, license_info, page_url, c))
            if i % 10 == 0:
                print(f"    [{vendor}] {i+1}/{min(len(links), max_pages)} pages, {len(out)} chunks")
            time.sleep(0.1)
        return out

    links = list(page_links.values())
    print(f"    cloudflare: {len(product_llms)} product indexes -> {len(links)} pages")
    return vendor, version, cf_fetch_pages(links, base, vendor, version, license_info, MAX_PAGES_PER_VENDOR)


def crawl_netlify() -> tuple[str, str, list[dict]]:
    vendor, version = "netlify", "latest"
    license_info = {
        "license": "Netlify Docs (agent-permitted via llms.txt)",
        "license_url": "https://docs.netlify.com/llms.txt",
        "attribution": "© Netlify, Inc. — via docs.netlify.com llms.txt interface",
    }
    base = "https://docs.netlify.com"
    txt = fetch(f"{base}/llms.txt")
    links = parse_llms_txt(txt or "")
    print(f"    netlify llms.txt: {len(links)} links")
    out = []
    for i, link in enumerate(links[:MAX_PAGES_PER_VENDOR]):
        url = strip_base(link["url"])
        if not url.startswith("http"):
            continue
        md_url = url + ".md" if not url.endswith(".md") else url
        md = fetch(md_url)
        if not md or len(md) < 200:
            time.sleep(0.15)
            continue
        rel = url.replace(base, "").strip("/") or "index"
        rel = re.sub(r"\.md$", "", rel) or "index"
        canonical = f"{base}/{rel}/"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, version, license_info, canonical, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(links), MAX_PAGES_PER_VENDOR)} pages, {len(out)} chunks")
        time.sleep(0.12)
    return vendor, version, out


VERCEL_SITEMAP_RE = re.compile(
    r"-\s+\[([^\]]+)\]\((/docs/[^\s)]+)\).*?Lastmod:\s*(\d{4}-\d{2}-\d{2})", re.M)


def crawl_vercel() -> tuple[str, str, list[dict]]:
    vendor, version = "vercel", "latest"
    license_info = {
        "license": "Vercel Docs (agent-permitted via llms.txt); framework docs MIT",
        "license_url": "https://vercel.com/docs/llms.txt",
        "attribution": "© Vercel, Inc. — via vercel.com/docs llms.txt interface",
    }
    base = "https://vercel.com"
    txt = fetch(f"{base}/docs/sitemap.md")
    links = []
    seen: set[str] = set()
    for m in VERCEL_SITEMAP_RE.finditer(txt or ""):
        title, rel, lastmod = m.group(1).strip(), m.group(2).rstrip("/"), m.group(3)
        url = base + rel
        if url in seen:
            continue
        seen.add(url)
        links.append({"title": title, "url": url, "desc": "", "lastmod": lastmod})
    print(f"    vercel sitemap: {len(links)} pages")
    out = []
    for i, link in enumerate(links[:60]):
        md = fetch(link["url"] + ".md")
        if not md or len(md) < 200:
            time.sleep(0.12)
            continue
        rel_path = link["url"].replace(f"{base}/docs", "").strip("/") or "index"
        for c in chunk_markdown(md, rel_path):
            c["lastmod"] = link.get("lastmod")
            out.append(make_chunk(vendor, version, license_info, link["url"], c))
        if i % 10 == 0:
            print(f"    [vercel] {i+1}/{min(len(links), 60)} pages, {len(out)} chunks")
        time.sleep(0.12)
    return vendor, version, out


K8S_VERSIONS = ["1.32", "1.29"]  # branch = release-{ver}
K8S_TOPICS = [
    "concepts/workloads/pods/_index.md",
    "concepts/workloads/pods/pod-lifecycle.md",          # CrashLoopBackOff, restart policy
    "concepts/workloads/pods/init-containers.md",
    "concepts/workloads/deployments/_index.md",
    "concepts/services-networking/service/_index.md",
    "concepts/configuration/configmaps/_index.md",
    "concepts/configuration/secrets/_index.md",
    "concepts/overview/working-with-objects/_index.md",
    "concepts/scheduling-eviction/assign-pod-node/_index.md",
    "concepts/security/service-accounts/_index.md",
    "tasks/debug-application-cluster/_index.md",
    "reference/kubernetes-api/workloads-resources/deployment-v1/_index.md",
]


def crawl_kubernetes() -> tuple[str, str, list[dict]]:
    license_info = {
        "license": "CC-BY-4.0",
        "license_url": "https://github.com/kubernetes/website/blob/main/LICENSE",
        "attribution": "© The Kubernetes Authors, CC BY 4.0 — via kubernetes/website",
    }
    vendor = "kubernetes"
    all_chunks = []
    for ver in K8S_VERSIONS:
        branch = f"release-{ver}"
        count = 0
        for topic in K8S_TOPICS:
            url = f"https://raw.githubusercontent.com/kubernetes/website/{branch}/content/en/docs/{topic}"
            md = fetch(url)
            if not md:
                continue
            rel = topic.replace("_index.md", "").replace(".md", "").strip("/")
            page_url = f"https://kubernetes.io/docs/{rel}/"
            for c in chunk_markdown(md, rel):
                all_chunks.append(make_chunk(vendor, ver, license_info, 
                    f"https://kubernetes.io/docs/{rel}/", c))
                count += 1
            time.sleep(0.1)
        print(f"    kubernetes[{ver}]: {count} chunks")
    return vendor, "multi", all_chunks


# ---------------------------------------------------------------- main
def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("cloudflare", crawl_cloudflare),
        ("netlify", crawl_netlify),
        ("vercel", crawl_vercel),
        ("kubernetes", crawl_kubernetes),
    ]
    manifest = {"built_at": SNAPSHOT_DATE, "vendors": {}}
    total = 0
    for name, fn in jobs:
        print(f"\n=== {name} ===")
        try:
            vendor, version, chunks = fn()
        except Exception as e:
            print(f"  !! {name} FAILED: {e}")
            continue
        out = CHUNKS_DIR / f"{vendor}_{version}.jsonl"
        with out.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        manifest["vendors"][vendor] = {
            "version": version,
            "chunks": len(chunks),
            "file": str(out.relative_to(BASE)),
        }
        total += len(chunks)
        print(f"  -> {len(chunks)} chunks -> {out.name}")
    manifest["total_chunks"] = total
    SNAPSHOT.write_text(json.dumps(manifest, indent=2))
    print(f"\nTOTAL: {total} chunks. snapshot -> {SNAPSHOT}")


if __name__ == "__main__":
    main()
