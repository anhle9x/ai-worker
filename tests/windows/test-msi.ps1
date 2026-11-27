# Try AI Worker plugin.msi on a clean machine (GitHub Actions, windows-latest): the server fills a company copy, then install, the setup window,
# Thử AI Worker plugin.msi trên máy sạch (GitHub Actions, windows-latest): máy chủ điền một bản công ty, rồi cài, cửa sổ cài,
# a plugin updated by /update, an upgrade, a refused downgrade, the uninstall, and a personal copy left unfilled.
# plugin đã cập nhật bằng /update, nâng cấp, hạ cấp bị từ chối, gỡ cài, và một bản cá nhân để nguyên không điền.
# The .msi installs for the runner's own user; the claude command is a fake that logs what it is asked (as in test-install.ps1).
# Gói .msi cài cho chính người dùng của máy chạy thử; lệnh claude là bản giả ghi lại lệnh được gọi (như test-install.ps1).
# Run: pwsh tests/windows/test-msi.ps1 -Msi <AI Worker plugin.msi> -NewerMsi <the same, one version higher>
# Chạy: pwsh tests/windows/test-msi.ps1 -Msi <AI Worker plugin.msi> -NewerMsi <cùng gói, cao hơn một bản>
param([Parameter(Mandatory = $true)][string]$Msi, [Parameter(Mandatory = $true)][string]$NewerMsi)
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$root = Join-Path $env:RUNNER_TEMP 'test-msi'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$errors = 0
$programDir = Join-Path $env:LOCALAPPDATA 'Programs\AI Worker Plugin'
$pluginDir = Join-Path $env:USERPROFILE 'claude-plugins-ai-worker'
$regKey = 'HKCU:\Software\AI Worker Plugin'
$shortcut = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Finish AI Worker setup.lnk'
$log = Join-Path $env:USERPROFILE 'commands.log'

function Check([string]$label, [scriptblock]$cond, [string]$detail = '') {
  $ok = $false
  try { $ok = [bool](& $cond) } catch { $ok = $false }
  if ($ok) { Write-Host "  PASS  $label" } else { Write-Host "  FAIL  $label"; if ($detail) { Write-Host $detail }; $script:errors++ }
}

# The company copy, filled by the server's own code (server/board/packages.py), as an admin would download it
# Bản công ty, điền bằng chính mã của máy chủ (server/board/packages.py), như quản trị tải về
function Fill([string]$source, [string]$target) {
  $dir = Join-Path $root ('fill-' + [guid]::NewGuid())
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  Copy-Item $source (Join-Path $dir 'AI-Worker-Plugin.msi')
  $code = @'
import sys
sys.path.insert(0, sys.argv[1])
from board import packages
packages.MENUBAR_DIR = sys.argv[2]
package = packages.plugin_msi("https://aiworker.example.com/", "TESTSENDKEY234567", "ai-worker ssh-ed25519 AAAAtestkey\n")
assert package, "the server did not fill the .msi"
open(sys.argv[3], "wb").write(package)
'@
  python -c $code (Join-Path $repo 'server') $dir $target
  if ($LASTEXITCODE -ne 0) { throw "filling $source failed" }
}

function Install([string]$file) {
  $p = Start-Process msiexec.exe -ArgumentList '/i', "`"$file`"", '/qn', '/norestart', '/l*v', "`"$root\install-$([IO.Path]::GetFileNameWithoutExtension($file)).log`"" -Wait -PassThru
  return $p.ExitCode
}
function Uninstall([string]$file) {
  $p = Start-Process msiexec.exe -ArgumentList '/x', "`"$file`"", '/qn', '/norestart', '/l*v', "`"$root\uninstall.log`"" -Wait -PassThru
  return $p.ExitCode
}

