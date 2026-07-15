#!/usr/bin/env bash
# One-click dev launcher for DomainForge.
# Starts: docker (postgres+redis), backend (uvicorn), frontend (next dev).
# Ctrl+C tears them all down.
#
# Usage:
#   ./domainforge.sh              start everything (foreground, Ctrl+C to stop)
#   ./domainforge.sh start        same as above
#   ./domainforge.sh stop         stop everything (kill backend/frontend, docker down)
#   ./domainforge.sh restart b    restart backend only
#   ./domainforge.sh restart f    restart frontend only
#   ./domainforge.sh restart      restart both backend and frontend
#   ./domainforge.sh status       show status of all services
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

DOCKER_STARTED=0
BACKEND_PID=""
FRONTEND_PID=""
HOST_PG_WAS_RUNNING=0   # host postgresql disabled by us? restore in cleanup.

log() { printf '\033[36m[domainforge]\033[0m %s\n' "$*"; }
err() { printf '\033[31m[domainforge:err]\033[0m %s\n' "$*" >&2; }

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
# Uses multiple strategies: fuser (rootless), lsof, and ss.
kill_port() {
  local port=$1
  local freed=0

  # Strategy 1: fuser (needs no root for own processes)
  if command -v fuser >/dev/null 2>&1; then
    if fuser "${port}/tcp" >/dev/null 2>&1; then
      log "fuser: killing processes on :${port}..."
      fuser -k "${port}/tcp" 2>/dev/null && freed=1
    fi
  fi

  # Strategy 2: lsof (fallback, may require root for some processes)
  if [ "$freed" = "0" ] && command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti "tcp:${port}" 2>/dev/null)
    if [ -n "$pids" ]; then
      log "lsof: killing PIDs on :${port} -> $(echo $pids | tr '\n' ' ')"
      kill -TERM $pids 2>/dev/null
      sleep 0.3
      kill -KILL $pids 2>/dev/null && freed=1
    fi
  fi

  # Strategy 3: ss -p (requires root for PID info, best-effort)
  if [ "$freed" = "0" ]; then
    local pids
    pids=$(ss -tlnpH 2>/dev/null | grep -E "[:.]${port}\b" \
           | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
    if [ -n "$pids" ]; then
      log "ss: killing PIDs on :${port} -> $(echo $pids | tr '\n' ' ')"
      kill -TERM $pids 2>/dev/null
      sleep 0.3
      kill -KILL $pids 2>/dev/null && freed=1
    fi
  fi

  [ "$freed" = "0" ] && return 1 || return 0
}

# Free a port used by docker containers (any compose project).
free_docker_port() {
  local port=$1
  local container_ids
  container_ids=$(docker ps -a --filter "publish=${port}" --format '{{.ID}}' 2>/dev/null)
  if [ -n "$container_ids" ]; then
    log "docker: removing container(s) on :${port}..."
    docker rm -f $container_ids 2>/dev/null
    return 0
  fi
  return 1
}

# Check if a service endpoint is healthy.
check_endpoint() {
  local url=$1 label=$2
  if curl -sf "$url" >/dev/null 2>&1; then
    printf '  \033[32m✓\033[0m %s (%s)\n' "$label" "$url"
    return 0
  else
    printf '  \033[31m✗\033[0m %s (%s)\n' "$label" "$url"
    return 1
  fi
}

check_docker() {
  if "${COMPOSE[@]}" ps --status running 2>/dev/null | grep -q 'Up'; then
    printf '  \033[32m✓\033[0m docker services (postgres + redis)\n'
    return 0
  else
    printf '  \033[31m✗\033[0m docker services (postgres + redis)\n'
    return 1
  fi
}

# Restore the host postgresql service if we stopped it earlier.
restore_host_postgres() {
  if [ "$HOST_PG_WAS_RUNNING" = "1" ]; then
    log "restarting host postgresql..."
    if sudo systemctl start postgresql; then
      log "host postgresql restarted."
    else
      err "failed to restart host postgresql — start it manually: sudo systemctl start postgresql"
    fi
    HOST_PG_WAS_RUNNING=0
  fi
}

