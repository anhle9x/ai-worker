# Installs the AI Worker icon next to the clock: copies the script, words and logo, starts it at login and now.
# Cài biểu tượng AI Worker cạnh đồng hồ: chép script, chữ và logo, cho chạy khi đăng nhập và chạy ngay.
# The server writes its own address into $BoardUrl when it hands out this file.
# Máy chủ ghi địa chỉ của chính nó vào $BoardUrl khi phát file này.
$ErrorActionPreference = 'Stop'
$BoardUrl = '__BOARD_URL__'
$Here = $PSScriptRoot
$Dir = Join-Path $env:APPDATA 'ai-worker'
$Startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI Worker menu bar.lnk'

# Language of the messages: AI_WORKER_LANG (en or vi), else the Windows language, else English
# Ngôn ngữ lời nhắn: AI_WORKER_LANG (en hoặc vi), không có thì ngôn ngữ của Windows, không có nữa thì tiếng Anh
$lang = if ($env:AI_WORKER_LANG) { [string]$env:AI_WORKER_LANG } else { try { (Get-Culture).Name } catch { 'en' } }
$lang = if ($lang -like 'vi*') { 'vi' } else { 'en' }
# Say-Text 'English' 'Vietnamese': prints the one for this computer's language; -NoNewline keeps the cursor on the line
# Say-Text 'English' 'Tiếng Việt': in câu theo ngôn ngữ của máy này; -NoNewline giữ con trỏ trên dòng
function Say-Text([string]$En, [string]$Vi, [switch]$NoNewline) {
  $text = if ($lang -eq 'vi') { $Vi } else { $En }
  if ($NoNewline) { Write-Host $text -NoNewline } else { Write-Host $text }
}

Say-Text 'AI Worker icon next to the clock' 'Biểu tượng AI Worker cạnh đồng hồ'
Write-Host ''
Say-Text '  1. Install, and start it every time you log in' '  1. Cài, và tự chạy mỗi lần đăng nhập'
Say-Text '  2. Remove it from this computer' '  2. Gỡ khỏi máy này'
Say-Text 'Choose 1 or 2: ' 'Chọn 1 hoặc 2: ' -NoNewline
$choice = Read-Host
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object { $_.CommandLine -like '*ai-worker-tray.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($choice -eq '2') {
  Remove-Item $Startup -ErrorAction SilentlyContinue
  foreach ($f in 'ai-worker-tray.ps1', 'menubar.json', 'menubar-session', 'menubar-pending.json', 'menubar-notified.json', 'menubar-vi.json', 'icon-black.png', 'icon-white.png') {
    Remove-Item (Join-Path $Dir $f) -ErrorAction SilentlyContinue
  }
  # the small window: its code, libraries, error note, data, Edge profile and notification logo, and the notification app name
  # khung nhỏ: mã, thư viện, ghi chú lỗi, dữ liệu, hồ sơ Edge, logo thông báo, và tên app thông báo
  Remove-Item 'HKCU:\Software\Classes\ai-worker-open' -Recurse -ErrorAction SilentlyContinue
  Remove-Item 'HKCU:\Software\Classes\AppUserModelId\AIWorker.MenuBar' -Recurse -ErrorAction SilentlyContinue
  foreach ($f in 'menubar-popup.cs', 'popup-error.txt', 'webview2', 'popup-data', 'edge-window', 'notification-logo.png', 'open-window.vbs', 'open-request') { Remove-Item (Join-Path $Dir $f) -Recurse -Force -ErrorAction SilentlyContinue }
  Say-Text 'Removed. Ask an admin to remove this computer from the Admin page too.' 'Đã gỡ. Nhờ quản trị gỡ máy này khỏi trang Quản trị nữa.'
  exit 0
}
if ($choice -ne '1') {
  Say-Text 'Nothing chosen, nothing changed.' 'Chưa chọn gì, không đổi gì.'
  exit 1
}
if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Path $Dir | Out-Null }
[IO.File]::WriteAllText((Join-Path $Dir 'menubar.json'), (@{ server = $BoardUrl; lang = $lang } | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $Here 'ai-worker-tray.ps1') (Join-Path $Dir 'ai-worker-tray.ps1') -Force
Copy-Item (Join-Path $Here 'vi.json') (Join-Path $Dir 'menubar-vi.json') -Force
Copy-Item (Join-Path $Here 'icon-black.png') (Join-Path $Dir 'icon-black.png') -Force
Copy-Item (Join-Path $Here 'icon-white.png') (Join-Path $Dir 'icon-white.png') -Force
# The small window like the Mac app: its code and Microsoft's WebView2 libraries (license in webview2\LICENSE.txt)
# Khung nhỏ giống app Mac: mã khung và thư viện WebView2 của Microsoft (giấy phép trong webview2\LICENSE.txt)
Remove-Item (Join-Path $Dir 'popup-error.txt'), (Join-Path $Dir 'notification-logo.png') -ErrorAction SilentlyContinue
# the notification logo: the app's shared logo (as on Mac and Ubuntu); an older package without it lets the tray draw one as before
# logo trong thông báo: logo chung của app (cùng Mac và Ubuntu); gói cũ không có thì khay tự vẽ như trước
if (Test-Path (Join-Path $Here 'app-icon.png')) { Copy-Item (Join-Path $Here 'app-icon.png') (Join-Path $Dir 'notification-logo.png') -Force }
if (Test-Path (Join-Path $Here 'webview2')) {
  Copy-Item (Join-Path $Here 'menubar-popup.cs') (Join-Path $Dir 'menubar-popup.cs') -Force
  Remove-Item (Join-Path $Dir 'webview2') -Recurse -Force -ErrorAction SilentlyContinue
  Copy-Item (Join-Path $Here 'webview2') (Join-Path $Dir 'webview2') -Recurse -Force
  # files downloaded from the web carry a Windows mark; clear it so PowerShell may load the libraries
  # file tải từ mạng bị Windows đánh dấu; bỏ dấu để PowerShell được nạp thư viện
  Get-ChildItem (Join-Path $Dir 'webview2') -Recurse -File | Unblock-File
  Unblock-File (Join-Path $Dir 'menubar-popup.cs')
}

# Start at every login: a shortcut in the Startup folder that runs the script without a window
# Chạy mỗi lần đăng nhập: lối tắt trong thư mục Startup, chạy script không hiện cửa sổ
$script = Join-Path $Dir 'ai-worker-tray.ps1'
$runArgs = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $script + '"'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($Startup)
$link.TargetPath = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
$link.Arguments = $runArgs
$link.WindowStyle = 7
$link.Save()

# Start the new icon; one from an older install was stopped above
# Chạy biểu tượng mới; bản từ lần cài trước đã tắt ở trên
Start-Process -FilePath $link.TargetPath -ArgumentList $runArgs -WindowStyle Hidden

Say-Text 'Installed. Click the new icon next to the clock to see the pairing code,' 'Đã cài. Bấm vào biểu tượng mới cạnh đồng hồ để xem mã ghép,'
Say-Text 'then ask an admin to approve it on the Admin page.' 'rồi nhờ quản trị duyệt mã ở trang Quản trị.'
