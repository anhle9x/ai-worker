# Try the Windows installer on a clean machine (GitHub Actions, windows-latest): each case gets its own fake user folder,
# Thử file cài Windows trên máy sạch (GitHub Actions, windows-latest): mỗi tình huống một thư mục người dùng giả,
# a fake claude command (it logs the commands called and returns the sign-in state from a file), and prepared answers fed to stdin.
# lệnh claude giả (ghi lại lệnh được gọi, trả trạng thái đăng nhập theo file), câu trả lời soạn sẵn đưa vào stdin.
# Run: pwsh tests/windows/test-install.ps1 -Package <folder with the unzipped AI-Worker>
# Chạy: pwsh tests/windows/test-install.ps1 -Package <thư mục đã giải nén AI-Worker>
param([Parameter(Mandatory = $true)][string]$Package)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'test-install'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$errors = 0

# Fake claude command: auth status reads %USERPROFILE%\login.json; every command is logged to %USERPROFILE%\commands.log
# Lệnh claude giả: auth status đọc %USERPROFILE%\login.json; mọi lệnh ghi vào %USERPROFILE%\commands.log
$fake = Join-Path $root 'fake'
New-Item -ItemType Directory -Force -Path $fake | Out-Null
Set-Content -Encoding ascii -Path (Join-Path $fake 'claude.cmd') -Value @'
@echo off
echo [claude] %*>> "%USERPROFILE%\commands.log"
if not "%1 %2"=="auth status" exit /b 0
if exist "%USERPROFILE%\login.json" (
  type "%USERPROFILE%\login.json"
  exit /b 0
)
echo {"loggedIn": false}
exit /b 1
'@

function Run([string]$name, [hashtable]$opts) {
  # $opts: HasCmd (bool), LoggedIn (email or ''), HasApp (bool), Company (bool), Answers (answers to the PowerShell questions, in order),
  # $opts: HasCmd (bool), LoggedIn (email hoặc ''), HasApp (bool), Company (bool), Answers (câu trả lời cho các câu hỏi PowerShell, theo thứ tự),
  #       HasUser (user.json exists before), Helpers (bool), Lang (en or vi, default en). The cmd "press any key" steps take Enter from stdin.
  #       HasUser (user.json có trước), Helpers (bool), Lang (en hoặc vi, mặc định en). Các lần 'nhấn phím' của cmd lấy Enter từ stdin.
  $userHome = Join-Path $root $name
  New-Item -ItemType Directory -Force -Path $userHome, "$userHome\AppData\Roaming", "$userHome\AppData\Local", "$userHome\Temp" | Out-Null
  $folder = Join-Path $root "package-$name"
  Copy-Item -Recurse -Force $Package $folder
  if ($opts.Company) { Set-Content -Path (Join-Path $folder 'setup\ASK-NAME') -Value 'test' } else { Remove-Item -ErrorAction SilentlyContinue (Join-Path $folder 'setup\ASK-NAME') }
  if ($opts.LoggedIn) { Set-Content -Encoding utf8 -Path "$userHome\login.json" -Value "{`"loggedIn`": true, `"email`": `"$($opts.LoggedIn)`"}" }
  if ($opts.HasApp) { New-Item -ItemType Directory -Force -Path "$userHome\AppData\Roaming\Claude" | Out-Null }
  if ($opts.HasUser) {
    New-Item -ItemType Directory -Force -Path "$userHome\.local\share\ai-worker" | Out-Null
    Set-Content -Encoding utf8 -Path "$userHome\.local\share\ai-worker\user.json" -Value '{"name":"Cu","account":"cu@example.com"}'
  }
  $stdin = Join-Path $root "stdin-$name.txt"
  [IO.File]::WriteAllText($stdin, ("`r`n" * 10), (New-Object Text.UTF8Encoding $false))
  $answersFile = Join-Path $root "answers-$name.txt"
  [IO.File]::WriteAllText($answersFile, ((@($opts.Answers) | ForEach-Object { "$_`r`n" }) -join ''), (New-Object Text.UTF8Encoding $false))
  $path = 'C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32\Wbem'
  if ($opts.HasCmd) { $path = "$fake;$path" }
  # A stand-in for winget that exits with the given code
  # Bản giả của winget, thoát với mã được chỉ định
  if ($null -ne $opts.Winget) {
    $wingetDir = Join-Path $root "winget-$name"
    New-Item -ItemType Directory -Force -Path $wingetDir | Out-Null
    Set-Content -Path (Join-Path $wingetDir 'winget.cmd') -Value "@echo %* > `"$wingetDir\args.txt`"`r`n@exit /b $($opts.Winget)"
    $path = "$wingetDir;$path"
  }
  $envMap = @{
    AI_WORKER_LANG = $(if ($opts.Lang) { $opts.Lang } else { 'en' }); AI_WORKER_ANSWERS_FILE = $answersFile; USERPROFILE = $userHome; APPDATA = "$userHome\AppData\Roaming"; LOCALAPPDATA = "$userHome\AppData\Local"; TEMP = "$userHome\Temp"; TMP = "$userHome\Temp"; Path = $path
  }
  $saved = @{}
  foreach ($k in $envMap.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envMap[$k]) }
  if (-not $opts.Helpers) { $env:AI_WORKER_SKIP_HELPERS = '1' } else { Remove-Item Env:AI_WORKER_SKIP_HELPERS -ErrorAction SilentlyContinue }
  try {
    # Each case gets 4 minutes at most: if it hangs (waiting for a key), cut it and print where it waits
    # Mỗi tình huống tối đa 4 phút: treo (chờ phím) thì cắt và in ra chỗ đang chờ
    $outFile = Join-Path $root "out-$name.txt"; $errFile = Join-Path $root "err-$name.txt"
    $p = Start-Process cmd.exe -ArgumentList '/d', '/c', "`"$folder\INSTALL-Windows.bat`"" -RedirectStandardInput $stdin `
      -RedirectStandardOutput $outFile -RedirectStandardError $errFile -NoNewWindow -PassThru
    if (-not $p.WaitForExit(240000)) {
      & taskkill.exe /T /F /PID $p.Id | Out-Null
      $exitCode = 'HUNG'
    } else { $exitCode = $p.ExitCode }
    $out = (Get-Content -Raw -ErrorAction SilentlyContinue $outFile) + (Get-Content -Raw -ErrorAction SilentlyContinue $errFile)
  } finally {
    foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
  }
  $userFile = Join-Path $userHome '.local\share\ai-worker\user.json'
  return [pscustomobject]@{
    Name = $name; ExitCode = $exitCode; Out = $out
    User = $(if (Test-Path $userFile) { [IO.File]::ReadAllText($userFile).Trim() } else { '' })
    Cmds = $(if (Test-Path "$userHome\commands.log") { Get-Content -Raw "$userHome\commands.log" } else { '' })
    Home = $userHome
  }
}

