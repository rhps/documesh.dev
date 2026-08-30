#!/usr/bin/env python3
"""Add 'Built with love by selatan.org' footer credit to all pages that lack it."""
from pathlib import Path
import re

APP = Path(__file__).resolve().parent.parent / "app"

CREDIT = '''  <div class="max-w-6xl mx-auto px-6 pb-6 text-sm text-slate-500">
    Built with ❤️ by <a href="https://selatan.org" target="_blank" class="font-medium text-slate-700 hover:text-orange-600">selatan.org</a>
  </div>
'''

for f in APP.glob("*.html"):
    text = f.read_text()
    if "Built with" in text and "selatan.org" in text:
        print(f"–  {f.name}: already has credit")
        continue
    # insert right before </footer>
    if "</footer>" in text:
        text = text.replace("</footer>", CREDIT + "</footer>", 1)
        f.write_text(text)
        print(f"✅ {f.name}: credit added")
    else:
        print(f"⚠️  {f.name}: no <footer> found")
