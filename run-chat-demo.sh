#!/usr/bin/env bash
# One command to run the conversational MVP demo.
#
# Starts the two services the path needs, wires them together, and drops you
# into the chat client:
#
#   Mosaic  (:8080)  -- GraphQL + the MCP boundary, incl. converse_query_spec
#   Exon    (:9100)  -- the stateless turn-taking planning service
#   chat             -- stands in for Aperture's UI; talks only to Mosaic
#
# Both services are stopped again on exit. Run from the repo root.
set -uo pipefail

MOSAIC_PORT="${MOSAIC_PORT:-8080}"
EXON_PORT="${EXON_TURN_PORT:-9100}"
EXON_URL="http://127.0.0.1:${EXON_PORT}/turn"
LOGDIR="$(mktemp -d)"

cleanup() {
  echo ""
  echo "Shutting down..."
  [[ -n "${EXON_PID:-}" ]] && kill "$EXON_PID" 2>/dev/null
  [[ -n "${MOSAIC_PID:-}" ]] && kill "$MOSAIC_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Logs kept in $LOGDIR"
}
trap cleanup EXIT INT TERM

die() { echo "ERROR: $*" >&2; exit 1; }

wait_for() { # wait_for <url> <name> <logfile>
  for _ in $(seq 1 40); do
    curl -s -o /dev/null --max-time 1 "$1" && return 0
    kill -0 "$2" 2>/dev/null || { echo "--- $3 ---"; cat "$3"; die "$4 died on startup."; }
    sleep 0.5
  done
  echo "--- $3 ---"; cat "$3"
  die "$4 did not come up in 20s."
}

[[ -f mosaic.yaml ]] || die "run this from the repo root (no mosaic.yaml here)."
[[ -f data/mosaic.db ]] || die "no data/mosaic.db -- run 'make migrate && make ingest' first."
command -v mosaic >/dev/null || die "'mosaic' not on PATH -- is datahelix-mosaic installed?"

if [[ -z "${AWS_BEARER_TOKEN_BEDROCK:-}${AWS_ACCESS_KEY_ID:-}${AWS_PROFILE:-}${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}${GEMINI_API_KEY:-}" ]]; then
  echo "WARNING: no model credential detected in the environment."
  echo "  Exon calls an LLM per turn; without one, every turn will fail."
  echo "  Default model is \$EXON_MODEL or bedrock/...claude-haiku-4-5 (see exon/README.md)."
  echo ""
fi

echo "1/3  Starting Mosaic on :${MOSAIC_PORT} (GraphQL + MCP, Exon at ${EXON_URL}) ..."
MOSAIC_EXON_URL="$EXON_URL" \
  mosaic serve --config mosaic.yaml --graphql --mcp --port "$MOSAIC_PORT" \
  > "$LOGDIR/mosaic.log" 2>&1 &
MOSAIC_PID=$!
wait_for "http://127.0.0.1:${MOSAIC_PORT}/graphql" "$MOSAIC_PID" "$LOGDIR/mosaic.log" "Mosaic"
echo "     Mosaic up."

echo "2/3  Starting Exon's turn service on :${EXON_PORT} ..."
EXON_TURN_PORT="$EXON_PORT" \
  MOSAIC_MCP_URL="http://127.0.0.1:${MOSAIC_PORT}/mcp" \
  python3 -m exon.conversational_server > "$LOGDIR/exon.log" 2>&1 &
EXON_PID=$!
# /turn is POST-only, so a GET returning 405 still proves it is listening.
wait_for "http://127.0.0.1:${EXON_PORT}/docs" "$EXON_PID" "$LOGDIR/exon.log" "Exon"
echo "     Exon up, grounded in the live schema."

echo "3/3  Starting chat."
echo ""
MOSAIC_MCP_URL="http://127.0.0.1:${MOSAIC_PORT}/mcp" python3 -m exon.chat
