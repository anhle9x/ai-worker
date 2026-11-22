# Try the scripts that close and reopen the Claude app after /update with Windows PowerShell 5 (GitHub Actions, windows-latest).
# Thử các script đóng rồi mở lại app Claude sau /update bằng Windows PowerShell 5 (GitHub Actions, windows-latest).
# The runner has no Claude app, so the Store app's lookup and the reopening are tried with stand-in data; closing a real app is tried by hand.
# Máy chạy không có app Claude, nên phần nhận diện app Store và việc mở lại được thử bằng dữ liệu giả; đóng một app thật thì thử bằng tay.
# Run: node --experimental-strip-types tests/windows/dump-restart-scripts.mjs <folder>, then powershell -File tests/windows/test-restart.ps1 -Scripts <folder>
# Chạy: node --experimental-strip-types tests/windows/dump-restart-scripts.mjs <thư mục>, rồi powershell -File tests/windows/test-restart.ps1 -Scripts <thư mục>
param([Parameter(Mandatory = $true)][string]$Scripts)
$ErrorActionPreference = 'Stop'
$errors = 0
function Check([string]$name, [bool]$ok) {
  if ($ok) { Write-Host "ok   $name" } else { Write-Host "FAIL $name"; $script:errors++ }
}
function Load([string]$name) { [IO.File]::ReadAllText((Join-Path $Scripts "$name.ps1")) }
# The text of one function in a script, to define it here on its own
# Nội dung một hàm trong script, để định nghĩa riêng nó ở đây
function FunctionText([string]$text, [string]$name) {
  $ast = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$null, [ref]$null)
  $f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
  if (-not $f) { throw "no function $name" }
  return $f.Extent.Text
}

$find = Load 'WINDOWS_FIND_SCRIPT'
$helper = Load 'WINDOWS_HELPER'
$restart = Load 'WINDOWS_RESTART_SCRIPT'
$claude = Load 'WINDOWS_CLAUDE_SCRIPT'

# Each script parses in this PowerShell
# Mỗi script phân tích cú pháp được trong PowerShell này
foreach ($pair in @(@('find', $find), @('helper', $helper), @('restart', $restart), @('Claude Code lookup', $claude))) {
  $parseErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseInput($pair[1], [ref]$null, [ref]$parseErrors)
  Check "the $($pair[0]) script parses in PowerShell $($PSVersionTable.PSVersion)" ($parseErrors.Count -eq 0)
}

# Outside the Claude app the find script prints nothing and does not fail, the way the plugin runs it
# Ở ngoài app Claude, script tìm app không in gì và không lỗi, chạy đúng cách plugin chạy nó
$env:AIW_SCRIPT = $find
$out = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command 'Invoke-Expression $env:AIW_SCRIPT'
Check 'outside the app the find script prints nothing and exits 0' (($LASTEXITCODE -eq 0) -and -not "$out")
Remove-Item Env:AIW_SCRIPT
$env:AIW_SCRIPT = $claude
$out = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command 'Invoke-Expression $env:AIW_SCRIPT'
Check 'outside Claude Code the lookup prints nothing and exits 0' (($LASTEXITCODE -eq 0) -and -not "$out")
Remove-Item Env:AIW_SCRIPT

# The Store app: which program and which package give an entry to open it again
# App Store: chương trình nào và gói nào cho ra mục để mở lại nó
. ([scriptblock]::Create((FunctionText $find 'StoreLauncher')))
$root = 'C:\Program Files\WindowsApps\Claude_6.28899.6.0_x64__pzs8sxrjxfjjc'
$exe = "$root\app\Claude.exe"
$entry = 'shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude'
# A package as Get-AppxPackage lists it on a real machine, with one property changed
# Một gói như Get-AppxPackage liệt kê trên máy thật, đổi một thuộc tính
function Pkg([hashtable]$change) {
  $p = [pscustomobject]@{
    PackageFamilyName = 'Claude_pzs8sxrjxfjjc'; SignatureKind = 'Developer'; IsDevelopmentMode = $false; InstallLocation = $root
    Apps = @([pscustomobject]@{ Id = 'SshProxy'; Executable = 'app\resources\claude-ssh-proxy.exe' }, [pscustomobject]@{ Id = 'Claude'; Executable = 'app\Claude.exe' })
  }
  foreach ($k in $change.Keys) { $p.$k = $change[$k] }
  return $p
}
Check 'the package signed by its publisher gives its own entry' ((StoreLauncher $exe $true @(Pkg @{})) -eq $entry)
Check 'a package from the Store gives its own entry' ((StoreLauncher $exe $true @(Pkg @{ SignatureKind = 'Store' })) -eq $entry)
Check 'the path decides when Windows cannot list the packages' ((StoreLauncher $exe $false @()) -eq $entry)
Check 'the program letters may differ in case' ((StoreLauncher $exe.ToLower() $true @(Pkg @{})) -eq $entry)
Check 'no package listed: refused' ($null -eq (StoreLauncher $exe $true @()))
Check 'a folder registered in developer mode: refused' ($null -eq (StoreLauncher $exe $true @(Pkg @{ IsDevelopmentMode = $true })))
Check 'an unsigned package: refused' ($null -eq (StoreLauncher $exe $true @(Pkg @{ SignatureKind = 'None' })))
Check 'another package family: refused' ($null -eq (StoreLauncher $exe $true @(Pkg @{ PackageFamilyName = 'Claude_aaaaaaaaaaaaa' })))
Check 'a program outside the package folder: refused' ($null -eq (StoreLauncher $exe $true @(Pkg @{ InstallLocation = 'C:\Program Files\WindowsApps\Claude_6.0.0.0_x64__pzs8sxrjxfjjc' })))
Check 'an app id with other characters: refused' ($null -eq (StoreLauncher $exe $true @(Pkg @{ Apps = @([pscustomobject]@{ Id = 'Claude & calc'; Executable = 'app\Claude.exe' }) })))
Check 'another publisher: refused' ($null -eq (StoreLauncher 'C:\Program Files\WindowsApps\Claude_1.0.0.0_x64__aaaaaaaaaaaaa\app\Claude.exe' $false @()))
Check 'a helper program of the package: refused' ($null -eq (StoreLauncher "$root\app\resources\claude-ssh-proxy.exe" $false @()))
Check 'the installed app is not the Store one' ($null -eq (StoreLauncher 'C:\Users\an\AppData\Local\AnthropicClaude\app-1.0.0\claude.exe' $false @()))

# Reopening: the Store entry goes through explorer, the installed app's program is started as it is
# Mở lại: mục Store đi qua explorer, chương trình của app cài thường được chạy nguyên như vậy
$script:started = @()
function Start-Process { param($FilePath, $ArgumentList) $script:started += , @([string]$FilePath, [string]$ArgumentList) }
. ([scriptblock]::Create((FunctionText $helper 'Open')))
$stub = 'C:\Users\an\AppData\Local\AnthropicClaude\claude.exe'
Open $entry
Open $stub
Check 'the Store app opens through explorer with its entry' (($started[0][0] -eq 'explorer.exe') -and ($started[0][1] -eq $entry))
Check 'the installed app opens with its own program' (($started[1][0] -eq $stub) -and -not $started[1][1])

if ($errors) { Write-Host "$errors failed"; exit 1 }
Write-Host 'all passed'
