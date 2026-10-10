@echo off
rem ติดตั้งเป็น Windows Service ด้วย NSSM (https://nssm.cc) — รันด้วยสิทธิ์ Administrator
chcp 65001 >nul
cd /d "%~dp0\.."
set APPDIR=%CD%
where nssm >nul 2>nul || (echo ไม่พบ nssm.exe กรุณาดาวน์โหลดจาก https://nssm.cc แล้ววางไว้ใน PATH & exit /b 1)
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
nssm install hosmap "%APPDIR%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --proxy-headers --forwarded-allow-ips=127.0.0.1
nssm set hosmap AppDirectory "%APPDIR%"
nssm set hosmap AppEnvironmentExtra PYTHONIOENCODING=utf-8
nssm set hosmap AppStdout "%APPDIR%\data\service.log"
nssm set hosmap AppStderr "%APPDIR%\data\service.log"
nssm set hosmap AppRotateFiles 1
nssm set hosmap AppRotateBytes 10485760
nssm set hosmap Start SERVICE_AUTO_START
nssm start hosmap
echo ติดตั้งแล้ว: ตรวจที่ http://127.0.0.1:8090/api/health
