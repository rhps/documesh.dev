# WebMCP Evals — Integration Plan for Documesh

**Source:** [GoogleChromeLabs/webmcp-tools/webmcp-evals](https://github.com/GoogleChromeLabs/webmcp-tools/tree/main/webmcp-evals)
**Date:** 2026-09-01 · Status: planned (post-hackathon feature, aligned with judging criteria)

---

## 1. What webmcp-evals Is

A TypeScript evaluation framework and CLI by GoogleChromeLabs for testing
**WebMCP tool-calling** against live pages. It has three execution modes:

| Mode | What it does | Needs LLM? | Needs browser? |
|------|-------------|------------|----------------|
| `local` | Tests static tool schema JSON files (offline) | Yes | No |
| `browser` | Tests live WebMCP tools on a real page via Puppeteer | Yes | Yes (Chromium) |
| **`smoke`** | Executes expected tool calls against a live page — **no LLM, no API key** | No | Yes (headless) |

**Key features:**
- **Constraint-based matching**: `$pattern`, `$contains`, `$gt/$gte`, `$lt/$lte`, `$type`, ordered/unordered
- **Reporters**: console, JSON, HTML (`.evals/` directory)
- **Analyze command**: LLM root-cause analysis of failures
- **Multi-backend**: Gemini, OpenAI, Ollama, Vercel AI SDK

---

## 2. How It Fits Documesh

Our current eval (`worker/eval.mjs`) tests the **API layer** directly (curl →
`/search` → assert results). webmcp-evals tests the **WebMCP layer** — the actual
agent-to-tool interaction on the live page. These are complementary:

```
worker/eval.mjs        → tests the API works (deterministic, no browser)
webmcp-evals smoke     → tests the WebMCP tools fire correctly on the live page
webmcp-evals browser   → tests the full agent loop (LLM → tool call → result)
```

This maps directly to our judging criteria:
| Criterion | Covered by |
|-----------|-----------|
| WebMCP Leverage | `webmcp-evals browser` — proves tools are discoverable and callable |
| Execution | `webmcp-evals smoke` — proves tools return correct results on the live page |
| API quality | `worker/eval.mjs` — proves the backend logic is correct |

---

## 3. Implementation Plan

### Phase 1 — Smoke evals (CI-ready, no LLM needed)

Create `evals/documesh-smoke.json`:

```json
[
  {
    "name": "search_docs_across — federated search returns results",
    "messages": [{
      "role": "user",
      "type": "message",
      "content": "Search for edge functions environment variables"
    }],
    "expectedCall": [{
      "functionName": "search_docs_across",
      "arguments": {
        "query": { "$contains": "edge functions" },
        "limit": { "$type": "number" }
      }
    }]
  },
  {
    "name": "explain_error — CrashLoopBackOff returns kubernetes match",
    "messages": [{
      "role": "user",
      "type": "message",
      "content": "Error: CrashLoopBackOff container failed to start, exit code 1"
    }],
    "expectedCall": [{
      "functionName": "explain_error",
      "arguments": {
        "log_excerpt": { "$contains": "CrashLoopBackOff" }
      }
    }]
  },
  {
    "name": "list_vendors — returns full registry",
    "messages": [{
      "role": "user",
      "type": "message",
      "content": "List all vendors in the mesh"
    }],
    "expectedCall": [{
      "functionName": "list_vendors",
      "arguments": {}
    }]
  }
]
```

Run against live staging:
```bash
npx webmcp-evals smoke -u https://documesh.selatan.org -e evals/documesh-smoke.json -v
```

**Gate:** all 3 cases must pass. Add to CI as a post-deploy smoke test.

### Phase 2 — Browser evals (full agent loop, needs Chromium + LLM key)

Create `evals/documesh-agent.json`:

```json
[
  {
    "name": "Agent finds Cross-vendor answer",
    "messages": [{
      "role": "user",
      "type": "message",
      "content": "Can I run Postgres on Cloudflare Workers with Terraform managing DNS?"
    }],
    "expectedCall": [{
      "functionName": "search_docs_across",
      "arguments": {
        "query": { "$contains": "postgres" }
      }
    }]
  },
  {
    "name": "Agent routes error to explain_error",
    "messages": [{
      "role": "user",
      "type": "message",
      "content": "My pod keeps crashing with OOMKilled, what do I do?"
    }],
    "expectedCall": [{
      "functionName": "explain_error",
      "arguments": {
        "log_excerpt": { "$contains": "OOMKilled" }
      }
    }]
  }
]
```

Run with Puppeteer against staging:
```bash
npx webmcp-evals browser -u https://documesh.selatan.org -e evals/documesh-agent.json --open
```

### Phase 3 — CI integration

Add to `deploy-staging.yml` (post-deploy, after smoke test):

```yaml
- name: WebMCP evals (smoke)
  run: |
    npx webmcp-evals smoke \
      -u https://documesh.selatan.org \
      -e evals/documesh-smoke.json \
      --timeout 30000
```

Add to `deploy-production.yml` (pre-promotion gate):
```yaml
- name: WebMCP evals (production gates)
  run: |
    npx webmcp-evals smoke \
      -u https://beta.documesh.dev \
      -e evals/documesh-smoke.json
```

### Phase 4 — Reports as submission evidence

- Run `npx webmcp-evals browser` with `--reporter html` → generates `.evals/report-*.html`
- Include the HTML report as a Devpost attachment — shows judges that tool-calling was **independently verified**
- Frame as: "We don't just claim our tools work — we have an automated evaluation suite proving it"

---

## 4. What This Gives Us for Judging

| Criterion | Evidence from webmcp-evals |
|-----------|--------------------------|
| WebMCP Leverage | Automated proof that tools are discoverable via WebMCP and return correct results |
| Execution | Smoke tests pass on the live production URL — not just locally |
| Potential Impact | Agent-loop evals show real conversations working end-to-end |
| Creativity | Using GoogleChromeLabs' own eval framework against our mesh = ecosystem validation |

---

## 5. Prerequisites

| Need | Where | Status |
|------|-------|--------|
| Node.js 22 | CI runners have it | ✅ |
| Chromium (for browser mode) | `npx puppeteer browsers install` | Install in CI |
| LLM API key (for browser mode only) | `GOOGLE_AI` or `OPENAI_API_KEY` secret | For smoke mode: not needed |
| Live staging/production URL | Already deployed | ✅ |

## 6. Timeline

| Phase | When | Blocked on |
|-------|------|-----------|
| Phase 1 (smoke) | Now — write evals JSON, test locally | Staging must be green |
| Phase 2 (browser) | After Phase 1 passes | Chromium + optional LLM key |
| Phase 3 (CI) | After Phase 2 | Staging green + secrets |
| Phase 4 (reports) | Before Devpost submission | All phases green |
