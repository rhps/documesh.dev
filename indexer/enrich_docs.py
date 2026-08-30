#!/usr/bin/env python3
"""
Enrichment indexer — add legally-verified vendors with agent interfaces.

ENRICHMENT TIER (verified 2026-08-30):
  OSS (permissive license + official llms.txt/md interface):
    vite       MIT           vitejs.dev/llms.txt → linked llms-full or section pages? (needs link parse)
    bun        MIT core      bun.sh/docs/llms.txt → direct .md page links ✓
    hono       MIT           hono.dev/llms.txt → llms-full.txt single file ✓
    deno       MIT           deno.com (llms.txt 404s via curl; skip v1)
    drizzle    Apache-2.0    orm.drizzle.team/llms.txt → page links (need .md test)
    nuxt       MIT           nuxt.com/llms.txt → raw/docs/*.md direct ✓
    elysia     MIT           elysiajs.com/llms.txt → direct .md links ✓
    solid      MIT           docs.solidjs.com/llms.txt → relative .md links ✓
    prisma     Apache-2.0    prisma.io/docs/llms.txt → per-area indexes, .md endpoints ✓
  VENDOR (llms.txt = explicit agent consent; license = proprietary docs TOS):
    stripe     proprietary   docs.stripe.com/llms.txt → .md endpoints ✓ (huge; cap)
    sentry     proprietary   docs.sentry.io/llms.txt → .md endpoints ✓
    upstash    proprietary   docs.upstash.com/llms.txt → .md links ✓
    turso      proprietary   docs.turso.tech/llms.txt → .md links ✓
  EXCLUDED: planetscale (empty llms.txt), deno (llms.txt 404 via curl), tailwind (none),
            qwik (none), astro (none), grafana (AGPL — copyleft risk for redistribution)
"""
from __future__ import annotations

import json
import re
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
CHUNKS_DIR = BASE / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (documesh indexer; hackathon)"}
MAX_PER = 60
CHUNK_TARGET = 1800
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)


def fetch(url, timeout=25, redirects=5):
    req_url = url
    req = urllib.request.Request(req_url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308) and redirects > 0:
            loc = e.headers.get("Location") or ""
            if loc:
                # Location can be relative — resolve against the ORIGINAL url
                if not loc.startswith("http"):
                    from urllib.parse import urljoin
                    loc = urljoin(url if url.startswith("http") else "https://bun.com", loc)
                return fetch(loc, timeout, redirects - 1)
        print(f"    !! {e.code} {url}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url}")
        return None


def parse_llms(text):
    out = []
    for m in re.finditer(r"^-\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$", text or "", re.M):
        out.append({"title": m.group(1).strip(), "url": m.group(2).strip()})
    return out


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
            pieces, buf, cur = [], [], ""
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


def crawl_llms_md_pages(vendor, lic, index_url, base=None, cap=MAX_PER, page_filter=None):
    """llms.txt with direct .md page links (bun, elysia, turso, upstash, sentry, stripe...)."""
    txt = fetch(index_url)
    links = parse_llms(txt)
    out = []
    default_base = base or index_url.rsplit("/", 1)[0]
    for i, link in enumerate(links):
        if len(out) >= cap:
            break
        url = link["url"]
        if page_filter and not page_filter(url):
            continue
        if not url.startswith("http"):
            url = default_base + url
        if ".md" not in url.split("/")[-1]:
            continue
        md = fetch(url)
        if not md or len(md) < 200:
            time.sleep(0.1)
            continue
        # canonical page url: strip .md
        page = url[:-3] if url.endswith(".md") else url
        path = re.sub(r"^https?://[^/]+/", "", page).strip("/") or "index"
        path = re.sub(r"\.md$", "", path)
        for c in chunk_markdown(md, path):
            out.append(make_chunk(vendor, lic, page, c))
        if i % 15 == 0:
            print(f"    [{vendor}] {i}/{len(links)} links, {len(out)} chunks")
        time.sleep(0.08)
    return out


def crawl_llms_full_file(vendor, lic, file_url, cap_pages=40):
    """llms-full.txt = entire docs in one markdown file. Split on H1/H2 page breaks."""
    txt = fetch(file_url)
    if not txt:
        return []
    # Split into pseudo-pages on H1 headings
    parts = re.split(r"^# ", txt, flags=re.M)[1:]
    out = []
    for p in parts[:cap_pages]:
        title = p.split("\n", 1)[0].strip()[:80]
        body = f"# {p}"
        rel = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        for c in chunk_markdown(body, rel):
            c["title"] = c["title"] or title
            out.append(make_chunk(vendor, lic, file_url, c))
    return out


