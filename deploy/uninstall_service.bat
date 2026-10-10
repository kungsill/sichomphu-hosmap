@echo off
chcp 65001 >nul
rem ถอนการติดตั้ง — ระบบจะขอสิทธิ์ Administrator ให้เอง
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_service.ps1"
pause
