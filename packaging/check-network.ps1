# Check whether this computer can reach the company server. It sends no code or numbers; a failure does not break the install.
# Thử xem máy này có tới được máy chủ công ty không. Không gửi mã hay số liệu gì; lỗi cũng không làm hỏng việc cài.
$ErrorActionPreference = 'Stop'
try {
  $langFile = Join-Path $PSScriptRoot 'lang.ps1'
  if (-not (Test-Path $langFile)) { Write-Host 'lang.ps1 is missing next to check-network.ps1. / Thiếu lang.ps1 cạnh check-network.ps1.'; exit 1 } # i18n-allow
  . $langFile
  $f = Join-Path $PSScriptRoot 'ai-worker\web\company.json'
  if (-not (Test-Path $f)) { exit 0 }
  $url = (Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json).sharing.webhook
  if (-not $url) { exit 0 }
  $code = 0
  try {
    $code = (Invoke-WebRequest -Uri ($url.TrimEnd('/') + '/ingest') -Method Post -TimeoutSec 10 -UseBasicParsing).StatusCode
  } catch {
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
  }
  if ($code -eq 401) {
    Say-Text 'Connection test done: this computer can reach the company server.' 'Đã thử kết nối: máy này tới được máy chủ công ty.'
  } elseif ($code -eq 403) {
    Write-Host ''
    Say-Text 'NOTE: the server is blocking this network, so this computer''s numbers are NOT reaching the company dashboard yet. Take a screenshot of this line and send it to your IT team.' 'LƯU Ý: máy chủ đang chặn mạng này, số liệu máy này CHƯA lên được bảng tổng. Chụp dòng này gửi phòng IT.'
  } else {
    Write-Host ''
    Say-Text "NOTE: could not reach the company server (code $code). If it keeps happening, take a screenshot of this line and send it to your IT team." "LƯU Ý: chưa tới được máy chủ công ty (mã $code). Nếu kéo dài, chụp dòng này gửi phòng IT."
  }
} catch { exit 0 }