# --- subcommands ------------------------------------------------------------

do_stop() {
  log "stopping everything..."
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  log "stopping docker services..."
  "${COMPOSE[@]}" down --remove-orphans
  # After compose down, stale docker-proxy processes or containers from other
  # compose projects may still hold our reserved ports. Clean them up so the
  # next "start" does not hit "address already in use".
  for port in 5432 6379; do
    free_docker_port "$port"
    kill_port "$port"
  done
  restore_host_postgres
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

do_start() {
  # --- 1. Docker (postgres + redis) ------------------------------------------
  # Check and free reserved ports before docker compose up.
  # Docker compose down does not always free host-level port bindings —
  # a stale docker-proxy or host process on :5432 / :6379 can block
  # the next "docker compose up -d" with "address already in use".
  for port in 5432 6379; do
    if ss -tlnH 2>/dev/null | grep -qE "[:.]${port}\b"; then
      log "port :${port} is busy — freeing docker containers + host processes..."
      free_docker_port "$port"
      kill_port "$port"
      # Wait for cleanup to propagate.
      for _ in 1 2 3 4 5; do
        ss -tlnH 2>/dev/null | grep -qE "[:.]${port}\b" || break
        sleep 0.5
      done
      if ss -tlnH 2>/dev/null | grep -qE "[:.]${port}\b"; then
        if [ "$port" = "5432" ] && systemctl is-active postgresql >/dev/null 2>&1; then
          log "detected host postgresql on :5432 — stopping it..."
          if sudo systemctl stop postgresql; then
            HOST_PG_WAS_RUNNING=1
            sleep 1
            # Verify port freed
            if ss -tlnH 2>/dev/null | grep -qE "[:.]${port}\b"; then
              err "host postgresql stopped but :${port} still in use."
              command -v lsof >/dev/null 2>&1 && lsof -i "tcp:${port}" || ss -tlnp "sport = :${port}"
              exit 1
            fi
            log "host postgresql stopped, :${port} freed."
          else
            err "failed to stop host postgresql (sudo may have failed)."
            exit 1
          fi
        else
          err ":${port} still in use after cleanup. Check what's bound:"
          command -v lsof >/dev/null 2>&1 && lsof -i "tcp:${port}" || ss -tlnp "sport = :${port}"
          exit 1
        fi
      fi
      log ":${port} freed."
    fi
  done

  log "starting docker services (postgres + redis)..."
  "${COMPOSE[@]}" up -d
  if [ $? -ne 0 ]; then
    err "compose up failed. Check port conflicts (5432/6379) or run './domainforge.sh stop'."
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

  # Block frontend launch until backend answers /api/v1/health, so Next.js's
  # proxy doesn't hit ECONNREFUSED during the brief window where uvicorn is
  # still binding the port.
  log "waiting for backend health check..."
  for i in $(seq 1 30); do
    if curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; then
      log "backend ready."
      break
    fi
    sleep 0.5
    [ "$i" = "30" ] && err "backend not ready after 15s, starting frontend anyway."
  done

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
}

do_status() {
  log "service status:"
  check_docker
  check_endpoint "http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/health" "backend"
  check_endpoint "http://localhost:${FRONTEND_PORT}" "frontend"
  exit 0
}

# --- entry point ------------------------------------------------------------
case "${1:-}" in
  stop|-stop|--stop)    do_stop ;;
  restart|-restart|--restart) do_restart "${2:-all}" ;;
  status|-status|--status)    do_status ;;
  start|-start|--start|"")    ;;  # fall through to main
  *)
    err "unknown command: '$1'"
    echo "Usage: $0 [start|stop|restart [b|f|all]|status]"
    exit 2
    ;;
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
  restore_host_postgres
  log "bye."
  exit 0
}

trap 'cleanup INT'  INT
trap 'cleanup TERM' TERM

# -- main (start) ------------------------------------------------------------
do_start
