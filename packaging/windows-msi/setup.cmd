@echo off
chcp 65001 >nul
:: "Finish AI Worker setup": the finish screen of AI Worker plugin.msi and its Start menu entry open this file.
:: "Finish AI Worker setup": màn hình cuối của AI Worker plugin.msi và mục của nó trong menu Start mở file này.
:: It unpacks the package into a work folder (prepare.ps1), runs the same INSTALL-Windows.bat as the zip, then deletes the work folder.
:: Nó giải nén gói vào một thư mục làm việc (prepare.ps1), chạy đúng INSTALL-Windows.bat của gói zip, rồi xoá thư mục làm việc.
setlocal
set "HERE=%~dp0"
set "WORK=%TEMP%\ai-worker-setup-%RANDOM%%RANDOM%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%prepare.ps1" -Zip "%HERE%AI-Worker.zip" -Work "%WORK%"
if errorlevel 1 (
  if exist "%WORK%" rmdir /s /q "%WORK%"
  pause
  exit /b 1
)
call "%WORK%\AI-Worker\INSTALL-Windows.bat"
set "RESULT=%ERRORLEVEL%"
cd /d "%TEMP%"
if exist "%WORK%" rmdir /s /q "%WORK%"
:: The company settings now sit in the plugin folder: delete the copy in the registry, so the send code is kept in one place only
:: Thiết lập công ty giờ đã nằm trong thư mục plugin: xoá bản trong registry, để mã gửi chỉ nằm ở một chỗ
if exist "%USERPROFILE%\claude-plugins-ai-worker\ai-worker\web\company.json" reg delete "HKCU\Software\AI Worker Plugin" /v Company /f >nul 2>nul
exit /b %RESULT%
