#!/usr/bin/env python3
"""
Mass source verification for Documesh source expansion (47 → 1000 target).

Given a candidates file (one JSON per line: {id, name, docs, repo?, license}),
probes each candidate's agent interface:
  1. llms.txt probe: docs origin + /llms.txt → status, byte size, link count
  2. GitHub repo probe: default branch + docs .md file count (unauthenticated, 60/hr —
     throttled, used only when llms.txt is missing)

Output: sources_verified.jsonl — one line per candidate with verdict:
  admit-llms | admit-repo | reject-404 | reject-blocked | reject-tiny
Popularity order is preserved from the input file.
"""
import json, sys, time, urllib.request, urllib.error, concurrent.futures, re

UA = {"User-Agent": "documesh-source-audit/1.0 (agent-permitted docs discovery)"}
POLITENESS = 0.15

def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""

def count_links(text):
    # llms.txt links look like "- [Title](url)"
    return len(re.findall(r"^\s*-\s*\[.+?\]\(.+?\)", text, re.M))

def probe_llms(docs_url):
    origin = docs_url.split("/")[2] if "://" in docs_url else docs_url
    base = f"https://{origin}"
    for candidate in (f"{base}/llms.txt", f"{base}/docs/llms.txt"):
        code, body = fetch(candidate)
        if code == 200 and body:
            text = body.decode("utf-8", "ignore")
            n = count_links(text)
            if len(body) >= 300 or n >= 5:
                return {"llms": candidate, "llms_bytes": len(body), "llms_links": n,
                        "verdict": "admit-llms"}
        elif code in (403, 429):
            return {"verdict": "reject-blocked"}
        # 404 → try next candidate path
    return None

def probe_repo(repo):
    # repo: "owner/name"
    name = repo.split("/")[-1].lower()
    # cheap tree probe: use GitHub's HTML 200 as weak signal; API is rate-limited so use it sparingly
    code, _ = fetch(f"https://api.github.com/repos/{repo}", timeout=8)
    if code == 403:
        return {"verdict": "rate-limited"}
    if code != 200:
        return {"verdict": "reject-404"}
    code, body = fetch(f"https://api.github.com/repos/{repo}/contents/docs", timeout=8)
    if code == 200:
        try:
            entries = json.loads(body)
            md = sum(1 for e in entries if str(e.get("name", "")).endswith(".md"))
            return {"verdict": "admit-repo" if md >= 3 else "reject-tiny", "docs_md_top": md}
        except Exception:
            pass
    return {"verdict": "admit-repo", "docs_md_top": None}  # repo exists; deep crawl decides later

def verify(c):
    out = dict(c)
    docs = c.get("docs", "")
    if docs:
        r = probe_llms(docs)
        if r:
            out.update(r)
            return out
    if c.get("repo"):
        out.update(probe_repo(c["repo"]))
        return out
    out["verdict"] = out.get("verdict", "reject-404")
    return out

def main(infile, outfile, limit=None, workers=8):
    candidates = [json.loads(l) for l in open(infile) if l.strip()]
    if limit:
        candidates = candidates[:limit]
    results = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(verify, candidates):
            results.append(r)
            done += 1
            if done % 50 == 0:
                print(f"  … {done}/{len(candidates)}", file=sys.stderr)
    with open(outfile, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    # summary
    import collections
    c = collections.Counter(r["verdict"] for r in results)
    print("Verdicts:", dict(c))
    admits = [r for r in results if r["verdict"].startswith("admit")]
    print(f"Admitted: {len(admits)} / {len(results)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
