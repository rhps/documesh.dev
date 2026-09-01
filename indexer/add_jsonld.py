#!/usr/bin/env python3
"""Add JSON-LD structured data to all HTML pages."""
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

JSON_LD = '''<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "Documesh",
  "description": "Federated developer documentation from 18 vendors — Cloudflare, Netlify, Vercel, Kubernetes, and more. Search, error matching, and vendor lookup with version-cited, license-attributed results. Powered by WebMCP.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Web",
  "url": "https://documesh.selatan.org",
  "license": "https://github.com/rhps/documesh.dev/blob/main/LICENSE",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
  "author": { "@type": "Organization", "name": "selatan.org", "url": "https://selatan.org" },
  "featureList": [
    "Federated documentation search across 18 vendors",
    "Error-to-documentation matching",
    "WebMCP tool registration for AI agents",
    "Version-cited results with license attribution"
  ]
}
</script>'''

for f in sorted(APP.glob("*.html")):
    text = f.read_text()
    if "application/ld+json" in text:
        print(f"–  {f.name}: already has JSON-LD")
        continue
    # insert before </head>
    if "</head>" in text:
        text = text.replace("</head>", JSON_LD + "\n</head>", 1)
        f.write_text(text)
        print(f"✅ {f.name}: JSON-LD added")
    else:
        print(f"⚠️  {f.name}: no </head> found")
