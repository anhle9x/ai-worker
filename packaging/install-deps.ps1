# Install the libraries the coding and testing skills need (Windows). Anything missing is reported at the end; it does not break the plugin install.
# Cài các thư viện mà skill viết code và kiểm thử cần (Windows). Thiếu gì thì báo ở cuối, không làm hỏng việc cài plugin.
param([string]$Plugin, [string]$Claude)
$ErrorActionPreference = 'Continue'
$langFile = Join-Path $PSScriptRoot 'lang.ps1'
if (-not (Test-Path $langFile)) { Write-Host 'lang.ps1 is missing next to install-deps.ps1. / Thiếu lang.ps1 cạnh install-deps.ps1.'; exit 1 } # i18n-allow
. $langFile
$missing = @()
# Reviewed commits: do not take the latest, because this is third-party code that runs on staff computers
# Commit đã rà: không lấy bản mới nhất, vì đây là mã của bên thứ ba chạy trên máy nhân viên
$videoCommit = '43bd349a136651865ecfa6ea1cf012f6e957d304'
$stageshowCommit = '299140fafd08df55a9c234e610c3f64af3f45531'
$ynPrompt = (
  Say-Text -AsString '(type y = yes, Enter = no)' '(gõ y = có, Enter = không)')
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + "$env:USERPROFILE\.local\bin" }
function Has($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Node-Ok {
  if (-not ((Has node) -and (Has npm))) { return $false }
  # stageshow and chrome-devtools-mcp need Node 20.19 or newer
  # stageshow và chrome-devtools-mcp cần Node từ 20.19
  node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>20||(a===20&&b>=19)?0:1)"
  return $LASTEXITCODE -eq 0
}
function Install-Package($package) {
  if (-not (Has winget)) { return $false }
  winget install -e --id $package --silent --accept-package-agreements --accept-source-agreements | Out-Null
  Refresh-Path
  return $true
}
Write-Host ''
Say-Text '== Libraries for the coding and testing skills ==' '== Thư viện cho các skill viết code và kiểm thử =='
if (-not (Node-Ok)) {
  Say-Text 'Installing Node.js ...' 'Cài Node.js ...'
  $null = Install-Package 'OpenJS.NodeJS.LTS'
  if (-not (Node-Ok)) {
    $missing += (
      Say-Text -AsString 'Node.js: download it from https://nodejs.org, then run the installer again' 'Node.js: tải tại https://nodejs.org rồi chạy lại file cài')
  }
}
$hasPy = $false
foreach ($p in @('python', 'py')) { if (Has $p) { & $p --version *> $null; if ($LASTEXITCODE -eq 0) { $hasPy = $true } } }
if (-not $hasPy) {
  Say-Text 'Installing Python ...' 'Cài Python ...'
  $null = Install-Package 'Python.Python.3.12'
  foreach ($p in @('python', 'py')) { if (Has $p) { & $p --version *> $null; if ($LASTEXITCODE -eq 0) { $hasPy = $true } } }
  if (-not $hasPy) {
    $missing += (
      Say-Text -AsString 'Python 3 (for ui-ux-pro-max): download it from https://www.python.org' 'Python 3 (cho ui-ux-pro-max): tải tại https://www.python.org')
  }
}
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
if (-not ($chrome | Where-Object { Test-Path $_ })) {
  Say-Text 'Installing Google Chrome ...' 'Cài Google Chrome ...'
  $null = Install-Package 'Google.Chrome'
  if (-not ($chrome | Where-Object { Test-Path $_ })) {
    $missing += (
      Say-Text -AsString 'Google Chrome (for the web testing skill): download it from https://www.google.com/chrome' 'Google Chrome (cho skill kiểm thử web): tải tại https://www.google.com/chrome')
  }
}
if ($Claude -and (Has npx)) {
  Say-Text 'Registering the browser control tools for the testing skills ...' 'Đăng ký công cụ điều khiển trình duyệt cho skill kiểm thử ...'
  # Pinned to the versions tried (2026-11-04): @latest can change how it runs without notice
  # Ghim đúng bản đã thử (04/11/2026): @latest có thể đổi cách chạy mà không báo
  foreach ($name in @('playwright', 'chrome-devtools')) { & cmd /d /c "`"$Claude`" mcp remove --scope user $name" *> $null }
  & cmd /d /c "`"$Claude`" mcp add --scope user playwright -- cmd /c npx -y @playwright/mcp@0.0.84 --browser chrome" *> $null
  & cmd /d /c "`"$Claude`" mcp add --scope user chrome-devtools -- cmd /c npx -y chrome-devtools-mcp@1.12.0" *> $null
}
Write-Host ''
Say-Text 'Also install stageshow to build sample UI images and animations? It is downloaded from benjitaylor/skills and needs Node.' 'Cài thêm stageshow để dựng ảnh và hoạt cảnh giao diện mẫu? Tải từ benjitaylor/skills, cần Node.'
Say-Text 'Note: the source code is MIT, but the app icons and logos that come with it belong to their owners; see NOTICE.md.' 'Lưu ý: mã nguồn MIT, nhưng biểu tượng ứng dụng và logo kèm theo thuộc chủ của chúng; xem NOTICE.md.'
$reply = $env:AI_WORKER_WITH_STAGESHOW
if (-not $reply) { $reply = Read-Host $ynPrompt }
if ($reply -eq 'y' -or $reply -eq 'Y') {
  $d = "$env:USERPROFILE\.claude\skills\stageshow"
  if (Test-Path $d) {
    Say-Text "$d already exists, left as it is." "Đã có $d, giữ nguyên."
  } else {
    $t = Join-Path $env:TEMP ("s" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $t, $d | Out-Null
    curl.exe -fsSL -m 300 "https://codeload.github.com/benjitaylor/skills/tar.gz/$stageshowCommit" -o "$t\s.tgz"
    if ($LASTEXITCODE -eq 0) { tar.exe -xzf "$t\s.tgz" -C "$d" --strip-components=2 "skills-$stageshowCommit/stageshow" }
    if ($LASTEXITCODE -eq 0) {
      Say-Text "Installed stageshow into $d" "Đã cài stageshow vào $d"
      if (Has npm) {
        Push-Location $d
        npm ci --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0) {
          $missing += (
            Say-Text -AsString "stageshow: go to $d and run  npm ci" "stageshow: vào $d chạy  npm ci")
        }
        Pop-Location
      } else {
        $missing += (
          Say-Text -AsString "stageshow: needs Node, then go to $d and run  npm ci" "stageshow: cần Node rồi vào $d chạy  npm ci")
      }
    } else {
      Remove-Item -Recurse -Force $d
      $missing += (
        Say-Text -AsString 'stageshow: could not be downloaded, run the installer again when you have internet' 'stageshow: tải không được, chạy lại file cài khi có mạng')
    }
    Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue
  }
}

Write-Host ''
Say-Text 'Also install video-shotcraft to make product videos? The download takes about 70 MB.' 'Cài thêm video-shotcraft để làm video sản phẩm? Tải và chiếm khoảng 70 MB.'
Say-Text 'Note: the Remotion video tool has its own license and your company may have to pay; some audio files' 'Lưu ý: công cụ dựng Remotion có giấy phép riêng, công ty có thể phải trả phí; một số file âm thanh'
Say-Text 'have an unclear source. Ask your admin before using it for company videos.' 'chưa rõ nguồn. Hỏi người quản trị trước khi dùng cho video của công ty.'
$reply = $env:AI_WORKER_WITH_VIDEO
if (-not $reply) { $reply = Read-Host $ynPrompt }
if ($reply -eq 'y' -or $reply -eq 'Y') {
  $d = "$env:USERPROFILE\.claude\skills\video-shotcraft"
  if (Test-Path $d) {
    Say-Text "$d already exists, left as it is." "Đã có $d, giữ nguyên."
  } else {
    $t = Join-Path $env:TEMP ("v" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $t, $d | Out-Null
    curl.exe -fsSL -m 600 "https://codeload.github.com/Vincentwei1021/video-shotcraft/tar.gz/$videoCommit" -o "$t\v.tgz"
    if ($LASTEXITCODE -eq 0) { tar.exe -xzf "$t\v.tgz" -C "$d" --strip-components=1 }
    if ($LASTEXITCODE -eq 0) {
      Say-Text "Installed video-shotcraft into $d" "Đã cài video-shotcraft vào $d"
    } else {
      Remove-Item -Recurse -Force $d
      $missing += (
        Say-Text -AsString 'video-shotcraft: could not be downloaded, run the installer again when you have internet' 'video-shotcraft: tải không được, chạy lại file cài khi có mạng')
    }
    Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue
  }
  if (-not (Has ffmpeg)) {
    Say-Text 'Installing ffmpeg ...' 'Cài ffmpeg ...'
    $null = Install-Package 'Gyan.FFmpeg'
    if (-not (Has ffmpeg)) {
      $missing += (
        Say-Text -AsString 'ffmpeg (for video-shotcraft): download it from https://ffmpeg.org/download.html' 'ffmpeg (cho video-shotcraft): tải tại https://ffmpeg.org/download.html')
    }
  }
}
Write-Host ''
if ($missing.Count -eq 0) {
  Say-Text 'All libraries are in place.' 'Đã đủ thư viện.'
} else {
  Say-Text 'Still missing, so the related skills cannot run yet:' 'Còn thiếu, các skill liên quan chưa chạy được:'
  $missing | ForEach-Object { Write-Host "  - $_" }
}
exit 0
