# Build AI Worker plugin.msi on Windows (GitHub Actions, job windows-app): stage the files, then run WiX 5.
# Dựng AI Worker plugin.msi trên Windows (GitHub Actions, job windows-app): xếp file vào chỗ, rồi chạy WiX 5.
# Run: pwsh packaging/windows-msi/build-msi.ps1 -Package <AI-Worker-x.y.z.zip from packaging/build.sh, the normal one> -Version x.y.z -Out <file.msi>
# Chạy: pwsh packaging/windows-msi/build-msi.ps1 -Package <AI-Worker-x.y.z.zip do packaging/build.sh dựng, bản thường> -Version x.y.z -Out <file.msi>
# Needs: dotnet tool wix 5.0.2 with WixToolset.UI.wixext and WixToolset.Util.wixext. The package must hold no company settings: the server fills them.
# Cần: dotnet tool wix 5.0.2 với WixToolset.UI.wixext và WixToolset.Util.wixext. Gói không được có thiết lập công ty: máy chủ điền sau.
param([Parameter(Mandatory = $true)][string]$Package, [Parameter(Mandatory = $true)][string]$Version, [Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$Out = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Out)
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
# The placeholder the server replaces (server/board/packages.py PLUGIN_MSI_PLACEHOLDER builds the same text): 2048 characters
# Chuỗi giữ chỗ máy chủ thay (server/board/packages.py PLUGIN_MSI_PLACEHOLDER dựng đúng chữ này): 2048 ký tự
$placeholder = 'AIWORKER-COMPANY-' + ('0' * 2031)

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $Package))
try {
  $names = $zip.Entries | ForEach-Object { $_.FullName }
  if ($names -contains 'AI-Worker/setup/ai-worker/web/company.json' -or $names -contains 'AI-Worker/setup/ASK-NAME') { throw "$Package is a company package: build the normal one (bash packaging/build.sh)" }
  if ($names -notcontains 'AI-Worker/INSTALL-Windows.bat') { throw "$Package has no AI-Worker/INSTALL-Windows.bat" }
} finally { $zip.Dispose() }

$stage = Join-Path ([IO.Path]::GetTempPath()) ('ai-worker-plugin-msi-' + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
  Copy-Item (Resolve-Path $Package) (Join-Path $stage 'AI-Worker.zip')
  # Windows files: CRLF line ends; PowerShell 5 reads Vietnamese in a .ps1 correctly only with a UTF-8 BOM
  # File cho Windows: xuống dòng CRLF; PowerShell 5 chỉ đọc đúng tiếng Việt trong .ps1 khi có BOM UTF-8
  foreach ($name in 'setup.cmd', 'uninstall.cmd', 'prepare.ps1') {
    $text = [IO.File]::ReadAllText((Join-Path $here $name)) -replace "`r?`n", "`r`n"
    [IO.File]::WriteAllText((Join-Path $stage $name), $text, (New-Object Text.UTF8Encoding ($name -like '*.ps1')))
  }
  $menubar = Join-Path $here '..\..\server\menubar\windows-app'
  Push-Location $here
  try {
    & wix build AIWorkerPlugin.wxs -d "Version=$Version" -d "StageDir=$stage" -d "MenubarDir=$menubar" -d "CompanyPlaceholder=$placeholder" `
      -ext WixToolset.UI.wixext -ext WixToolset.Util.wixext -o $Out
    if ($LASTEXITCODE -ne 0) { throw "wix build failed ($LASTEXITCODE)" }
  } finally { Pop-Location }
} finally { Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue }

# The server fills the placeholder in place, so it must sit in the file in one piece, exactly once
# Máy chủ điền chuỗi giữ chỗ ngay trong file, nên nó phải nằm liền một khúc, đúng một lần
$bytes = [IO.File]::ReadAllBytes((Resolve-Path $Out))
$text = [Text.Encoding]::GetEncoding(28591).GetString($bytes)
$count = ([regex]::Matches($text, [regex]::Escape($placeholder))).Count
if ($count -ne 1) { throw "The .msi holds the placeholder $count times, not exactly once" }
Write-Host "Built $Out ($($bytes.Length) bytes, version $Version)"
