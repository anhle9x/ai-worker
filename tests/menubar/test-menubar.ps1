# The Windows icon script against a fake server, without the icon (-Once): first round pairs, the next counts 2 waiting.
# Script biểu tượng Windows với máy chủ giả, không hiện biểu tượng (-Once): lượt đầu ghép, lượt sau đếm 2 người chờ.
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$Tmp = Join-Path ([IO.Path]::GetTempPath()) ('menubar-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Tmp | Out-Null
$server = Start-Process python -ArgumentList @((Join-Path $Root 'tests\menubar\fake_server.py'), '8792') -PassThru -RedirectStandardOutput (Join-Path $Tmp 'server.log') -RedirectStandardError (Join-Path $Tmp 'server.err') -NoNewWindow
try {
  for ($i = 0; $i -lt 30; $i++) { if ((Test-Path (Join-Path $Tmp 'server.log')) -and (Get-Content (Join-Path $Tmp 'server.log') -Raw) -match 'ready') { break }; Start-Sleep -Milliseconds 500 }
  $env:AI_WORKER_MENUBAR_DIR = Join-Path $Tmp 'cfg'
  New-Item -ItemType Directory -Path $env:AI_WORKER_MENUBAR_DIR | Out-Null
  '{"server": "http://127.0.0.1:8792", "lang": "en"}' | Set-Content (Join-Path $env:AI_WORKER_MENUBAR_DIR 'menubar.json') -Encoding ASCII
  $fail = 0
  function Check($ok, $name) { if ($ok) { Write-Host "PASS $name" } else { Write-Host "FAIL $name"; $script:fail = 1 } }
  $script = Join-Path $Root 'server\menubar\ai-worker-tray.ps1'
  $first = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Once 2>&1 | ForEach-Object { "$_" }
  $first = $first -join ' / '
  Check ($first -match '^pair\|0\|Pairing code: \d{4}-\d{4}\|$') "first round shows a pairing code ($first)"
  Start-Sleep -Seconds 1
  $second = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Once 2>&1 | ForEach-Object { "$_" }
  $second = $second -join ' / '
  Check ($second -match '^long\|2\|2 waiting\|url$') "second round shows 2 waiting, one past the limit ($second)"
  Check (Test-Path (Join-Path $env:AI_WORKER_MENUBAR_DIR 'menubar-session')) 'the session is saved'
  $env:AI_WORKER_MENUBAR_DIR = Join-Path $Tmp 'empty'
  $none = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Once
  Check ($none -match '^setup\|') "without settings it asks to run the installer ($none)"
  # the installer as Windows PowerShell 5 reads it: no parse error, and its Vietnamese words arrive intact (they need the UTF-8 BOM)
  # file cài theo cách Windows PowerShell 5 đọc: không lỗi cú pháp, và chữ tiếng Việt còn nguyên (cần BOM UTF-8)
  $installer = Join-Path $Root 'server\menubar\install-menubar.ps1'
  $parsed = & powershell -NoProfile -Command "`$e = `$null; `$t = `$null; [void][System.Management.Automation.Language.Parser]::ParseFile('$installer', [ref]`$t, [ref]`$e); '' + `$e.Count + '|' + (@(`$t | Where-Object { `$_.Kind -eq 'StringLiteral' -and `$_.Value -match '^Ch' } | ForEach-Object { [int][char]`$_.Value[2] }) -join ',')"
  Check ($parsed -match '^0\|.*\b432\b') "the installer parses and keeps its Vietnamese words ($parsed)"
  # the tray script parses, and the small window's code and libraries ship next to it
  # script khay không lỗi cú pháp, và mã cùng thư viện của khung nhỏ đi kèm
  $trayErrors = & powershell -NoProfile -Command "`$e = `$null; `$t = `$null; [void][System.Management.Automation.Language.Parser]::ParseFile('$script', [ref]`$t, [ref]`$e); `$e.Count"
  Check ("$trayErrors" -eq '0') "the tray script parses ($trayErrors errors)"
  Check (Test-Path (Join-Path $Root 'server\menubar\menubar-popup.cs')) 'the small window code exists'
  Check (Test-Path (Join-Path $Root 'server\menubar\webview2\Microsoft.Web.WebView2.WinForms.dll')) 'the WebView2 libraries exist'
  # the round badge of a notification, drawn by the tray script's own function in Windows PowerShell 5: "Phòng IT" gives a P on a colour
  # ô tròn của thông báo, vẽ bằng chính hàm của script khay trong Windows PowerShell 5: "Phòng IT" cho chữ P trên nền màu
  $badgeTest = Join-Path $Tmp 'badge.ps1'
  @"
`$e = `$null; `$t = `$null
`$ast = [System.Management.Automation.Language.Parser]::ParseFile('$script', [ref]`$t, [ref]`$e)
`$fn = `$ast.Find({ param(`$n) `$n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and `$n.Name -eq 'Get-Avatar' }, `$true)
`$colors = `$ast.Find({ param(`$n) `$n -is [System.Management.Automation.Language.AssignmentStatementAst] -and `$n.Left.Extent.Text -eq '`$AvatarColors' }, `$true)
Add-Type -AssemblyName System.Drawing
`$ConfigDir = '$Tmp'
Invoke-Expression `$colors.Extent.Text
Invoke-Expression `$fn.Extent.Text
`$p = Get-Avatar `$env:BADGE_NAME
`$b = New-Object System.Drawing.Bitmap `$p
'' + `$b.Width + '|' + `$b.GetPixel(64, 6).Name + '|' + `$b.GetPixel(2, 2).A + '|' + `$p
"@ | Set-Content $badgeTest -Encoding UTF8
  $env:BADGE_NAME = 'Ph' + [char]0xF2 + 'ng IT'
  $badge = & powershell -NoProfile -ExecutionPolicy Bypass -File $badgeTest 2>&1 | ForEach-Object { "$_" }
  $badge = $badge -join ' / '
  Check ($badge -match '^128\|ff[0-9a-f]{6}\|0\|.*50-[0-9a-f]{6}\.png$') "a notification badge is drawn for the first letter P ($badge)"
  if ($env:BADGE_OUT -and $badge -match '\|([^|]+\.png)$') { Copy-Item $Matches[1] $env:BADGE_OUT -ErrorAction SilentlyContinue }
  # a long wait is notified once, not again on every later round; one of the two names has Vietnamese letters
  # một lần chờ lâu chỉ được báo một lần, không báo lại ở các lượt sau; một trong hai tên có chữ tiếng Việt
  $onceTest = Join-Path $Tmp 'once.ps1'
  @"
