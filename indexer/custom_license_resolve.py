#!/usr/bin/env python3
"""Resolve the 8 CUSTOM/NOT-FOUND licenses by reading actual license text."""
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (docs-mesh sweep)"}

CHECKS = [
    ("bun", "oven-sh/bun", "main", ["LICENSE"]),
    ("ceph", "ceph/ceph", "main", ["COPYING", "COPYING-LGPL2.1", "LICENSE"]),
    ("django", "django/django", "main", ["LICENSE", "LICENSE.python", "LICENSE Whitespace"]),
    ("flask", "pallets/flask", "main", ["LICENSE.txt", "LICENSE"]),
    ("haproxy", "haproxy/haproxy", "master", ["LICENSE", "LICENSE-gpl"]),
    ("next.js", "vercel/next.js", "canary", ["LICENSE", "license.md"]),
    ("pytorch", "pytorch/pytorch", "main", ["LICENSE"]),
    ("vim", "vim/vim", "master", ["LICENSE", "README.txt"]),
]


def fetch_raw(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read().decode("utf-8", "ignore")[:800].lower()
    except Exception:
        return None


def classify(t):
    if not t:
        return None
    if "apache license" in t:
        return "Apache-2.0"
    if "permission is hereby granted" in t or "mit license" in t:
        return "MIT"
    if "bsd" in t and "redistribution" in t:
        return "BSD"
    if "mozilla public" in t:
        return "MPL-2.0"
    if "creative commons" in t:
        return "CC-BY"
    if "business source" in t:
        return "BUSL"
    if "gnu" in t and ("general public" in t or "affero" in t):
        return "GPL/AGPL/LGPL"
    if "charityware" in t:
        return "Charityware (Vim)"
    if "psf" in t or "python software foundation" in t:
        return "PSF (Python-like)"
    if "redistribution and use" in t:
        return "BSD-style"
    return "CUSTOM: " + t[:80]


for name, repo, branch, files in CHECKS:
    verdict = "NOT-FOUND"
    for f in files:
        for b in [branch, "master", "main"]:
            t = fetch_raw(f"https://raw.githubusercontent.com/{repo}/{b}/{f}")
            if t:
                v = classify(t)
                if v and not v.startswith("CUSTOM"):
                    verdict = v
                    break
                if verdict == "NOT-FOUND" and v:
                    verdict = v  # remember first custom finding as fallback
    print(f"{name:10s} → {verdict}")
