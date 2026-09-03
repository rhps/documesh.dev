#!/usr/bin/env python3
"""
Documesh continuous coverage-deepening loop.

Every cycle:
  1. Read live coverage from D1 (chunks per vendor).
  2. Rank vendors by coverage % (Have / Available-est), worst first.
  3. Pick the 3 worst (that have a known crawler) and deepen them — NO caps.
  4. Backfill D1 (idempotent).
  5. Report a Have/Available/Coverage table; commit chunk files.
Loops forever until every vendor is at ~100% of its crawlable corpus, or
`--max-cycles` is reached. Safe to Ctrl-C: every chunk is upserted to D1 and
committed to git, so progress is never lost.

Usage:
  export CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=...
  python3 indexer/deepen_loop.py                # forever
  python3 indexer/deepen_loop.py --max-cycles 3 # bounded
  python3 indexer/deepen_loop.py --dry          # just rank & print plan
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "indexer"))
from deepen_log import install  # stdout + crash tracebacks -> data/logs/deepen.log
install(__file__)
CHUNKS_DIR = BASE / "data" / "chunks"
SOURCES = json.load(open(BASE / "indexer" / "crawl_sources.json"))

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
DB_ID = "0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b"
BATCH_SIZE = 10          # vendors deepened per cycle, in PARALLEL
CYCLE_PAUSE = 60          # seconds between cycles
PARALLEL_WORKERS = 10     # crawlers running at the same time
NO_COMMIT = False         # --no-commit: skip git commit/push after cycles

# ── Available (est.) crawlable corpus per vendor — the denominator ──────────
AVAILABLE = {
    "cloudflare": 40000, "netlify": 1800, "vercel": 2500, "kubernetes": 4500,
    "bun": 350, "elysia": 150, "turso": 600, "upstash": 700, "sentry": 1500,
    "stripe": 3500, "hono": 300, "nuxt": 1200, "solid": 400, "opentelemetry": 2000,
    "argocd": 700, "helm": 800, "flux": 600, "cilium": 1100, "react": 1600,
    "pytorch": 6000, "tensorflow": 5000, "langchain": 2500, "playwright": 900,
    "clickhouse": 2500, "ollama": 80, "electron": 1200, "hugo": 900,
    "docusaurus": 400, "pytest": 350, "godot": 3000, "neovim": 700,
    "terragrunt": 450, "moby": 1800, "elasticsearch": 4000, "svelte-core": 1700,
    "vue-core-docs": 1500, "gitea": 800, "aws": 45000, "digitalocean": 4000,
    "ibmcloud": 10000, "anthropic": 700, "neon": 500, "clerk": 900,
    "pulumi": 2000, "temporal": 800, "kong": 2000, "nodejs": 5000,
}

# ── Crawler registry: vendor -> callable() -> list[chunk-dicts] ─────────────
# Lazy imports so --dry doesn't need network.

def _crawl_via_deepen(vendor):
    import importlib
    mod = importlib.import_module("deepen_batch1")
    fn = {"aws": mod.crawl_aws, "stripe": mod.crawl_stripe,
          "kubernetes": mod.crawl_kubernetes, "pytorch": mod.crawl_pytorch,
          "ollama": mod.crawl_ollama}.get(vendor)
    return fn() if fn else None


def _crawl_aws_v2():
    import deepen_aws_v2  # runs its own main() writing aws_latest.jsonl
    # re-implement as importable: it's a script; call via subprocess instead
    return None


CRAWLERS = {
    "aws": ("deepen_aws_v2.py", "script"),
    "stripe": ("deepen_batch1.py", "func:crawl_stripe"),
    "kubernetes": ("deepen_batch1.py", "func:crawl_kubernetes"),
    "pytorch": ("deepen_batch1.py", "func:crawl_pytorch"),
    "ollama": ("deepen_batch1.py", "func:crawl_ollama"),
    # generic crawler (add_vendor.py VENDORS patterns) for the rest:
    "digitalocean": ("add_vendor.py", "cli:digitalocean"),
    "ibmcloud": ("add_vendor.py", "cli:ibmcloud"),
    "opentelemetry": ("add_vendor.py", "cli:opentelemetry"),
    "pulumi": ("add_vendor.py", "cli:pulumi"),
    "sentry": ("add_vendor.py", "cli:sentry"),
    "langchain": ("add_vendor.py", "cli:langchain"),
    "vercel": ("add_vendor.py", "cli:vercel"),
    "hugo": ("add_vendor.py", "cli:hugo"),
    "docusaurus": ("add_vendor.py", "cli:docusaurus"),
    "upstash": ("add_vendor.py", "cli:upstash"),
    "bun": ("add_vendor.py", "cli:bun"),
    "tensorflow": ("add_vendor.py", "cli:tensorflow"),
    "clickhouse": ("add_vendor.py", "cli:clickhouse"),
    "nuxt": ("add_vendor.py", "cli:nuxt"),
    "solid": ("add_vendor.py", "cli:solid"),
    "vue-core-docs": ("add_vendor.py", "cli:vue-core-docs"),
    "gitea": ("add_vendor.py", "cli:gitea"),
    "terragrunt": ("add_vendor.py", "cli:terragrunt"),
    "argocd": ("add_vendor.py", "cli:argocd"),
    "moby": ("add_vendor.py", "cli:moby"),
    "helm": ("add_vendor.py", "cli:helm"),
    "flux": ("add_vendor.py", "cli:flux"),
    "cilium": ("add_vendor.py", "cli:cilium"),
    "temporal": ("add_vendor.py", "cli:temporal"),
    "kong": ("add_vendor.py", "cli:kong"),
    "react": ("add_vendor.py", "cli:react"),
    "neovim": ("add_vendor.py", "cli:neovim"),
    "netlify": ("add_vendor.py", "cli:netlify"),
    "elasticsearch": ("add_vendor.py", "cli:elasticsearch"),
    "godot": ("add_vendor.py", "cli:godot"),
    "electron": ("add_vendor.py", "cli:electron"),
    "svelte-core": ("add_vendor.py", "cli:svelte-core"),
    "anthropic": ("add_vendor.py", "cli:anthropic"),
    "neon": ("add_vendor.py", "cli:neon"),
    "clerk": ("add_vendor.py", "cli:clerk"),
    "cloudflare": ("add_vendor.py", "cli:cloudflare"),
}


def have_counts() -> dict[str, int]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query"
    req = urllib.request.Request(url, data=json.dumps(
        {"sql": "SELECT vendor, COUNT(*) n FROM chunks GROUP BY vendor"}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    return {row["vendor"]: row["n"] for row in d["result"][0]["results"]}


def rank(vendor, n):
    avail = AVAILABLE.get(vendor)
    if not avail:
        return 0.0
    return min(100.0, round(100 * n / avail, 1))


def run_crawler_tagged(vendor, counts: dict, results: dict) -> bool:
    """
    Thread-worker wrapper: announces the vendor, runs its crawler, records
    the result. All output is prefixed with [vendor] so parallel threads
    stay distinguishable in stdout and deepen.log.
    """
    print(f"[{vendor}] --- deepening (have {counts.get(vendor, '?')}, "
          f"target {AVAILABLE.get(vendor)}) ---")
    try:
        ok = run_crawler(vendor)
    except Exception as e:
        print(f"[{vendor}] !! crashed: {e}")
        ok = False
    print(f"[{vendor}] done: {'ok' if ok else 'FAILED'}")
    results[vendor] = ok
    return ok


def run_crawler(vendor) -> bool:
    spec = CRAWLERS.get(vendor)
    if not spec:
        print(f"  [{vendor}] !! no crawler registered")
        return False
    script, mode = spec
    if mode == "script":
        print(f"  $ python3 indexer/{script}")
        return subprocess.run(["python3", f"indexer/{script}"], cwd=BASE).returncode == 0
    if mode.startswith("func:"):
        import importlib
        mod = importlib.import_module(script.replace(".py", ""))
        fn = getattr(mod, mode.split(":", 1)[1])
        chunks = fn()
        outp = CHUNKS_DIR / f"{vendor}_latest.jsonl"
        with outp.open("w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"  -> {vendor}: {len(chunks)} chunks written")
        return True
    if mode.startswith("cli:"):
        # add_vendor.py CLI with per-vendor source args from crawl_sources.json
        src = SOURCES.get(vendor)
        if not src:
            print(f"  !! no source registered for {vendor} in crawl_sources.json")
            return False
        cmd = ["python3", f"indexer/{script}", "--id", vendor,
               "--name", src["name"], "--license", src["license"],
               "--cap", "1000000", "--exclude", "changelog,_test,cmdref,blog"]
        if src.get("llms"):
            cmd += ["--llms", src["llms"]]
        elif src.get("repo"):
            cmd += ["--repo", src["repo"], "--docs-path", src.get("docs_path", "")]
            if src.get("branch"):
                cmd += ["--branch", src["branch"]]
        else:
            print(f"  !! source for {vendor} has neither llms nor repo")
            return False
        print(f"  $ {' '.join(cmd[:8])} ...")
        return subprocess.run(cmd, cwd=BASE).returncode == 0
    return False


def backfill_d1() -> bool:
    print("\n--- backfill D1 (idempotent upsert) ---")
    return subprocess.run(["python3", "indexer/load_d1.py"], cwd=BASE).returncode == 0


def git_commit(msg):
    if NO_COMMIT:
        print(f"  (commit skipped — NO_COMMIT mode: {msg})")
        return
    subprocess.run(["git", "add", "-A"], cwd=BASE, capture_output=True)
    r = subprocess.run(["git", "commit", "-m", msg], cwd=BASE, capture_output=True, text=True)
    if "nothing to commit" not in (r.stdout + r.stderr):
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE, capture_output=True)


def report_table(counts, title):
    print(f"\n### {title}\n")
    print(f"| Vendor | Have | Available (est.) | Coverage |")
    print(f"|---|---:|---:|---:|")
    for v in sorted(counts, key=lambda x: rank(x, counts[x])):
        avail = AVAILABLE.get(v)
        avail_s = f"{avail:,}" if isinstance(avail, int) else str(avail)
        print(f"| {v} | {counts[v]:,} | {avail_s} | {rank(v, counts[v]):.0f}% |")
    total = sum(counts.values())
    print(f"\nTotal: {total:,} chunks across {len(counts)} vendors\n")


def acquire_lock():
    """Prevent concurrent instances (double-fetch protection).

    PID lockfile: stale locks (crashed process) are auto-detected via
    /proc (Linux) or `ps` fallback and broken. A live instance blocks startup.
    """
    lock_path = BASE / "indexer" / ".deepen_loop.lock"
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
        except ValueError:
            old_pid = 0
        alive = False
        if old_pid:
            if Path(f"/proc/{old_pid}").exists():          # Linux
                alive = True
            else:                                           # macOS fallback
                alive = subprocess.run(
                    ["pgrep", "-p", str(old_pid)],
                    capture_output=True).returncode == 0
        if alive:
            print(f"another deepen_loop is already running (pid {old_pid}). Exiting.")
            sys.exit(0)
        print(f"removing stale lock (pid {old_pid} not running)")
    lock_path.write_text(str(os.getpid()))

    import atexit
    atexit.register(lambda: lock_path.unlink(missing_ok=True))
    return lock_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cycles", type=int, default=0, help="0 = loop forever")
    ap.add_argument("--dry", action="store_true", help="rank and print plan only")
    ap.add_argument("--batch", type=int, default=BATCH_SIZE)
    ap.add_argument("--workers", type=int, default=PARALLEL_WORKERS,
                    help="crawlers running in parallel per cycle")
    ap.add_argument("--no-commit", action="store_true",
                    help="do NOT git commit/push after each cycle "
                         "(chunks still written to data/chunks/ and backfilled to D1)")
    args = ap.parse_args()
    global NO_COMMIT
    NO_COMMIT = args.no_commit

    if not args.dry and (not TOKEN or not ACCOUNT_ID):
        print("need CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID")
        sys.exit(1)

    if not args.dry:
        acquire_lock()

    cycle = 0
    while True:
        cycle += 1
        print(f"\n{'='*60}\nCYCLE {cycle}\n{'='*60}")
        counts = have_counts()
        report_table(counts, f"Coverage at cycle {cycle} start")

        # rank worst-first; skip vendors already ~complete or without crawler
        ranked = sorted(counts, key=lambda v: rank(v, counts[v]))
        queue = [v for v in ranked
                 if rank(v, counts[v]) < 97.0 and v in CRAWLERS]
        batch = queue[:args.batch]
        if not batch:
            print("ALL VENDORS AT TARGET COVERAGE — done.")
            return
        print(f"batch for this cycle: {batch}\n")

        if args.dry:
            print("(dry) would deepen:", batch)
            return

        # ── deepen the batch, up to args.workers crawlers IN PARALLEL ──
        # Each worker (thread) runs one vendor's crawler. Crawlers are
        # I/O-bound (HTTP fetches), so threads parallelize them cleanly.
        # Logging stays per-vendor-tagged and deep-log writes are locked.
        print(f"\n=== running {len(batch)} crawlers, {args.workers} in parallel ===")
        results = {}
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_crawler_tagged, v, counts, results): v for v in batch}
            for fut in cf.as_completed(futs):
                v = futs[fut]
                try:
                    results[v] = fut.result()
                except Exception as e:
                    results[v] = False
                    print(f"  !! {v}: crawler crashed: {e}")
        for v in batch:
            print(f"  {v}: {'ok' if results.get(v) else 'FAILED'}")
        if not all(results.get(v) for v in batch):
            print("  (some crawlers failed — continuing with what succeeded)")

        if backfill_d1():
            new_counts = have_counts()
            report_table(new_counts, f"Coverage after cycle {cycle} batch")
            git_commit(f"coverage: cycle {cycle} deepen {','.join(batch)}")

        if args.max_cycles and cycle >= args.max_cycles:
            print(f"\nreached --max-cycles {args.max_cycles} — stopping")
            return
        print(f"\nsleeping {CYCLE_PAUSE}s before next cycle...")
        time.sleep(CYCLE_PAUSE)


if __name__ == "__main__":
    main()
