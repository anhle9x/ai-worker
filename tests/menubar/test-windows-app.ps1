# Tests AI Worker.exe and AI Worker.msi on Windows: fill the server address into the placeholder the way the server does,
# install for this user only (no admin rights), pair and count waiting people with the fake server, read an old plain session,
# take over from the old PowerShell icon, notify each wait once, then uninstall cleanly.
# Parameters: -Msi the built .msi (address not filled in yet); -NewerMsi a newer build (1.0.1) to install over it.
# Thử AI Worker.exe và gói AI Worker.msi trên Windows: điền địa chỉ máy chủ vào chỗ giữ chỗ như máy chủ làm,
# cài cho riêng người dùng (không cần quyền quản trị), ghép và đếm người chờ với máy chủ giả, đọc phiên cũ chưa mã hoá,
# thay bản PowerShell cũ, báo mỗi lần chờ một lần, rồi gỡ sạch.
# Tham số: -Msi đường dẫn file .msi đã dựng (chưa điền địa chỉ); -NewerMsi bản dựng mới hơn (1.0.1) để thử cài đè.
param([Parameter(Mandatory = $true)][string]$Msi, [Parameter(Mandatory = $true)][string]$NewerMsi)
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$Tmp = Join-Path ([IO.Path]::GetTempPath()) ('windows-app-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Tmp | Out-Null
$fail = 0
function Check($ok, $name) { if ($ok) { Write-Host "PASS $name" } else { Write-Host "FAIL $name"; $script:fail = 1 } }
# Runs a command and waits a limited time: prints the start time; past the limit it stops it and returns -1, so the test names the step that hung
# Chạy một lệnh, chờ tối đa vài giây: in giờ bắt đầu, quá hạn thì tắt và trả -1 để bài thử báo đúng bước treo
function Run([string]$file, [string[]]$arguments, [int]$seconds = 120) {
  Write-Host ('.. {0:HH:mm:ss} {1} {2}' -f (Get-Date), (Split-Path $file -Leaf), ($arguments -join ' '))
  $q = Start-Process $file -ArgumentList $arguments -PassThru
  if (-not $q.WaitForExit($seconds * 1000)) { Write-Host "HUNG after $seconds seconds: $file $($arguments -join ' ')"; Stop-Process -Id $q.Id -Force -ErrorAction SilentlyContinue; return -1 }
  return $q.ExitCode
}

# the placeholder must be one block, exactly once, so the server can replace it with its address
# chỗ giữ chỗ phải nằm liền một khối, đúng một lần, để máy chủ thay được bằng địa chỉ của nó
$Placeholder = 'AIWORKER-SERVER-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX'
$bytes = [IO.File]::ReadAllBytes($Msi)
$text = [Text.Encoding]::ASCII.GetString($bytes)
$count = ([regex]::Matches($text, [regex]::Escape($Placeholder))).Count
Check ($count -eq 1) "the address placeholder is one block, once ($count)"

# fill the address like the server: same length, padded with spaces
# điền địa chỉ như máy chủ: cùng độ dài, đệm dấu cách
$address = 'http://127.0.0.1:8794'
$filled = [Text.Encoding]::ASCII.GetBytes($address.PadRight($Placeholder.Length))
[Array]::Copy($filled, 0, $bytes, $text.IndexOf($Placeholder), $filled.Length)
$package = Join-Path $Tmp 'AI Worker.msi'
[IO.File]::WriteAllBytes($package, $bytes)

$server = Start-Process python -ArgumentList @((Join-Path $Root 'tests\menubar\fake_server.py'), '8794') -PassThru -RedirectStandardOutput (Join-Path $Tmp 'server.log') -RedirectStandardError (Join-Path $Tmp 'server.err') -NoNewWindow
try {
  for ($i = 0; $i -lt 30; $i++) { if ((Test-Path (Join-Path $Tmp 'server.log')) -and (Get-Content (Join-Path $Tmp 'server.log') -Raw) -match 'ready') { break }; Start-Sleep -Milliseconds 500 }
  $p = @{ ExitCode = (Run msiexec.exe @('/i', "`"$package`"", '/qn', '/norestart', '/l*v', "`"$Tmp\install.log`"")) }
  Check ($p.ExitCode -eq 0) "the .msi installs without admin rights (code $($p.ExitCode))"
  $exe = Join-Path $env:LOCALAPPDATA 'Programs\AI Worker\AI Worker.exe'
  Check (Test-Path $exe) 'the app sits in LOCALAPPDATA\Programs\AI Worker'
  Check (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\AI Worker\webview2\arm64\WebView2Loader.dll')) 'the WebView2 library for ARM64 is there'
  Check (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\AI Worker\vi.json')) 'the Vietnamese words are there'
  $written = (Get-ItemProperty 'HKCU:\Software\AI Worker' -ErrorAction SilentlyContinue).Server
  Check ($written -and $written.Trim() -eq $address) "the installer wrote the server address ($written)"
  # Windows Installer knows the package by its upgrade code: the way the app finds it to uninstall itself, and the entry in Settings > Apps
  # Windows Installer biết gói qua mã nâng cấp: chính cách app tìm gói để tự gỡ, và là mục gỡ trong Settings > Apps
  $installer = New-Object -ComObject WindowsInstaller.Installer
  $products = @($installer.RelatedProducts('{CD80F6D2-E13A-423F-A6E7-0D2FC58C8EAE}'))
  Check ($products.Count -eq 1) "Windows Installer knows AI Worker (the entry in Settings > Apps) ($($products.Count))"

  # run like a real user: the address from the key the installer wrote, the settings in APPDATA\ai-worker
  # chạy như người dùng thật: địa chỉ lấy từ khoá do gói cài ghi, cài đặt ở APPDATA\ai-worker
  $outFile = Join-Path $Tmp 'round.txt'
  [void](Run $exe @('--round', '--out', "`"$outFile`"") 60)
  $first = Get-Content $outFile -Raw -Encoding UTF8
  Check ($first -match '^pair\|0\|Pairing code: \d{4}-\d{4}\|$') "the first round shows a pairing code ($first)"
  Start-Sleep -Seconds 1
  [void](Run $exe @('--round', '--out', "`"$outFile`"") 60)
  $second = Get-Content $outFile -Raw -Encoding UTF8
  Check ($second -match '^long\|2\|2 waiting\|url$') "the second round shows 2 waiting, one past the limit ($second)"
  $sessionFile = Join-Path $env:APPDATA 'ai-worker\menubar-session'
  Check ((Get-Content $sessionFile -Raw) -match '^dpapi:') 'the session file is encrypted with DPAPI'

  # a plain session file from the old PowerShell icon: read, then written back encrypted
  # file phiên chữ thường của bản PowerShell cũ: đọc được rồi ghi lại dạng mã hoá
  $decrypt = "Add-Type -AssemblyName System.Security; `$s = (Get-Content '$sessionFile' -Raw).Trim().Substring(6); [Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String(`$s), `$null, 'CurrentUser'))"
  $token = (& powershell -NoProfile -Command $decrypt).Trim()
  [IO.File]::WriteAllText($sessionFile, $token)
  [void](Run $exe @('--round', '--out', "`"$outFile`"") 60)
  $old = Get-Content $outFile -Raw -Encoding UTF8
  Check ($old -match '^long\|2\|' -and (Get-Content $sessionFile -Raw) -match '^dpapi:') "an old plain session is read and encrypted again ($old)"

  # upgrading from the PowerShell icon: the app stops the old one, removes its Startup shortcut and script, keeps the pairing
  # nâng cấp từ bản PowerShell: app tắt bản cũ, xoá lối tắt Startup và script cũ, giữ phiên ghép
  $shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI Worker menu bar.lnk'
  Set-Content $shortcut 'old'
  Set-Content (Join-Path $env:APPDATA 'ai-worker\ai-worker-tray.ps1') '# old'
  $oldIcon = Start-Process powershell -ArgumentList @('-NoProfile', '-Command', "Start-Sleep 120 # ai-worker-tray.ps1") -PassThru -WindowStyle Hidden
  Start-Sleep -Seconds 2
  Start-Process $exe
  Start-Sleep -Seconds 8
  Check ($oldIcon.HasExited) 'the running PowerShell icon is stopped'
  Check (-not (Test-Path $shortcut)) 'the old Startup shortcut is removed'
  Check (-not (Test-Path (Join-Path $env:APPDATA 'ai-worker\ai-worker-tray.ps1'))) 'the old script is removed'
  Check ((Get-Content $sessionFile -Raw) -match '^dpapi:') 'the pairing is kept'
  Check ((Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue).'AI Worker' -like '*AI Worker.exe*') 'AI Worker.exe starts at login'
  if (-not $oldIcon.HasExited) { Stop-Process -Id $oldIcon.Id -Force }
  # installing a newer build (1.0.1) over the running app, as an update does: done without a reboot (code 0, not 3010) and the old copy has quit
  # cài bản mới (1.0.1) đè lên app đang chạy, như khi cập nhật: xong không đòi khởi động lại (mã 0, không phải 3010) và app cũ đã thoát
  # at most 2 minutes: a hang fails the check instead of running forever
  # tối đa 2 phút: treo thì báo trượt thay vì chạy mãi
  $newer = [IO.File]::ReadAllBytes($NewerMsi)
  [Array]::Copy($filled, 0, $newer, [Text.Encoding]::ASCII.GetString($newer).IndexOf($Placeholder), $filled.Length)
  $newerPackage = Join-Path $Tmp 'AI Worker 1.0.1.msi'
  [IO.File]::WriteAllBytes($newerPackage, $newer)
  $p = @{ ExitCode = (Run msiexec.exe @('/i', "`"$newerPackage`"", '/qn', '/norestart', '/l*v', "`"$Tmp\reinstall.log`"")) }
  if ($p.ExitCode -eq -1) { Get-Process 'AI Worker' -ErrorAction SilentlyContinue | Stop-Process -Force }
  Check ($p.ExitCode -eq 0) "installing over the running app needs no reboot (code $($p.ExitCode))"
  Start-Sleep -Seconds 1
  Check (-not (Get-Process 'AI Worker' -ErrorAction SilentlyContinue)) 'the old copy quit during the install'
  Get-Process 'AI Worker' -ErrorAction SilentlyContinue | Stop-Process -Force

  # each long wait is notified once, also for a name with Vietnamese letters
  # mỗi lần chờ lâu chỉ báo một lần, kể cả tên có dấu
  $env:AI_WORKER_MENUBAR_DIR = Join-Path $Tmp 'notify-test'
  $env:TEST_NAME = 'Ph' + [char]0xF2 + 'ng IT'
  [void](Run $exe @('--test-notify', '--out', "`"$outFile`"") 60)
  $notified = Get-Content $outFile -Raw -Encoding UTF8
  Check ($notified -match '^2\|An,Ph.ng IT$') "three rounds notify each long wait once ($notified)"
  Remove-Item Env:AI_WORKER_MENUBAR_DIR

  # uninstall
  # gỡ
  $p = @{ ExitCode = (Run msiexec.exe @('/x', "`"$newerPackage`"", '/qn', '/norestart')) }
  Check ($p.ExitCode -eq 0 -and -not (Test-Path $exe)) "uninstalling the .msi removes the app (code $($p.ExitCode))"
  Check (-not ((Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue).'AI Worker')) 'after uninstalling it no longer starts at login'
  Check (-not (Test-Path 'HKCU:\Software\Classes\ai-worker-open') -and -not (Test-Path 'HKCU:\Software\Classes\AppUserModelId\AIWorker.MenuBar')) 'after uninstalling the notification registration is gone'
  if ($fail) {
    Write-Host '--- server output'; Get-Content (Join-Path $Tmp 'server.log') -ErrorAction SilentlyContinue
    Write-Host '--- server errors'; Get-Content (Join-Path $Tmp 'server.err') -ErrorAction SilentlyContinue
    Write-Host '--- install log (error lines)'; Select-String -Path "$Tmp\install.log" -Pattern 'error|Return value 3' -ErrorAction SilentlyContinue | Select-Object -First 20 | ForEach-Object { $_.Line }
    Write-Host '--- reinstall.log'; Select-String -Path "$Tmp\reinstall.log" -Pattern 'Action start|Action ended|Return value|WixClose|FilesInUse|reboot' -ErrorAction SilentlyContinue | Select-Object -Last 60 | ForEach-Object { $_.Line }
  }
  exit $fail
} finally {
  Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
