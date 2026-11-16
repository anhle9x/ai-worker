@echo off
chcp 65001 >nul
setlocal
:: Show Codex, Cursor and Gemini CLI on the AI Worker board, on Windows. Claude Code is not needed. Double-click this file to run it.
:: To take it out again, run in PowerShell:  powershell -ExecutionPolicy Bypass -File "%USERPROFILE%\.local\share\ai-worker\connector\install.ps1" -Uninstall
:: Cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker, trên Windows. Không cần có Claude Code. Bấm đúp file này để chạy.
:: Muốn gỡ, chạy trong PowerShell:  powershell -ExecutionPolicy Bypass -File "%USERPROFILE%\.local\share\ai-worker\connector\install.ps1" -Uninstall
cd /d "%~dp0"
:: The helper files and the plugin sit in setup\, so only the installers show at the top of the zip
:: File phụ và plugin nằm trong setup\, để ngoài cùng của zip chỉ còn các file cài
if exist setup cd setup
if not exist "ai-worker\connectors\install.ps1" (
  echo The setup folder is incomplete: unzip the whole zip file and run again. / Thu muc setup thieu file: giai nen ca file zip roi chay lai.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "ai-worker\connectors\install.ps1" %*
echo.
pause
