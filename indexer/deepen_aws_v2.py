#!/usr/bin/env python3
"""
AWS deep crawl v2: root llms.txt → 952 sub-llms.txt indexes → per-service .md pages.
Focuses on top services; caps total pages.
"""
from __future__ import annotations
import json, re, time, hashlib, urllib.request, urllib.error
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from deepen_log import install  # stdout + crash tracebacks -> data/logs/deepen.log
install(__file__)

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (compatible; documesh-indexer/1.0)"}
CHUNK_TARGET = 1800
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")

PRIORITY_SERVICES = [
    "ec2", "s3", "lambda", "bedrock", "rds", "dynamodb", "iam", "cloudformation",
    "eks", "ecs", "route53", "sqs", "sns", "cloudwatch", "secrets-manager",
    "apigateway", "cloudfront", "sagemaker", "elasticloadbalancing", "vpc",
]
MAX_TOTAL_PAGES = 400
PAGES_PER_INDEX = 15


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
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


def make_chunk(lic, url, c):
    slug = re.sub(r"[^a-z0-9]+", "-", f"{c['path']}#{c['heading_path']}".lower()).strip("-")[:80]
    h = hashlib.sha1(c["content"].encode()).hexdigest()[:8]
    return {"chunk_id": f"aws:latest:{slug}:{h}", "vendor": "aws", "version": "latest",
            "path": c["path"], "heading_path": c["heading_path"], "title": c["title"],
            "content": c["content"], "source_url": url,
            "license": lic["license"], "license_url": lic["license_url"],
            "attribution": lic["attribution"], "last_updated": SNAPSHOT_DATE}


def rank_index(url):
    u = url.lower()
    for i, svc in enumerate(PRIORITY_SERVICES):
        if f"/{svc}/" in u or f"/{svc}-" in u:
            return i
    return 100


def main():
    lic = {"license": "AWS Docs (agent-permitted via llms.txt)",
           "license_url": "https://docs.aws.amazon.com/llms.txt",
           "attribution": "© Amazon Web Services — via llms.txt agent interface, via documesh"}
    root = fetch("https://docs.aws.amazon.com/llms.txt")
    sub_indexes = list(dict.fromkeys(re.findall(r"\((https://docs\.aws\.amazon\.com/[^)\s]+llms\.txt)\)", root or "")))
    sub_indexes.sort(key=rank_index)
    print(f"root: {len(sub_indexes)} sub-indexes; prioritizing {PRIORITY_SERVICES}")

    out = []
    seen_pages = set()
    idx_count = 0
    for sub_url in sub_indexes:
        if len(out) >= MAX_TOTAL_PAGES * 2:   # chunks ≈ 2x pages
            break
        sub = fetch(sub_url)
        idx_count += 1
        if not sub:
            continue
        pages = re.findall(r"\[([^\]]+)\]\((https://docs\.aws\.amazon\.com/[^)\s]+\.md)\)", sub)
        got = 0
        for _, page_md in pages:
            if got >= PAGES_PER_INDEX or len(out) >= MAX_TOTAL_PAGES * 2:
                break
            if page_md in seen_pages:
                continue
            seen_pages.add(page_md)
            md = fetch(page_md)
            if not md or len(md) < 250 or md.lstrip().startswith("<"):
                time.sleep(0.06)
                continue
            page = page_md[:-3]
            path = re.sub(r"^https?://docs\.aws\.amazon\.com/", "", page).strip("/")
            for c in chunk_markdown(md, path):
                out.append(make_chunk(lic, page, c))
            got += 1
            time.sleep(0.08)
        if idx_count % 15 == 0:
            print(f"  {idx_count}/{len(sub_indexes)} indexes, {len(out)} chunks, {len(seen_pages)} pages")

    outp = CHUNKS_DIR / "aws_latest.jsonl"
    with outp.open("w") as f:
        for c in out:
            f.write(json.dumps(c) + "\n")
    print(f"-> aws: {len(out)} chunks ({len(seen_pages)} pages, {idx_count} indexes)")


if __name__ == "__main__":
    main()