# The setup window (setup.cmd from the installed folder, as the finish screen and the Start menu open it), with the fake claude, signed in
# Cửa sổ cài (setup.cmd trong thư mục đã cài, như màn hình cuối và menu Start mở), với lệnh claude giả, đã đăng nhập
$fake = Join-Path $root 'fake'
New-Item -ItemType Directory -Force -Path $fake | Out-Null
Set-Content -Encoding ascii -Path (Join-Path $fake 'claude.cmd') -Value @'
@echo off
echo [claude] %*>> "%USERPROFILE%\commands.log"
if not "%1 %2"=="auth status" exit /b 0
echo {"loggedIn": true, "email": "lan@example.com"}
exit /b 0
'@
function Setup([string]$name, [string[]]$answers) {
  $stdin = Join-Path $root "stdin-$name.txt"
  [IO.File]::WriteAllText($stdin, ("`r`n" * 10), (New-Object Text.UTF8Encoding $false))
  $answersFile = Join-Path $root "answers-$name.txt"
  [IO.File]::WriteAllText($answersFile, ((@($answers) | ForEach-Object { "$_`r`n" }) -join ''), (New-Object Text.UTF8Encoding $false))
  $saved = @{}
  $envMap = @{ AI_WORKER_LANG = 'en'; AI_WORKER_ANSWERS_FILE = $answersFile; AI_WORKER_NO_OPEN = '1'; AI_WORKER_SKIP_HELPERS = '1'; Path = "$fake;$env:Path" }
  foreach ($k in $envMap.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envMap[$k]) }
  try {
    $outFile = Join-Path $root "out-$name.txt"
    $p = Start-Process cmd.exe -ArgumentList '/d', '/c', "`"$programDir\setup.cmd`"" -RedirectStandardInput $stdin -RedirectStandardOutput $outFile `
      -RedirectStandardError (Join-Path $root "err-$name.txt") -NoNewWindow -PassThru
    if (-not $p.WaitForExit(240000)) { & taskkill.exe /T /F /PID $p.Id | Out-Null; $code = 'HUNG' } else { $code = $p.ExitCode }
  } finally { foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) } }
  return [pscustomobject]@{ ExitCode = $code; Out = (Get-Content -Raw -ErrorAction SilentlyContinue $outFile) + (Get-Content -Raw -ErrorAction SilentlyContinue (Join-Path $root "err-$name.txt")) }
}
function Version() { (Get-Content -Raw (Join-Path $pluginDir 'ai-worker\.claude-plugin\plugin.json') | ConvertFrom-Json).version }
function Company() { Get-Content -Raw (Join-Path $pluginDir 'ai-worker\web\company.json') | ConvertFrom-Json }
function UserFile() { Get-Content -Raw (Join-Path $env:USERPROFILE '.local\share\ai-worker\user.json') | ConvertFrom-Json }

$company = Join-Path $root 'company.msi'; Fill $Msi $company
$companyNewer = Join-Path $root 'company-newer.msi'; Fill $NewerMsi $companyNewer

Write-Host '== M1 install the company copy silently, no admin rights'
Check 'msiexec exits 0' { (Install $company) -eq 0 }
Check 'the package and its scripts are in LocalAppData\Programs' { (Test-Path "$programDir\AI-Worker.zip") -and (Test-Path "$programDir\setup.cmd") -and (Test-Path "$programDir\uninstall.cmd") }
Check 'the company settings wait in the registry, filled' { $v = (Get-ItemProperty $regKey).Company.Trim(); $v -and -not $v.StartsWith('AIWORKER-COMPANY-') }
Check 'the Start menu entry is there' { Test-Path $shortcut }
Check 'nothing is written into the plugin folder yet' { -not (Test-Path $pluginDir) }

Write-Host '== M2 the setup window: signed in, types a Vietnamese name'
$r = Setup 'm2' @('Nguyễn Thị Lan') # i18n-allow
Check 'exit 0' { $r.ExitCode -eq 0 } $r.Out
Check 'registers the plugin with Claude Code' { (Get-Content -Raw $log) -match 'plugin install ai-worker@ai-worker' } $r.Out
Check 'company.json holds the server address and the send code' { $c = Company; $c.sharing.enabled -and $c.sharing.webhook -eq 'https://aiworker.example.com' -and $c.sharing.ingestKey -eq 'TESTSENDKEY234567' }
Check 'the update signing key is in place' { (Get-Content -Raw (Join-Path $pluginDir 'ai-worker\keys\allowed_signers')) -match 'ai-worker ssh-ed25519 AAAAtestkey' }
Check 'the name with accents is saved' { (UserFile).name -eq 'Nguyễn Thị Lan' } # i18n-allow
Check 'the registry copy of the send code is deleted' { -not (Get-ItemProperty $regKey -Name Company -ErrorAction SilentlyContinue) }
Check 'the work folder is gone' { -not (Get-ChildItem $env:TEMP -Directory -Filter 'ai-worker-setup-*' -ErrorAction SilentlyContinue) }

