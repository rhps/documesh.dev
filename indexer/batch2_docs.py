#!/usr/bin/env python3
"""
Batch 2 ingestion: vendors whose docs live in separate repos / RST / different structure.
TensorFlow (master), React (react.dev), pytest (RST), Godot (godot-docs RST), Neovim (runtime/doc .txt).
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
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
MAX = 60


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
        print(f"    !! {e.code} {url[:70]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:50]} {url[:70]}")
        return None


def chunk(md, rel):
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
        if len(body) > 3600:
            pieces, cur = [], ""
            for para in body.split("\n\n"):
                if len(cur) + len(para) > 1800 and cur:
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


def make(vendor, lic, url, c):
    slug = re.sub(r"[^a-z0-9]+", "-", f"{c['path']}#{c['heading_path']}".lower()).strip("-")[:80]
    h = hashlib.sha1(c["content"].encode()).hexdigest()[:8]
    return {"chunk_id": f"{vendor}:latest:{slug}:{h}", "vendor": vendor, "version": "latest",
            "path": c["path"], "heading_path": c["heading_path"], "title": c["title"],
            "content": c["content"], "source_url": url,
            "license": lic["license"], "license_url": lic["license_url"],
            "attribution": lic["attribution"], "last_updated": time.strftime("%Y-%m-%d")}


def rst_to_md(rst):
    out, lines = [], rst.split("\n")
    i, lm = 0, {}
    levels = ["#", "##", "###", "####"]
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and len(nxt) >= len(line.strip()) and re.fullmatch(r"[=\-~^]{3,}", nxt):
                ch = nxt[0]
                if ch not in lm:
                    lm[ch] = min(len(lm), 3)
                out.append(f"{levels[lm[ch]]} {line.strip()}")
                i += 2
                continue
        out.append(line)
        i += 1
    text = "\n".join(out)
    text = re.sub(r".. code-block:: (\w+)", "```\\1", text)
    text = re.sub(r".. note::", "**Note:**", text)
    text = re.sub(r".. warning::", "**Warning:**", text)
    text = re.sub(r"\.\. \w+::", "", text)
    return text


def raw(repo, branch, path):
    return fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")


def crawl_list(vendor, lic, entries, url_fn, transform=None, cap=MAX):
    """entries: list of repo_paths. Fetch raw, optional transform, chunk."""
    out = []
    for i, rp in enumerate(entries[:cap]):
        md = raw(vendor, rp) if False else None
        # raw fetch is done by caller-provided fetcher; use simple raw pattern
        time.sleep(0.06)
    return out


def main():
    total = 0

    # ============ TensorFlow (tensorflow/docs @ master, site/en/*.md) ============
    print("=== tensorflow ===")
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/tensorflow/tensorflow/blob/master/LICENSE",
           "attribution": "© TensorFlow authors, Apache-2.0 — via tensorflow/docs"}
    req = urllib.request.Request("https://api.github.com/repos/tensorflow/docs/git/trees/master?recursive=1", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    mds = sorted(t["path"] for t in d.get("tree", []) if t["path"].startswith("site/en/") and t["path"].endswith(".md"))
    print(f"    {len(mds)} pages")
    chunks = []
    for i, rp in enumerate(mds[:MAX]):
        md = fetch(f"https://raw.githubusercontent.com/tensorflow/docs/master/{rp}")
        if not md or len(md) < 200:
            continue
        rel = rp.replace("site/en/", "").removesuffix(".md")
        page = f"https://www.tensorflow.org/{rel}"
        for c in chunk(md, rel):
            chunks.append(make("tensorflow", lic, page, c))
        if i % 10 == 0:
            print(f"    {i+1}/{len(mds)}")
        time.sleep(0.06)
    out = CHUNKS_DIR / "tensorflow_latest.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in chunks))
    print(f"  -> {len(chunks)} chunks")
    total += len(chunks)

    # ============ React (reactjs/react.dev @ main, src/content/**/*.md) ============
    print("=== react (react.dev) ===")
    lic = {"license": "CC-BY-4.0",
           "license_url": "https://github.com/reactjs/react.dev/blob/main/LICENSE.md",
           "attribution": "© Meta Platforms, Inc., CC BY 4.0 — via reactjs/react.dev"}
    req = urllib.request.Request("https://api.github.com/repos/reactjs/react.dev/git/trees/main?recursive=1", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    mds = sorted(t["path"] for t in d.get("tree", [])
                 if t["path"].startswith("src/content/") and t["path"].endswith(".md")
                 and "/blog/" not in t["path"])
    print(f"    {len(mds)} pages")
    chunks = []
    for i, rp in enumerate(mds[:MAX]):
        md = fetch(f"https://raw.githubusercontent.com/reactjs/react.dev/main/{rp}")
        if not md or len(md) < 200:
            continue
        rel = rp.replace("src/content/", "").removesuffix(".md")
        page = f"https://react.dev/{rel}" if rel != "index" else "https://react.dev/"
        for c in chunk(md, rel):
            chunks.append(make("react", lic, page, c))
        if i % 10 == 0:
            print(f"    {i+1}/{len(mds)}")
        time.sleep(0.06)
    out = CHUNKS_DIR / "react_latest.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in chunks))
    print(f"  -> {len(chunks)} chunks")
    total += len(chunks)

    # ============ pytest (pytest-dev/pytest @ main, doc/en/*.rst) ============
    print("=== pytest (RST) ===")
    lic = {"license": "MIT",
           "license_url": "https://github.com/pytest-dev/pytest/blob/main/LICENSE",
           "attribution": "© pytest contributors — MIT, via pytest-dev/pytest"}
    req = urllib.request.Request("https://api.github.com/repos/pytest-dev/pytest/git/trees/main?recursive=1", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    rsts = sorted(t["path"] for t in d.get("tree", [])
                  if t["path"].startswith("doc/en/") and t["path"].endswith(".rst"))
    print(f"    {len(rsts)} rst files")
    chunks = []
    for i, rp in enumerate(rsts[:MAX]):
        rawmd = fetch(f"https://raw.githubusercontent.com/pytest-dev/pytest/main/{rp}")
        if not rawmd or len(rawmd) < 200:
            continue
        # light rst→md (underline headings)
        out_lines, lm = [], {}
        lines = rawmd.split("\n")
        levels = ["#", "##", "###", "####"]
        j = 0
        while j < len(lines):
            line = lines[j]
            if j + 1 < len(lines):
                nxt = lines[j + 1].strip()
                if nxt and len(nxt) >= len(line.strip()) and re.fullmatch(r"[=\-~^]{3,}", nxt):
                    ch = nxt[0]
                    if ch not in lm:
                        lm[ch] = min(len(lm), 3)
                    out_lines.append(f"{levels[lm[ch]]} {line.strip()}")
                    j += 2
                    continue
            out_lines.append(line)
            j += 1
        md = "\n".join(out_lines)
        rel = rp.replace("doc/en/", "").removesuffix(".rst")
        page = f"https://docs.pytest.org/en/stable/{rel}.html"
        for c in chunk(md, rel):
            chunks.append(make("pytest", lic, page, c))
        if i % 10 == 0:
            print(f"    {i+1}/{len(rsts)}")
        time.sleep(0.06)
    out = CHUNKS_DIR / "pytest_latest.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in chunks))
    print(f"  -> {len(chunks)} chunks")
    total += len(chunks)

    # ============ Godot (godotengine/godot-docs @ master, *.rst) ============
    print("=== godot (RST) ===")
    lic = {"license": "MIT",
           "license_url": "https://github.com/godotengine/godot-docs/blob/master/LICENSE",
           "attribution": "© Godot Engine contributors — MIT, via godotengine/godot-docs"}
    req = urllib.request.Request("https://api.github.com/repos/godotengine/godot-docs/git/trees/master?recursive=1", headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    rsts = sorted(t["path"] for t in d.get("tree", [])
                  if t["path"].endswith(".rst") and not t["path"].startswith(("404", "_")))
    # prioritize concept/tutorial pages
    rsts = [p for p in rsts if any(k in p for k in
            ("getting_started", "scripting", "physics", "rendering", "tutorials", "about"))][:MAX]
    print(f"    {len(rsts)} rst files")
    chunks = []
    for i, rp in enumerate(rsts):
        rawmd = fetch(f"https://raw.githubusercontent.com/godotengine/godot-docs/master/{rp}")
        if not rawmd or len(rawmd) < 200:
            continue
        out_lines, lm = [], {}
        lines = rawmd.split("\n")
        levels = ["#", "##", "###", "####"]
        j = 0
        while j < len(lines):
            line = lines[j]
            if j + 1 < len(lines):
                nxt = lines[j + 1].strip()
                if nxt and len(nxt) >= len(line.strip()) and re.fullmatch(r"[=\-~^]{3,}", nxt):
                    ch = nxt[0]
                    if ch not in lm:
                        lm[ch] = min(len(lm), 3)
                    out_lines.append(f"{levels[lm[ch]]} {line.strip()}")
                    j += 2
                    continue
            out_lines.append(line)
            j += 1
        md = "\n".join(out_lines)
        rel = rp.removesuffix(".rst")
        page = f"https://docs.godotengine.org/en/stable/{rel}.html"
        for c in chunk(md, rel):
            chunks.append(make("godot", lic, page, c))
        if i % 10 == 0:
            print(f"    {i+1}/{len(rsts)}")
        time.sleep(0.06)
    out = CHUNKS_DIR / "godot_latest.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in chunks))
    print(f"  -> {len(chunks)} chunks")
    total += len(chunks)

    # ============ Neovim (neovim/neovim @ master, runtime/doc/*.txt) ============
    print("=== neovim (txt help) ===")
    lic = {"license": "Apache-2.0",
           "license_url": "https://github.com/neovim/neovim/blob/master/LICENSE",
           "attribution": "© Neovim contributors, Apache-2.0 — via neovim/neovim"}
    req = urllib.request.Request("https://api.github.com/repos/neovim/neovim/git/trees/master?recursive=1", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    txts = sorted(t["path"] for t in d.get("tree", [])
                  if t["path"].startswith("runtime/doc/") and t["path"].endswith(".txt"))
    print(f"    {len(txts)} txt files")
    chunks = []
    for i, rp in enumerate(txts[:30]):
        rawmd = fetch(f"https://raw.githubusercontent.com/neovim/neovim/master/{rp}")
        if not rawmd or len(rawmd) < 200:
            continue
        # vim help: first line = title, use as H1
        md = f"# {rp.split('/')[-1].replace('.txt','').capitalize()}\n\n" + rawmd
        rel = rp.replace("runtime/doc/", "").removesuffix(".txt")
        page = f"https://neovim.io/doc/user/{rel}.html"
        for c in chunk(md, rel):
            chunks.append(make("neovim", lic, page, c))
        if i % 10 == 0:
            print(f"    {i+1}/{len(txts)}")
        time.sleep(0.06)
    out = CHUNKS_DIR / "neovim_latest.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in chunks))
    print(f"  -> {len(chunks)} chunks")
    total += len(chunks)

    print(f"\nBATCH2 TOTAL: {total} chunks")


if __name__ == "__main__":
    main()
