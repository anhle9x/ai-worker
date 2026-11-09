# Install the helper AI assistants for Claude on Windows (called by INSTALL-Windows.bat, after the plugin is installed):
# Cài nhân viên AI phụ cho Claude trên Windows (INSTALL-Windows.bat gọi, sau khi cài plugin):
#   ChatGPT via Codex CLI (default), Gemma via Ollama (size by computer), Gemini via Antigravity CLI (optional).
#   ChatGPT qua Codex CLI (mặc định), Gemma qua Ollama (cỡ theo máy), Gemini qua Antigravity CLI (tuỳ chọn).
# Only official installers: chatgpt.com/codex, ollama.com, antigravity.google.
# Chỉ dùng bộ cài chính thức: chatgpt.com/codex, ollama.com, antigravity.google.
# When one part fails, report it and go on; do not stop the whole installer.
# Một phần hỏng thì báo rồi đi tiếp, không dừng cả file cài.
$ErrorActionPreference = 'Continue'
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
$dataDir = Join-Path $env:USERPROFILE '.local\share\ai-worker'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

function Ask-Yes([string]$question) {
  $hint = (
    Say-Text -AsString "(Enter = yes, type n = no)" "(Enter = có, gõ n = không)")
  $reply = (Ask "$question $hint")
  return ($reply.Trim().ToLower() -ne 'n')
}
function Find([string]$name, [string[]]$folders) {
  $c = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { return $c.Source }
  foreach ($d in $folders) {
    foreach ($ext in @('.exe', '.cmd')) { $p = Join-Path $d "$name$ext"; if (Test-Path $p) { return $p } }
  }
  return ''
}
# Run the official installer in a separate PowerShell: an exit command in the installer does not close this file
# Chạy bộ cài chính thức trong một PowerShell riêng: lệnh exit trong bộ cài không đóng file này
function Run-Installer([string]$url) {
  $tmpFile = Join-Path $env:TEMP ("ai-worker-" + [IO.Path]::GetRandomFileName() + '.ps1')
  try {
    Invoke-WebRequest -UseBasicParsing $url -OutFile $tmpFile
    & powershell -NoProfile -ExecutionPolicy Bypass -File $tmpFile
  } catch {
    Say-Text "Error while downloading or running ${url} : $_" "Lỗi khi tải hoặc chạy ${url} : $_"
  }
  Remove-Item $tmpFile -ErrorAction SilentlyContinue
}
# The installer just added a folder to the user's PATH: read it again so it shows up in this window right away
# Bộ cài vừa thêm thư mục vào PATH của người dùng: đọc lại để thấy ngay trong cửa sổ này
function Reload-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

Write-Host ''
Say-Text '== Helper AI assistants for Claude ==' '== Nhân viên AI phụ cho Claude =='

# ---- ChatGPT (Codex CLI): installed by default ----
# ---- ChatGPT (Codex CLI): mặc định cài ----
$codexDirs = @((Join-Path $env:LOCALAPPDATA 'Programs\OpenAI\Codex\bin'), (Join-Path $env:APPDATA 'npm'))
$codex = Find 'codex' $codexDirs
if (-not $codex) {
  Say-Text 'Installing Codex CLI (ChatGPT, the official OpenAI installer)...' 'Cài Codex CLI (ChatGPT, bộ cài chính thức của OpenAI)...'
  Run-Installer 'https://chatgpt.com/codex/install.ps1'
  Reload-Path
  $codex = Find 'codex' $codexDirs
}
if ($codex) {
  & $codex login status *> $null
  if ($LASTEXITCODE -eq 0) {
    Say-Text 'ChatGPT (Codex): installed and signed in.' 'ChatGPT (Codex): đã cài, đã đăng nhập.'
  } else {
    Say-Text 'ChatGPT (Codex): needs sign-in with the company ChatGPT account (ask your IT team if you do not have one).' 'ChatGPT (Codex): cần đăng nhập bằng tài khoản ChatGPT của công ty (hỏi phòng IT nếu chưa có).'
    $qLogin = (
      Say-Text -AsString 'Open the browser to sign in now?' 'Mở trình duyệt để đăng nhập ngay?')
    if (Ask-Yes $qLogin) {
      & $codex login
      if ($LASTEXITCODE -ne 0) {
        Say-Text 'Codex sign-in not finished. Later, open PowerShell and type: codex login' 'Đăng nhập Codex chưa xong. Sau này mở PowerShell gõ: codex login'
      }
    } else {
      Say-Text 'Later: open PowerShell and type  codex login' 'Để sau: mở PowerShell gõ  codex login'
    }
  }
} else {
  Say-Text 'ChatGPT (Codex): could not install, skipped. Take a screenshot and send it to your IT team.' 'ChatGPT (Codex): cài chưa được, bỏ qua. Chụp màn hình gửi phòng IT.'
}

