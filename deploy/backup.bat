@echo off
rem สำรองแผนที่ + ฐานข้อมูลระบบนำทาง (ตั้งใน Task Scheduler ทุกคืน) เก็บย้อนหลัง 30 วัน
chcp 65001 >nul
cd /d "%~dp0\.."
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set D=%%i
if not exist backups mkdir backups
.venv\Scripts\python -m app.mapio export backups\map_%D%.json
rem SQLite (ค่าเริ่มต้น)
if exist data\hospital_navigation.db copy /y data\hospital_navigation.db backups\nav_%D%.db >nul
rem MySQL (ถ้าใช้) — แก้ user/รหัส แล้วเอา rem ออก
rem mysqldump -u nav -pCHANGE_ME hospital_navigation > backups\nav_%D%.sql
forfiles /p backups /d -30 /c "cmd /c del @path" 2>nul
echo สำรองแล้ว: backups\*_%D%.*
