# Documesh Agent Plugin

This repository is also a distributable **Agent Plugin** ([agent-plugins.org](https://agent-plugins.org) spec v1.0.0).

## Install

Point any Agent Plugins-compatible client at this repository (or clone it and load the directory).

## What it provides

| Component | Type | Description |
|---|---|---|
| `skills/search-docs` | Agent Skill | Federated documentation search across 47 sources |
| `skills/explain-error` | Agent Skill | Match error messages/log excerpts to the closest official docs |
| `skills/list-sources` | Agent Skill | Browse the source registry with license + attribution requirements |
| `mcp.json` | MCP server | `documesh` — Streamable HTTP at `https://documesh.selatan.org/mcp` (no auth, read-only) |

## Manifest

- `plugin.json` — Agent Plugins v1.0.0 manifest (`$schema: .../schemas/1.0.0/plugin.schema.json`)
- `mcp.json` — MCP server configuration (Streamable HTTP, no credentials required)

All components are read-only and hit the public Documesh API; results carry
per-source license attribution.