# ---- Gemma (Ollama): size by RAM, downloaded in the background ----
# ---- Gemma (Ollama): cỡ theo RAM, tải ngầm ----
$ramGb = 0; $slow = ''
try { $ramGb = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch { }
$noGpu = (
  Say-Text -AsString 'no dedicated graphics card' 'không có card đồ hoạ rời')
try {
  # Without a dedicated NVIDIA / AMD Radeon card Ollama runs on the CPU: go down one size
  # Không có card rời NVIDIA / AMD Radeon thì Ollama chạy bằng CPU: hạ một cỡ
  $card = (Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join ' '
  if ($card -notmatch 'NVIDIA|Radeon RX|Radeon Pro') { $slow = $noGpu }
} catch { $slow = $noGpu }
$freeGb = 0
try { $freeGb = [math]::Floor((Get-PSDrive ($env:USERPROFILE.Substring(0, 1))).Free / 1GB) } catch { }
$tier = 0
if ($ramGb -ge 8) { $tier = 1 }
if ($ramGb -ge 16) { $tier = 2 }
if ($ramGb -ge 32) { $tier = 3 }
if ($slow -and $tier -gt 0) { $tier-- }
$gemmaVariants = @{ 3 = @('gemma4:26b', 17, 25); 2 = @('gemma4:e4b', 7, 14); 1 = @('gemma4:e2b', 5, 12) }
$ramTier = $tier
# If the disk has no room for the size that fits the RAM, go down until one fits
# Ổ không đủ chỗ cho bản hợp RAM thì hạ dần tới bản vừa
while ($tier -gt 0 -and $freeGb -lt $gemmaVariants[$tier][2]) { $tier-- }
$gemma = $gemmaVariants[$tier]
$desc = (
  Say-Text -AsString "This computer has $ramGb GB RAM and $freeGb GB free disk space" "Máy có $ramGb GB RAM, ổ còn trống $freeGb GB") + $(if ($slow) { ", $slow" } else { '' })
$api = 'http://127.0.0.1:11434'
function Ollama-Alive { try { Invoke-RestMethod "$api/api/tags" -TimeoutSec 2 | Out-Null; return $true } catch { return $false } }
if ($gemma) {
  $qGemma = (
    Say-Text -AsString "Gemma (runs on this computer, data stays here): $desc -> install version $($gemma[0]) (about $($gemma[1]) GB, downloaded in the background). OK?" "Gemma (chạy ngay trên máy, dữ liệu không ra ngoài): $desc -> cài bản $($gemma[0]) (khoảng $($gemma[1]) GB, tải ngầm). Đồng ý?")
}
if (-not $gemma -and $ramTier -eq 0) {
  Say-Text "Gemma: not installed ($desc; needs at least 8 GB RAM)." "Gemma: không cài ($desc; cần ít nhất 8 GB RAM)."
} elseif (-not $gemma) {
  Say-Text "Gemma: not installed ($desc; needs at least 12 GB free)." "Gemma: không cài ($desc; cần trống ít nhất 12 GB)."
} elseif (Ask-Yes $qGemma) {
  $ollama = Find 'ollama' @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama'))
  if (-not $ollama) {
    Say-Text 'Installing Ollama (the official installer)...' 'Cài Ollama (bộ cài chính thức)...'
    Run-Installer 'https://ollama.com/install.ps1'
    Reload-Path
    $ollama = Find 'ollama' @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama'))
  }
  if ($ollama -and -not (Ollama-Alive)) { Start-Process -WindowStyle Hidden $ollama 'serve' }
  for ($i = 0; $i -lt 30 -and -not (Ollama-Alive); $i++) { Start-Sleep -Seconds 2 }
  if (Ollama-Alive) {
    $have = (Invoke-RestMethod "$api/api/tags").models | Where-Object { $_.name -eq $gemma[0] }
    if ($have) {
      Say-Text "Gemma: $($gemma[0]) is already there." "Gemma: đã có sẵn $($gemma[0])."
    } else {
      # Download with a separate curl.exe: closing this window does not stop the download
      # Tải bằng curl.exe chạy riêng: đóng cửa sổ này không dừng việc tải
      $bodyFile = Join-Path $dataDir 'gemma-download.json'
      [IO.File]::WriteAllText($bodyFile, "{`"model`":`"$($gemma[0])`"}", (New-Object Text.UTF8Encoding $false))
      Start-Process -WindowStyle Hidden 'curl.exe' @('-s', "$api/api/pull", '-d', "@$bodyFile", '-o', (Join-Path $dataDir 'gemma-download.log'))
      Say-Text "Gemma: downloading $($gemma[0]) in the background (about $($gemma[1]) GB). When it finishes, reopen Claude and the Gemma desk appears." "Gemma: đang tải ngầm $($gemma[0]) (khoảng $($gemma[1]) GB). Tải xong, mở lại Claude là bàn Gemma hiện."
    }
  } else {
    Say-Text 'Gemma: Ollama could not start, so the model was not downloaded. Take a screenshot and send it to your IT team.' 'Gemma: Ollama chưa chạy được, chưa tải mô hình. Chụp màn hình gửi phòng IT.'
  }
} else {
  Say-Text 'Gemma: skipped.' 'Gemma: bỏ qua.'
}

# ---- Gemini (Antigravity CLI): optional, personal Google account ----
# ---- Gemini (Antigravity CLI): tuỳ chọn, tài khoản Google cá nhân ----
$agyDirs = @((Join-Path $env:USERPROFILE '.local\bin'), (Join-Path $env:LOCALAPPDATA 'Programs\Antigravity\bin'))
if (Find 'agy' $agyDirs) {
  Say-Text 'Gemini: installed (Antigravity CLI).' 'Gemini: đã cài (Antigravity CLI).'
} else {
  $qGemini = (
    Say-Text -AsString 'Also install Gemini? Free, sign in with your own Google account, used only for web research. (type y = yes, Enter = no)' 'Cài thêm Gemini? Miễn phí, đăng nhập bằng tài khoản Google của bạn, chỉ dùng tra cứu web. (gõ y = có, Enter = không)')
  $reply = (Ask $qGemini)
  if ($reply.Trim().ToLower() -eq 'y') {
    Run-Installer 'https://antigravity.google/cli/install.ps1'
    Reload-Path
    if (Find 'agy' $agyDirs) {
      Say-Text 'Gemini: installed. First time: open PowerShell, type  agy  and sign in with your Google account, then press Ctrl+C to leave.' 'Gemini: đã cài. Lần đầu: mở PowerShell, gõ  agy  rồi đăng nhập tài khoản Google, xong nhấn Ctrl+C để thoát.'
    } else {
      Say-Text 'Gemini: could not install, skipped.' 'Gemini: cài chưa được, bỏ qua.'
    }
  } else {
    Say-Text 'Gemini: not installed (the Gemini desk will be hidden).' 'Gemini: không cài (bàn Gemini sẽ ẩn).'
  }
}
Say-Text 'The helper AI assistants appear in the office after you reopen Claude.' 'Nhân viên AI phụ hiện lên văn phòng sau khi mở lại Claude.'
exit 0
