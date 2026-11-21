@echo off
chcp 65001 >nul
:: Remove AI Worker Office from Claude Code on Windows (installed with INSTALL-Windows.bat). Double-click this file to run it.
:: Gỡ Văn phòng AI Worker khỏi Claude Code trên Windows (đã cài bằng INSTALL-Windows.bat). Bấm đúp file này để chạy.
:: The work is done by setup\uninstall.cmd, the same file AI-Worker-Plugin.msi runs when it is uninstalled.
:: Việc gỡ do setup\uninstall.cmd làm, cùng file mà AI-Worker-Plugin.msi chạy khi bị gỡ.
setlocal
cd /d "%~dp0"
:: Language: AI_WORKER_LANG (en or vi) wins, else the Windows language, else English.
:: Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ Windows, không có nữa thì tiếng Anh.
if not defined AI_WORKER_LANG for /f "delims=" %%L in ('powershell -NoProfile -Command "[System.Globalization.CultureInfo]::CurrentCulture.TwoLetterISOLanguageName" 2^>nul') do set "AI_WORKER_LANG=%%L"
if not defined AI_WORKER_LANG set "AI_WORKER_LANG=en"
if /i "%AI_WORKER_LANG:~0,2%"=="vi" (set "AI_WORKER_LANG=vi") else (set "AI_WORKER_LANG=en")
if not exist "%~dp0setup\uninstall.cmd" (
  call :say "setup\uninstall.cmd is missing: unzip the whole zip file and run again." "Thiếu setup\uninstall.cmd: giải nén cả file zip rồi chạy lại."
  pause
  exit /b 1
)

call :say "== Removing AI Worker Office ==" "== Gỡ Văn phòng AI Worker =="
call :say "This unregisters the plugin from Claude Code and deletes %USERPROFILE%\claude-plugins-ai-worker." "Việc này bỏ đăng ký plugin khỏi Claude Code và xoá %USERPROFILE%\claude-plugins-ai-worker."
call :say "Your name and history in %USERPROFILE%\.local\share\ai-worker are kept." "Họ tên và lịch sử của bạn trong %USERPROFILE%\.local\share\ai-worker được giữ lại."
set "ANSWER="
call :say "Remove it? (y/N): " "Gỡ không? (y/N): " nonl
:: Automatic runs and tests: the answer comes from the file AI_WORKER_ANSWERS_FILE, as in the other installers (set /p did not get a redirected stdin on the test machine)
:: Chạy tự động và thử nghiệm: câu trả lời lấy từ file AI_WORKER_ANSWERS_FILE, như các file cài khác (set /p không nhận được stdin chuyển hướng trên máy thử)
if defined AI_WORKER_ANSWERS_FILE (
  set /p "ANSWER=" < "%AI_WORKER_ANSWERS_FILE%"
  echo(
) else (
  set /p "ANSWER="
)
if /i not "%ANSWER%"=="y" (
  call :say "Nothing was changed." "Không thay đổi gì."
  pause
  exit /b 0
)
call "%~dp0setup\uninstall.cmd"
if exist "%USERPROFILE%\claude-plugins-ai-worker\.claude-plugin\marketplace.json" (
  call :say "The plugin folder could not be deleted: quit the Claude app completely and run this file again." "Không xoá được thư mục plugin: thoát hẳn app Claude rồi chạy lại file này."
  pause
  exit /b 1
)
call :say "Done. If Claude Code is open: quit it completely and open it again." "Xong. Nếu Claude Code đang mở: thoát hẳn rồi mở lại."
pause
exit /b 0

:say
:: Print English or Vietnamese, by AI_WORKER_LANG. Third argument "nonl" = no line break (the same as INSTALL-Windows.bat).
:: In ra tiếng Anh hoặc tiếng Việt, theo AI_WORKER_LANG. Tham số thứ ba "nonl" = không xuống dòng (giống INSTALL-Windows.bat).
setlocal EnableDelayedExpansion
set "SAY_TEXT=%~1"
if /i "!AI_WORKER_LANG!"=="vi" set "SAY_TEXT=%~2"
if /i "%~3"=="nonl" (
  <nul set /p "=!SAY_TEXT!"
) else (
  echo(!SAY_TEXT!
)
endlocal
exit /b 0
