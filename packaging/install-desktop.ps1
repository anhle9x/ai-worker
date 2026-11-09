# Installs the Claude Desktop app on Windows with winget after asking once. Exit 0 installed, 1 not installed.
# Cài app Claude Desktop trên Windows bằng winget sau khi hỏi một lần. Thoát 0 là đã cài, 1 là chưa cài.
# winget checks the installer against the checksum in Microsoft's package catalog.
# winget kiểm bộ cài theo mã kiểm tra trong danh mục gói của Microsoft.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$langFile = Join-Path $PSScriptRoot 'lang.ps1'
if (-not (Test-Path $langFile)) { Write-Host 'lang.ps1 is missing next to this file: unzip the whole zip file and run again.'; exit 1 }
. $langFile

function Not-Installed {
  Say-Text "Claude is not installed on this computer." "Máy chưa cài Claude."
  Say-Text "Download Claude Desktop at https://claude.com/download, sign in, open the Code tab once, then run this file again." "Tải Claude Desktop tại https://claude.com/download, đăng nhập, mở tab Code một lần, rồi chạy lại file này."
  # Leaves PowerShell itself, so cmd.exe always sees the code, whatever called this function.
  # Thoát hẳn PowerShell, để cmd.exe luôn nhận đúng mã, dù hàm này được gọi từ đâu.
  [Environment]::Exit(1)
}

# Test runs answer from a file, one answer per line.
# Khi chạy thử, câu trả lời lấy từ file, mỗi dòng một câu.
function Ask([string]$question) {
  if ($env:AI_WORKER_ANSWERS_FILE) {
    $counter = "$env:AI_WORKER_ANSWERS_FILE.pos"
    $i = 0
    if (Test-Path $counter) { $i = [int](Get-Content $counter) }
    Set-Content -Path $counter -Value ($i + 1)
    $lines = @([IO.File]::ReadAllLines($env:AI_WORKER_ANSWERS_FILE, [Text.Encoding]::UTF8))
    if ($i -ge $lines.Count) { exit 3 }
    Write-Host "${question}: $($lines[$i])"
    return [string]$lines[$i]
  }
  return [string](Read-Host $question)
}

Say-Text "Claude Desktop is not on this computer. It is needed to use this plugin." "Máy chưa có Claude Desktop. Plugin này cần app đó."
$question = (
  Say-Text "Install it now from Anthropic with winget? This means you accept Anthropic's terms and the winget source terms (Microsoft Store). [Y/n]" "Cài ngay từ Anthropic bằng winget? Như vậy là bạn đồng ý điều khoản của Anthropic và điều khoản nguồn của winget (Microsoft Store). [Y/n]" -AsString
)
$answer = Ask $question
if ($answer -match '^[nNkK]') { Not-Installed }

$winget = (Get-Command winget -ErrorAction SilentlyContinue).Source
if (-not $winget) {
  $candidate = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
  if (Test-Path $candidate) { $winget = $candidate }
}
if (-not $winget) {
  Say-Text "This computer has no winget, so the download page is opening." "Máy này không có winget, nên đang mở trang tải."
  if (-not $env:AI_WORKER_ANSWERS_FILE) { Start-Process 'https://claude.com/download' }
  Not-Installed
}

Say-Text "Installing Claude Desktop, this can take a few minutes..." "Đang cài Claude Desktop, có thể mất vài phút..."
& $winget install --id Anthropic.Claude --exact --silent --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
  Say-Text "winget could not install it (code $LASTEXITCODE)." "winget không cài được (mã $LASTEXITCODE)."
  Not-Installed
}
Say-Text "Claude Desktop is installed. Open it from the Start menu, sign in, open the Code tab once, then run this file again." "Đã cài Claude Desktop. Hãy mở app từ menu Start, đăng nhập, mở tab Code một lần, rồi chạy lại file này."
exit 0
