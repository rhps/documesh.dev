#!/usr/bin/env python3
"""
Build per-vendor raw JSON shards for lazy Cloudflare Worker loading.
Output: app/shards/index_<vendor>.json (uncompressed JSON, served as static asset)
Worker fetches only needed shards per query — fits free-tier memory.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
OUT_DIR = BASE / "app" / "shards"

STOP = set("a an and are as at be by for from has have how in is it its of on or that the to was what when where which who why will with".split())
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def tokenize(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


def make_snippet(content: str, max_chars: int = 280) -> str:
    """Extract a quotable plaintext snippet from a chunk for LLM consumption.

    Strips markdown formatting; prefers the first prose paragraph over
    headings/code fences; hard-truncates at word boundary with ellipsis.
    """
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", content)      # inline code / fences
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)            # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)        # links → text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)          # headings
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    # prefer first paragraph that isn't a nav/header artifact
    snippet = next((p for p in paras
                    if len(p) > 80 and not re.match(r"^(last updated|copy as markdown|\|)", p, re.I)),
                   paras[0] if paras else "")
    snippet = snippet.replace("\n", " ").strip()
    if len(snippet) <= max_chars:
        return snippet
    cut = snippet[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_docs = []
    for f in sorted(CHUNKS_DIR.glob("*.jsonl")):
        for line in open(f):
            all_docs.append(json.loads(line))

    by_vendor = {}
    for d in all_docs:
        by_vendor.setdefault(d["vendor"], []).append(d)

    for vendor, docs in sorted(by_vendor.items()):
        doc_list = []
        postings = {}
        for idx, c in enumerate(docs):
            doc_list.append({
                "chunk_id": c["chunk_id"], "vendor": c["vendor"], "version": c["version"],
                "title": c["title"], "heading_path": c["heading_path"], "path": c["path"],
                "source_url": c["source_url"], "license": c["license"],
                "attribution": c["attribution"], "last_updated": c["last_updated"],
                "snippet": make_snippet(c.get("content", "")),
            })
            toks = tokenize(c["title"] + " " + c["heading_path"]) * 3 + tokenize(c["content"])
            for tok, tf in Counter(toks).items():
                postings.setdefault(tok, {})[idx] = tf

        n = len(docs)
        idf = {t: math.log(1 + n / len(pl)) for t, pl in postings.items()}
        compact = {t: [[i, tf * idf[t]] for i, tf in pl.items()] for t, pl in postings.items()}

        payload = {
            "docs": doc_list,
            "postings": compact,
            "built_at": max(d.get("last_updated", "") for d in docs) if docs else "",
        }
        out = OUT_DIR / f"index_{vendor}.json"
        with open(out, "w") as f:
            json.dump(payload, f)
        sz = out.stat().st_size / 1e6
        print(f"  {vendor:15s} {n:5d} docs, {sz:.2f} MB")

    total = sum((OUT_DIR / f"index_{v}.json").stat().st_size for v in by_vendor) / 1e6
    print(f"\nTotal: {total:.1f} MB across {len(by_vendor)} shards → {OUT_DIR}")


if __name__ == "__main__":
    build()
