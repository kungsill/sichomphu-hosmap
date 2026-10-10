@echo off

rem ตัวรันเซิร์ฟเวอร์สำหรับ Service / Task Scheduler (ไม่ต้องเปิดเอง)

rem HOST: 0.0.0.0 = เครื่องอื่นใน LAN เข้าได้โดยตรง (http://<IP เครื่องนี้>:8090)

rem       127.0.0.1 = ใช้คู่กับ Caddy/nginx (HTTPS) ตาม deploy\DEPLOY.md

set HOST=0.0.0.0

set PORT=8090

cd /d "%~dp0\.."

set PYTHONIOENCODING=utf-8

if not exist data mkdir data

echo [%date% %time%] start hosmap on %HOST%:%PORT% >> data\service.log

".venv\Scripts\python.exe" -m uvicorn app.main:app --host %HOST% --port %PORT% --no-access-log --proxy-headers --forwarded-allow-ips=127.0.0.1 >> data\service.log 2>&1

