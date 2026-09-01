# Agent Readiness Score — Analysis & Fix Plan

**Source:** [ora.ai/score/documesh.selatan.org](https://ora.ai/score/documesh.selatan.org)
**Score:** 18/100 (F) · Scanned Sep 1, 2026

---

## Score Breakdown

| Layer | Score | Max | Issue |
|-------|-------|-----|-------|
| Discovery (robots, sitemap, skills) | 25 | 100 | No sitemap, no agent discovery file |
| Access (robots, crawl, bot auth) | 4 | 30 | AI crawlers blocked (ora-agent, DeepSeekBot) |
| Understand (HTML, JSON-LD, llms.txt, skills, docs, NL web) | 0 | 100 | No machine-readable offering description |
| Operate (HTML, WebMCP, NL web, llms.txt, markdown, a11y) | 14 | 100 | WebMCP not detected by external scanner |
| Payments | N/A | — | — |

## Agent Feedback (ora-scan, Sep 1)

> "No machine-readable API documentation or structured data. No sitemap. No agent
> discovery file. Some AI crawlers blocked. No WebMCP support detected, no
> modelContext usage. No agent instruction file with when-to-use guidance."

---

## Root Cause Analysis

These are all **server-level metadata issues** — they're about what Cloudflare
serves at the domain level, not about our application code. The app's WebMCP
tools ARE registered in the browser, but an external scanner checks for
**static files** at well-known paths.

| Missing file | What it is | Impact |
|-------------|-----------|--------|
| `/robots.txt` | Tells crawlers what they can access | Discovery score |
| `/sitemap.xml` | Lists all pages for indexing | Discovery score |
| `/llms.txt` | Declares agent interface (the standard we champion!) | Understand + Operate |
| `/.well-known/ai-plugin.json` | Agent discovery file | Understand |
| JSON-LD structured data | Schema.org markup on pages | Understand |
| `.well-known/skills.json` | Agent skills declaration | Understand |
| robots.txt AI agent rules | Allow/block specific AI crawlers | Access |

---

## Fix Plan (ordered by impact)

### 1. Create static metadata files → `app/`

| File | Content |
|------|---------|
| `app/robots.txt` | Allow all agents, list sitemap |
| `app/sitemap.xml` | List all 6 pages |
| `app/llms.txt` | Documesh agent interface declaration (like Cloudflare/Netlify) |
| `app/.well-known/ai-plugin.json` | Agent plugin manifest |

### 2. Add JSON-LD structured data → all HTML pages

Schema.org `WebApplication` type with name, description, applicationCategory, offers.

### 3. Fix Cloudflare bot protection → CF Dashboard

The scanner reported `ora-agent` and `DeepSeekBot` are blocked. This is Cloudflare's
default "Block AI Scrapers and Crawlers" setting. Go to:
**CF Dashboard → selatan.org → Security → Bots → toggle off "Block AI Scrapers"**

Or better: create a WAF exception rule for `ora-agent` and known agent user-agents.

### 4. Add llms.txt — our own agent interface declaration

This is the same pattern we identified in Cloudflare, Netlify, and Vercel.
It's the highest-impact fix — it turns the "Understand" score from 0 to ~60+.

```
# Documesh
> Documentation that agents can not only read, but operate.
> Federated developer documentation from 18 vendors, version-cited.

## Markdown versions
Every page is available as Markdown: append .md to any URL.

## Pages
- [Home](https://documesh.selatan.org/index.md): Overview and stats
- [App](https://documesh.selatan.org/app.md): Chat interface with WebMCP tools
- [Capabilities](https://documesh.selatan.org/capabilities.md): Tool documentation
- [WebMCP Tools](https://documesh.selatan.org/webmcp.md): Tool reference
- [Coverage](https://documesh.selatan.org/coverage.md): Vendors and licenses
- [Submit Vendor](https://documesh.selatan.org/submit.md): Request ingestion

## API
- GET /health: Service health check
- GET /search?q=&vendors=&limit=: Federated documentation search
- GET /explain?error=&vendor=: Error-to-docs matching
- GET /vendors: Vendor registry with licenses
```

### 5. Add `.md` endpoints for all pages

Cloudflare Workers with static assets can serve `.md` versions if we generate them.
Simpler approach: add a Worker route that returns a markdown representation of each page.

---

## Expected Score After Fix

| Layer | Current | After fix (est.) |
|-------|---------|-----------------|
| Discovery | 25 | 70+ (sitemap + robots) |
| Access | 4 | 25+ (unblock AI crawlers) |
| Understand | 0 | 60+ (llms.txt + JSON-LD) |
| Operate | 14 | 40+ (llms.txt declares WebMCP tools) |
| **Total** | **18** | **~55-65** |

This is realistic — the remaining gap is vendor-side (CF bot protection config)
and needs dashboard access.

---

## Execution Order

| Step | Task | File | Effort |
|------|------|------|--------|
| 1 | robots.txt | `app/robots.txt` | 5 min |
| 2 | sitemap.xml | `app/sitemap.xml` | 5 min |
| 3 | llms.txt | `app/llms.txt` | 10 min |
| 4 | ai-plugin.json | `app/.well-known/ai-plugin.json` | 10 min |
| 5 | JSON-LD on index.html | inline `<script type="application/ld+json">` | 10 min |
| 6 | CF Bot protection config | CF Dashboard (manual) | 5 min |
| 7 | Commit + push → staging auto-deploys | git | 1 min |
