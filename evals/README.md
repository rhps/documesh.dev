# Documesh Evals

Automated evaluation suite for Documesh WebMCP tools, built on
[webmcp-evals](https://github.com/GoogleChromeLabs/webmcp-tools/tree/main/webmcp-evals)
by GoogleChromeLabs.

## Test Suites

| File | Mode | What it tests | LLM needed |
|------|------|---------------|------------|
| `documesh-smoke.json` | `smoke` | 4 tool-call correctness checks against live page | ❌ No |
| `documesh-agent.json` | `browser` | 3 full agent-loop scenarios (LLM discovers + calls tools) | ✅ Yes |

## Run Locally

```bash
# Smoke (deterministic, no LLM):
npx webmcp-evals smoke -u https://documesh.selatan.org -e evals/documesh-smoke.json -v

# Browser (full agent loop, needs GOOGLE_AI or OPENAI_API_KEY):
npx webmcp-evals browser -u https://documesh.selatan.org -e evals/documesh-agent.json --open
```

## CI Integration

- `deploy-staging.yml`: runs `smoke` after deploy — fail-closed gate
- `deploy-production.yml`: runs `smoke` pre-promotion
- `browser` mode is optional (needs Chromium + LLM key in secrets)

## What each eval checks

| Case | Tool | Asserts |
|------|------|---------|
| federated search | `search_docs_across` | query contains "edge functions", limit is a number |
| CrashLoopBackOff | `explain_error` | log_excerpt contains "CrashLoopBackOff" |
| vendor registry | `list_vendors` | no args needed |
| vendor filter | `search_docs_across` | query contains "redirect", vendors contains "vercel" |
