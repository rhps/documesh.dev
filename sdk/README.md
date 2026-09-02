# documesh

Official JavaScript SDK and CLI for [Documesh](https://documesh.selatan.org) — federated developer documentation search across 47 vendors (Cloudflare, Netlify, Vercel, Kubernetes, React, PyTorch, Stripe, Sentry, and more). Every result carries vendor, version, license, and canonical source URL.

- REST API: open, no keys required
- MCP server: `https://documesh.selatan.org/mcp` (Streamable HTTP)
- Docs: [developers.html](https://documesh.selatan.org/developers.html) · [OpenAPI spec](https://documesh.selatan.org/openapi.json)

## Install

```bash
npm install documesh            # SDK
npm install -g documesh         # CLI (documesh on PATH)
```

## SDK usage

```js
import DocumeshClient from "documesh";

const client = new DocumeshClient();

// Federated search
const { results } = await client.search("edge functions env vars", {
  vendors: ["cloudflare", "vercel"],
  limit: 5,
});
for (const r of results) {
  console.log(`[${r.vendor}@${r.version}] ${r.title} — ${r.source_url} (${r.license})`);
}

// Error → documentation
const { matches } = await client.explainError("CrashLoopBackOff in pod docs-api");

// Vendor registry with licenses
const { vendors } = await client.listVendors();
```

## CLI usage

```bash
documesh search "edge functions env vars" --vendors cloudflare,vercel --limit 5
documesh explain "CrashLoopBackOff in pod docs-api"
documesh vendors
documesh health
```

## Authentication

None. The Documesh API is fully open for read-only use. Rate limits are advertised via IETF `RateLimit-*` response headers.

## License

MIT — © selatan.org. Documentation content remains the property of its respective owners; see the [coverage page](https://documesh.selatan.org/coverage.html) for per-source licensing.
