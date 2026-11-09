@echo off
chcp 65001 >nul
:: Install AI Worker Office for Claude Code on Windows. Double-click this file to run it.
:: Cài Văn phòng AI Worker cho Claude Code trên Windows. Bấm đúp file này để chạy.
cd /d "%~dp0"
:: The helper files and the plugin sit in setup\, so only the installers show at the top of the zip
:: File phụ và plugin nằm trong setup\, để ngoài cùng của zip chỉ còn các file cài
if exist "%~dp0setup\" cd /d "%~dp0setup"
:: Language: AI_WORKER_LANG (en or vi) wins, else the Windows language, else English.
:: Ngôn ngữ: AI_WORKER_LANG (en hoặc vi) thắng, không có thì lấy ngôn ngữ Windows, không có nữa thì tiếng Anh.
if not defined AI_WORKER_LANG for /f "delims=" %%L in ('powershell -NoProfile -Command "[System.Globalization.CultureInfo]::CurrentCulture.TwoLetterISOLanguageName" 2^>nul') do set "AI_WORKER_LANG=%%L"
if not defined AI_WORKER_LANG set "AI_WORKER_LANG=en"
if /i "%AI_WORKER_LANG:~0,2%"=="vi" (set "AI_WORKER_LANG=vi") else (set "AI_WORKER_LANG=en")
if not exist "ai-worker\" (
  call :say "Cannot find the ai-worker folder in the setup folder: unzip the whole zip file and run again." "Không thấy thư mục ai-worker trong thư mục setup: giải nén cả file zip rồi chạy lại."
  pause
  exit /b 1
)
if not exist "%CD%\lang.ps1" (
  call :say "lang.ps1 is missing in the setup folder: unzip the whole zip file and run again." "Thiếu lang.ps1 trong thư mục setup: giải nén cả file zip rồi chạy lại."
  pause
  exit /b 1
)

set "INSTALL_DIR=%USERPROFILE%\claude-plugins-ai-worker"

call :say "== Installing AI Worker Office ==" "== Cài Văn phòng AI Worker =="
:: The claude command: installed on its own, or maybe bundled with the Claude Desktop app; if missing, install with commands typed in the app
:: Lệnh claude: cài riêng, hoặc bản app Claude Desktop có thể kèm sẵn; không có thì cài bằng lệnh gõ trong app
set "CLAUDE="
where claude >nul 2>nul && set "CLAUDE=claude"
if not defined CLAUDE if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE for /f "delims=" %%F in ('dir /s /b /o:d "%APPDATA%\Claude\claude-code\claude.exe" 2^>nul') do set "CLAUDE=%%F"
set "HAS_APP="
if exist "%APPDATA%\Claude" set "HAS_APP=1"
if exist "%LOCALAPPDATA%\AnthropicClaude" set "HAS_APP=1"
if not defined CLAUDE if not defined HAS_APP goto :no_claude

