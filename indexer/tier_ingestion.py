#!/usr/bin/env python3
"""
Full-tier ingestion: easiest → hardest.
Tier 1: llms.txt vendors not yet in mesh (Node.js, Astro)
Tier 2: git repo in-repo markdown, single branch, known path (~28 vendors)
Every vendor: license pre-verified in WIKI_FOSS_TIERS.md.
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
MAX_PAGES = 60
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)

SNAPSHOT_DATE = time.strftime("%Y-%m-%d")


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
        print(f"    !! {e.code} {url[:80]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:50]} {url[:80]}")
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
            "attribution": lic["attribution"], "last_updated": SNAPSHOT_DATE}


def parse_llms(text):
    return [{"title": m.group(1).strip(), "url": m.group(2).strip()}
            for m in re.finditer(r"^-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text or "", re.M)]


# ============================================================ TIER 1 (llms.txt)
def crawl_llms_pages(vendor, lic, index_url, base=None, cap=MAX_PAGES):
    txt = fetch(index_url)
    links = parse_llms(txt)
    default_base = base or index_url.rsplit("/", 1)[0]
    out = []
    for i, link in enumerate(links):
        if len(out) >= cap:
            break
        url = link["url"]
        if not url.startswith("http"):
            url = default_base + (url if url.startswith("/") else "/" + url)
        if ".md" not in url.split("/")[-1]:
            continue
        md = fetch(url)
        if not md or len(md) < 200:
            time.sleep(0.08)
            continue
        page = url[:-3] if url.endswith(".md") else url
        path = re.sub(r"^https?://[^/]+/", "", page).strip("/")
        path = re.sub(r"\.md$", "", path) or "index"
        for c in chunk_markdown(md, path):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 15 == 0:
            print(f"    [{vendor}] {i+1}/{len(links)} links, {len(out)} chunks")
        time.sleep(0.08)
    return out


# ============================================================ TIER 2 (git repo)
def gh_tree_md(repo, branch, prefix=None):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    paths = [t["path"] for t in d.get("tree", [])
             if t["path"].endswith(".md") and (not prefix or t["path"].startswith(prefix))]
    paths.sort()
    return paths, d.get("truncated", False)


def crawl_git(vendor, lic, repo, branch, prefixes, url_fn, cap=MAX_PAGES, exclude=()):
    """Generic P4: tree-walk markdown, fetch via raw.githubusercontent, chunk."""
    try:
        paths, trunc = gh_tree_md(repo, branch)
    except Exception as e:
        print(f"    !! tree fetch failed: {str(e)[:60]}")
        return []
    matched = []
    for prefix in prefixes:
        matched += [p for p in paths if p.startswith(prefix) and p.endswith(".md")]
    matched = list(dict.fromkeys(matched))  # dedupe preserving order
    for ex in exclude:
        matched = [p for p in matched if ex not in p]
    matched.sort()
    print(f"    [{vendor}] {len(matched)} md files matched (repo total {len(paths)}, truncated={trunc})")

    out = []
    for i, repo_path in enumerate(matched[:cap]):
        raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{repo_path}"
        md = fetch(raw)
        if not md or len(md) < 200:
            time.sleep(0.08)
            continue
        rel = re.sub(r"\.md$", "", repo_path)
        for pref in prefixes:
            if rel.startswith(pref):
                rel = rel[len(pref):].lstrip("/")
                break
        rel = rel or "index"
        page = url_fn(rel, repo_path)
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 10 == 0:
            print(f"    [{vendor}] {i+1}/{min(len(matched), cap)} pages, {len(out)} chunks")
        time.sleep(0.06)
    return out


LIC_MIT = lambda name: {"license": "MIT",
                        "license_url": f"https://github.com/{name}/blob/main/LICENSE",
                        "attribution": f"© {name} contributors — MIT License, via docs-mesh"}
LIC_AP2 = lambda name: {"license": "Apache-2.0",
                        "license_url": f"https://github.com/{name}/blob/main/LICENSE",
                        "attribution": f"© {name} contributors, Apache-2.0 — via docs-mesh"}

JOBS = [
    # ---------- TIER 1: llms.txt ----------
    ("astro", LIC_MIT("withastro/astro"),
     lambda: crawl_llms_pages("astro", LIC_MIT("withastro/astro"),
                              "https://docs.astro.build/llms.txt", cap=40)),

    # ---------- TIER 2: git in-repo markdown (easiest → harder) ----------
    ("react", LIC_MIT("facebook/react"),
     lambda: crawl_git("react", LIC_MIT("facebook/react"), "facebook/react", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://react.dev/reference/{rel}" if rel.startswith("api") else f"https://github.com/facebook/react/tree/main/docs/{rel}",
                       exclude=["blog", "community"])),

    ("pytorch", {"license": "BSD-style (permissive)",
                 "license_url": "https://github.com/pytorch/pytorch/blob/main/LICENSE",
                 "attribution": "© PyTorch contributors — BSD-style, via pytorch/pytorch"},
     lambda: crawl_git("pytorch", LIC_MIT("pytorch/pytorch"), "pytorch/pytorch", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://pytorch.org/docs/stable/{rel}.html",
                       exclude=["es_src", "source", "_templates", "de"])),

    ("tensorflow", LIC_AP2("tensorflow/tensorflow"),
     lambda: crawl_git("tensorflow", LIC_AP2("tensorflow/tensorflow"),
                       "tensorflow/tensorflow", "master",
                       ["tensorflow/docs/"],
                       lambda rel, rp: f"https://www.tensorflow.org/{rel.replace('tensorflow/docs/', '')}",
                       exclude=["api_docs"])),

    ("langchain", LIC_MIT("langchain-ai/langchain"),
     lambda: crawl_git("langchain", LIC_MIT("langchain-ai/langchain"),
                       "langchain-ai/langchain", "master",
                       ["docs/"],
                       lambda rel, rp: f"https://python.langchain.com/docs/{rel}",
                       exclude=["api_reference"])),

    ("playwright", LIC_AP2("microsoft/playwright"),
     lambda: crawl_git("playwright", LIC_AP2("microsoft/playwright"),
                       "microsoft/playwright", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://playwright.dev/docs/{rel}",
                       exclude=["api", "release-notes"])),

    ("clickhouse", LIC_AP2("clickhouse/clickhouse"),
     lambda: crawl_git("clickhouse", LIC_AP2("clickhouse/clickhouse"),
                       "clickhouse/clickhouse", "master",
                       ["docs/en/"],
                       lambda rel, rp: f"https://clickhouse.com/docs/en/{rel}",
                       exclude=["js"])), 

    ("ollama", LIC_MIT("ollama/ollama"),
     lambda: crawl_git("ollama", LIC_MIT("ollama/ollama"), "ollama/ollama", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://github.com/ollama/ollama/tree/main/docs/{rel}",
                       exclude=["development", "api"])), 

    ("electron", LIC_MIT("electron/electron"),
     lambda: crawl_git("electron", LIC_MIT("electron/electron"), "electron/electron", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://www.electronjs.org/docs/latest/{rel}",
                       exclude=["api/images", "tutorial/quick"])),

    ("hugo", LIC_AP2("gohugoio/hugo"),
     lambda: crawl_git("hugo", LIC_AP2("gohugoio/hugo"), "gohugoio/hugo", "master",
                       ["docs/content/en/"],
                       lambda rel, rp: f"https://gohugo.io/{rel}/",
                       exclude=["_index"])),

    ("docusaurus", LIC_MIT("facebook/docusaurus"),
     lambda: crawl_git("docusaurus", LIC_MIT("facebook/docusaurus"),
                       "facebook/docusaurus", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://docusaurus.io/docs/{rel}",
                       exclude=[])),

    ("pytest", LIC_MIT("pytest-dev/pytest"),
     lambda: crawl_git("pytest", LIC_MIT("pytest-dev/pytest"), "pytest-dev/pytest", "main",
                       ["doc/en/"],
                       lambda rel, rp: f"https://docs.pytest.org/en/stable/{rel}",
                       exclude=[])),

    ("nodejs", LIC_MIT("nodejs/node"),
     lambda: crawl_git("nodejs", LIC_MIT("nodejs/node"), "nodejs/node", "main",
                       ["doc/api/"],
                       lambda rel, rp: f"https://nodejs.org/api/{rel}.html",
                       exclude=[])),

    ("godot-docs", LIC_MIT("godotengine/godot"),
     lambda: crawl_git("godot-docs", LIC_MIT("godotengine/godot"), "godotengine/godot", "master",
                       ["doc/source/"],
                       lambda rel, rp: f"https://docs.godotengine.org/en/stable/{rel}.html",
                       exclude=[])),

    ("neovim", LIC_AP2("neovim/neovim"),
     lambda: crawl_git("neovim", LIC_AP2("neovim/neovim"), "neovim/neovim", "master",
                       ["runtime/doc/"],
                       lambda rel, rp: f"https://neovim.io/doc/user/{rel.replace('.txt','')}.html",
                       exclude=[])),

    ("terragrunt", LIC_MIT("gruntwork-io/terragrunt"),
     lambda: crawl_git("terragrunt", LIC_MIT("gruntwork-io/terragrunt"),
                       "gruntwork-io/terragrunt", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://terragrunt.gruntwork.io/docs/{rel}",
                       exclude=["_includes", "starship"])),

    ("moby", LIC_AP2("moby/moby"),
     lambda: crawl_git("moby", LIC_AP2("moby/moby"), "moby/moby", "master",
                       ["docs/"],
                       lambda rel, rp: f"https://docs.docker.com/{rel}/",
                       exclude=[])),

    ("elasticsearch", LIC_AP2("elastic/elasticsearch"),
     lambda: crawl_git("elasticsearch", LIC_AP2("elastic/elasticsearch"),
                       "elastic/elasticsearch", "main",
                       ["docs/reference/"],
                       lambda rel, rp: f"https://www.elastic.co/guide/en/elasticsearch/reference/{rel}",
                       exclude=[])),

    ("svelte-core", LIC_MIT("sveltejs/svelte"),
     lambda: crawl_git("svelte-core", LIC_MIT("sveltejs/svelte"), "sveltejs/svelte", "main",
                       ["packages/svelte/src/internal/../../documentation/"],
                       lambda rel, rp: f"https://svelte.dev/docs",
                       exclude=[])),

    ("vue-core-docs", LIC_MIT("vuejs/core"),
     lambda: crawl_git("vue-core-docs", LIC_MIT("vuejs/core"), "vuejs/core", "main",
                       ["packages/", "CHANGELOG.md"],
                       lambda rel, rp: f"https://github.com/vuejs/core/tree/main/{rel}",
                       exclude=["test", "__tests__", ".github"])),

    ("spring-framework", LIC_AP2("spring-projects/spring-framework"),
     lambda: crawl_git("spring-framework", LIC_AP2("spring-projects/spring-framework"),
                       "spring-projects/spring-framework", "main",
                       ["framework/src/docs/kdoc-api/", "src/docs/kdoc-api/"],
                       lambda rel, rp: f"https://docs.spring.io/spring-framework/reference/",
                       exclude=[])),

    ("keycloak", LIC_AP2("keycloak/keycloak"),
     lambda: crawl_git("keycloak", LIC_AP2("keycloak/keycloak"), "keycloak/keycloak", "main",
                       ["docs/documentation/"],
                       lambda rel, rp: f"https://www.keycloak.org/documentation",
                       exclude=[])),

    ("gitea", LIC_MIT("go-gitea/gitea"),
     lambda: crawl_git("gitea", LIC_MIT("go-gitea/gitea"), "go-gitea/gitea", "main",
                       ["docs/"],
                       lambda rel, rp: f"https://docs.gitea.com/{rel}",
                       exclude=["config", "help"])),
]


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    grand_total = 0
    done = []
    for vendor, lic, fn in JOBS:
        print(f"\n=== {vendor} (Tier 1/2) ===")
        try:
            chunks = fn()
        except Exception as e:
            print(f"  !! FAILED: {str(e)[:100]}")
            continue
        if not chunks:
            print(f"  !! 0 chunks — check paths/filters")
            continue
        outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
        with outp.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {len(chunks)} chunks")
        grand_total += len(chunks)
        done.append((vendor, len(chunks)))
    print(f"\nINGESTION TOTAL: {grand_total} chunks across {len(done)} vendors")
    for v, n in done:
        print(f"  {v}: {n}")


if __name__ == "__main__":
    main()
