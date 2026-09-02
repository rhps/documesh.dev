/**
 * Documesh SDK — lightweight client for the Documesh federated documentation API.
 * Zero dependencies, ESM + CJS compatible.
 */
const DEFAULT_BASE = "https://documesh.selatan.org";

export class DocumeshClient {
  constructor({ base = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
    this.base = base.replace(/\/$/, "");
    this.fetch = fetchImpl;
  }

  async #get(path) {
    const res = await this.fetch(`${this.base}${path}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      let err;
      try { err = (await res.json()).error; } catch {}
      const message = err?.message || `Documesh API error ${res.status}`;
      const e = new Error(message);
      e.code = err?.code || "http_error";
      e.status = res.status;
      throw e;
    }
    return res.json();
  }

  /** Federated documentation search across vendors. */
  async search(query, { vendors, limit = 5, cursor } = {}) {
    const params = new URLSearchParams({ q: query });
    if (vendors?.length) params.set("vendors", vendors.join(","));
    if (limit) params.set("limit", String(limit));
    if (cursor) params.set("cursor", cursor);
    return this.#get(`/v1/search?${params}`);
  }

  /** Match an error message or log excerpt to documentation sections. */
  async explainError(logExcerpt, { vendor } = {}) {
    const params = new URLSearchParams({ error: logExcerpt });
    if (vendor) params.set("vendor", vendor);
    return this.#get(`/v1/explain?${params}`);
  }

  /** List all vendors in the mesh with license and attribution info. */
  async listVendors({ cursor, limit } = {}) {
    const params = new URLSearchParams();
    if (cursor) params.set("cursor", cursor);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return this.#get(`/v1/vendors${qs ? `?${qs}` : ""}`);
  }

  /** Service health. */
  async health() {
    return this.#get("/v1/health");
  }

  /** NLWeb natural-language query (JSON mode). */
  async ask(query) {
    return this.#get(`/ask?q=${encodeURIComponent(query)}`);
  }
}

export default DocumeshClient;