set "USER_FILE=%USERPROFILE%\.local\share\ai-worker\user.json"
:: Sign in (open the Claude app so the user signs in) and ask the full name: done in PowerShell
:: Đăng nhập (mở app Claude cho nhân viên tự đăng nhập) và hỏi họ tên: làm trong PowerShell
set "AI_WORKER_CLAUDE=%CLAUDE%"
set "AI_WORKER_HAS_APP=%HAS_APP%"
set "AI_WORKER_USER_FILE="
set "AI_WORKER_SETTINGS_FILE=%USER_FILE%"
if exist "ASK-NAME" set "AI_WORKER_USER_FILE=%USER_FILE%"
set "AI_WORKER_CMD_OUT=%TEMP%\ai-worker-claude-%RANDOM%.txt"
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\ask-name.ps1"
set "PS_ERR=%errorlevel%"
if exist "%AI_WORKER_CMD_OUT%" (
  set /p CLAUDE=<"%AI_WORKER_CMD_OUT%"
  del "%AI_WORKER_CMD_OUT%" >nul 2>nul
)
if not defined AI_WORKER_USER_FILE goto :after_ask
if "%PS_ERR%"=="0" goto :after_ask
if exist "%USER_FILE%" findstr /c:name "%USER_FILE%" >nul 2>nul && goto :after_ask
:: PowerShell is blocked: ask with cmd (a name with accents may break, fix it in the file later)
:: PowerShell bị chặn: hỏi bằng cmd (tên có dấu có thể bị lỗi, sửa lại trong file sau)
echo.
call :say "This package sends usage numbers (sessions, tokens, cost; NOT chat content or file names)" "Gói này gửi số liệu sử dụng (số phiên, token, chi phí; KHÔNG có nội dung chat hay tên file)"
call :say "to the company dashboard." "lên bảng tổng của công ty."
set "TRY=0"
:ask_name
:: Do not ask forever when nobody answers (automatic install)
:: Không hỏi lại mãi khi không có ai trả lời (cài tự động)
set /a TRY+=1
if %TRY% GTR 5 goto :after_ask
set "NAME="
call :say "Your full name: " "Họ tên của bạn: " nonl
set /p "NAME="
if not defined NAME goto :ask_name
:ask_account
set /a TRY+=1
if %TRY% GTR 10 goto :save_name
set "ACCOUNT="
call :say "Claude account email (Enter to skip): " "Email tài khoản Claude (Enter để bỏ qua): " nonl
set /p "ACCOUNT="
if not defined ACCOUNT goto :save_name
echo %ACCOUNT%| find "@" >nul || goto :ask_account
:save_name
set "NAME=%NAME:"=%"
if defined ACCOUNT set "ACCOUNT=%ACCOUNT:"=%"
if defined ACCOUNT set "ACCOUNT=%ACCOUNT: =%"
if not exist "%USERPROFILE%\.local\share\ai-worker" mkdir "%USERPROFILE%\.local\share\ai-worker"
> "%USER_FILE%" echo {"name": "%NAME%", "account": "%ACCOUNT%", "language": "%AI_WORKER_LANG%"}
call :say "Saved. You can edit it later at: %USER_FILE%" "Đã lưu. Sửa sau ở: %USER_FILE%"
:after_ask
:: If PowerShell could not write user.json, at least save the language
:: Nếu PowerShell không ghi được user.json thì ít nhất ghi ngôn ngữ
if not exist "%USER_FILE%" (
  if not exist "%USERPROFILE%\.local\share\ai-worker" mkdir "%USERPROFILE%\.local\share\ai-worker"
  > "%USER_FILE%" echo {"language": "%AI_WORKER_LANG%"}
)

call :say "Copying the plugin to %INSTALL_DIR% ..." "Chép plugin vào %INSTALL_DIR% ..."
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
mkdir "%INSTALL_DIR%"
xcopy /e /i /q /y ".claude-plugin" "%INSTALL_DIR%\.claude-plugin" >nul
xcopy /e /i /q /y "ai-worker" "%INSTALL_DIR%\ai-worker" >nul

if defined CLAUDE goto :have_cmd
:: The Claude app is here but not the claude command: install with two commands typed in the Code tab, each one copied for the user
:: Có app Claude nhưng chưa có lệnh claude: cài bằng hai lệnh gõ trong tab Code, chép sẵn từng lệnh
echo.
call :say "This computer has the Claude app but the 'claude' command was not found. Install inside the app, in two steps:" "Máy có app Claude nhưng chưa tìm thấy lệnh 'claude'. Cài trong app, hai bước:"
call :say "Open the Claude app > Code tab (start a new session if needed)." "Mở app Claude > tab Code (mở phiên mới nếu cần)."
set "CMD=/plugin marketplace add %INSTALL_DIR%"
if not "%INSTALL_DIR: =%"=="%INSTALL_DIR%" set "CMD=/plugin marketplace add "%INSTALL_DIR%""
<nul set /p "=%CMD%" | clip
call :say "  1. Command copied:" "  1. Đã chép lệnh:"
echo     %CMD%
call :say "     Paste it into the chat box (Ctrl+V), press Enter, and wait until it says it is done." "     Dán vào khung chat (Ctrl+V) rồi Enter, chờ báo xong."
call :say "     When done, press any key here to copy the second command..." "     Xong thì nhấn phím bất kỳ ở đây để chép lệnh thứ hai..."
pause >nul
<nul set /p "=/plugin install ai-worker@ai-worker" | clip
call :say "  2. Command copied:  /plugin install ai-worker@ai-worker" "  2. Đã chép lệnh:  /plugin install ai-worker@ai-worker"
call :say "     Paste it into the chat box and press Enter. Then type /reload-plugins, then /office." "     Dán vào khung chat rồi Enter. Sau đó gõ /reload-plugins, rồi /office."
if not defined AI_WORKER_SKIP_HELPERS if exist "%CD%\helpers.ps1" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\helpers.ps1"
pause
exit /b 0

