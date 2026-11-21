# The first half of "Finish AI Worker setup" (setup.cmd calls it): unpack the package the .msi carries into a work folder and make it a company package.
# Nửa đầu của "Finish AI Worker setup" (setup.cmd gọi): giải nén gói mà .msi mang vào một thư mục làm việc và biến nó thành gói công ty.
# The company settings come from HKCU\Software\AI Worker Plugin\Company (base64 text the server wrote into the .msi), else from the plugin folder
# Thiết lập công ty lấy từ HKCU\Software\AI Worker Plugin\Company (chữ base64 máy chủ ghi vào .msi), không có thì lấy từ thư mục plugin
# already installed; with neither it stays a personal package. A plugin folder newer than the package (/update) is kept, never downgraded.
# đã cài; không có cả hai thì vẫn là gói cá nhân. Thư mục plugin mới hơn gói (/update) được giữ, không bao giờ hạ bản.
param([Parameter(Mandatory = $true)][string]$Zip, [Parameter(Mandatory = $true)][string]$Work)
$ErrorActionPreference = 'Stop'
$lang = $env:AI_WORKER_LANG
if (-not $lang) { $lang = [System.Globalization.CultureInfo]::CurrentCulture.TwoLetterISOLanguageName }
function Say([string]$en, [string]$vi) { if ($lang -like 'vi*') { Write-Host $vi } else { Write-Host $en } }
$placeholderStart = 'AIWORKER-COMPANY-'

try {
  # unpack: the zip holds one folder, AI-Worker, with INSTALL-Windows.bat and setup\
  # giải nén: zip có một thư mục AI-Worker, trong đó là INSTALL-Windows.bat và setup\
  if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Work)
  $setup = Join-Path $Work 'AI-Worker\setup'
  $plugin = Join-Path $setup 'ai-worker'
  if (-not (Test-Path (Join-Path $plugin '.claude-plugin\plugin.json'))) { throw 'the package has no plugin' }

  # the company settings written by the server, when this .msi is a company one
  # thiết lập công ty do máy chủ ghi, khi .msi này là bản của công ty
  $company = $null; $signers = ''
  $raw = (Get-ItemProperty -Path 'HKCU:\Software\AI Worker Plugin' -Name Company -ErrorAction SilentlyContinue).Company
  if ($raw) { $raw = $raw.Trim() }
  if ($raw -and -not $raw.StartsWith($placeholderStart)) {
    $payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($raw)) | ConvertFrom-Json
    if ($payload.company.sharing.webhook -notmatch '^https?://[A-Za-z0-9.:\[\]-]+$') { throw 'the company settings in this installer are not valid' }
    $company = $payload.company | ConvertTo-Json -Depth 10 -Compress
    $signers = [string]$payload.signers
  }

  # a plugin folder already newer than the package (updated with /update): set up that one instead of the older copy
  # thư mục plugin đã mới hơn gói (cập nhật bằng /update): cài lại chính bản đó thay cho bản cũ hơn
  $live = Join-Path $env:USERPROFILE 'claude-plugins-ai-worker\ai-worker'
  $liveManifest = Join-Path $live '.claude-plugin\plugin.json'
  if (Test-Path $liveManifest) {
    $mine = [version](Get-Content -Raw (Join-Path $plugin '.claude-plugin\plugin.json') | ConvertFrom-Json).version
    $theirs = $null
    try { $theirs = [version](Get-Content -Raw $liveManifest | ConvertFrom-Json).version } catch { $theirs = $null }
    if ($theirs -and $theirs -gt $mine) {
      Remove-Item -Recurse -Force $plugin
      Copy-Item -Recurse -Force $live $plugin
      Say "The plugin on this computer ($theirs) is newer than this installer ($mine): keeping it." "Plugin trên máy ($theirs) mới hơn bản trong file cài ($mine): giữ bản trên máy." # i18n-allow
    }
  }

  # no company settings in the .msi (a re-run after they were used): keep the ones of the installed plugin
  # .msi không có thiết lập công ty (chạy lại sau khi đã dùng): giữ thiết lập của plugin đã cài
  $liveCompany = Join-Path $live 'web\company.json'
  if (-not $company -and (Test-Path $liveCompany)) {
    $company = [IO.File]::ReadAllText($liveCompany)
    $liveSigners = Join-Path $live 'keys\allowed_signers'
    if (Test-Path $liveSigners) { $signers = [IO.File]::ReadAllText($liveSigners) }
  }
  if ($company) {
    $utf8 = New-Object Text.UTF8Encoding $false
    [IO.File]::WriteAllText((Join-Path $plugin 'web\company.json'), $company, $utf8)
    if ($signers -match '(?m)^\s*ai-worker\s+ssh-') { [IO.File]::WriteAllText((Join-Path $plugin 'keys\allowed_signers'), $signers, $utf8) }
    # INSTALL-Windows.bat asks the full name when this file is there, like the company zip
    # INSTALL-Windows.bat hỏi họ tên khi có file này, giống gói zip công ty
    [IO.File]::WriteAllText((Join-Path $setup 'ASK-NAME'), "Company package: the company dashboard is on.`r`n", $utf8)
  }
  exit 0
} catch {
  Say "Could not prepare the setup: $($_.Exception.Message). Take a screenshot of this window and send it to your admin." "Không chuẩn bị được bước cài: $($_.Exception.Message). Chụp màn hình cửa sổ này gửi người quản trị." # i18n-allow
  exit 1
}
