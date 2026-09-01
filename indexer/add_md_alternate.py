#!/usr/bin/env python3
"""Add markdown alternate link tags + lastmod to all HTML pages."""
from pathlib import Path
import re

APP = Path(__file__).resolve().parent.parent / "app"

for f in sorted(APP.glob("*.html")):
    text = f.read_text()
    if "text/markdown" in text:
        print(f"–  {f.name}: already has markdown alternate")
        continue

    page_name = f.stem
    canonical = f"https://documesh.selatan.org/{page_name}" if page_name != "index" else "https://documesh.selatan.org/"
    md_link = f'<link rel="alternate" type="text/markdown" href="{canonical}.md" />'

    if "</head>" in text:
        text = text.replace("</head>", md_link + "\n</head>", 1)
        f.write_text(text)
        print(f"✅ {f.name}: markdown alternate added → {canonical}.md")
    else:
        print(f"⚠️  {f.name}: no </head>")
