#!/usr/bin/env bash
# One command to run the conversational MVP demo.
#
# Starts the services the path needs, wires them together, and drops you into
# the chat client:
#
#   Mosaic        (:8080)  -- GraphQL + the MCP boundary, incl. converse_query_spec
#   Exon          (:9100)  -- the stateless turn-taking planning service
#   Aperture web  (:5173)  -- the browser SPA, dev server (vite); optional --
#                              set APERTURE_WEB_DIR to enable, see below
#   chat                   -- terminal stand-in for Aperture's UI; talks only to Mosaic
#
# Aperture's web dev server is started only when APERTURE_WEB_DIR points at a
# checkout with dependencies installed (`npm install` in that directory) --
# see openspec/changes/add-aperture-chat-panel/tasks.md 3.1/3.2. It boots
# alongside Mosaic/Exon but, until Mosaic's converseQuerySpec mutation and
# Aperture's own chat panel both exist (tracked external to this repo), it has
# nothing new to demo over the terminal chat -- starting it now just proves
# the launcher wiring ahead of that landing.
#
# All started services are stopped again on exit. Run from the repo root.
set -uo pipefail

MOSAIC_PORT="${MOSAIC_PORT:-8080}"
EXON_PORT="${EXON_TURN_PORT:-9100}"
EXON_URL="http://127.0.0.1:${EXON_PORT}/turn"
APERTURE_WEB_DIR="${APERTURE_WEB_DIR:-}"
APERTURE_WEB_PORT="${APERTURE_WEB_PORT:-5173}"
LOGDIR="$(mktemp -d)"

cleanup() {
  echo ""
  echo "Shutting down..."
  [[ -n "${APERTURE_PID:-}" ]] && kill "$APERTURE_PID" 2>/dev/null
  [[ -n "${EXON_PID:-}" ]] && kill "$EXON_PID" 2>/dev/null
  [[ -n "${MOSAIC_PID:-}" ]] && kill "$MOSAIC_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Logs kept in $LOGDIR"
}
trap cleanup EXIT INT TERM

die() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to run when something already holds a port we need.
#
# Without this the script lies: our own server fails to bind, dies, and the
# readiness check below is then satisfied by the FOREIGN process already on
# that port -- so it prints "up" about a server it did not start and cannot
# configure. That happened for real: a leftover Mosaic started without
# MOSAIC_EXON_URL answered /graphql, so the launcher reported success and the
# chat then correctly complained that converse_query_spec was missing. The
# error was three steps from the cause, which is exactly the kind of thing a
# preflight check should make impossible.
require_free_port() { # require_free_port <port> <what-it-is-for>
  local pid
  pid="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  [[ -z "$pid" ]] && return 0
  echo "ERROR: port $1 is already in use (needed for $2)." >&2
  echo "  PID $pid: $(ps -p "$pid" -o args= 2>/dev/null | cut -c1-120)" >&2
  echo "" >&2
  echo "  This script starts and configures its own servers, so a leftover one" >&2
  echo "  cannot be reused -- it almost certainly lacks the wiring this demo needs." >&2
  echo "  Stop it and retry:   kill $pid" >&2
  exit 1
}

wait_for() { # wait_for <url> <pid> <logfile> <name> <port>
  for _ in $(seq 1 40); do
    if curl -s -o /dev/null --max-time 1 "$1"; then
      # Liveness is not enough: confirm the thing answering is OURS.
      local owner
      owner="$(lsof -nP -iTCP:"$5" -sTCP:LISTEN -t 2>/dev/null | head -1)"
      if [[ -n "$owner" && "$owner" != "$2" ]]; then
        echo "--- $3 ---"; cat "$3"
        die "$4 responded on :$5 but from PID $owner, not the one we started ($2)."
      fi
      return 0
    fi
    kill -0 "$2" 2>/dev/null || { echo "--- $3 ---"; cat "$3"; die "$4 died on startup."; }
    sleep 0.5
  done
  echo "--- $3 ---"; cat "$3"
  die "$4 did not come up in 20s."
}

[[ -f mosaic.yaml ]] || die "run this from the repo root (no mosaic.yaml here)."
[[ -f data/mosaic.db ]] || die "no data/mosaic.db -- run 'make migrate && make ingest' first."
command -v mosaic >/dev/null || die "'mosaic' not on PATH -- is datahelix-mosaic installed?"

