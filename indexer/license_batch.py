#!/usr/bin/env python3
"""
License classification ONLY for the known-repo candidates.
Uses raw.githubusercontent (NO API rate limit). Parallel-friendly, fast.
"""
from __future__ import annotations

import concurrent.futures as cf
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (docs-mesh sweep)"}

KNOWN = {
    "pytorch": ("pytorch/pytorch", "main"),
    "tensorflow": ("tensorflow/tensorflow", "master"),
    "langchain": ("langchain-ai/langchain", "master"),
    "grafana": ("grafana/grafana", "main"),
    "prometheus": ("prometheus/prometheus", "main"),
    "envoy": ("envoyproxy/envoy", "main"),
    "helm": ("helm/helm", "main"),
    "argo cd": ("argoproj/argo-cd", "master"),
    "istio": ("istio/istio", "master"),
    "cilium": ("cilium/cilium", "main"),
    "ansible": ("ansible/ansible", "master"),
    "vault": ("hashicorp/vault", "main"),
    "nomad": ("hashicorp/nomad", "main"),
    "docker": ("moby/moby", "master"),
    "redis": ("redis/redis", "master"),
    "elasticsearch": ("elastic/elasticsearch", "main"),
    "clickhouse": ("clickhouse/clickhouse", "master"),
    "django": ("django/django", "main"),
    "flask": ("pallets/flask", "main"),
    "rails": ("rails/rails", "main"),
    "spring framework": ("spring-projects/spring-framework", "main"),
    "vue.js": ("vuejs/core", "main"),
    "svelte": ("sveltejs/svelte", "main"),
    "react": ("facebook/react", "main"),
    "node.js": ("nodejs/node", "main"),
    "deno": ("denoland/deno", "main"),
    "bun": ("oven-sh/bun", "main"),
    "vite": ("vitejs/vite", "main"),
    "webpack": ("webpack/webpack", "main"),
    "gitlab": ("gitlabhq/gitlabhq", "master"),
    "jenkins": ("jenkinsci/jenkins", "master"),
    "cypress": ("cypress-io/cypress", "develop"),
    "playwright": ("microsoft/playwright", "main"),
    "pytest": ("pytest-dev/pytest", "main"),
    "hugo": ("gohugoio/hugo", "master"),
    "docusaurus": ("facebook/docusaurus", "main"),
    "electron": ("electron/electron", "main"),
    "opencv": ("opencv/opencv", "4.x"),
    "ollama": ("ollama/ollama", "main"),
    "keycloak": ("keycloak/keycloak", "main"),
    "traefik": ("traefik/traefik", "master"),
    "haproxy": ("haproxy/haproxy", "master"),
    "minio": ("minio/minio", "master"),
    "ceph": ("ceph/ceph", "main"),
    "next.js": ("vercel/next.js", "canary"),
    "ghost": ("tryghost/ghost", "main"),
    "mediawiki": ("wikimedia/mediawiki", "master"),
    "gitea": ("go-gitea/gitea", "main"),
    "nagios": ("NagiosEnterprises/nagioscore", "master"),
    "consul": ("hashicorp/consul", "main"),
    "packer": ("hashicorp/packer", "main"),
    "vagrant": ("hashicorp/vagrant", "main"),
    "terragrunt": ("gruntwork-io/terragrunt", "main"),
    "pulumi": ("pulumi/pulumi", "master"),
    "rancher": ("rancher/rancher", "main"),
    "minikube": ("kubernetes/minikube", "master"),
    "apache airflow": ("apache/airflow", "main"),
    "apache spark": ("apache/spark", "master"),
    "apache kafka": ("apache/kafka", "trunk"),
    "apache tomcat": ("apache/tomcat", "trunk"),
    "apache maven": ("apache/maven", "master"),
    "apache echarts": ("apache/echarts", "master"),
    "angular": ("angular/angular", "main"),
    "tailwind css": ("tailwindlabs/tailwindcss", "main"),
    "bootstrap": ("twbs/bootstrap", "main"),
    "selenium": ("seleniumhq/selenium", "trunk"),
    "godot": ("godotengine/godot", "master"),
    "ffmpeg": ("FFmpeg/FFmpeg", "master"),
    "obs studio": ("obsproject/obs-studio", "master"),
    "audacity": ("audacity/audacity", "master"),
    "neovim": ("neovim/neovim", "master"),
    "vim": ("vim/vim", "master"),
}

BRANCHES = ("main", "master", "trunk", "develop", "canary", "unstable")
FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.txt",
         "LICENSE-MIT", "MIT-LICENSE")


def classify(text: str) -> str | None:
    t = text.lower()
    if "apache license" in t or "apache 2.0" in t:
        return "Apache-2.0"
    if "permission is hereby granted" in t or "mit license" in t:
        return "MIT"
    if "bsd" in t and "redistribution" in t:
        return "BSD"
    if "mozilla public" in t:
        return "MPL-2.0"
    if "creative commons" in t:
        if "sharealike" in t:
            return "CC-BY-SA"
        if "public domain" in t or "cc0" in t:
            return "CC0"
        return "CC-BY"
    if "business source" in t:
        return "BUSL"
    if "gnu" in t and ("general public" in t or "affero" in t or "lesser general" in t):
        return "GPL/AGPL/LGPL"
    return "CUSTOM"


def probe(repo):
    for b in BRANCHES:
        for f in FILES:
            url = f"https://raw.githubusercontent.com/{repo}/{b}/{f}"
            req = urllib.request.Request(url, headers=UA)
            try:
                with urllib.request.urlopen(req, timeout=8) as r:
                    lic = classify(r.read().decode("utf-8", "ignore")[:600])
                if lic:
                    return lic, b
            except Exception:
                continue
    return "NOT-FOUND", None


def main():
    names = list(KNOWN.keys())
    results = {}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(probe, KNOWN[n][0]): n for n in names}
        for fut in cf.as_completed(futs):
            n = futs[fut]
            results[n] = fut.result()

    legal = {"Apache-2.0", "MIT", "BSD", "MPL-2.0", "CC-BY", "CC0", "CUSTOM"}
    restricted = {"GPL/AGPL/LGPL", "BUSL"}

    ok, exc, unk = [], [], []
    for n in names:
        lic, b = results[n]
        row = (n, KNOWN[n][0], lic, b)
        if lic in restricted:
            exc.append(row)
        elif lic == "NOT-FOUND":
            unk.append(row)
        elif lic == "CUSTOM":
            unk.append(row)
        else:
            ok.append(row)

    print(f"permissive: {len(ok)} | restricted: {len(exc)} | not-found/custom: {len(unk)}\n")
    print("--- PERMISSIVE (ingestible) ---")
    for n, repo, lic, b in sorted(ok):
        print(f"  {n:22s} {repo:38s} {lic}")
    print("\n--- RESTRICTED (excluded) ---")
    for n, repo, lic, b in sorted(exc):
        print(f"  {n:22s} {repo:38s} {lic}")
    print("\n--- NOT FOUND / CUSTOM ---")
    for n, repo, lic, b in sorted(unk):
        print(f"  {n:22s} {repo:38s} {lic}")

    import json as j
    with open("/tmp/wiki_license_results.json", "w") as f:
        j.dump({n: {"repo": KNOWN[n][0], "license": results[n][0], "branch": results[n][1]} for n in names}, f, indent=1)


if __name__ == "__main__":
    main()
