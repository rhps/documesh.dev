#!/bin/sh
# DNS-AID record creation for documesh.selatan.org (isitagentready DNS-AID check)
#
# Creates SVCB records in the _agents namespace advertising the A2A and
# MCP agent endpoints. Requires CLOUDFLARE_API_TOKEN with Zone:DNS:Edit
# on selatan.org and CLOUDFLARE_ZONE_ID.
#
# Records (SVCB, per DNS-AID draft):
#   _a2a._agents.documesh.selatan.org   -> a2a endpoint on this host
#   _mcp._agents.documesh.selatan.org   -> MCP streamable-http endpoint
#   _index._agents.documesh.selatan.org -> index (agent-card) pointer
#
# Usage: CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ZONE_ID=... ./scripts/create-dns-aid.sh
set -eu

: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN (Zone:DNS:Edit on selatan.org)}"
: "${CLOUDFLARE_ZONE_ID:?Set CLOUDFLARE_ZONE_ID for selatan.org}"

API="https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records"
AUTH=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json")

add_record() {
  name="$1"; data="$2"
  body=$(printf '{"type":"SVCB","name":"%s","data":{"priority":1,"targetname":"documesh.selatan.org","alpn":"%s","port":443,"mandatory":["alpn","port"]},"ttl":3600}' "$name" "$data")
  resp=$(curl -s -X POST "$API" "${AUTH[@]}" -d "$body")
  ok=$(echo "$resp" | grep -o '"success":[a-z]*' | head -1)
  echo "$name -> $ok"
}

# _a2a._agents — advertises the A2A JSON-RPC service (alpn token: a2a)
add_record "_a2a._agents.documesh.selatan.org" "a2a"
# _mcp._agents — advertises the MCP streamable-http service
add_record "_mcp._agents.documesh.selatan.org" "mcp"
# _index._agents — advertises the agent-card index
add_record "_index._agents.documesh.selatan.org" "a2a"

echo "Done. Verify with:"
echo "  curl 'https://dns.google/resolve?name=_a2a._agents.documesh.selatan.org&type=SVCB'"