# A missing credential is fatal, not advisory: Exon calls a model on EVERY
# turn, so the demo would start cleanly and then fail on the first thing you
# type -- the worst possible moment. Stop here instead, where the fix is
# obvious. Set DEMO_SKIP_CRED_CHECK=1 to start anyway.
if [[ -z "${AWS_BEARER_TOKEN_BEDROCK:-}${AWS_ACCESS_KEY_ID:-}${AWS_SESSION_TOKEN:-}${AWS_PROFILE:-}${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}${GEMINI_API_KEY:-}" ]]; then
  # A default-profile credentials file counts too -- litellm/boto3 will find it.
  if [[ -r "$HOME/.aws/credentials" ]] || [[ -r "$HOME/.aws/config" ]]; then
    echo "NOTE: no model credential in the environment, but ~/.aws/ exists --"
    echo "      assuming boto3 picks it up. If turns fail with an auth error,"
    echo "      export AWS_BEARER_TOKEN_BEDROCK or AWS_PROFILE explicitly."
    echo ""
  elif [[ -n "${DEMO_SKIP_CRED_CHECK:-}" ]]; then
    echo "WARNING: no model credential found; continuing because DEMO_SKIP_CRED_CHECK is set."
    echo ""
  else
    echo "ERROR: no model credential found, and Exon calls a model on every turn." >&2
    echo "  Every message you type would fail, so stopping here instead." >&2
    echo "" >&2
    echo "  Set ONE of these in this shell, then retry:" >&2
    echo "    export AWS_BEARER_TOKEN_BEDROCK=...   # Bedrock bearer token" >&2
    echo "    export AWS_PROFILE=...                # or a configured AWS profile" >&2
    echo "    export ANTHROPIC_API_KEY=...          # with EXON_MODEL=anthropic/claude-..." >&2
    echo "" >&2
    echo "  Current model: \${EXON_MODEL:-bedrock/global.anthropic.claude-haiku-4-5-...}" >&2
    echo "  Provider conventions: exon/README.md, 'Running it'." >&2
    echo "  To start anyway:  DEMO_SKIP_CRED_CHECK=1 ./run-chat-demo.sh" >&2
    exit 1
  fi
fi

require_free_port "$MOSAIC_PORT" "Mosaic"
require_free_port "$EXON_PORT" "Exon's turn service"

STEP_COUNT=3
if [[ -n "$APERTURE_WEB_DIR" ]]; then
  [[ -d "$APERTURE_WEB_DIR" ]] || die "APERTURE_WEB_DIR=$APERTURE_WEB_DIR does not exist."
  [[ -d "$APERTURE_WEB_DIR/node_modules" ]] || die \
    "$APERTURE_WEB_DIR has no node_modules -- run 'npm install' there first."
  require_free_port "$APERTURE_WEB_PORT" "Aperture's web dev server"
  STEP_COUNT=4
fi

echo "1/${STEP_COUNT}  Starting Mosaic on :${MOSAIC_PORT} (GraphQL + MCP, Exon at ${EXON_URL}) ..."
MOSAIC_EXON_URL="$EXON_URL" \
  mosaic serve --config mosaic.yaml --graphql --mcp --port "$MOSAIC_PORT" \
  > "$LOGDIR/mosaic.log" 2>&1 &
MOSAIC_PID=$!
wait_for "http://127.0.0.1:${MOSAIC_PORT}/graphql" "$MOSAIC_PID" \
         "$LOGDIR/mosaic.log" "Mosaic" "$MOSAIC_PORT"
echo "     Mosaic up."

echo "2/${STEP_COUNT}  Starting Exon's turn service on :${EXON_PORT} ..."
EXON_TURN_PORT="$EXON_PORT" \
  MOSAIC_MCP_URL="http://127.0.0.1:${MOSAIC_PORT}/mcp" \
  python3 -m exon.conversational_server > "$LOGDIR/exon.log" 2>&1 &
EXON_PID=$!
# /turn is POST-only, so a GET returning 405 still proves it is listening.
wait_for "http://127.0.0.1:${EXON_PORT}/docs" "$EXON_PID" \
         "$LOGDIR/exon.log" "Exon" "$EXON_PORT"
echo "     Exon up, grounded in the live schema."

if [[ -n "$APERTURE_WEB_DIR" ]]; then
  echo "3/${STEP_COUNT}  Starting Aperture's web dev server on :${APERTURE_WEB_PORT} ..."
  ( cd "$APERTURE_WEB_DIR" && \
    VITE_HIPPO_GRAPHQL_URL="http://127.0.0.1:${MOSAIC_PORT}/graphql" \
    npm run dev -- --port "$APERTURE_WEB_PORT" --strictPort \
    > "$LOGDIR/aperture-web.log" 2>&1 ) &
  APERTURE_PID=$!
  wait_for "http://127.0.0.1:${APERTURE_WEB_PORT}/" "$APERTURE_PID" \
           "$LOGDIR/aperture-web.log" "Aperture web" "$APERTURE_WEB_PORT"
  echo "     Aperture web up at http://127.0.0.1:${APERTURE_WEB_PORT}/"
  echo "     (no chat panel there yet -- see openspec/changes/add-aperture-chat-panel)"
  echo "4/${STEP_COUNT}  Starting chat."
else
  echo "3/${STEP_COUNT}  Starting chat."
  echo "     (set APERTURE_WEB_DIR to also boot Aperture's web dev server alongside this)"
fi
echo ""
MOSAIC_MCP_URL="http://127.0.0.1:${MOSAIC_PORT}/mcp" python3 -m exon.chat
