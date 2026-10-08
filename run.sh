#!/usr/bin/env sh
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
fi
PORT="${PORT:-8090}"
echo "เปิดใช้งานที่ http://localhost:$PORT"
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
