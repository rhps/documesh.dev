#!/usr/bin/env python3
"""
Foundation enrichment round 2 — Helm, Flux CD, Cilium.
All CNCF, Apache-2.0, git-hosted markdown (verified 2026-08-31, see FOUNDATION_SWEEP.md).

Ingestion pattern: P4 (git tree-walk, single branch, content-path config)
  helm    helm/helm-www        docs/**/*.md          (1,689 files — cap & filter)
  fluxcd  fluxcd/website       content/en/flux/**/*.md (106 files)
  cilium  cilium/cilium        Documentation/**/*.md (340 files — cap & filter)
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
UA = {"User-Agent": "Mozilla/5.0 (docs-mesh indexer)"}
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
            "attribution": lic["attribution"], "last_updated": time.strftime("%Y-%m-%d")}


def gh_tree_md(repo, branch, prefix=None):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    paths = [t["path"] for t in d.get("tree", [])
             if t["path"].endswith(".md") and (not prefix or t["path"].startswith(prefix))]
    return paths


def crawl_git_docs(vendor, lic, repo, branch, content_prefix, page_url_fn,
                   include=None, exclude=(), cap=60):
    paths = gh_tree_md(repo, branch, content_prefix)
    if include:
        paths = [p for p in paths if any(inc in p for inc in include)]
    for ex in exclude:
        paths = [p for p in paths if ex not in p]
    paths.sort()
    print(f"    [{vendor}] {len(paths)} md files matched (cap {cap})")
    out = []
    for i, repo_path in enumerate(paths[:cap]):
        raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{repo_path}"
        md = fetch(raw)
        if not md or len(md) < 200:
            time.sleep(0.08)
            continue
        rel = repo_path[len(content_prefix):].lstrip("/")
        rel = re.sub(r"\.md$", "", rel)
        rel = re.sub(r"/_index$", "", rel)
        rel = re.sub(r"/index$", "", rel) or "index"
        page = page_url_fn(rel)
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(paths), cap)} pages, {len(out)} chunks")
        time.sleep(0.08)
    return out


def crawl_helm():
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/helm/helm-www/blob/main/LICENSE",
           "attribution": "© Helm Authors, Apache-2.0 — via helm/helm-www"}
    return crawl_git_docs(
        "helm", lic,
        repo="helm/helm-www", branch="main",
        content_prefix="docs/",                     # docs live at docs/ (docusaurus), not content/en
        page_url_fn=lambda rel: f"https://helm.sh/docs/{rel}/",
        include=["docs/topics/", "docs/intro/", "docs/howto/", "docs/chart_template_guide/",
                 "docs/chart_best_practices/", "docs/using_gke/", "docs/rbac/", "docs/community/"],
        exclude=["changelog"],
        cap=60)


def crawl_flux():
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/fluxcd/flux2/blob/main/LICENSE",
           "attribution": "© Flux authors, Apache-2.0 — via fluxcd/website"}
    return crawl_git_docs(
        "flux", lic,
        repo="fluxcd/website", branch="main",
        content_prefix="content/en/flux/",
        page_url_fn=lambda rel: f"https://fluxcd.io/flux/{rel}/",
        cap=60)


def crawl_cilium():
    """Cilium docs are Sphinx RST (306 non-cmdref files). RST is close enough to
    markdown for heading-chunking: =/- underline headings, no # syntax.
    We convert RST headings to markdown-style for the chunker."""
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/cilium/cilium/blob/main/LICENSE",
           "attribution": "© Cilium Authors, Apache-2.0 — via cilium/cilium"}

    def rst_to_md(rst: str) -> str:
        # Convert RST heading underlines to # headings
        out = []
        lines = rst.split("\n")
        i = 0
        level_map = {}
        levels = ["#", "##", "###", "####"]
        while i < len(lines):
            line = lines[i]
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and len(nxt) >= len(line.strip()) and re.fullmatch(r"[=\-~^]{3,}", nxt):
                    char = nxt[0]
                    if char not in level_map:
                        level_map[char] = min(len(level_map), 3)
                    out.append(f"{levels[level_map[char]]} {line.strip()}")
                    i += 2
                    continue
            out.append(line)
            i += 1
        text = "\n".join(out)
        # strip RST directives we don't need
        text = re.sub(r".. code-block:: (\w+)", "```\\1", text)
        text = re.sub(r".. note::", "**Note:**", text)
        text = re.sub(r".. warning::", "**Warning:**", text)
        text = re.sub(r"\.\. \w+::", "", text)
        return text

    # Cilium: RST files, curated topic dirs (cmdref excluded — it's auto-generated CLI docs)
    lic_local = lic
    paths = gh_tree_md_filtered("cilium/cilium", "main", "Documentation/",
                                include=["network/", "security/", "observability/",
                                         "gettingstarted/", "installation/", "operations/",
                                         "configuration/"],
                                exclude=["cmdref", "_static", "images", "contributing"],
                                ext=".rst")
    print(f"    [cilium] {len(paths)} rst files matched")
    out = []
    for i, repo_path in enumerate(paths[:60]):
        raw = f"https://raw.githubusercontent.com/cilium/cilium/main/{repo_path}"
        rst = fetch(raw)
        if not rst or len(rst) < 200:
            time.sleep(0.08)
            continue
        md = rst_to_md(rst)
        rel = repo_path[len("Documentation/"):].rsplit(".", 1)[0]
        page = f"https://docs.cilium.io/en/latest/{rel}/"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("cilium", lic_local, page, c))
        if i % 10 == 0:
            print(f"    [cilium] {i+1}/{min(len(paths), 60)} pages, {len(out)} chunks")
        time.sleep(0.08)
    return out


def gh_tree_md_filtered(repo, branch, prefix, include=(), exclude=(), ext=".md"):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    paths = [t["path"] for t in d.get("tree", [])
             if t["path"].startswith(prefix) and t["path"].endswith(ext)]
    if include:
        paths = [p for p in paths if any(p[len(prefix):].startswith(inc) for inc in include)]
    for ex in exclude:
        paths = [p for p in paths if ex not in p]
    paths.sort()
    return paths


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for vendor, fn in [("helm", crawl_helm), ("flux", crawl_flux), ("cilium", crawl_cilium)]:
        print(f"\n=== {vendor} ===")
        try:
            chunks = fn()
        except Exception as e:
            print(f"  !! FAILED: {str(e)[:80]}")
            continue
        outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
        with outp.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {len(chunks)} chunks")
        total += len(chunks)
    print(f"\nFOUNDATION R2 TOTAL: {total} chunks")


if __name__ == "__main__":
    main()
