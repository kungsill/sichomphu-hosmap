@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist .venv (
  echo กำลังติดตั้งครั้งแรก...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if "%PORT%"=="" set PORT=8090
echo เปิดใช้งานที่ http://localhost:%PORT%
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
