#!/usr/bin/env python3
"""
Repair data/vendors.json v2 — the conflict stack is deep (5 cycles of
markers nested inside each other), so instead of parsing the broken file,
RECONSTRUCT the registry from scratch:

1. Start from the authoritative 47-vendor registry: the last known-good
   full registry is recoverable from the git history of the OLD machine's
   commits — but simplest authoritative source: origin/main's copy of
   data/vendors.json is broken, so rebuild from:
     - worker/src/search-core-lite.js VENDOR_META (names/licenses for all 47)
     - the last clean registry in git: edd8964 (4 vendors w/ license_url+docs_origin)
   and then
2. Overlay EVERY complete vendor entry salvageable from the conflicted file
   (all conflict sides + normal regions), newest wins.
"""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PATH = BASE / "data" / "vendors.json"


def salvage_entries(frag: str) -> dict:
    """Brace-match individual '"vendor": {...}' blocks out of broken JSON."""
    out = {}
    for m in re.finditer(r'"([a-zA-Z0-9_-]+)":\s*\{', frag):
        start = m.end() - 1
        depth = 0
        for j in range(start, len(frag)):
            if frag[j] == "{":
                depth += 1
            elif frag[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out[m.group(1)] = json.loads(frag[start:j + 1])
                    except json.JSONDecodeError:
                        pass
                    break
    return out


def strip_conflict_keep_all(text: str) -> dict:
    lines = text.splitlines()
    merged = {}
    buf = []
    i, n = 0, len(lines)

    def flush(frag_lines, label):
        frag = "\n".join(frag_lines).strip()
        if not frag:
            return
        got = salvage_entries(frag)
        if got:
            print(f"  + {label}: {len(got)} entries: {sorted(got)[:10]}")
            merged.update(got)

    while i < n:
        line = lines[i]
        if line.startswith("<<<<<<<"):
            flush(buf, "normal region")
            buf = []
            i += 1
            side = []
            while i < n and not lines[i].startswith(">>>>>>>"):
                if lines[i].startswith("======="):
                    flush(side, "  side")
                    side = []
                else:
                    side.append(lines[i])
                i += 1
            flush(side, "  side(final)")
        else:
            buf.append(line)
        i += 1
    flush(buf, "normal region(final)")
    return merged


def main():
    # 1. authoritative base: all 47 from search-core-lite.js VENDOR_META
    src = (BASE / "worker" / "src" / "search-core-lite.js").read_text()
    # entries look like:   cloudflare: { name: "Cloudflare", license: "CC-BY-4.0", ... }
    entries = re.findall(
        r'^\s+"?([a-zA-Z0-9_-]+)"?\s*:\s*\{\s*name:\s*"([^"]+)",\s*license:\s*"([^"]*)"', src, re.M)
    final = {}
    for vid, name, lic in entries:
        final[vid] = {
            "name": name, "license": lic, "license_url": "",
            "docs_origin": "worker/src/search-core-lite.js (registry rebuild)",
            "attribution_required": True,
        }
    print(f"base from VENDOR_META: {len(final)} vendors")

    # 2. richer fields from the last clean git version (edd8964: 4 vendors)
    r = subprocess.run(["git", "show", "edd8964:data/vendors.json"],
                       capture_output=True, text=True, cwd=BASE)
    if r.returncode == 0:
        try:
            old = json.loads(r.stdout)
            for k, v in old.items():
                if k in final:
                    final[k].update(v)   # restore license_url/docs_origin/added
                else:
                    final[k] = v
            print(f"overlay from edd8964 clean registry: +{len(old)} enriched")
        except json.JSONDecodeError:
            print("edd8964 registry unreadable — skipped")

    # 3. salvage everything from the conflicted working file (all sides)
    conflicted = PATH.read_text()
    salvaged = strip_conflict_keep_all(conflicted)
    final.update(salvaged)   # newest crawl data wins
    print(f"after salvage overlay: {len(final)} vendors")

    PATH.write_text(json.dumps(final, indent=1) + "\n")
    check = json.loads(PATH.read_text())
    print(f"\nFINAL: {len(check)} vendors, valid JSON ✓")

    # sanity: the sources the site advertises
    must = ["cloudflare", "netlify", "vercel", "kubernetes", "langchain",
            "clickhouse", "ibmcloud", "hugo", "moby", "pytorch", "aws"]
    missing = [m for m in must if m not in check]
    print("spot-check missing:", missing if missing else "none ✓")
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