:have_cmd
call :say "Registering and installing the plugin ..." "Đăng ký và cài plugin ..."
call "%CLAUDE%" plugin marketplace add "%INSTALL_DIR%" || call "%CLAUDE%" plugin marketplace update ai-worker
call "%CLAUDE%" plugin install ai-worker@ai-worker
if errorlevel 1 (
  call :say "The install did not succeed. Take a screenshot of this window and send it to your IT team." "Cài chưa thành công. Chụp màn hình cửa sổ này gửi phòng IT."
  pause
  exit /b 1
)

:: Company package: check whether this computer can reach the server
:: Gói công ty: thử xem máy này có tới được máy chủ không
if exist "%CD%\ASK-NAME" if exist "%CD%\check-network.ps1" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\check-network.ps1"

:: Helper AI assistants: Codex (default), Gemma by computer size, Gemini optional
:: Nhân viên AI phụ: Codex (mặc định), Gemma theo máy, Gemini tuỳ chọn
if not defined AI_WORKER_SKIP_HELPERS if exist "%CD%\helpers.ps1" powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\helpers.ps1"

:: Open the office page now: the plugin copies it at the first session, so put the same files there first
:: Mở trang văn phòng ngay: plugin chỉ chép trang ở phiên đầu tiên, nên chép sẵn đúng các file đó trước
if defined AI_WORKER_SKIP_HELPERS goto :after_open
if defined AI_WORKER_NO_OPEN goto :after_open
set "WEB_DIR=%USERPROFILE%\.local\share\ai-worker"
if not exist "%WEB_DIR%" mkdir "%WEB_DIR%"
for %%F in (index.html i18n.js index.vi.js ops.vi.js ops.js ops.css ops3d.js three.js three.LICENSE) do copy /y "%INSTALL_DIR%\ai-worker\web\%%F" "%WEB_DIR%\" >nul 2>&1
if not exist "%WEB_DIR%\config.js" copy /y "%INSTALL_DIR%\ai-worker\web\config.js" "%WEB_DIR%\" >nul 2>&1
if not exist "%WEB_DIR%\index.html" goto :after_open
start "" "%WEB_DIR%\index.html"
call :say "The office page is open in the browser; your sessions show up there once Claude Code is running." "Đã mở trang văn phòng trên trình duyệt; các phiên sẽ hiện ở đó khi Claude Code chạy."
:after_open

echo.
call :say "Done. Open (or reopen) Claude Code, then type /office to see the office." "Xong. Mở (hoặc mở lại) Claude Code, rồi gõ /office để xem văn phòng."
call :say "If Claude Code is already open: type /reload-plugins." "Nếu Claude Code đang mở: gõ /reload-plugins."
pause
exit /b 0

:no_claude
:: Claude Desktop is missing: offer to install it. Either way the user signs in first, then runs this file again.
:: Thiếu Claude Desktop: đề nghị cài. Dù cách nào thì người dùng cũng đăng nhập trước, rồi chạy lại file này.
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\install-desktop.ps1"
set "DESKTOP_RESULT=%ERRORLEVEL%"
pause
exit /b %DESKTOP_RESULT%

:say
:: Print English or Vietnamese, by AI_WORKER_LANG. Third argument "nonl" = no line break. Delayed expansion keeps characters such as ( ) & safe.
:: In ra tiếng Anh hoặc tiếng Việt, theo AI_WORKER_LANG. Tham số thứ ba "nonl" = không xuống dòng. Mở rộng trễ giữ an toàn cho các ký tự như ( ) &.
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