VENDORS = [
    # OSS, permissive
    ("bun", {"license": "MIT (Bun core)", "license_url": "https://github.com/oven-sh/bun/blob/main/LICENSE",
             "attribution": "© Oven, Inc. — via bun.sh official llms.txt agent interface"},
     lambda: crawl_llms_md_pages("bun", VENDORS_LIC["bun"], "https://bun.com/docs/llms.txt")),
    ("elysia", {"license": "MIT", "license_url": "https://github.com/elysiajs/elysia/blob/main/LICENSE",
                "attribution": "© ElysiaJS — via elysiajs.com official llms.txt"},
     lambda: crawl_llms_md_pages("elysia", VENDORS_LIC["elysia"], "https://elysiajs.com/llms.txt")),
    ("turso", {"license": "Turso Docs (agent-permitted via llms.txt)", "license_url": "https://docs.turso.tech/llms.txt",
               "attribution": "© Turso — via docs.turso.tech llms.txt"},
     lambda: crawl_llms_md_pages("turso", VENDORS_LIC["turso"], "https://docs.turso.tech/llms.txt")),
    ("upstash", {"license": "Upstash Docs (agent-permitted via llms.txt)", "license_url": "https://docs.upstash.com/llms.txt",
                 "attribution": "© Upstash — via docs.upstash.com llms.txt"},
     lambda: crawl_llms_md_pages("upstash", VENDORS_LIC["upstash"], "https://docs.upstash.com/llms.txt")),
    ("sentry", {"license": "Sentry Docs (agent-permitted via llms.txt)", "license_url": "https://docs.sentry.io/llms.txt",
                "attribution": "© Functional Software, Inc. (Sentry) — via docs.sentry.io llms.txt"},
     lambda: crawl_llms_md_pages("sentry", VENDORS_LIC["sentry"], "https://docs.sentry.io/llms.txt", cap=40)),
    ("stripe", {"license": "Stripe Docs (agent-permitted via llms.txt)", "license_url": "https://docs.stripe.com/llms.txt",
                "attribution": "© Stripe, Inc. — via docs.stripe.com llms.txt"},
     lambda: crawl_llms_md_pages("stripe", VENDORS_LIC["stripe"], "https://docs.stripe.com/llms.txt", cap=40)),
    ("hono", {"license": "MIT", "license_url": "https://github.com/honojs/hono/blob/main/LICENSE",
              "attribution": "© Hono contributors — via hono.dev official llms.txt"},
     lambda: crawl_llms_full_file("hono", VENDORS_LIC["hono"], "https://hono.dev/llms-small.txt")),
    ("drizzle", None,
     lambda: []),  # drizzle: llms.txt has plain HTML links, no .md endpoints — needs HTML parsing; defer to v2
    ("nuxt", {"license": "MIT", "license_url": "https://github.com/nuxt/nuxt/blob/main/LICENSE",
              "attribution": "© Nuxt team — via nuxt.com llms.txt"},
     lambda: crawl_llms_md_pages("nuxt", VENDORS_LIC["nuxt"], "https://nuxt.com/llms.txt")),
    ("solid", {"license": "MIT", "license_url": "https://github.com/solidjs/solid/blob/main/LICENSE",
               "attribution": "© SolidJS — via docs.solidjs.com llms.txt"},
     lambda: crawl_llms_md_pages("solid", VENDORS_LIC["solid"], "https://docs.solidjs.com/llms.txt",
                                 base="https://docs.solidjs.com")),
]

# shared license dict lookup (defined after to reference keys)
VENDORS_LIC = {v[0]: v[1] for v in VENDORS}


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for vendor, lic, fn in VENDORS:
        print(f"\n=== {vendor} ===")
        try:
            chunks = fn()
        except Exception as e:
            print(f"  !! FAILED: {str(e)[:80]}")
            continue
        out = CHUNKS_DIR / f"{vendor}_latest.jsonl"
        with out.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {len(chunks)} chunks")
        total += len(chunks)
    print(f"\nENRICHMENT TOTAL: {total} chunks")


if __name__ == "__main__":
    main()