`$e = `$null; `$t = `$null
`$ast = [System.Management.Automation.Language.Parser]::ParseFile('$script', [ref]`$t, [ref]`$e)
foreach (`$name in 'Read-Notified', 'Notify-Long', 'Save-Private') {
  Invoke-Expression `$ast.Find({ param(`$n) `$n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and `$n.Name -eq `$name }, `$true).Extent.Text
}
function T([string]`$text) { `$text }
`$script:sent = @()
function Send-Notification(`$title, `$body, `$who) { `$script:sent += `$who }
`$ConfigDir = '$Tmp'
`$NotifiedFile = Join-Path '$Tmp' 'notified.json'
`$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
`$r = @{ Notify = `$true; NotifyMinutes = 10; Waiting = @(@{ name = 'An'; since = `$now - 900000 }, @{ name = `$env:BADGE_NAME; since = `$now - 720000 }) }
Notify-Long `$r; Notify-Long `$r; Notify-Long `$r
'' + `$script:sent.Count + '|' + (`$script:sent -join ',')
"@ | Set-Content $onceTest -Encoding UTF8
  $once = & powershell -NoProfile -ExecutionPolicy Bypass -File $onceTest 2>&1 | ForEach-Object { "$_" }
  $once = $once -join ' / '
  Check ($once -match '^2\|An,Ph.ng IT$') "three rounds notify each long wait once ($once)"
  if ($fail) {
    Write-Host '--- server output'; Get-Content (Join-Path $Tmp 'server.log') -ErrorAction SilentlyContinue
    Write-Host '--- server errors'; Get-Content (Join-Path $Tmp 'server.err') -ErrorAction SilentlyContinue
  }
  exit $fail
} finally {
  Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
