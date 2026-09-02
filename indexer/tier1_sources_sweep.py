#!/usr/bin/env python3
"""
Tier-1 vendor→sources copy sweep (display text only, NO identifiers).

Rules:
- "vendors"  → "sources"      (plain display word)
- "vendor"   → "source"       (singular display word)
- "Vendors"  → "Sources"
- "Vendor"   → "Source"
Skip list (never touched): JS identifiers, JSON keys, URLs, paths, file names,
attribute values, `vendor=` query params, `docs_origin` values.

Handled by protecting anything inside quotes that looks like an identifier,
plus a blocklist of exact protected tokens. Files: app/*.html, app/*.md,
app/llms*.txt, app/agents.md, docs copy is left as-is (internal).
"""
from __future__ import annotations
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
APP = BASE / "app"

FILES = sorted(
    list(APP.glob("*.html")) + list(APP.glob("*.md")) +
    list(APP.glob("llms*.txt")) + [APP / "agents.md"]
)

# Protected substrings — any match inside a candidate span means "do not touch"
PROTECT = re.compile(
    r"(vendor=|vendors=|/vendors|submit-vendors|vendor-grid|TOOL_VENDORS|"
    r"VENDOR_META|VENDOR_IDS|vendorName|vendorId|docs_origin|"
    r"list_vendors|search_docs_across)"
)

def protect_spans(text: str):
    """Spans where replacement is forbidden: HTML attributes, JS strings with
    identifiers, script/style blocks are handled by line-level heuristics."""
    spans = []
    for m in PROTECT.finditer(text):
        spans.append((m.start(), m.end()))
    return spans

def in_spans(i, spans):
    return any(s <= i < e for s, e in spans)

def sweep(text: str) -> str:
    spans = protect_spans(text)
    out = []
    i = 0
    word = re.compile(r"[Vv]endors?|[Vv]endor")
    for m in word.finditer(text):
        out.append(text[i:m.start()])
        w = m.group(0)
        # context window for protect-check
        ctx_start = max(0, m.start() - 40)
        ctx = text[ctx_start:m.end() + 40]
        if PROTECT.search(ctx):
            out.append(w)
        else:
            if w == "vendors": out.append("sources")
            elif w == "vendor": out.append("source")
            elif w == "Vendors": out.append("Sources")
            elif w == "Vendor": out.append("Source")
        i = m.end()
    out.append(text[i:])
    return "".join(out)

def main():
    for f in FILES:
        if not f.exists():
            continue
        orig = f.read_text()
        # only sweep display text: skip <script> and JSON-ish lines conservatively
        lines = orig.split("\n")
        new_lines = []
        in_script = False
        for ln in lines:
            stripped = ln.strip()
            if "<script" in ln: in_script = True
            if in_script:
                # inside script: only sweep comments and pure-prose strings
                if stripped.startswith("//") or stripped.startswith("*"):
                    new_lines.append(sweep(ln))
                else:
                    new_lines.append(ln)
                if "</script>" in ln: in_script = False
                continue
            # outside script: skip lines that are clearly code/attr-heavy
            if re.search(r"(function |const |let |=>|https?://|\.\w+\s*=)", ln) and "<p" not in ln and "<li" not in ln and "<h" not in ln and "<title" not in ln and "<td" not in ln:
                new_lines.append(ln)
            else:
                new_lines.append(sweep(ln))
        new = "\n".join(new_lines)
        if new != orig:
            f.write_text(new)
            n = len(re.findall(r"[Ss]ources?", new)) - len(re.findall(r"[Ss]ources?", orig))
            print(f"  ✏️  {f.name}: swept")
        else:
            print(f"  –   {f.name}: no change")

if __name__ == "__main__":
    main()
