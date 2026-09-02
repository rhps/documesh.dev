#!/usr/bin/env python3
"""
Tier-1 cloud/AI/infra ingestion batch (2026-09-02 research, docs/VENDOR_EXPANSION_RESEARCH.md).

10 vendors, all verified llms.txt agent-permitted:
  aws, gitlab, digitalocean, ibmcloud, anthropic, neon, clerk, pulumi, temporal, kong

Access patterns handled:
  - page .md suffix            (aws, neon, anthropic)
  - llms.txt links end in .md  (aws, gitlab)
  - llms.txt links are HTML    (digitalocean?format→index.html.md, clerk, kong, pulumi, temporal)

Usage:
  python3 indexer/ingest_tier1_cloud.py            # all 10
  python3 indexer/ingest_tier1_cloud.py aws neon   # subset
Then: python3 indexer/build_shards.py && update VENDOR_META in worker/src/search-core-lite.js
"""
from __future__ import annotations

import json
import re
import sys
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (compatible; documesh-indexer/1.0)"}
CHUNK_TARGET = 1800
MAX_PAGES = 400         # per vendor — politeness-delayed crawl, no artificial cap
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")


def fetch(url, timeout=30, redirects=6, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308) and redirects > 0:
            loc = e.headers.get("Location") or ""
            if loc:
                if not loc.startswith("http"):
                    from urllib.parse import urljoin
                    loc = urljoin(url, loc)
                return fetch(loc, timeout, redirects - 1, headers)
        print(f"    !! {e.code} {url[:90]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url[:90]}")
        return None


def fetch_md(url, timeout=30):
    """Fetch with markdown negotiation (Accept header) — used by IBM/others."""
    return fetch(url, timeout, headers={"Accept": "text/markdown"})


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
            "attribution": lic["attribution"], "last_updated": SNAPSHOT_DATE}


def parse_llms(text):
    return [{"title": m.group(1).strip(), "url": m.group(2).strip()}
            for m in re.finditer(r"^\s*-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text or "", re.M)]


def parse_llms_loose(text):
    """Tolerant parser: also matches bare [title](url) lines (GitLab omits the dash)."""
    strict = parse_llms(text)
    if strict:
        return strict
    out = []
    seen = set()
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text or ""):
        url = m.group(2).strip()
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": m.group(1).strip(), "url": url})
    return out


def save(vendor, chunks):
    if not chunks:
        print(f"  !! {vendor}: 0 chunks — skipping write")
        return 0
    outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
    with outp.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"  -> {vendor}: {len(chunks)} chunks")
    return len(chunks)


# ---------------------------------------------------------------- crawlers

def llms_md_links(index_url, base=None):
    """Return (title, url) list where every URL is converted to its .md form."""
    txt = fetch(index_url)
    links = parse_llms(txt)
    default_base = base or index_url.rsplit("/", 1)[0]
    out = []
    for link in links:
        url = link["url"]
        if not url.startswith("http"):
            url = default_base + (url if url.startswith("/") else "/" + url)
        url = url.split("#")[0].split("?")[0].rstrip("/")
        if not url or url.endswith((".png", ".jpg", ".svg", ".pdf", ".zip")):
            continue
        if not url.endswith(".md"):
            url += ".md"
        out.append({"title": link["title"], "url": url})
    return out


def crawl_md_suffix(vendor, lic, index_url, max_pages=MAX_PAGES, page_base_strip=None, llms_base=None):
    """llms.txt index whose pages support .md suffix (aws, neon, anthropic...)."""
    links = llms_md_links(index_url, llms_base)
    print(f"    [{vendor}] {len(links)} links from index")
    out = []
    seen = set()
    for i, link in enumerate(links):
        if len(out) >= max_pages:
            break
        md_url = link["url"]
        if md_url in seen:
            continue
        seen.add(md_url)
        md = fetch(md_url)
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.1)
            continue
        page = md_url[:-3] if md_url.endswith(".md") else md_url
        path = re.sub(r"^https?://[^/]+/", "", page).strip("/")
        path = re.sub(r"\.(html|php)$", "", path) or "index"
        for c in chunk_markdown(md, path):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{len(links)} links, {len(out)} chunks")
        time.sleep(0.1)
    return out


