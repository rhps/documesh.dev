#!/usr/bin/env python3
"""
Recolor Documesh from orange/slate to Army Greens palette with dominant light tones.

Palette (color-hex.com/1037642):
  #2b310a  darkest olive  (text on light, dark sections)
  #4b5320  army green     (primary buttons, accents)
  #6a7337  olive          (hover states, secondary accents)
  #929a68  sage           (borders, subtle accents)
  #a9af8b  light sage     (light backgrounds, badges)

Dominant light → background stays white/slate-50, buttons/accents = army green family.
"""
from pathlib import Path
import re

APP = Path(__file__).resolve().parent.parent / "app"

# orange-* → army-green-* replacements (Tailwind class mapping)
ORANGE_MAP = [
    # primary buttons / CTAs
    ("bg-orange-600", "bg-[#4b5320]"),
    ("hover:bg-orange-500", "hover:bg-[#6a7337]"),
    ("bg-orange-500", "bg-[#6a7337]"),
    ("text-orange-600", "text-[#4b5320]"),
    ("hover:text-orange-500", "hover:text-[#6a7337]"),
    ("text-orange-500", "text-[#6a7337]"),
    ("text-orange-700", "text-[#4b5320]"),
    ("border-orange-500", "border-[#4b5320]"),
    ("border-orange-400", "border-[#929a68]"),
    ("border-orange-200", "border-[#929a68]"),
    ("bg-orange-50", "bg-[#a9af8b]/20"),
    ("bg-orange-100", "bg-[#a9af8b]/30"),
    ("text-orange-300", "text-[#929a68]"),
    ("text-orange-400", "text-[#929a68]"),
    ("hover:border-orange-500", "hover:border-[#4b5320]"),
    ("hover:border-orange-400", "hover:border-[#929a68]"),
    ("hover:border-orange-200", "hover:border-[#929a68]"),
    ("focus:border-orange-500", "focus:border-[#4b5320]"),
    ("shadow-orange-200", "shadow-[#a9af8b]/40"),
    ("bg-gradient-to-r from-orange-600 to-amber-500", "bg-gradient-to-r from-[#4b5320] to-[#6a7337]"),
    # amber (disclaimers etc) → olive
    ("text-amber-600", "text-[#6a7337]"),
    ("text-amber-400", "text-[#6a7337]"),
    ("text-amber-400/80", "text-[#929a68]"),
    ("border-amber-200", "border-[#929a68]"),
    ("bg-amber-100", "bg-[#a9af8b]/30"),
    ("text-amber-700", "text-[#4b5320]"),
]

for f in sorted(APP.glob("*.html")):
    text = f.read_text()
    orig = text
    for old, new in ORANGE_MAP:
        text = text.replace(old, new)
    if text != orig:
        f.write_text(text)
        count = sum(1 for o, _ in ORANGE_MAP if o in orig)
        print(f"✅ {f.name}: recolored")
    else:
        print(f"–  {f.name}: no changes")

print("\nDone — Army Greens palette applied with dominant light background.")
