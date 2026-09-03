# Source Expansion Runbook — 47 → 1000 targets

**Status:** Milestone 1 complete — **547 verified sources** in `indexer/crawl_sources.json`
(was 47 live in D1; the remaining 500 are verified-ready, backfill pending).
**Backfill:** run later on the server via `deepen_loop.py` / `add_vendor.py` (unchanged flow).

---

## What was done (milestone 1, laptop-run)

All sources verified **live** before admission, prioritized by popularity:

| Tier | Selection basis | Added | Interface |
|---|---|---:|---|
| 0 | Major SaaS/cloud/framework docs (hand-curated ~200, popularity = market adoption) | 102 | llms.txt × 88, repo × 14 |
| 1 | Languages, runtimes, data/ML/ORM ecosystems (hand-curated) | 114 | llms.txt × 55, repo × rest, sitemap fallback |
| 2 | npm ecosystem: top packages' homepages probed for /llms.txt (3700+ homepages scanned) + PyPI top-3000 (readthedocs/sitemap) | 294 | llms.txt × 350, sitemap × 22 |

Verification method (`indexer/source_expansion.py`):
- `GET <origin>/llms.txt` and `/docs/llms.txt` → admit if ≥300 bytes AND ≥3/5 links
- Repo fallback: GitHub API default-branch + docs/ .md count (rate-limited: 60/hr unauth)
- Junk filtered: stars >400k anomalies, GPL/AGPL/SSPL/BUSL licenses, generic ids

Sampled re-verification after merge: **8/8 still 200 OK**.

## Remaining gap to 1000: ~453 sources

The bottleneck is **candidate discovery**, not verification. Proven next levers, in order:

### Lever A — GitHub token (unlocks ~200–400 repo admits, biggest win)
The 1200 repos harvested from awesome-lists (`/tmp/sources/awesome_repos.json` — regenerate
via `gen_candidates.py` logic) were only partially verified because unauthenticated GitHub
API = 60 req/hr. With a token (5000/hr):
```bash
export GITHUB_TOKEN=ghp_...        # user creates: github.com → settings → tokens (read:public)
python3 indexer/source_expansion.py /tmp/sources/awesome_repos_converted.jsonl /tmp/sources/awesome_verified.jsonl
# merge admits: same merge block as milestone 1
```
Repo admits need the git-tree crawler (`add_vendor.py` pattern) at backfill time.

### Lever B — more npm rounds (unlimited, ~100–150 admits per ~15 min)
`registry.npmjs.org/-/v1/search` is unauthenticated and generous. Each round:
different term set → homepages → `llms.txt` probe → merge. 784 origins/round yielded 139
admits. ~4 more rounds ≈ +400–500 candidates ≈ +150 admits, reaching ~700 total.

### Lever C — docs-platform sweeps
- Mintlify-hosted docs: `<sub>.mintlify.app/llms.txt` auto-exists for every hosted project.
  Needs a subdomain list (mintlify.com/explore or sitemap harvest).
- Docusaurus/Nextra sites commonly expose `/llms.txt` via plugins — probe awesome-docusaurus
  lists' deployed URLs.
- GitLab Pages, Vercel/Netlify preview domains: same pattern.

### Lever D — PyPI via libraries.io or BigQuery (needs free API key)
Top-PyPI gave only 22 because readthedocs redirects were not probed deeply. libraries.io
(free key) exposes homepages for 100k+ packages — same homepage→llms.txt probe.

## Backfill (when ready — server, laptop-independent)

1. `git pull` on server.
2. `deepen_loop.py` picks worst-coverage sources automatically — but new sources have
   `AVAILABLE` unset, so first run:
   ```bash
   python3 indexer/add_vendor.py --id <source_id> --cap 300   # per new source, or
   # a batch wrapper over crawl_sources.json entries (llms → P1 crawler, repo → P4, sitemap → sitemap crawl)
   ```
3. `python3 indexer/load_d1.py` — upserts into production D1; live immediately, no deploy.
4. **Frontend counts**: the "47 sources" strings in `app/index.html` (meta tags),
   `openapi.json`, `agent-card.json`, ARD, npm description are hand-set. Update AFTER
   backfill when the real count is known — one `grep -rn "47 sources\|47 vendors" app/ sdk/`
   pass. (Deliberately not done now: the live site must not claim counts D1 doesn't have.)

## Honesty guards (unchanged)
- Only llms.txt agent-permitted or permissive-license repos admitted; BUSL/SSPL/GPL excluded.
- Every chunk keeps license + attribution + source_url via existing crawlers.
- Registry ids are slugs; collisions skipped (`if sid in sources: continue`).
