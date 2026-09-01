#!/usr/bin/env python3
"""
Build a static search index from chunks: tokenized inverted index + chunk store.
Output: data/index/search-index.json  (loaded by the Worker at request time or bundled)

Design: Worker loads this JSON into memory (a few MB is fine on CF Workers with
static assets). Search = TF scoring over tokens. Deterministic, zero deps.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
CHUNKS_DIR = BASE / "chunks"
OUT = BASE / "search-index.json"

STOP = set("""a an and are as at be by for from has have how in is it its of on or that the to was what when where which who why will with""".split())

TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


def main():
    docs = []       # chunk metadata (without content for index file; content in chunks file)
    postings = {}   # token -> {doc_idx: tf}
    for f in sorted(CHUNKS_DIR.glob("*.jsonl")):
        with f.open() as fh:
            for line in fh:
                c = json.loads(line)
                idx = len(docs)
                docs.append({
                    "chunk_id": c["chunk_id"],
                    "vendor": c["vendor"],
                    "version": c["version"],
                    "title": c["title"],
                    "heading_path": c["heading_path"],
                    "path": c["path"],
                    "source_url": c["source_url"],
                    "license": c["license"],
                    "attribution": c["attribution"],
                    "last_updated": c["last_updated"],
                })
                toks = tokenize(c["title"] + " " + c["heading_path"]) * 3 + tokenize(c["content"])
                for tok, tf in Counter(toks).items():
                    postings.setdefault(tok, {})[idx] = tf

    # IDF
    n = len(docs)
    idf = {t: math.log(1 + n / len(pl)) for t, pl in postings.items()}

    # Compact postings: token -> [[doc_idx, weight], ...]
    compact = {t: [[i, tf * idf[t]] for i, tf in pl.items()] for t, pl in postings.items()}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"docs": docs, "postings": compact, "built_at": __import__("time").strftime("%Y-%m-%d")}))
    size_mb = OUT.stat().st_size / 1e6
    print(f"index: {n} docs, {len(compact)} tokens, {size_mb:.1f} MB -> {OUT}")


if __name__ == "__main__":
    main()
