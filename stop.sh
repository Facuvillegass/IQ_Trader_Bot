#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

stop_pidfile() {
  local f="$1"
  if [[ -f "$f" ]]; then
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping pid $pid ($f)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
  fi
}

stop_pidfile logs/api.pid
stop_pidfile logs/frontend.pid

# Also clear listeners if still bound
for port in 8010 5173; do
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "${pids}" ]]; then
      kill $pids 2>/dev/null || true
    fi
  fi
done

echo "Stopped."
