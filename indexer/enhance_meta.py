#!/usr/bin/env python3
"""Enhance JSON-LD and add meta tags (canonical, og:image, og:type) to all pages."""
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Enhanced JSON-LD to replace existing
OLD_LD_START = '<script type="application/ld+json">'
ENHANCED_LD = '''<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "Documesh",
  "url": "https://documesh.selatan.org",
  "description": "Federated developer documentation from 18 vendors — Cloudflare, Netlify, Vercel, Kubernetes, and more. Search, error matching, and vendor lookup with version-cited, license-attributed results. Powered by WebMCP.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Web",
  "license": "https://github.com/rhps/documesh.dev/blob/main/LICENSE",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
  "author": {
    "@type": "Organization",
    "name": "selatan.org",
    "url": "https://selatan.org",
    "contactPoint": {
      "@type": "ContactPoint",
      "email": "rhps@selatan.org",
      "contactType": "technical support"
    },
    "address": {
      "@type": "PostalAddress",
      "addressCountry": "GB"
    }
  },
  "publisher": {
    "@type": "Organization",
    "name": "selatan.org",
    "url": "https://selatan.org"
  },
  "sameAs": [
    "https://github.com/rhps/documesh.dev",
    "https://selatan.org",
    "https://webmcp.devpost.com"
  ],
  "featureList": [
    "Federated documentation search across 18 vendors",
    "Error-to-documentation matching",
    "WebMCP tool registration for AI agents",
    "Version-cited results with license attribution",
    "License-aware ingestion with legal exclusions"
  ],
  "softwareRequirements": "WebMCP-compatible browser (ChatGPT in-app browser or Chrome 149+)"
}
</script>'''

# Meta tags to add after <meta name="viewport"...>
META_TAGS = '''<link rel="canonical" href="https://documesh.selatan.org/" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://documesh.selatan.org/" />
  <meta property="og:title" content="Documesh — documentation that agents can read and operate" />
  <meta property="og:description" content="Federated developer documentation from 18 vendors. Powered by WebMCP." />
  <meta property="og:image" content="https://documesh.selatan.org/og-image.png" />
  <meta property="og:site_name" content="Documesh" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="Documesh" />
  <meta name="twitter:description" content="Federated developer documentation from 18 vendors. Powered by WebMCP." />'''

for f in sorted(APP.glob("*.html")):
    text = f.read_text()
    changed = False

    # Replace existing JSON-LD with enhanced version
    if "application/ld+json" in text:
        import re
        text = re.sub(
            r'<script type="application/ld\+json">.*?</script>',
            ENHANCED_LD,
            text,
            count=1,
            flags=re.S
        )
        changed = True

    # Add canonical + og tags if missing
    if 'rel="canonical"' not in text:
        # set per-page canonical
        page_name = f.stem
        canonical = "https://documesh.selatan.org/" if page_name == "index" else f"https://documesh.selatan.org/{page_name}"
        meta = META_TAGS.replace('href="https://documesh.selatan.org/"', f'href="{canonical}"')
        meta = meta.replace('content="https://documesh.selatan.org/"', f'content="{canonical}"')
        # insert after viewport meta
        text = text.replace(
            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n' + meta
        )
        changed = True

    if changed:
        f.write_text(text)
        print(f"✅ {f.name}")
    else:
        print(f"–  {f.name}")
