# The sign-in and ask-the-name step of the Windows installer (called by INSTALL-Windows.bat).
# Bước đăng nhập và hỏi họ tên của file cài Windows (INSTALL-Windows.bat gọi).
# It receives its input through environment variables (empty parameters are easily dropped by PowerShell 5):
# Nhận qua biến môi trường (tham số rỗng dễ bị PowerShell 5 bỏ mất):
#   AI_WORKER_CLAUDE         the claude command that was found (empty if none)
#   AI_WORKER_CLAUDE         lệnh claude đã tìm thấy (rỗng nếu chưa có)
#   AI_WORKER_HAS_APP        1 if the computer has the Claude Desktop app
#   AI_WORKER_HAS_APP        1 nếu máy có app Claude Desktop
#   AI_WORKER_USER_FILE      user.json to write when the name is needed (empty = normal package, do not ask the name)
#   AI_WORKER_USER_FILE      file user.json cần ghi khi cần hỏi tên (rỗng = gói thường, không hỏi tên)
#   AI_WORKER_SETTINGS_FILE  user.json that always gets the language field
#   AI_WORKER_SETTINGS_FILE  user.json luôn được ghi trường language
#   AI_WORKER_CMD_OUT        file to report back the claude command found after the app is opened (the app downloads it when the Code tab opens)
#   AI_WORKER_CMD_OUT        file để báo lại lệnh claude tìm thấy sau khi mở app (app tải về khi mở tab Code)
# PowerShell reads Vietnamese typed in; cmd may not.
# PowerShell đọc được tiếng Việt gõ vào; cmd thì không chắc.
$Claude = [string]$env:AI_WORKER_CLAUDE
$HasApp = [string]$env:AI_WORKER_HAS_APP
$UserFile = [string]$env:AI_WORKER_USER_FILE
$SettingsFile = [string]$env:AI_WORKER_SETTINGS_FILE
$CmdOut = [string]$env:AI_WORKER_CMD_OUT
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$langFile = Join-Path $PSScriptRoot 'lang.ps1'
if (-not (Test-Path $langFile)) { Write-Host 'lang.ps1 is missing next to this file: unzip the whole zip file and run again. / Thiếu lang.ps1 cạnh file này: giải nén cả file zip rồi chạy lại.'; exit 1 } # i18n-allow
. $langFile
# Ask one line; for automatic install / tests: take answers one by one from the file AI_WORKER_ANSWERS_FILE (PowerShell swallows stdin when it starts)
# Hỏi một dòng; cài tự động / thử nghiệm: lấy lần lượt từ file AI_WORKER_ANSWERS_FILE (stdin bị PowerShell đọc mất khi khởi động)
function Ask([string]$question) {
  if ($env:AI_WORKER_ANSWERS_FILE) {
    $counter = "$env:AI_WORKER_ANSWERS_FILE.pos"
    $i = 0
    if (Test-Path $counter) { $i = [int](Get-Content $counter) }
    Set-Content -Path $counter -Value ($i + 1)
    $lines = @([IO.File]::ReadAllLines($env:AI_WORKER_ANSWERS_FILE, [Text.Encoding]::UTF8))
    if ($i -ge $lines.Count) {
      Say-Text "${question}: (out of answers)" "${question}: (hết câu trả lời)"
      exit 3
    }
    Write-Host "${question}: $($lines[$i])"
    return [string]$lines[$i]
  }
  return [string](Read-Host $question)
}

function Find-Claude {
  $root = Join-Path $env:APPDATA 'Claude\claude-code'
  if (-not (Test-Path $root)) { return '' }
  $f = Get-ChildItem -Path $root -Recurse -Filter 'claude.exe' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
  if ($f) { return $f.FullName } else { return '' }
}

# Email of the signed-in account: ask the claude command, else read the config file; '' = not signed in
# Email tài khoản đang đăng nhập: hỏi lệnh claude, không được thì đọc file cấu hình; '' = chưa đăng nhập
function Signed-In-Email {
  if ($Claude) {
    try {
      $j = (& $Claude auth status --json 2>$null | Out-String) | ConvertFrom-Json
      if ($j.loggedIn -eq $true) { return ([string]$j.email).Trim().ToLower() }
      if ($j.loggedIn -eq $false) { return '' }
    } catch { }
  }
  try {
    $folder = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { $env:USERPROFILE }
    # Read with a regular expression, not ConvertFrom-Json: this file can be very large
    # Đọc bằng biểu thức, không ConvertFrom-Json: file này có thể rất lớn
    $m = [regex]::Match([IO.File]::ReadAllText((Join-Path $folder '.claude.json')), '"emailAddress"\s*:\s*"([^"\s]+@[^"\s]+)"')
    if ($m.Success) { return $m.Groups[1].Value.ToLower() }
  } catch { }
  return ''
}