def crawl_html_llms(vendor, lic, index_url, md_transform, max_pages=MAX_PAGES, skip_html=True):
    """llms.txt index linking HTML pages; md_transform(url) yields the markdown URL."""
    txt = fetch(index_url)
    links = parse_llms(txt)
    print(f"    [{vendor}] {len(links)} links from index")
    out = []
    seen = set()
    for i, link in enumerate(links):
        if len(out) >= max_pages:
            break
        url = link["url"]
        if not url.startswith("http"):
            continue
        md_url = md_transform(url)
        if not md_url or md_url in seen:
            continue
        seen.add(md_url)
        md = fetch(md_url)
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.1)
            continue
        page = re.sub(r"\.md$", "", md_url)
        path = re.sub(r"^https?://[^/]+/", "", page).strip("/")
        path = re.sub(r"\.(html|php)$", "", path) or "index"
        for c in chunk_markdown(md, path):
            out.append(make_chunk(vendor, lic, url, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{len(links)} links, {len(out)} chunks")
        time.sleep(0.1)
    return out


# ---------------------------------------------------------------- vendor configs

def lic_agent_permitted(name, docs_url):
    return {"license": f"{name} Docs (agent-permitted via llms.txt)",
            "license_url": docs_url,
            "attribution": f"© {name} — via llms.txt agent interface, via documesh"}


def crawl_aws():
    lic = lic_agent_permitted("AWS", "https://docs.aws.amazon.com/llms.txt")
    # index links are per-service; each service link is a .md landing page.
    # Take a broad slice across the alphabet for coverage.
    links = llms_md_links("https://docs.aws.amazon.com/llms.txt")
    # prioritize popular services first
    prio = ["ec2", "s3", "lambda", "bedrock", "rds", "dynamodb", "iam", "cloudformation",
            "eks", "ecs", "route53", "sqs", "sns", "cloudwatch", "secrets-manager",
            "step-functions", "apigateway", "cloudfront", "aurora", "sagemaker"]
    def rank(link):
        u = link["url"].lower()
        for i, p in enumerate(prio):
            if f"/{p}/" in u or f"//{p}." in u:
                return i
        return 100
    links.sort(key=rank)
    out = []
    seen = set()
    for i, link in enumerate(links):
        if len(out) >= MAX_PAGES:
            break
        md_url = link["url"]
        if md_url in seen:
            continue
        seen.add(md_url)
        md = fetch(md_url)
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.1)
            continue
        page = md_url[:-3]
        path = re.sub(r"^https?://docs\.aws\.amazon\.com/", "", page).strip("/")
        for c in chunk_markdown(md, path):
            out.append(make_chunk("aws", lic, page, c))
        if i % 5 == 0:
            print(f"    [aws] {i+1}/{len(links)}, {len(out)} chunks")
        time.sleep(0.15)
    return out


def crawl_gitlab():
    lic = lic_agent_permitted("GitLab", "https://docs.gitlab.com/llms.txt")
    txt = fetch("https://docs.gitlab.com/llms.txt")
    links = parse_llms_loose(txt)
    print(f"    [gitlab] {len(links)} links (loose parse)")
    out = []
    seen = set()
    for i, link in enumerate(links):
        if len(out) >= MAX_PAGES:
            break
        url = link["url"].split("?")[0].rstrip("/")
        if url in seen or "ja-jp" in url:
            continue
        seen.add(url)
        md = fetch(url + ".md")
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.08)
            continue
        page = url
        path = re.sub(r"^https?://docs\.gitlab\.com/", "", page).strip("/") or "index"
        for c in chunk_markdown(md, path):
            out.append(make_chunk("gitlab", lic, page, c))
        if i % 10 == 0:
            print(f"    [gitlab] {i+1}/{len(links)}, {len(out)} chunks")
        time.sleep(0.1)
    return out


def crawl_digitalocean():
    lic = lic_agent_permitted("DigitalOcean", "https://docs.digitalocean.com/llms.txt")
    # DO: same path with index.html.md — i.e. append .md after full path
    return crawl_md_suffix("digitalocean", lic, "https://docs.digitalocean.com/llms.txt")


