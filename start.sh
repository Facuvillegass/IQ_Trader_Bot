#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> MNQ Paper Trading — starting"

if [[ ! -f .env ]]; then
  echo "Creating .env from .env.example (PAPER / mock defaults)"
  cp .env.example .env
fi

# Python venv
if [[ ! -d .venv ]]; then
  echo "Creating Python virtualenv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -q -r requirements.txt

mkdir -p logs data reports data/raw

API_PORT="$(grep -E '^API_PORT=' .env | cut -d= -f2 || true)"
FE_PORT="$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2 || true)"
API_PORT=${API_PORT:-8010}
FE_PORT=${FE_PORT:-5173}

for port in "$API_PORT" "$FE_PORT"; do
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "${pids}" ]]; then
      echo "Freeing port $port (pids: $pids)"
      kill $pids 2>/dev/null || true
      sleep 1
    fi
  fi
done

export PYTHONPATH="$ROOT"
export PYTHONUNBUFFERED=1

echo "Running quick tests..."
pytest backend/tests -q || {
  echo "Tests failed — aborting start"
  exit 1
}

echo "Starting API + embedded worker on :$API_PORT ..."
nohup python -m backend.app.main > logs/api.stdout.log 2>&1 &
echo $! > logs/api.pid
sleep 2
if ! kill -0 "$(cat logs/api.pid)" 2>/dev/null; then
  echo "API failed to start — see logs/api.stdout.log / logs/errors.log"
  exit 1
fi

echo "Starting dashboard on :$FE_PORT ..."
cd frontend
if [[ ! -d node_modules ]]; then
  npm install
fi
nohup npm run dev -- --host 127.0.0.1 --port "$FE_PORT" > ../logs/frontend.stdout.log 2>&1 &
echo $! > ../logs/frontend.pid
cd "$ROOT"

sleep 2
echo ""
echo "============================================"
echo " PAPER TRADING SYSTEM IS UP"
echo " Dashboard: http://127.0.0.1:${FE_PORT}"
echo " Health:    http://127.0.0.1:${API_PORT}/health"
echo " API:       http://127.0.0.1:${API_PORT}/api/state"
echo " Logs:      logs/"
echo " DB:        data/paper_trading.db"
echo " Stop with: ./stop.sh"
echo "============================================"
