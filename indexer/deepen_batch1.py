#!/usr/bin/env python3
"""
Deep-coverage ingestion for existing vendors (batch 1: aws, stripe, kubernetes,
pytorch, ollama). Replaces the shallow chunks file per vendor; then rebuild shards.

  python3 indexer/deepen_batch1.py            # all 5
  python3 indexer/deepen_batch1.py aws stripe # subset
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from deepen_log import install  # stdout + crash tracebacks -> data/logs/deepen.log
install(__file__)

BASE = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE / "data" / "chunks"
UA = {"User-Agent": "Mozilla/5.0 (compatible; documesh-indexer/1.0)"}
CHUNK_TARGET = 1800
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")


def fetch(url, timeout=30, redirects=6):
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
        print(f"    !! {e.code} {url[:90]}")
        return None
    except Exception as e:
        print(f"    !! {str(e)[:60]} {url[:90]}")
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


def save(vendor, chunks):
    if not chunks:
        print(f"  !! {vendor}: 0 chunks")
        return 0
    outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
    with outp.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"  -> {vendor}: {len(chunks)} chunks (replaces old file)")
    return len(chunks)


# ────────────────────────────────────────────────────────── AWS ──────────────
# Strategy: the root llms.txt lists per-service sub-indexes. Crawl each service's
# OWN llms.txt for its .md pages. Focus on the top-20 asked-about services.

AWS_SERVICES = [
    "ec2", "s3", "lambda", "bedrock", "rds", "dynamodb", "iam", "cloudformation",
    "eks", "ecs", "route53", "sqs", "sns", "cloudwatch", "secrets-manager",
    "apigateway", "cloudfront", "sagemaker", "elasticloadbalancing", "vpc",
]
AWS_PAGES_PER_SERVICE = 12   # 20 services x 12 pages = ~240 pages


def crawl_aws():
    lic = {"license": "AWS Docs (agent-permitted via llms.txt)",
           "license_url": "https://docs.aws.amazon.com/llms.txt",
           "attribution": "© Amazon Web Services — via llms.txt agent interface, via documesh"}
    out = []
    seen = set()
    root = fetch("https://docs.aws.amazon.com/llms.txt")
    # root index: [Title](https://docs.aws.amazon.com/<svc>/latest/...md)
    service_links = []
    for m in re.finditer(r"\[([^\]]+)\]\((https://docs\.aws\.amazon\.com/[^)\s]+\.md)\)", root or ""):
        url = m.group(2)
        svc = url.split("/")[3]
        service_links.append((svc, m.group(1), url))
    print(f"    root index: {len(service_links)} service pages")

    pages_fetched = 0
    for svc in AWS_SERVICES:
        if pages_fetched >= 240:
            break
        # find service landing pages in root index
        svc_links = [l for l in service_links if l[0] == svc][:3]
        if not svc_links:
            continue
        for _, title, page_md in svc_links:
            md = fetch(page_md)
            if not md or len(md) < 250 or md.lstrip().startswith("<"):
                continue
            # does the landing page reference its own sub-llms.txt? AWS pages link
            # "...llms.txt" — crawl that for deeper pages
            sub_llms = re.findall(r"\((https://docs\.aws\.amazon\.com/[^)\s]+llms\.txt)\)", md)
            page_pool = [(title, page_md)]
            if sub_llms:
                sub = fetch(sub_llms[0])
                for m2 in re.finditer(r"\[([^\]]+)\]\((https://docs\.aws\.amazon\.com/[^)\s]+\.md)\)", sub or ""):
                    page_pool.append((m2.group(1), m2.group(2)))
            fetched_this_svc = 0
            for t2, u2 in page_pool:
                if fetched_this_svc >= AWS_PAGES_PER_SERVICE or pages_fetched >= 240:
                    break
                if u2 in seen:
                    continue
                seen.add(u2)
                md2 = fetch(u2)
                if not md2 or len(md2) < 250 or md2.lstrip().startswith("<"):
                    time.sleep(0.08)
                    continue
                page = u2[:-3] if u2.endswith(".md") else u2
                path = re.sub(r"^https?://docs\.aws\.amazon\.com/", "", page).strip("/")
                for c in chunk_markdown(md2, path):
                    out.append(make_chunk("aws", lic, page, c))
                fetched_this_svc += 1
                pages_fetched += 1
                time.sleep(0.1)
        print(f"    [aws] {svc}: total {len(out)} chunks")
    return out


# ────────────────────────────────────────────────────────── Stripe ───────────
# docs.stripe.com serves .md natively. Crawl llms.txt (large) with wide cap,
# skipping marketing pages.

def crawl_stripe():
    lic = {"license": "Stripe Docs (agent-permitted via llms.txt)",
           "license_url": "https://docs.stripe.com/llms.txt",
           "attribution": "© Stripe — via docs.stripe.com llms.txt interface, via documesh"}
    txt = fetch("https://docs.stripe.com/llms.txt")
    links = [{"title": m.group(1).strip(), "url": m.group(2).strip()}
             for m in re.finditer(r"^\s*-\s+\[([^\]]+)\]\(([^)\s]+)\)", txt or "", re.M)]
    # prioritize API + core guides; skip blog/changelog
    skip = re.compile(r"/(blog|changelog|newsletter)/")
    prio = [l for l in links if "/api" in l["url"] or "/payments" in l["url"]
            or "/billing" in l["url"] or "/connect" in l["url"] or "/terminal" in l["url"]
            or "/cli" in l["url"] or "/webhooks" in l["url"] or "/radar" in l["url"]]
    rest = [l for l in links if l not in prio and not skip.search(l["url"])]
    ordered = prio + rest
    print(f"    [stripe] {len(links)} links; {len(ordered)} after skip")
    out = []
    seen = set()
    cap = 220
    for i, link in enumerate(ordered):
        if len(out) >= cap:
            break
        url = link["url"].split("?")[0].rstrip("/")
        if url in seen or not url.startswith("https://docs.stripe.com/"):
            continue
        seen.add(url)
        # links already end in .md — only append when missing
        md_url = url if url.endswith(".md") else url + ".md"
        md = fetch(md_url)
        if not md or len(md) < 250 or md.lstrip().startswith("<"):
            time.sleep(0.08)
            continue
        path = re.sub(r"^https?://docs\.stripe\.com/", "", url).strip("/") or "index"
        path = re.sub(r"\.md$", "", path)
        for c in chunk_markdown(md, path):
            out.append(make_chunk("stripe", lic, url, c))
        if i % 20 == 0:
            print(f"    [stripe] {i+1}/{len(ordered)}, {len(out)} chunks")
        time.sleep(0.08)
    return out


# ────────────────────────────────────────────────────────── Kubernetes ───────
# Expand K8S_TOPICS massively via the git crawler pattern (raw.githubusercontent).

K8S_EXTRA_TOPICS = [
    # workloads
    "concepts/workloads/pods/disruptions.md", "concepts/workloads/pods/pod-lifecycle.md",
    "concepts/workloads/controllers/_index.md", "concepts/workloads/controllers/deployment.md",
    "concepts/workloads/controllers/statefulset.md", "concepts/workloads/controllers/daemonset.md",
    "concepts/workloads/controllers/job-cron-translation.md",
    "concepts/workloads/cron-jobs.md", "concepts/workloads/replicaset.md",
    # configuration
    "concepts/configuration/overview.md", "concepts/configuration/configmap/_index.md",
    "concepts/configuration/secret/_index.md", "concepts/configuration/resource-management-development.md",
    "concepts/configuration/labels-annotations-taints/_index.md",
    "concepts/configuration/organize-cluster-access-kubeconfig.md",
    "concepts/configuration/manage-resources-containers.md",
    # networking
    "concepts/services-networking/service/_index.md", "concepts/services-networking/ingress.md",
    "concepts/services-networking/network-policies.md", "concepts/services-networking/dns-pod-service.md",
    "concepts/services-networking/gateway.md",
    # storage
    "concepts/storage/volumes.md", "concepts/storage/persistent-volumes.md",
    "concepts/storage/storage-classes.md", "concepts/storage/dynamic-provisioning.md",
    # scheduling/security/cluster
    "concepts/scheduling-eviction/assign-pod-node.md", "concepts/scheduling-eviction/taint-and-toleration.md",
    "concepts/scheduling-eviction/resource-based-pod-scheduling.md",
    "concepts/security/service-accounts.md", "concepts/security/rbac-good-practices.md",
    "concepts/security/secrets-good-practices.md", "concepts/security/controlling-access.md",
    "concepts/architecture/_index.md", "concepts/architecture/control-plane-node-communication.md",
    "concepts/cluster-administration/system-metrics.md", "concepts/cluster-administration/networking.md",
    "concepts/overview/components.md", "concepts/overview/working-with-objects/_index.md",
    "concepts/overview/working-with-objects/names.md", "concepts/overview/working-with-objects/namespaces.md",
    "concepts/overview/working-with-objects/kubernetes-objects.md",
    "concepts/containers/_index.md", "concepts/containers/images.md",
    "concepts/containers/container-lifecycle-hooks.md", "concepts/containers/container-environment.md",
    # tasks
    "tasks/debug-application-cluster/debug-pods.md", "tasks/debug-application-cluster/get-shell-running-container.md",
    "tasks/debug-application-cluster/determine-reason-pod-failure.md",
    "tasks/debug-application-cluster/debug-stateful-set.md", "tasks/debug-application-cluster/debug-service.md",
    "tasks/configure-pod-container/assign-memory-resource.md", "tasks/configure-pod-container/assign-cpu-resource.md",
    "tasks/configure-pod-container/quality-service-pod.md", "tasks/configure-pod-container/configure-volume-storage.md",
    "tasks/run-application/run-stateless-application-deployment.md",
    "tasks/run-application/run-single-instance-stateful-application.md",
    "tasks/run-application/horizontal-pod-autoscale.md", "tasks/run-application/delete-deployment.md",
    "tasks/administer-cluster/kubeadm/kubeadm-upgrade.md",
    "tasks/access-application-cluster/access-cluster.md",
    "tasks/inject-data-application/define-environment-variable-container.md",
    "tasks/inject-data-application/distribute-credentials-secure.md",
    # reference concepts
    "reference/kubernetes-api/workloads-resources/deployment-v1/_index.md",
    "reference/kubernetes-api/workloads-resources/pod-v1/_index.md",
    "reference/kubernetes-api/service-resources/service-v1/_index.md",
    "reference/kubectl/command-response/_index.md",
    "reference/kubectl/cheatsheet/_index.md",
    "reference/glossary/_index.md",
]


def crawl_kubernetes():
    lic = {"license": "CC-BY-4.0",
           "license_url": "https://github.com/kubernetes/website/blob/main/LICENSE",
           "attribution": "© The Kubernetes Authors, CC BY 4.0 — via kubernetes/website"}
    vendor = "kubernetes"
    branch = "main"
    out = []
    ok = 0
    for topic in K8S_EXTRA_TOPICS:
        url = f"https://raw.githubusercontent.com/kubernetes/website/{branch}/content/en/docs/{topic}"
        md = fetch(url)
        if not md or len(md) < 200:
            time.sleep(0.06)
            continue
        rel = topic.replace("_index.md", "").replace(".md", "").strip("/")
        page = f"https://kubernetes.io/docs/{rel}/"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk(vendor, lic, page, c))
        ok += 1
    print(f"    [kubernetes] {ok}/{len(K8S_EXTRA_TOPICS)} topics fetched")
    return out


# ────────────────────────────────────────────────────────── PyTorch ──────────
# pytorch tutorials repo (separate from pytorch/pytorch): docs are .md/.ipynb —
# take the .md ones; plus pytorch/pytorch docs/python_api.

def crawl_pytorch():
    lic = {"license": "BSD-style (permissive)",
           "license_url": "https://github.com/pytorch/tutorials/blob/main/LICENSE",
           "attribution": "© PyTorch contributors — BSD-style, via pytorch/tutorials"}
    out = []
    # tutorials repo: gh tree
    url = "https://api.github.com/repos/pytorch/tutorials/git/trees/main?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        paths = [t["path"] for t in d.get("tree", []) if t["path"].endswith(".md")
                 and not t["path"].startswith((".", "_"))]
    except Exception as e:
        print(f"    !! tree failed: {str(e)[:60]}")
        return out
    paths.sort()
    # prefer beginner/API/recipes dirs
    prio = [p for p in paths if p.startswith(("beginner_source/", "intermediate_source/", "recipes_source/", "advanced_source/"))]
    rest = [p for p in paths if p not in prio]
    matched = [p for p in (prio + rest) if p.count("/") <= 3][:60]
    print(f"    [pytorch] {len(matched)} md files matched (repo total {len(paths)})")
    for i, rp in enumerate(matched):
        raw = f"https://raw.githubusercontent.com/pytorch/tutorials/main/{rp}"
        md = fetch(raw)
        if not md or len(md) < 200:
            time.sleep(0.06)
            continue
        rel = re.sub(r"_(source|tutorials)/", "/", rp).replace(".md", "").replace(".ipynb", "")
        page = f"https://pytorch.org/tutorials/{rel}"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("pytorch", lic, page, c))
        if i % 10 == 0:
            print(f"    [pytorch] {i+1}/{len(matched)}, {len(out)} chunks")
        time.sleep(0.06)
    return out


# ────────────────────────────────────────────────────────── Ollama ───────────
# ollama/ollama docs dir was capped to 8; take the whole docs/ tree + api docs.

def crawl_ollama():
    lic = {"license": "MIT",
           "license_url": "https://github.com/ollama/ollama/blob/main/LICENSE",
           "attribution": "© Ollama contributors — MIT License, via docs-mesh"}
    out = []
    url = "https://api.github.com/repos/ollama/ollama/git/trees/main?recursive=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        paths = [t["path"] for t in d.get("tree", []) if t["path"].endswith(".md")
                 and t["path"].startswith(("docs/", "api/", "README"))]
    except Exception as e:
        print(f"    !! tree failed: {str(e)[:60]}")
        return out
    paths.sort()
    print(f"    [ollama] {len(paths)} md files")
    for i, rp in enumerate(paths):
        raw = f"https://raw.githubusercontent.com/ollama/ollama/main/{rp}"
        md = fetch(raw)
        if not md or len(md) < 150:
            time.sleep(0.05)
            continue
        rel = re.sub(r"\.md$", "", rp).lstrip("/")
        page = f"https://github.com/ollama/ollama/tree/main/{rp}"
        for c in chunk_markdown(md, rel):
            out.append(make_chunk("ollama", lic, page, c))
    print(f"    [ollama] {len(out)} chunks")
    return out


JOBS = {
    "aws": crawl_aws,
    "stripe": crawl_stripe,
    "kubernetes": crawl_kubernetes,
    "pytorch": crawl_pytorch,
    "ollama": crawl_ollama,
}


def main():
    requested = sys.argv[1:] or list(JOBS.keys())
    unknown = [v for v in requested if v not in JOBS]
    if unknown:
        print(f"unknown: {unknown}. available: {list(JOBS.keys())}")
        sys.exit(1)
    totals = {}
    for v in requested:
        print(f"\n=== {v} (deepen) ===")
        try:
            totals[v] = save(v, JOBS[v]())
        except Exception as e:
            print(f"  !! FAILED: {str(e)[:120]}")
    print("\n=== BATCH 1 SUMMARY ===")
    for v, n in totals.items():
        print(f"  {v}: {n} chunks")
    print("next: python3 indexer/build_shards.py && rebuild D1 backfill for these vendors")


if __name__ == "__main__":
    main()
