#!/usr/bin/env python3
"""
Rebrand vendor IDs to dev-friendly display names across all user-facing pages.
E.g. "cloudflare" → "Cloudflare", "kubernetes" → "Kubernetes",
     "godot-docs" → "Godot", "vue-core-docs" → "Vue"
"""
from pathlib import Path
import re

APP = Path(__file__).resolve().parent.parent / "app"

# Display name mapping: raw_id → Dev Friendly Name
DISPLAY_NAMES = {
    "cloudflare": "Cloudflare",
    "netlify": "Netlify",
    "vercel": "Vercel",
    "kubernetes": "Kubernetes",
    "bun": "Bun",
    "elysia": "ElysiaJS",
    "turso": "Turso",
    "upstash": "Upstash",
    "sentry": "Sentry",
    "stripe": "Stripe",
    "hono": "Hono",
    "nuxt": "Nuxt",
    "solid": "SolidJS",
    "opentelemetry": "OpenTelemetry",
    "argocd": "Argo CD",
    "helm": "Helm",
    "flux": "Flux CD",
    "cilium": "Cilium",
    "react": "React",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "langchain": "LangChain",
    "playwright": "Playwright",
    "clickhouse": "ClickHouse",
    "ollama": "Ollama",
    "electron": "Electron",
    "hugo": "Hugo",
    "docusaurus": "Docusaurus",
    "pytest": "pytest",
    "nodejs": "Node.js",
    "godot-docs": "Godot",
    "neovim": "Neovim",
    "terragrunt": "Terragrunt",
    "moby": "Docker",
    "elasticsearch": "Elasticsearch",
    "svelte-core": "Svelte",
    "vue-core-docs": "Vue",
    "gitea": "Gitea",
}

# In app.html and coverage.html, replace the raw vendor ID shown to users
# with the display name. We need to find patterns like:
#   <span class="...">cloudflare</span>  → <span class="...">Cloudflare</span>
#   ${r.vendor} → needs a lookup

# For JS-rendered pages (app.html), we inject a vendor display name lookup map
# and patch the renderResults/renderExplain functions.

lookup_js = """
// Vendor display names (dev-friendly, not raw IDs)
const VENDOR_NAMES = """ + json_dumps(DISPLAY_NAMES) + """;
function vendorName(id) { return VENDOR_NAMES[id] || id; }
"""

def json_dumps(d):
    import json
    return json.dumps(d)

# For each HTML file, replace raw vendor IDs in visible text with display names
for f in sorted(APP.glob("*.html")):
    text = f.read_text()
    orig = text
    for vid, display in DISPLAY_NAMES.items():
        # Replace in visible text content (between > <), not in JS code or attributes
        # Pattern: >vendor_id< → >Display Name<
        text = text.replace(f">{vid}<", f">{display}<")
        # Also replace in template literals: `${r.vendor}` patterns
        pass
    if text != orig:
        f.write_text(text)
        print(f"✅ {f.name}")
    else:
        print(f"–  {f.name}")
