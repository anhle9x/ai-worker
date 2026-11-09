@echo off
rem Installs the AI Worker icon next to the clock for a manager on Windows; the work is done by install-menubar.ps1 next to this file.
rem Cai bieu tuong AI Worker canh dong ho cho quan ly tren Windows; viec cai do install-menubar.ps1 canh file nay lam.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-menubar.ps1"
if errorlevel 1 pause & exit /b 1
pause