Write-Host '== M3 after /update, running the setup again keeps the newer plugin and the company settings'
$manifest = Join-Path $pluginDir 'ai-worker\.claude-plugin\plugin.json'
(Get-Content -Raw $manifest) -replace '"version": *"[^"]*"', '"version": "99.0.0"' | Set-Content -NoNewline -Encoding utf8 $manifest
$r = Setup 'm3' @()
Check 'exit 0' { $r.ExitCode -eq 0 } $r.Out
Check 'says it keeps the newer plugin' { $r.Out -match 'newer than this installer' } $r.Out
Check 'the plugin is still 99.0.0' { (Version) -eq '99.0.0' }
Check 'company.json is still there' { (Company).sharing.ingestKey -eq 'TESTSENDKEY234567' }
Check 'the name is not asked again' { (UserFile).name -eq 'Nguyễn Thị Lan' } # i18n-allow

Write-Host '== M4 upgrade to the newer .msi: the plugin stays registered and in place'
Remove-Item -ErrorAction SilentlyContinue $log
Check 'msiexec exits 0' { (Install $companyNewer) -eq 0 }
Check 'the plugin folder is still there (the old product was removed without the uninstall step)' { (Version) -eq '99.0.0' }
Check 'the uninstall step did not run' { -not (Test-Path $log) -or (Get-Content -Raw $log) -notmatch 'plugin uninstall' }
# a per-user product may be listed under HKCU or HKLM, depending on the Windows version: count both
# sản phẩm cài cho riêng người dùng có thể nằm ở HKCU hoặc HKLM, tuỳ bản Windows: đếm cả hai
Check 'one AI Worker plugin entry in Settings > Apps' { @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue | Where-Object { $_.GetValue('DisplayName') -eq 'AI Worker plugin' }).Count -eq 1 }

Write-Host '== M5 the older .msi over the newer one is refused'
Check 'msiexec refuses' { (Install $company) -ne 0 }
Check 'the plugin is untouched' { (Version) -eq '99.0.0' }

Write-Host '== M6 uninstall: the plugin folder and the registry go, the person''s own data stays'
Check 'msiexec exits 0' { (Uninstall $companyNewer) -eq 0 }
Check 'LocalAppData\Programs\AI Worker Plugin is gone' { -not (Test-Path $programDir) }
Check 'the plugin folder with company.json is gone' { -not (Test-Path $pluginDir) } (Get-Content -Raw -ErrorAction SilentlyContinue "$root\uninstall.log" | Select-String -Pattern 'UninstallPlugin' | Out-String)
Check 'the registry key is gone' { -not (Test-Path $regKey) }
Check 'the Start menu entry is gone' { -not (Test-Path $shortcut) }
Check 'user.json stays' { (UserFile).name -eq 'Nguyễn Thị Lan' } # i18n-allow

Write-Host '== M7 the uninstall script asks Claude Code to forget the plugin when it finds the claude command'
New-Item -ItemType Directory -Force -Path "$pluginDir\.claude-plugin" | Out-Null
Set-Content -Path "$pluginDir\.claude-plugin\marketplace.json" -Value '{}'
Remove-Item -ErrorAction SilentlyContinue $log
$saved = $env:Path; $env:Path = "$fake;$env:Path"
try { & cmd.exe /d /c "`"$repo\packaging\windows-msi\uninstall.cmd`" `"$env:LOCALAPPDATA\`" `"$env:APPDATA\`"" | Out-Null } finally { $env:Path = $saved }
Check 'calls plugin uninstall and marketplace remove' { $t = Get-Content -Raw $log; $t -match 'plugin uninstall ai-worker@ai-worker' -and $t -match 'plugin marketplace remove ai-worker' }
Check 'deletes the plugin folder' { -not (Test-Path $pluginDir) }

Write-Host '== M8 the copy nobody filled is a personal install (for the public repository)'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $env:USERPROFILE '.local\share\ai-worker')
Check 'msiexec exits 0' { (Install (Resolve-Path $Msi)) -eq 0 }
$r = Setup 'm8' @()
Check 'exit 0' { $r.ExitCode -eq 0 } $r.Out
Check 'no company.json' { (Test-Path (Join-Path $pluginDir 'ai-worker\.claude-plugin\plugin.json')) -and -not (Test-Path (Join-Path $pluginDir 'ai-worker\web\company.json')) }
Check 'no name asked' { -not (UserFile).name -and $r.Out -notmatch 'out of answers' } $r.Out
Check 'uninstalls' { (Uninstall (Resolve-Path $Msi)) -eq 0 -and -not (Test-Path $pluginDir) }

if ($errors) { Write-Host "$errors checks FAILED"; exit 1 }
Write-Host 'All passed.'
