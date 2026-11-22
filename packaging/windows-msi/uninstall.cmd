@echo off
:: Run by AI Worker plugin.msi when it is really uninstalled (not when an upgrade removes the old version): unregister the plugin from
:: Claude Code, then delete the plugin folder and Claude Code's copy of it, so the company send code does not stay behind.
:: AI Worker plugin.msi chạy file này khi bị gỡ thật (không phải lúc nâng cấp dọn bản cũ): bỏ đăng ký plugin khỏi Claude Code,
:: rồi xoá thư mục plugin và bản sao của Claude Code, để mã gửi của công ty không còn sót lại.
:: The person's own data (%USERPROFILE%\.local\share\ai-worker: name, history) stays. Every step may fail without stopping the uninstall.
:: Dữ liệu của người dùng (%USERPROFILE%\.local\share\ai-worker: họ tên, lịch sử) được giữ. Bước nào hỏng cũng không chặn việc gỡ.
setlocal
:: The user's folders come from the .msi (arguments: LocalAppData, AppData), since this may run without the user's environment
:: Thư mục của người dùng lấy từ .msi (tham số: LocalAppData, AppData), vì file này có thể chạy không có biến môi trường của người dùng
if not "%~1"=="" (
  set "LOCALAPPDATA=%~1"
  for %%I in ("%~1\..\..") do set "USERPROFILE=%%~fI"
)
if not "%~2"=="" set "APPDATA=%~2"
:: The claude command, found the same way as INSTALL-Windows.bat
:: Lệnh claude, tìm giống INSTALL-Windows.bat
set "CLAUDE="
where claude >nul 2>nul && set "CLAUDE=claude"
if not defined CLAUDE if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE for /f "delims=" %%F in ('dir /s /b /o:d "%APPDATA%\Claude\claude-code\claude.exe" 2^>nul') do set "CLAUDE=%%F"
if not defined CLAUDE for /f "delims=" %%F in ('dir /s /b /o:d "%LOCALAPPDATA%\Claude-Data\claude.exe" 2^>nul') do set "CLAUDE=%%F"
if defined CLAUDE (
  call "%CLAUDE%" plugin uninstall ai-worker@ai-worker
  call "%CLAUDE%" plugin marketplace remove ai-worker
)
:: Only a folder that holds the AI Worker marketplace is deleted
:: Chỉ xoá thư mục có marketplace AI Worker
set "DIR=%USERPROFILE%\claude-plugins-ai-worker"
if exist "%DIR%\.claude-plugin\marketplace.json" rmdir /s /q "%DIR%"
if exist "%USERPROFILE%\.claude\plugins\cache\ai-worker" rmdir /s /q "%USERPROFILE%\.claude\plugins\cache\ai-worker"
exit /b 0
