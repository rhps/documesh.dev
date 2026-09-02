#!/usr/bin/env python3
"""
Build app/stats/coverage-catalog.json from the coverage audit.

Maps audit vendor ids -> mesh ids (alias table), defaults vendors with
unreachable catalogs to pct:null (unknown, shown as gray). Commit the output
so the /stats endpoint (and the coverage page) can read it as a static asset.

Usage: python3 indexer/build_coverage_catalog.py
"""
from __future__ import annotations
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# audit id -> mesh id (differs only for these)
ALIAS = {
    "hono": "hono",
    "bun": "bun",
    "upstash": "upstash",
}

# mesh ids with no catalog figure (audit 'unreach' or git-tree-only sources):
# coverage unknown -> null (gray on the coverage page)
UNKNOWN = {
    "bun": None, "upstash": None,
    # git-tree ingested sources (no llms.txt catalog to diff against)
    "react": None, "pytorch": None, "tensorflow": None, "ollama": None,
    "electron": None, "hugo": None, "pytest": None, "nodejs": None,
    "godot": None, "neovim": None, "terragrunt": None, "moby": None,
    "elasticsearch": None, "opentelemetry": None, "argocd": None, "helm": None,
    "flux": None, "cilium": None, "gitea": None, "playwright": None,
    "docusaurus": None, "svelte-core": None, "vue-core-docs": None,
    "langchain": None, "clickhouse": None, "kubernetes": None,
}

def main():
    audit_path = BASE / "data" / "coverage_audit.json"
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}

    out = {}
    for audit_id, info in audit.items():
        mesh_id = ALIAS.get(audit_id, audit_id)
        if info.get("catalog") is None:
            out[mesh_id] = {"catalog": None, "pct": None}
        else:
            out[mesh_id] = {"catalog": info["catalog"], "pct": info.get("pct")}
    for mesh_id, val in UNKNOWN.items():
        out.setdefault(mesh_id, {"catalog": None, "pct": val})

    dest = BASE / "app" / "stats" / "coverage-catalog.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    known = sum(1 for v in out.values() if v["pct"] is not None)
    print(f"wrote {dest} — {len(out)} entries, {known} with known coverage")

if __name__ == "__main__":
    main()