# Save the language in user.json (the plugin reads it); other fields stay as they are
# Ghi ngôn ngữ vào user.json (plugin đọc trường này); các trường khác giữ nguyên
function Save-Language {
  if (-not $SettingsFile) { return }
  try {
    New-Item -ItemType Directory -Force -Path (Split-Path $SettingsFile) | Out-Null
    $data = [pscustomobject]@{}
    if ((Test-Path $SettingsFile) -and ([IO.File]::ReadAllText($SettingsFile).Trim())) {
      $data = [IO.File]::ReadAllText($SettingsFile) | ConvertFrom-Json
    }
    $data | Add-Member -NotePropertyName language -NotePropertyValue $env:AI_WORKER_LANG -Force
    [IO.File]::WriteAllText($SettingsFile, ($data | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
  } catch { }
}

# Sign in: we cannot sign in to the Claude app for the user, so open the app, let them sign in, then wait for confirmation
# Đăng nhập: không đăng nhập hộ được app Claude, nên mở app cho nhân viên tự đăng nhập rồi chờ xác nhận
$account = Signed-In-Email
if ($account) {
  Say-Text "Claude is signed in: $account" "Claude đã đăng nhập: $account"
} elseif ($HasApp -eq '1') {
  Write-Host ''
  Say-Text 'Claude does not look signed in on this computer. Opening the Claude app...' 'Chưa thấy Claude đăng nhập trên máy này. Đang mở app Claude...'
  # Through explorer.exe the app does not share this window, so its warnings do not print here.
  # Mở qua explorer.exe thì app không dùng chung cửa sổ này, nên cảnh báo của app không in ra đây.
  $exe = Join-Path $env:LOCALAPPDATA 'AnthropicClaude\claude.exe'
  try {
    if (Test-Path 'Registry::HKEY_CLASSES_ROOT\claude') { Start-Process explorer.exe 'claude://' }
    elseif (Test-Path $exe) { Start-Process explorer.exe $exe }
  } catch { }
  Say-Text 'In the Claude app: if you see the sign-in screen, sign in with the account your company gave you,' 'Trong app Claude: nếu thấy màn hình đăng nhập thì đăng nhập bằng tài khoản công ty cấp,'
  Say-Text 'then click the Code tab once (so the app downloads Claude Code to this computer).' 'rồi bấm sang tab Code một lần (để app tải phần Claude Code về máy).'
  [void](Ask (
    Say-Text -AsString 'When done, press Enter here to continue installing' 'Xong thì nhấn Enter ở đây để cài tiếp'))
  if (-not $Claude) {
    $Claude = Find-Claude
    if ($Claude -and $CmdOut) { [IO.File]::WriteAllText($CmdOut, $Claude, (New-Object Text.UTF8Encoding $false)) }
  }
  $account = Signed-In-Email
  if ($account) {
    Say-Text "Claude is signed in: $account" "Claude đã đăng nhập: $account"
  }
} elseif ($Claude) {
  Write-Host ''
  Say-Text 'Claude Code is not signed in.' 'Claude Code chưa đăng nhập.'
  $answer = (Ask (
    Say-Text -AsString 'Open the browser to sign in now? (Enter = yes, type n = later)' 'Mở trình duyệt để đăng nhập ngay? (Enter = có, gõ n = để sau)'))
  if ($answer.Trim().ToLower() -ne 'n') {
    try { & $Claude auth login --claudeai } catch {
      Say-Text 'Sign-in not finished; you can sign in later.' 'Đăng nhập chưa xong; đăng nhập sau cũng được.'
    }
    $account = Signed-In-Email
    if ($account) {
      Say-Text "Claude is signed in: $account" "Claude đã đăng nhập: $account"
    }
  }
}

# Ask for a name only when user.json has no name yet (it may hold just the language from an earlier install)
# Chỉ hỏi tên khi user.json chưa có tên (file có thể chỉ có ngôn ngữ từ lần cài trước)
$hasName = $false
if ($UserFile -and (Test-Path $UserFile)) {
  try { $hasName = [bool]([IO.File]::ReadAllText($UserFile) | ConvertFrom-Json).name } catch { $hasName = $false }
}
if (-not $UserFile -or $hasName) { Save-Language; exit 0 }

Write-Host ''
Say-Text 'This package sends usage numbers (sessions, tokens, cost; NOT chat content or file names)' 'Gói này gửi số liệu sử dụng (số phiên, token, chi phí; KHÔNG có nội dung chat hay tên file)'
Say-Text 'to the company dashboard.' 'lên bảng tổng của công ty.'
$name = ''
while (-not $name.Trim()) {
  $name = (Ask (
    Say-Text -AsString 'Your full name' 'Họ tên của bạn'))
}
$name = (($name -replace '[\x00-\x1f]', ' ') -replace '["\\]', '').Trim()

if (-not $account) {
  Say-Text 'Could not get the email of your Claude account. Signing in later is fine: the office will pick it up.' 'Chưa lấy được email tài khoản Claude. Đăng nhập sau cũng được: văn phòng sẽ tự nhận.'
  while ($true) {
    $account = ((Ask (
      Say-Text -AsString 'Claude account email (Enter to skip)' 'Email tài khoản Claude (Enter để bỏ qua)')) -replace '[\s"\\]', '').ToLower()
    if (-not $account -or $account -match '^[^@]+@[^@]+\.[^@]+$') { break }
    Say-Text 'That email does not look right (e.g. name@example.com). Type it again or press Enter to skip.' 'Email chưa đúng dạng (vd: ten@example.com), nhập lại hoặc Enter để bỏ qua.'
  }
}

New-Item -ItemType Directory -Force -Path (Split-Path $UserFile) | Out-Null
$json = @{ name = $name; account = $account } | ConvertTo-Json -Compress
[IO.File]::WriteAllText($UserFile, $json, (New-Object Text.UTF8Encoding $false))
Say-Text "Saved. You can edit it later at: $UserFile" "Đã lưu. Sửa sau ở: $UserFile"
Save-Language