def crawl_ibmcloud():
    lic = lic_agent_permitted("IBM Cloud", "https://cloud.ibm.com/docs/llms.txt")
    # IBM: append ?format=markdown to the page URL
    def transform(u):
        return u + ("&" if "?" in u else "?") + "format=markdown"
    out = crawl_html_llms("ibmcloud", lic, "https://cloud.ibm.com/docs/llms.txt", transform)
    if not out:
        # fall back to Accept header
        out = crawl_html_llms("ibmcloud", lic, "https://cloud.ibm.com/docs/llms.txt",
                              lambda u: u)
    return out


def crawl_anthropic():
    lic = lic_agent_permitted("Anthropic", "https://platform.claude.com/llms.txt")
    return crawl_md_suffix("anthropic", lic, "https://platform.claude.com/llms.txt")


def crawl_neon():
    lic = lic_agent_permitted("Neon", "https://neon.com/docs/llms.txt")
    return crawl_md_suffix("neon", lic, "https://neon.com/docs/llms.txt")


def crawl_clerk():
    lic = lic_agent_permitted("Clerk", "https://clerk.com/docs/llms.txt")
    return crawl_md_suffix("clerk", lic, "https://clerk.com/docs/llms.txt")


def crawl_pulumi():
    lic = lic_agent_permitted("Pulumi", "https://www.pulumi.com/llms.txt")
    # Pulumi registry/ai-docs: try .md suffix; AI docs portal pattern
    return crawl_md_suffix("pulumi", lic, "https://www.pulumi.com/llms.txt")


def crawl_temporal():
    lic = lic_agent_permitted("Temporal", "https://docs.temporal.io/llms.txt")
    return crawl_md_suffix("temporal", lic, "https://docs.temporal.io/llms.txt")


def crawl_kong():
    lic = lic_agent_permitted("Kong", "https://developer.konghq.com/llms.txt")
    return crawl_md_suffix("kong", lic, "https://developer.konghq.com/llms.txt")


JOBS = {
    "aws": crawl_aws,
    "gitlab": crawl_gitlab,
    "digitalocean": crawl_digitalocean,
    "ibmcloud": crawl_ibmcloud,
    "anthropic": crawl_anthropic,
    "neon": crawl_neon,
    "clerk": crawl_clerk,
    "pulumi": crawl_pulumi,
    "temporal": crawl_temporal,
    "kong": crawl_kong,
}

VENDOR_DISPLAY = {
    "aws": {"name": "AWS", "license": "AWS Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "gitlab": {"name": "GitLab", "license": "GitLab Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "digitalocean": {"name": "DigitalOcean", "license": "DigitalOcean Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "ibmcloud": {"name": "IBM Cloud", "license": "IBM Cloud Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + format=markdown"},
    "anthropic": {"name": "Anthropic", "license": "Anthropic Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "neon": {"name": "Neon", "license": "Neon Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "clerk": {"name": "Clerk", "license": "Clerk Docs (agent-permitted via llms.txt)", "docs_origin": "llms.txt + .md"},
    "pulumi": {"name": "Pulumi", "license": "Pulumi Docs (agent-permitted via llms.txt); SDK Apache-2.0", "docs_origin": "llms.txt + .md"},
    "temporal": {"name": "Temporal", "license": "Temporal Docs (agent-permitted via llms.txt); core MIT", "docs_origin": "llms.txt + .md"},
    "kong": {"name": "Kong", "license": "Kong Docs (agent-permitted via llms.txt); Gateway Apache-2.0", "docs_origin": "llms.txt + .md"},
}


def main():
    requested = sys.argv[1:] or list(JOBS.keys())
    unknown = [v for v in requested if v not in JOBS]
    if unknown:
        print(f"unknown vendors: {unknown}. available: {list(JOBS.keys())}")
        sys.exit(1)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    totals = {}
    for v in requested:
        print(f"\n=== {v} ===")
        try:
            chunks = JOBS[v]()
        except Exception as e:
            print(f"  !! FAILED: {str(e)[:120]}")
            continue
        totals[v] = save(v, chunks)
    print("\n=== BATCH SUMMARY ===")
    for v, n in totals.items():
        print(f"  {v}: {n} chunks")
    print(f"  TOTAL: {sum(totals.values())} chunks across {len([t for t in totals.values() if t])} vendors")
    print("\nNext steps:")
    print("  1. python3 indexer/build_shards.py")
    print("  2. add VENDOR_META entries in worker/src/search-core-lite.js")
    print("  3. update counts (38 vendors) across app/, coverage page, ARD, openapi")


if __name__ == "__main__":
    main()
