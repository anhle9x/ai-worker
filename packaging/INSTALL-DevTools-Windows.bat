@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
:: Language: AI_WORKER_LANG (en or vi) wins, else the Windows language, else English.
:: Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ Windows, không có nữa thì tiếng Anh.
if not defined AI_WORKER_LANG for /f "delims=" %%L in ('powershell -NoProfile -Command "[System.Globalization.CultureInfo]::CurrentCulture.TwoLetterISOLanguageName" 2^>nul') do set "AI_WORKER_LANG=%%L"
if not defined AI_WORKER_LANG set "AI_WORKER_LANG=en"
if /i "%AI_WORKER_LANG:~0,2%"=="vi" (set "AI_WORKER_LANG=vi") else (set "AI_WORKER_LANG=en")
if not exist "%~dp0lang.ps1" (
  call :say "lang.ps1 is missing next to the installer: unzip the whole pack and run again." "Thiếu lang.ps1 cạnh file cài: giải nén cả gói rồi chạy lại."
  pause
  exit /b 1
)
set "INSTALL_DIR=%USERPROFILE%\claude-plugins-ai-worker"
set "PATH=%USERPROFILE%\.local\bin;%APPDATA%\npm;%PATH%"
call :say "== Installing the tools for the coding and testing skills ==" "== Cài công cụ cho các skill viết code và kiểm thử =="
set "CLAUDE="
for /f "delims=" %%i in ('where claude 2^>nul') do if not defined CLAUDE set "CLAUDE=%%i"
if not defined CLAUDE for /f "delims=" %%i in ('dir /b /s /o-d "%APPDATA%\Claude\claude-code\claude.exe" 2^>nul') do if not defined CLAUDE set "CLAUDE=%%i"
if not defined CLAUDE (
  call :say "Claude Code was not found. Open the Claude app, sign in, click the Code tab once, then run this file again." "Chưa tìm thấy Claude Code. Mở app Claude, đăng nhập, bấm sang tab Code một lần rồi chạy lại file này."
  pause
  exit /b 1
)
if not exist "%INSTALL_DIR%\ai-worker" (
  call :say "The AI Worker plugin is not installed yet: run INSTALL-Windows.bat first, then this file." "Chưa cài plugin AI Worker: chạy INSTALL-Windows.bat trước, rồi mới chạy file này."
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-deps.ps1" -Plugin "%INSTALL_DIR%\ai-worker" -Claude "%CLAUDE%"
echo.
call :say "Done. Quit the Claude app (right-click its icon next to the clock, then Exit; closing the window only hides it) and open it again to use it." "Xong. Thoát app Claude (bấm chuột phải vào biểu tượng cạnh đồng hồ, chọn Exit; đóng cửa sổ chỉ làm app ẩn đi) rồi mở lại để dùng."
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
