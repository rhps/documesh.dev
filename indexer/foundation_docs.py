#!/usr/bin/env python3
"""
Foundation enrichment: OpenTelemetry (CNCF, CC-BY-4.0, llms.txt + .md endpoints)
and Argo CD (CNCF, Apache-2.0, git-hosted docs/*.md).
"""
from __future__ import annotations

import json
import re
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (documesh indexer)"}
CHUNK_TARGET = 1800
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)


def fetch(url, timeout=25, redirects=5):
    req = urllib.request.Request(url, headers=UA)
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
                return fetch(loc, timeout, redirects - 1)
        print(f"    !! {e.code} {url}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url}")
        return None


def parse_llms(text):
    return [{"title": m.group(1).strip(), "url": m.group(2).strip()}
            for m in re.finditer(r"^-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text or "", re.M)]


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
            "attribution": lic["attribution"], "last_updated": c.get("lastmod") or time.strftime("%Y-%m-%d")}


import time as _time


def crawl_otel():
    lic = {"license": "CC-BY-4.0",
           "license_url": "https://github.com/open-telemetry/opentelemetry.io/blob/main/LICENSE",
           "attribution": "© OpenTelemetry contributors, CC BY 4.0 — via opentelemetry.io llms.txt"}
    base = "https://opentelemetry.io"
    txt = fetch(f"{base}/llms.txt")
    links = parse_llms(txt)
    # English docs pages only (skip locale duplicates)
    doc_links = [l for l in links
                 if l["url"].startswith("https://opentelemetry.io/")
                 and l["url"].endswith(".md")
                 and not re.match(r"https://opentelemetry\.io/(bn|es|fr|ja|ko|pt|ro|uk|zh)/", l["url"])]
    print(f"    otel: {len(doc_links)} EN pages (of {len(links)} links)")
    out = []
    for i, link in enumerate(doc_links):
        url = link["url"]
        md = fetch(url)
        if not md or len(md) < 200:
            time.sleep(0.1)
            continue
        page = url[:-3] if url.endswith(".md") else url
        rel = page.replace(base, "").strip("/") or "index"
        rel = re.sub(r"/index$", "", rel) or "index"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("opentelemetry", lic, page, c))
        if i % 10 == 0:
            print(f"    [otel] {i+1}/{len(doc_links)} pages, {len(out)} chunks")
        time.sleep(0.1)
    return out


# Argo CD: ingest key git-hosted docs (Apache-2.0)
ARGO_PAGES = [
    ("index", "docs/index.md"),
    ("security_concepts", "docs/security_concepts.md"),
    ("architecture/architecture", "docs/architecture.md"),
    ("operator-manual/declarative-setup", "docs/operator-manual/declarative-setup.md"),
    ("operator-manual/high-availability", "docs/operator-manual/high-availability.md"),
    ("operator-manual/disaster-recovery", "docs/operator-manual/disaster-recovery.md"),
    ("user-guide/application-declaration", "docs/user-guide/application_declaration.md"),
    ("user-guide/sync-waves", "docs/user-guide/sync-waves.md"),
    ("user-guide/health", "docs/operator-manual/health.md"),
    ("user-guide/commands_overview", "docs/user-guide/commands_overview.md"),
]


def crawl_argocd():
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/argoproj/argo-cd/blob/master/LICENSE",
           "attribution": "© Argo CD contributors, Apache-2.0 — via argoproj/argo-cd"}
    branch = "master"
    out = []
    for rel, repo_path in ARGO_PAGES:
        url = f"https://raw.githubusercontent.com/argoproj/argo-cd/{branch}/{repo_path}"
        md = fetch(url)
        if not md or len(md) < 200:
            print(f"    !! skip {repo_path}")
            continue
        page = f"https://argo-cd.readthedocs.io/en/stable/{rel.replace('_', '-')}/"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("argocd", lic, page, c))
        time.sleep(0.1)
    return out


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for vendor, fn in [("opentelemetry", crawl_otel), ("argocd", crawl_argocd)]:
        print(f"\n=== {vendor} ===")
        chunks = fn()
        outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
        with outp.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {len(chunks)} chunks")
        total += len(chunks)
    print(f"\nFOUNDATION TOTAL: {total} chunks")


if __name__ == "__main__":
    main()
