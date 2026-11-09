@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
:: Language: AI_WORKER_LANG (en or vi) wins, else the Windows language, else English.
:: Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ Windows, không có nữa thì tiếng Anh.
if not defined AI_WORKER_LANG for /f "delims=" %%L in ('powershell -NoProfile -Command "[System.Globalization.CultureInfo]::CurrentCulture.TwoLetterISOLanguageName" 2^>nul') do set "AI_WORKER_LANG=%%L"
if not defined AI_WORKER_LANG set "AI_WORKER_LANG=en"
if /i "%AI_WORKER_LANG:~0,2%"=="vi" (set "AI_WORKER_LANG=vi") else (set "AI_WORKER_LANG=en")
if not exist "ai-worker-dev" (
  call :say "Cannot find the ai-worker-dev folder next to the installer: unzip the whole pack and run again." "Không thấy thư mục ai-worker-dev cạnh file cài: giải nén cả gói rồi chạy lại."
  pause
  exit /b 1
)
if not exist "%~dp0lang.ps1" (
  call :say "lang.ps1 is missing next to the installer: unzip the whole pack and run again." "Thiếu lang.ps1 cạnh file cài: giải nén cả gói rồi chạy lại."
  pause
  exit /b 1
)
set "INSTALL_DIR=%USERPROFILE%\claude-plugins-ai-worker-dev"
set "PATH=%USERPROFILE%\.local\bin;%APPDATA%\npm;%PATH%"
call :say "== Installing the AI Worker technical pack ==" "== Cài gói kỹ thuật AI Worker =="
set "CLAUDE="
for /f "delims=" %%i in ('where claude 2^>nul') do if not defined CLAUDE set "CLAUDE=%%i"
if not defined CLAUDE for /f "delims=" %%i in ('dir /b /s /o-d "%APPDATA%\Claude\claude-code\claude.exe" 2^>nul') do if not defined CLAUDE set "CLAUDE=%%i"
if not defined CLAUDE (
  call :say "Claude Code was not found. Open the Claude app, sign in, click the Code tab once, then run this file again." "Chưa tìm thấy Claude Code. Mở app Claude, đăng nhập, bấm sang tab Code một lần rồi chạy lại file này."
  pause
  exit /b 1
)
call :say "Copying the plugin to %INSTALL_DIR% ..." "Chép plugin vào %INSTALL_DIR% ..."
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
xcopy /e /i /q /y ".claude-plugin" "%INSTALL_DIR%\.claude-plugin" >nul
xcopy /e /i /q /y "ai-worker-dev" "%INSTALL_DIR%\ai-worker-dev" >nul
call "%CLAUDE%" plugin marketplace add "%INSTALL_DIR%" || call "%CLAUDE%" plugin marketplace update ai-worker-dev
call "%CLAUDE%" plugin install ai-worker-dev@ai-worker-dev
if errorlevel 1 (
  call :say "The install did not succeed. Take a screenshot of this window and send it to your admin." "Cài chưa thành công. Chụp màn hình cửa sổ này gửi người quản trị."
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-deps.ps1" -Plugin "%INSTALL_DIR%\ai-worker-dev" -Claude "%CLAUDE%"
echo.
call :say "Done. Close all Claude app windows and open it again to use it." "Xong. Đóng hết cửa sổ app Claude rồi mở lại để dùng."
pause
exit /b 0

:say
:: Print English or Vietnamese, by AI_WORKER_LANG. Delayed expansion keeps characters such as ( ) & safe.
:: In ra tiếng Anh hoặc tiếng Việt, theo AI_WORKER_LANG. Mở rộng trễ giữ an toàn cho các ký tự như ( ) &.
setlocal EnableDelayedExpansion
set "SAY_TEXT=%~1"
if /i "!AI_WORKER_LANG!"=="vi" set "SAY_TEXT=%~2"
echo(!SAY_TEXT!
endlocal
exit /b 0