function Check($result, [string]$label, [scriptblock]$cond) {
  $ok = $false
  try { $ok = [bool](& $cond $result) } catch { $ok = $false }
  if ($ok) { Write-Host "  PASS  $label" } else {
    Write-Host "  FAIL  $label"
    $script:errors++
    Write-Host '---- installer window ----'; Write-Host $result.Out
    Write-Host "---- user.json: $($result.User)"; Write-Host "---- commands: $($result.Cmds)"
  }
}

Write-Host '== W1 normal package, already signed in'
$k = Run 'w1' @{ HasCmd = $true; LoggedIn = 'lan@example.com'; Answers = @() }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'calls plugin install' { param($k) $k.Cmds -match 'plugin install ai-worker@ai-worker' }
Check $k 'asks nothing (no name saved, no answers ran out)' { param($k) -not ($k.User | ConvertFrom-Json).name -and $k.Out -notmatch 'out of answers' }
Check $k 'says it is signed in' { param($k) $k.Out -match 'Claude is signed in: lan@example.com' }
Check $k 'saves the language en' { param($k) ($k.User | ConvertFrom-Json).language -eq 'en' }

Write-Host '== W2 company package, signed in, Vietnamese name'
$k = Run 'w2' @{ HasCmd = $true; LoggedIn = 'lan@example.com'; Company = $true; Answers = @('Nguyễn Thị Lan') } # i18n-allow
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'saves the name with accents, the detected email and the language' { param($k) ($k.User | ConvertFrom-Json).name -eq 'Nguyễn Thị Lan' -and ($k.User | ConvertFrom-Json).account -eq 'lan@example.com' -and ($k.User | ConvertFrom-Json).language -eq 'en' } # i18n-allow

Write-Host '== W3 company package, not signed in, no app, declines the browser, types an email'
$k = Run 'w3' @{ HasCmd = $true; Company = $true; Answers = @('n', 'Minh', 'minh@example.com') }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'does not call auth login' { param($k) $k.Cmds -notmatch 'auth login' }
Check $k 'saves the typed email' { param($k) ($k.User | ConvertFrom-Json).account -eq 'minh@example.com' }

