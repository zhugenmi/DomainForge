#!/usr/bin/env bash
# One-click dev launcher for DomainForge.
# Starts: docker (postgres+redis), backend (uvicorn), frontend (next dev).
# Ctrl+C tears them all down.
#
# Usage:
#   ./dev.sh              start everything (foreground, Ctrl+C to stop)
#   ./dev.sh -stop        stop everything (kill backend/frontend, docker down)
#   ./dev.sh -restart b   restart backend only
#   ./dev.sh -restart f   restart frontend only
#   ./dev.sh -restart     restart both backend and frontend
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

DOCKER_STARTED=0
BACKEND_PID=""
FRONTEND_PID=""

log() { printf '\033[36m[dev]\033[0m %s\n' "$*"; }
err() { printf '\033[31m[dev:err]\033[0m %s\n' "$*" >&2; }

# Pick compose command: prefer v2 plugin, fall back to v1 standalone.
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  err "neither 'docker compose' (v2 plugin) nor 'docker-compose' (v1) found."
  exit 1
fi

# Kill whatever is listening on a given port (best-effort).
kill_port() {
  local port=$1
  local pids
  pids=$(ss -tlnpH 2>/dev/null | grep -E "[:.]${port}\b" \
         | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
  [ -z "$pids" ] && return 0
  log "killing listeners on :${port} -> $(echo $pids | tr '\n' ' ')"
  kill -TERM $pids 2>/dev/null
  sleep 0.3
  kill -KILL $pids 2>/dev/null
}

do_stop() {
  log "stopping everything..."
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  log "stopping docker services..."
  "${COMPOSE[@]}" down --remove-orphans
  log "stopped."
  exit 0
}

# Start backend in background (detached, logs to stdout).
start_backend() {
  log "starting backend on http://${BACKEND_HOST}:${BACKEND_PORT} ..."
  nohup bash -c "cd '$ROOT' && exec .venv/bin/uvicorn app.main:app --reload \
    --host '$BACKEND_HOST' --port '$BACKEND_PORT'" \
    >/tmp/domainforge-backend.log 2>&1 &
  log "  backend pid=$!  logs: /tmp/domainforge-backend.log"
}

# Start frontend in background (detached, logs to stdout).
start_frontend() {
  log "starting frontend on http://localhost:${FRONTEND_PORT} ..."
  nohup bash -c "cd '$ROOT/frontend' && exec npx next dev --port '$FRONTEND_PORT'" \
    >/tmp/domainforge-frontend.log 2>&1 &
  log "  frontend pid=$!  logs: /tmp/domainforge-frontend.log"
}

do_restart() {
  local what="${1:-all}"
  case "$what" in
    b|backend)
      kill_port "$BACKEND_PORT"
      start_backend
      ;;
    f|frontend)
      kill_port "$FRONTEND_PORT"
      start_frontend
      ;;
    all|"")
      kill_port "$BACKEND_PORT"
      kill_port "$FRONTEND_PORT"
      start_backend
      start_frontend
      ;;
    *)
      err "unknown restart target: '$what' (use b | f | all)"
      exit 2
      ;;
  esac
  log "restart done."
  exit 0
}

# --- subcommands ------------------------------------------------------------
case "${1:-}" in
  -stop|--stop|stop) do_stop ;;
  -restart|--restart|restart) do_restart "${2:-all}" ;;
esac

cleanup() {
  local sig=$1
  log "shutting down (signal=$sig)..."
  [ -n "$FRONTEND_PID" ] && kill -TERM "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ]  && kill -TERM "$BACKEND_PID"  2>/dev/null
  for _ in 1 2 3 4 5; do
    { [ -z "$FRONTEND_PID" ] || ! kill -0 "$FRONTEND_PID" 2>/dev/null; } \
      && { [ -z "$BACKEND_PID" ] || ! kill -0 "$BACKEND_PID" 2>/dev/null; } && break
    sleep 0.3
  done
  [ -n "$FRONTEND_PID" ] && kill -KILL "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ]  && kill -KILL "$BACKEND_PID"  2>/dev/null

  if [ "$DOCKER_STARTED" = "1" ]; then
    log "stopping docker services..."
    "${COMPOSE[@]}" down --remove-orphans
  fi
  log "bye."
  exit 0
}

trap 'cleanup INT'  INT
trap 'cleanup TERM' TERM

# --- 1. Docker (postgres + redis) ------------------------------------------
log "starting docker services (postgres + redis)..."
"${COMPOSE[@]}" up -d
if [ $? -ne 0 ]; then
  err "compose up failed. Check port conflicts (5432/6379) or run './dev.sh -stop'."
  exit 1
fi
DOCKER_STARTED=1

log "waiting for postgres..."
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U domainforge >/dev/null 2>&1; then
    log "postgres ready."
    break
  fi
  sleep 1
  [ "$i" = "30" ] && err "postgres not ready after 30s, continuing anyway."
done

# --- 2. Backend -------------------------------------------------------------
log "starting backend on http://${BACKEND_HOST}:${BACKEND_PORT} ..."
( cd "$ROOT" && \
  exec .venv/bin/uvicorn app.main:app --reload \
    --host "$BACKEND_HOST" --port "$BACKEND_PORT" ) &
BACKEND_PID=$!

# --- 3. Frontend ------------------------------------------------------------
log "starting frontend on http://localhost:${FRONTEND_PORT} ..."
( cd "$ROOT/frontend" && exec npx next dev --port "$FRONTEND_PORT" ) &
FRONTEND_PID=$!

log "all up. Ctrl+C to stop everything."
log "  backend  : http://localhost:${BACKEND_PORT}/docs"
log "  frontend : http://localhost:${FRONTEND_PORT}"

while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    err "backend exited."
    break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    err "frontend exited."
    break
  fi
  wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || sleep 1
done

cleanup EXIT
