# Backfill Guide — Staging vs Production D1

There are two D1 databases. Pick the right one for the job.

| Database | ID | Bound to Worker env | Who writes it |
|---|---|---|---|
| `documesh-search-staging` | `ebf178ef-b7c6-4f92-920c-6d95528b9f19` | staging worker (Deploy Staging) | test/experiment runs |
| `documesh-search` | `0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b` | production worker (Deploy Production, tagged) | **the deepen loop + normal backfills** |

## TL;DR

**The deepen loop and `load_d1.py` already default to the PRODUCTION database.**
If you just run them, you are backfilling production. Nothing extra needed:

```bash
export CLOUDFLARE_API_TOKEN=***
export CLOUDFLARE_ACCOUNT_ID=bbcfb524d633f21f6a7888b0aade6f4f

python3 indexer/load_d1.py                      # backfill production DB (default)
nohup python3 indexer/deepen_loop.py > deepen.log 2>&1 &   # loop → production DB
```

## Explicit control (recommended habit)

Every script honors the `D1_DATABASE_ID` env var — set it explicitly so you never
guess which DB you're touching:

```bash
# PRODUCTION (default, but be explicit)
export D1_DATABASE_ID=0a83a2f0-86c3-49ff-b98c-a7856d3a0d8b
python3 indexer/load_d1.py

# STAGING (only when you deliberately want to test against the staging DB)
export D1_DATABASE_ID=ebf178ef-b7c6-4f92-920c-6d95528b9f19
python3 indexer/load_d1.py
```

(`deepen_loop.py` currently has the production ID hardcoded; use load_d1.py with
`D1_DATABASE_ID` if you ever need the loop to target staging — or ask for the
one-line change to make it env-driven too.)

## Verify which DB you just wrote

```bash
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/d1/database/$D1_DATABASE_ID/query" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT COUNT(*) AS n FROM chunks"}'
```

## Verify what the LIVE SITE sees

The site reads whichever DB the *running worker* is bound to:

```bash
# federated search through the live worker
curl -s 'https://documesh.selatan.org/search?q=crashloopbackoff&limit=1' | head -c 200
```

- Results come back with `backend: d1` → the live worker's DB has the data. Done.
- Empty/`results: []` for something you just backfilled → the live worker is bound
  to the OTHER database. Fix: promote (tag → Deploy Production) so the production
  worker (bound to `documesh-search`) serves — or re-point the staging env's binding
  in wrangler.jsonc if you want both envs on the same DB.

## Schema (one-time, per database)

Both DBs already have the schema applied. If you ever create a new database:

```bash
python3 indexer/d1_schema_apply.py    # honors D1_DATABASE_ID too
```