Write-Host '== W4 company package, not signed in, types a wrong email then skips'
$k = Run 'w4' @{ HasCmd = $true; Company = $true; Answers = @('n', 'Tuan', 'sai-email', '') }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'warns about the wrong email format' { param($k) $k.Out -match 'does not look right' }
Check $k 'saves an empty email' { param($k) ($k.User | ConvertFrom-Json).account -eq '' }

Write-Host '== W5 Claude is not installed at all, the user declines the install'
$k = Run 'w5' @{ Answers = @('n') }
Check $k 'exit 1' { param($k) $k.ExitCode -eq 1 }
Check $k 'tells the user to download Claude Desktop' { param($k) $k.Out -match 'Claude is not installed on this computer' }

Write-Host '== W5b no Claude, agrees, winget installs it'
$k = Run 'w5b' @{ Winget = 0; Answers = @('') }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'calls winget for the Anthropic package' { param($k) (Get-Content (Join-Path $root 'winget-w5b\args.txt') -Raw) -match 'install --id Anthropic\.Claude --exact' }
Check $k 'tells the user to sign in and run again' { param($k) $k.Out -match 'Claude Desktop is installed' }
Write-Host '== W5c no Claude, agrees, winget fails'
$k = Run 'w5c' @{ Winget = 5; Answers = @('y') }
Check $k 'exit 1' { param($k) $k.ExitCode -eq 1 }
Check $k 'falls back to the download link' { param($k) $k.Out -match 'claude\.com/download' }
Write-Host '== W5d no Claude, agrees, no winget'
$k = Run 'w5d' @{ Answers = @('y') }
Check $k 'exit 1' { param($k) $k.ExitCode -eq 1 }
Check $k 'says winget is missing' { param($k) $k.Out -match 'no winget' }
Write-Host '== W5e the package id still exists at Microsoft'
$real = (Get-Command winget -ErrorAction SilentlyContinue).Source
if ($real) { $show = & $real show --id Anthropic.Claude --exact --accept-source-agreements 2>&1 | Out-String; Write-Host ($show.Substring(0, [Math]::Min(300, $show.Length))); if ($show -match 'Anthropic') { Write-Host '  PASS  winget knows Anthropic.Claude' } else { Write-Host '  FAIL  winget does not know Anthropic.Claude'; $errors++ } } else { Write-Host '  SKIP  this runner has no winget' }
Write-Host '== W6 app but no claude command: copies the commands to paste'
$k = Run 'w6' @{ HasApp = $true; Answers = @('') }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'explains how to paste the command' { param($k) $k.Out -match 'Command copied' }
Check $k 'copied the plugin into the user folder' { param($k) Test-Path (Join-Path $k.Home 'claude-plugins-ai-worker\ai-worker\.claude-plugin\plugin.json') }

Write-Host '== W7 reinstall when a name already exists'
$k = Run 'w7' @{ HasCmd = $true; LoggedIn = 'cu@example.com'; Company = $true; HasUser = $true; Answers = @() }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'keeps the old name' { param($k) ($k.User | ConvertFrom-Json).name -eq 'Cu' }
Check $k 'adds the language and keeps the account' { param($k) ($k.User | ConvertFrom-Json).language -eq 'en' -and ($k.User | ConvertFrom-Json).account -eq 'cu@example.com' }

Write-Host '== W8 helper AI assistants: real Codex install, declines Codex sign-in, declines Gemma, no Gemini'
$k = Run 'w8' @{ HasCmd = $true; LoggedIn = 'lan@example.com'; Helpers = $true; Answers = @('n', 'n', '') }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'Codex is installed' { param($k) $k.Out -match 'ChatGPT \(Codex\): needs sign-in|ChatGPT \(Codex\): installed' }
Check $k 'Gemma: offers one size or gives the reason' { param($k) $k.Out -match 'install version gemma4:|Gemma: not installed' }
Check $k 'Gemini is not installed' { param($k) $k.Out -match 'Gemini: not installed' }

Write-Host '== W9 Vietnamese: AI_WORKER_LANG=vi shows Vietnamese and saves vi'
$k = Run 'w9' @{ HasCmd = $true; LoggedIn = 'lan@example.com'; Lang = 'vi'; Answers = @() }
Check $k 'exit 0' { param($k) $k.ExitCode -eq 0 }
Check $k 'prints the Vietnamese sign-in line' { param($k) $k.Out -match 'Claude đã đăng nhập: lan@example.com' } # i18n-allow
Check $k 'saves the language vi' { param($k) ($k.User | ConvertFrom-Json).language -eq 'vi' }

if ($errors) { Write-Host "$errors checks FAILED"; exit 1 }
Write-Host 'All passed.'
