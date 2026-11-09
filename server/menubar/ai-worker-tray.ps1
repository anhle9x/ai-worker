# Menu bar icon for managers on Windows: an icon in the notification area with the number of people waiting.
# Built-in PowerShell and .NET only. It pairs once like a wall screen, then every minute asks the server who is waiting.
# -Once: one round without the icon, printing the state (used by the tests).
# Biểu tượng cho quản lý trên Windows: biểu tượng ở khay cạnh đồng hồ, kèm số người đang chờ.
# Chỉ dùng PowerShell và .NET có sẵn. Ghép một lần như màn hình treo tường, rồi mỗi phút hỏi máy chủ ai đang chờ.
# -Once: chạy một lượt không hiện biểu tượng, in trạng thái ra (dùng cho bài thử).
param([switch]$Once)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

$ConfigDir = if ($env:AI_WORKER_MENUBAR_DIR) { $env:AI_WORKER_MENUBAR_DIR } else { Join-Path $env:APPDATA 'ai-worker' }
$ConfigFile = Join-Path $ConfigDir 'menubar.json'
$SessionFile = Join-Path $ConfigDir 'menubar-session'
$PendingFile = Join-Path $ConfigDir 'menubar-pending.json'
$NotifiedFile = Join-Path $ConfigDir 'menubar-notified.json'

$Cfg = if (Test-Path $ConfigFile) { Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
$Server = if ($Cfg -and $Cfg.server) { ([string]$Cfg.server).TrimEnd('/') } else { '' }
$Lang = if ($Cfg -and $Cfg.lang) { [string]$Cfg.lang } elseif ((Get-Culture).Name -like 'vi*') { 'vi' } else { 'en' }
# the language goes into the window's address, so only the two known codes are kept
# ngôn ngữ đi vào địa chỉ của khung, nên chỉ giữ hai mã đã biết
if ($Lang -ne 'en' -and $Lang -ne 'vi') { $Lang = 'en' }

# The board address: https, or http only to this very computer (the host exactly localhost, 127.0.0.1 or ::1, not a name that starts with it).
# It holds only letters, digits and - _ . : / [ ], so it is safe inside the Edge command line.
# Địa chỉ bảng: https, hoặc http chỉ tới chính máy này (máy chủ đúng là localhost, 127.0.0.1 hoặc ::1, không phải tên bắt đầu bằng mấy chữ đó).
# Chỉ gồm chữ, số và - _ . : / [ ], nên an toàn trong dòng lệnh mở Edge.
function Test-Server([string]$address) {
  if ($address -notmatch '^[A-Za-z0-9._:/\[\]-]+$') { return $false }
  $uri = $null
  if (-not [Uri]::TryCreate($address, [UriKind]::Absolute, [ref]$uri)) { return $false }
  if ($uri.Scheme -eq 'https') { return [bool]$uri.Host }
  return ($uri.Scheme -eq 'http' -and @('localhost', '127.0.0.1', '[::1]') -contains $uri.Host)
}

# Vietnamese words: vi.json in the settings folder, else next to this script
# Chữ tiếng Việt: vi.json trong thư mục cài đặt, không thì cạnh script này
$Vi = @{}
foreach ($path in @((Join-Path $ConfigDir 'menubar-vi.json'), (Join-Path $PSScriptRoot 'vi.json'))) {
  if (Test-Path $path) {
    (Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $Vi[$_.Name] = $_.Value }
    break
  }
}
function T([string]$text) {
  if ($Lang -eq 'vi' -and $Vi.ContainsKey($text)) { return $Vi[$text] }
  return $text
}

function Save-Private([string]$path, [string]$text) {
  # %APPDATA% is readable only by this user, so the session file is too
  # %APPDATA% chỉ người dùng này đọc được, nên file phiên cũng vậy
  if (-not (Test-Path $ConfigDir)) { New-Item -ItemType Directory -Path $ConfigDir | Out-Null }
  [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false))
}

# Saves the chosen language next to the server address and redraws the tray texts; the page is where the person chooses it.
# Lưu ngôn ngữ đã chọn cạnh địa chỉ máy chủ và vẽ lại chữ ở khay; người dùng chọn trong trang.
$StartupLink = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI Worker menu bar.lnk'
# Same shortcut the installer makes: runs this script hidden at every login. Off removes it.
# Cùng lối tắt file cài tạo: chạy script này ẩn mỗi lần đăng nhập. Tắt thì xoá lối tắt.
function Set-StartAtLogin([bool]$on) {
  if (-not $on) { Remove-Item $StartupLink -ErrorAction SilentlyContinue; return }
  $shell = New-Object -ComObject WScript.Shell
  $link = $shell.CreateShortcut($StartupLink)
  $link.TargetPath = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
  $link.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $ConfigDir 'ai-worker-tray.ps1') + '"'
  $link.WindowStyle = 7
  $link.Save()
}

# Removes this computer's icon the way option 2 of the installer does, then quits. The loaded WebView2 files are in use,
# so a hidden command deletes the settings folder a few seconds after the icon has quit.
# Gỡ biểu tượng khỏi máy này như lựa chọn 2 của file cài, rồi thoát. Thư viện WebView2 đang được dùng,
# nên một lệnh chạy ẩn xoá thư mục cài đặt vài giây sau khi biểu tượng thoát.
function Remove-App {
  Remove-Item $StartupLink -ErrorAction SilentlyContinue
  foreach ($k in 'HKCU:\Software\Classes\AppUserModelId\AIWorker.MenuBar', 'HKCU:\Software\Classes\ai-worker-open') { Remove-Item $k -Recurse -ErrorAction SilentlyContinue }
  if (Test-Path $ConfigDir) {
    # the whole folder goes only when it is the app's own (AI_WORKER_MENUBAR_DIR may point anywhere); otherwise only the app's own files go
    # chỉ xoá cả thư mục khi đó là thư mục riêng của app (AI_WORKER_MENUBAR_DIR có thể trỏ tới bất cứ đâu); không thì chỉ xoá file của app
    if ((Split-Path $ConfigDir -Leaf) -eq 'ai-worker') {
      $removal = 'rmdir /s /q "' + $ConfigDir + '"'
    } else {
      $files = 'ai-worker-tray.ps1', 'menubar.json', 'menubar-session', 'menubar-pending.json', 'menubar-notified.json', 'menubar-vi.json', 'icon-black.png', 'icon-white.png',
        'menubar-popup.cs', 'popup-error.txt', 'notification-logo.png', 'open-window.vbs', 'open-request'
      $folders = 'webview2', 'popup-data', 'edge-window'
      $removal = (@($files | ForEach-Object { 'del /f /q "' + (Join-Path $ConfigDir $_) + '"' }) + @($folders | ForEach-Object { 'rmdir /s /q "' + (Join-Path $ConfigDir $_) + '"' })) -join ' & '
    }
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') -ArgumentList ('/c timeout /t 4 /nobreak >nul & ' + $removal) -WindowStyle Hidden
  }
  $tray.Visible = $false
  [System.Windows.Forms.Application]::Exit()
}

function Set-Language([string]$code) {
  if ($code -ne 'en' -and $code -ne 'vi') { return }
  if ($code -eq $script:Lang) { return }
  $script:Lang = $code
  Save-Private $ConfigFile (@{ server = $Server; lang = $code } | ConvertTo-Json -Compress)
  if ($itemBoard) { $itemBoard.Text = (T 'Open board') }
  if ($itemQuit) { $itemQuit.Text = (T 'Quit') }
  if (Get-Command Refresh -ErrorAction SilentlyContinue) { Refresh }
}
function Read-Text([string]$path) { if (Test-Path $path) { return ([IO.File]::ReadAllText($path)).Trim() } return '' }

$Handler = New-Object System.Net.Http.HttpClientHandler
$Handler.UseCookies = $false
$Handler.AllowAutoRedirect = $false
$Client = [System.Net.Http.HttpClient]::new($Handler)
$Client.Timeout = [TimeSpan]::FromSeconds(8)
$Client.DefaultRequestHeaders.UserAgent.ParseAdd('AIWorkerMenuBar/1.0 (Windows)')

# One request; returns status, JSON and Set-Cookie values. Never follows a redirect, so a session cannot leak to another host.
# Một yêu cầu; trả mã, JSON và các Set-Cookie. Không đi theo chuyển hướng, để phiên không lọt sang máy khác.
function Call([string]$method, [string]$path, [string]$cookie = '') {
  $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($method), [Uri]($Server + $path))
  if ($cookie) { $req.Headers.Add('Cookie', $cookie) }
  # a POST goes with an empty body: the pairing routes do not read one, and an unread body makes Windows reset the connection
  # POST gửi thân rỗng: đường ghép mã không đọc thân, và thân không được đọc làm Windows ngắt kết nối
  if ($method -eq 'POST') { $req.Content = [System.Net.Http.ByteArrayContent]::new([byte[]]@()) }
  $res = $Client.SendAsync($req).GetAwaiter().GetResult()
  $body = $res.Content.ReadAsStringAsync().GetAwaiter().GetResult()
  $cookies = @()
  $values = $null
  if ($res.Headers.TryGetValues('Set-Cookie', [ref]$values)) { $cookies = @($values) }
  $json = $null
  try { $json = $body | ConvertFrom-Json } catch { }
  return @{ Status = [int]$res.StatusCode; Json = $json; Cookies = $cookies }
}
function Cookie-Value($cookies, [string]$name) {
  foreach ($c in $cookies) {
    $first = ($c -split ';')[0]
    $k, $v = $first -split '=', 2
    if ($k.Trim() -eq $name -and $v) { return $v }
  }
  return ''
}

# One round: returns @{ State = ok|long|off|pair|setup; Count; Text; Url; Code }.
# Một lượt: trả @{ State = ok|long|off|pair|setup; Count; Text; Url; Code }.
function Round {
  if (-not (Test-Server $Server)) { return @{ State = 'setup'; Count = 0; Text = (T 'Not set up: run the installer again') } }
  try {
    $token = Read-Text $SessionFile
    if (-not $token) {
      $pending = if (Test-Path $PendingFile) { Get-Content $PendingFile -Raw | ConvertFrom-Json } else { $null }
      if ($pending -and $pending.key) {
        $r = Call 'POST' '/tv/poll' ('tv-pending=' + $pending.key)
        if ($r.Status -eq 200 -and $r.Json.status -eq 'done') {
          $token = Cookie-Value $r.Cookies 'session'
          if ($token) { Save-Private $SessionFile $token; Remove-Item $PendingFile -ErrorAction SilentlyContinue }
        } elseif ($r.Status -eq 200 -and $r.Json.status -eq 'pending') {
          return @{ State = 'pair'; Count = 0; Code = $pending.code; Text = ('{0}: {1}-{2}' -f (T 'Pairing code'), $pending.code.Substring(0, 4), $pending.code.Substring(4)) }
        } else { Remove-Item $PendingFile -ErrorAction SilentlyContinue }
      }
      if (-not $token) {
        $r = Call 'POST' '/tv/request-code'
        $key = Cookie-Value $r.Cookies 'tv-pending'
        if ($r.Status -ne 200 -or -not $key -or ([string]$r.Json.code) -notmatch '^\d{8}$') { return @{ State = 'off'; Count = 0; Text = (T 'The server refused the pairing, try again later') } }
        Save-Private $PendingFile (@{ key = $key; code = [string]$r.Json.code } | ConvertTo-Json -Compress)
        $code = [string]$r.Json.code
        return @{ State = 'pair'; Count = 0; Code = $code; Text = ('{0}: {1}-{2}' -f (T 'Pairing code'), $code.Substring(0, 4), $code.Substring(4)) }
      }
    }
    $s = Call 'GET' '/mini/state' ('session=' + $token)
    if ($s.Status -eq 401 -or $s.Status -eq 403) { Remove-Item $SessionFile -ErrorAction SilentlyContinue; return Round }
    if ($s.Status -ne 200) { throw "status $($s.Status)" }
    $h = Call 'POST' '/mini/handoff' ('session=' + $token)
    $waiting = @($s.Json.waiting)
    $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $limitMs = [int]$s.Json.notifyMinutes * 60000
    $long = @($waiting | Where-Object { $_.since -and ($nowMs - [long]$_.since) -ge $limitMs }).Count -gt 0
    $text = if ($waiting.Count) { (T '{n} waiting').Replace('{n}', [string]$waiting.Count) } else { T 'Nobody is waiting' }
    # the one-time window code from the server: anything else (a hostile server, a tampered reply) never goes into the address; the board opens instead
    # mã mở khung dùng một lần từ máy chủ: thứ khác (máy chủ xấu, câu trả lời bị sửa) không bao giờ vào địa chỉ; mở bảng thay vào đó
    $handoff = if ($h.Json) { [string]$h.Json.code } else { '' }
    $url = if ($handoff -cmatch '^[A-Za-z0-9_-]{8,128}$') { $Server + '/mini?h=' + $handoff + '&lang=' + $script:Lang } else { $Server + '/board' }
    return @{ State = $(if ($long) { 'long' } else { 'ok' }); Count = $waiting.Count; Text = $text; Url = $url; Waiting = $waiting; Notify = [bool]$s.Json.notify; NotifyMinutes = [int]$s.Json.notifyMinutes }
  } catch {
    $script:LastError = $_.Exception.Message
    return @{ State = 'off'; Count = 0; Text = (T 'Cannot reach the server') }
  }
}

if ($Once) {
  $r = Round
  Write-Output ('{0}|{1}|{2}|{3}' -f $r.State, $r.Count, $r.Text, $(if ($r.Url) { 'url' } else { '' }))
  if ($script:LastError) { [Console]::Error.WriteLine($script:LastError) }
  exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# The logo matching the taskbar: white on a dark taskbar, black on a light one. The company's own logo (icon-white.png,
# icon-black.png in the settings folder) wins over the one shipped next to this script.
# Logo hợp với thanh tác vụ: trắng trên thanh tối, đen trên thanh sáng. Logo riêng của công ty (icon-white.png,
# icon-black.png trong thư mục cài đặt) được dùng trước logo đi kèm script.
function Load-Logo {
  $light = 0
  try { $light = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' -ErrorAction Stop).SystemUsesLightTheme } catch { }
  $color = if ($light -eq 1) { 'black' } else { 'white' }
  foreach ($path in @((Join-Path $ConfigDir "icon-$color.png"), (Join-Path $PSScriptRoot "icons\generic-$color.png"))) {
    if ((Test-Path $path) -and (Get-Item $path).Length -le 20000) { return [System.Drawing.Image]::FromFile($path) }
  }
  return $null
}
$Logo = Load-Logo

# Draw the icon: the logo, the count on a round badge; the badge turns deep blue when someone waited past the limit; the logo fades without a connection.
# Vẽ biểu tượng: logo, số đếm trong chấm tròn; chấm chuyển xanh lam đậm khi có người chờ quá hạn; logo mờ đi khi mất kết nối.
function Make-Icon([string]$state, [int]$count) {
  $bmp = New-Object System.Drawing.Bitmap 32, 32
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'
  $g.InterpolationMode = 'HighQualityBicubic'
  if ($Logo) {
    $attrs = New-Object System.Drawing.Imaging.ImageAttributes
    if ($state -eq 'off' -or $state -eq 'pair') {
      $matrix = New-Object System.Drawing.Imaging.ColorMatrix
      $matrix.Matrix33 = 0.4
      $attrs.SetColorMatrix($matrix)
    }
    $g.DrawImage($Logo, (New-Object System.Drawing.Rectangle 0, 0, 32, 32), 0, 0, $Logo.Width, $Logo.Height, 'Pixel', $attrs)
  } else {
    $g.FillEllipse([System.Drawing.Brushes]::Gray, 4, 4, 24, 24)
  }
  if ($count -gt 0) {
    $badge = if ($state -eq 'long') { [System.Drawing.Color]::FromArgb(26, 86, 200) } else { [System.Drawing.Color]::FromArgb(200, 40, 40) }
    $g.FillEllipse((New-Object System.Drawing.SolidBrush $badge), 14, 14, 18, 18)
    $font = New-Object System.Drawing.Font('Segoe UI', $(if ($count -gt 9) { 8 } else { 10 }), [System.Drawing.FontStyle]::Bold)
    $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
    $g.DrawString($(if ($count -gt 99) { '99' } else { [string]$count }), $font, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF 14, 14, 18, 18), $fmt)
  }
  $g.Dispose()
  return [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
}

# The small window like the Mac app (menubar-popup.cs, WebView2): borderless, rounded, frosted, anchored above the tray, sized to the page.
# The installer copies the WebView2 libraries into the settings folder; if they are missing or fail, the compact Edge window is used instead.
# Khung nhỏ giống app Mac (menubar-popup.cs, WebView2): không viền, bo góc, kính mờ, dính trên khay, co theo trang.
# File cài chép thư viện WebView2 vào thư mục cài đặt; thiếu thư viện hay lỗi thì quay về cửa sổ Edge gọn.
$script:Popup = $null
$script:PopupFailed = $false
$PopupErrorFile = Join-Path $ConfigDir 'popup-error.txt'
function New-Popup {
  if ($script:PopupFailed) { return $null }
  try {
    $wv = Join-Path $ConfigDir 'webview2'
    $source = Join-Path $ConfigDir 'menubar-popup.cs'
    if (-not (Test-Path (Join-Path $wv 'Microsoft.Web.WebView2.WinForms.dll')) -or -not (Test-Path $source)) { throw 'WebView2 libraries are missing' }
    $arch = switch ($env:PROCESSOR_ARCHITECTURE) { 'ARM64' { 'arm64' } 'x86' { 'x86' } default { 'x64' } }
    $core = Join-Path $wv 'Microsoft.Web.WebView2.Core.dll'
    $winforms = Join-Path $wv 'Microsoft.Web.WebView2.WinForms.dll'
    Add-Type -Path $core
    Add-Type -Path $winforms
    # compile the class once per process
    # dịch lớp một lần cho mỗi tiến trình
    if (-not ('MenuBarPopup' -as [type])) {
      Add-Type -TypeDefinition ([IO.File]::ReadAllText($source)) -ReferencedAssemblies @('System.Windows.Forms', 'System.Drawing', $core, $winforms)
    }
    $popup = New-Object MenuBarPopup((Join-Path $ConfigDir 'popup-data'), (Join-Path $wv $arch))
    # the language chosen in the window's Settings also drives the tray menu and the notifications
    # ngôn ngữ chọn trong Cài đặt của khung cũng đổi menu ở khay và thông báo
    $popup.add_LanguageChanged([Action[string]] { param($code) Set-Language $code })
    # start at login: the page asks for the state and turns it on or off; the shortcut in the Startup folder is the state
    # tự chạy khi đăng nhập: trang hỏi tình trạng và bật tắt; lối tắt trong thư mục Startup chính là tình trạng
    $popup.add_Hello([Action] { $script:Popup.TellLogin((Test-Path $StartupLink)) })
    $popup.add_UninstallRequested([Action] { Remove-App })
    $popup.add_QuitRequested([Action] { $tray.Visible = $false; [System.Windows.Forms.Application]::Exit() })
    $popup.add_LoginChanged([Action[bool]] { param($on) Set-StartAtLogin $on; $script:Popup.TellLogin((Test-Path $StartupLink)) })
    return $popup
  } catch {
    $script:PopupFailed = $true
    try { Save-Private $PopupErrorFile ([string]$_.Exception.Message) } catch { }
    return $null
  }
}

function Open-Window([string]$url) {
  # clear the notifications still showing, so nothing sits on top of the window
  # xoá các thông báo còn đang hiện, để không gì đè lên khung
  if ($script:HasToasts) { try { [Windows.UI.Notifications.ToastNotificationManager]::History.Clear($AppId) } catch { } }
  if (-not $script:Popup) { $script:Popup = New-Popup }
  if ($script:Popup) {
    try { $script:Popup.Open($url, $Server); return } catch { try { Save-Private $PopupErrorFile ([string]$_.Exception.Message) } catch { } }
  }
  # fallback: a compact Edge window with no address bar, next to the notification area
  # dự phòng: cửa sổ Edge gọn, không thanh địa chỉ, sát khay đồng hồ
  $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $x = $area.Right - 380; $y = $area.Bottom - 480
  $edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
  # a profile of its own: the window runs apart from the Edge the user already has open, so it keeps its compact size and place
  # hồ sơ Edge riêng: khung chạy tách khỏi Edge người dùng đang mở, nên luôn đúng cỡ gọn và đúng chỗ
  $profileDir = Join-Path $ConfigDir 'edge-window'
  # the address goes quoted as one argument: Windows PowerShell joins the list with spaces and does not quote it
  # địa chỉ đi trong dấu nháy thành một tham số: Windows PowerShell nối danh sách bằng dấu cách và không tự thêm nháy
  if ($edge) { Start-Process $edge -ArgumentList @("--app=`"$url`"", '--window-size=380,480', "--window-position=$x,$y", "--user-data-dir=`"$profileDir`"", '--no-first-run', '--no-default-browser-check') } else { Start-Process $url }
}

$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Visible = $true
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$itemText = $menu.Items.Add('')
$itemText.Enabled = $false
$itemBoard = $menu.Items.Add((T 'Open board'))
$itemBoard.Add_Click({ if ($Server) { Start-Process ($Server + '/board') } })
$itemQuit = $menu.Items.Add((T 'Quit'))
$itemQuit.Add_Click({ $tray.Visible = $false; [System.Windows.Forms.Application]::Exit() })
$tray.ContextMenuStrip = $menu
$script:last = $null

# Notifications named "AI Worker" with its logo instead of "Windows PowerShell": register an app name with Windows (a key of the current user,
# no admin rights), then send Windows 10/11 toasts. On any error the old tray balloon is used.
# Thông báo mang tên AI Worker và logo thay cho "Windows PowerShell": đăng ký một tên app với Windows (khoá riêng của người dùng,
# không cần quyền quản trị), rồi gửi thông báo kiểu Windows 10/11. Lỗi thì quay về bong bóng thông báo cũ của khay.
$AppId = 'AIWorker.MenuBar'
$OpenScript = Join-Path $ConfigDir 'open-window.vbs'
$OpenRequest = Join-Path $ConfigDir 'open-request'
function Register-AppName {
  try {
    $logoFile = Join-Path $ConfigDir 'notification-logo.png'
    if ($Logo -and -not (Test-Path $logoFile)) {
      # the white logo on a rounded blue square: clear on light and dark notifications alike
      # logo trắng trên ô xanh bo góc: rõ cả trên thông báo nền sáng lẫn nền tối
      $bmp = New-Object System.Drawing.Bitmap 96, 96
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.SmoothingMode = 'AntiAlias'; $g.InterpolationMode = 'HighQualityBicubic'
      $path = New-Object System.Drawing.Drawing2D.GraphicsPath
      $r = 20
      $path.AddArc(0, 0, $r * 2, $r * 2, 180, 90); $path.AddArc(96 - $r * 2, 0, $r * 2, $r * 2, 270, 90)
      $path.AddArc(96 - $r * 2, 96 - $r * 2, $r * 2, $r * 2, 0, 90); $path.AddArc(0, 96 - $r * 2, $r * 2, $r * 2, 90, 90); $path.CloseFigure()
      $g.FillPath((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(24, 95, 165))), $path)
      $white = $Logo
      $whiteFile = Join-Path $ConfigDir 'icon-white.png'
      if (Test-Path $whiteFile) { $white = [System.Drawing.Image]::FromFile($whiteFile) }
      $g.DrawImage($white, 18, 18, 60, 60)
      $g.Dispose(); $bmp.Save($logoFile, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    }
    $key = "HKCU:\Software\Classes\AppUserModelId\$AppId"
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name 'DisplayName' -Value 'AI Worker'
    if (Test-Path $logoFile) { Set-ItemProperty -Path $key -Name 'IconUri' -Value $logoFile }
    # A click on a notification runs the ai-worker-open: link: a tiny hidden script leaves a request file, and the tray opens the window
    # Bấm vào thông báo thì chạy đường dẫn ai-worker-open:: một script nhỏ chạy ẩn để lại file yêu cầu, rồi khay mở khung
    [IO.File]::WriteAllText($OpenScript, ('CreateObject("Scripting.FileSystemObject").CreateTextFile("' + $OpenRequest + '", True).Close'), (New-Object Text.UTF8Encoding $false))
    $proto = 'HKCU:\Software\Classes\ai-worker-open'
    if (-not (Test-Path "$proto\shell\open\command")) { New-Item -Path "$proto\shell\open\command" -Force | Out-Null }
    Set-ItemProperty -Path $proto -Name '(default)' -Value 'URL:AI Worker'
    Set-ItemProperty -Path $proto -Name 'URL Protocol' -Value ''
    Set-ItemProperty -Path "$proto\shell\open\command" -Name '(default)' -Value ('"' + (Join-Path $env:SystemRoot 'System32\wscript.exe') + '" "' + $OpenScript + '"')
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    return $true
  } catch { return $false }
}
$script:HasToasts = $false

# the round badge in a notification: the first letter of the person's name on a colour fixed by the name (same rule as the Mac and Ubuntu apps)
# ô tròn trong thông báo: chữ cái đầu của tên người trên một màu cố định theo tên (cùng quy tắc với app Mac và Ubuntu)
$AvatarColors = @('#e17076', '#faa774', '#a695e7', '#7bc862', '#6ec9cb', '#65aadd', '#ee7aae')
function Get-Avatar([string]$name) {
  try {
    $letter = '?'
    foreach ($c in $name.ToCharArray()) { if ([char]::IsLetterOrDigit($c)) { $letter = ([string]$c).ToUpper(); break } }
    $sum = 0; foreach ($b in [Text.Encoding]::UTF8.GetBytes($name)) { $sum += $b }
    $color = $AvatarColors[$sum % $AvatarColors.Count]
    $dir = Join-Path $ConfigDir 'avatars'
    $path = Join-Path $dir ('{0:x}-{1}.png' -f [int][char]$letter, $color.Substring(1))
    if (Test-Path $path) { return $path }
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $size = 128
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'
    $g.FillEllipse((New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml($color))), 0, 0, $size, $size)
    $font = New-Object System.Drawing.Font 'Segoe UI', ($size * 0.5), ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
    $g.DrawString($letter, $font, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF 0, 0, $size, $size), $fmt)
    $g.Dispose(); $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    return $path
  } catch { return $null }
}

function Send-Notification([string]$title, [string]$body, [string]$who = '') {
  # the window is open: the person already sees the list, so no notification on top of it
  # khung đang mở: người dùng đã thấy danh sách, khỏi bật thông báo đè lên khung
  try { if ($script:Opening -or ($script:Popup -and $script:Popup.IsOpen)) { return } } catch { }
  if ($script:HasToasts) {
    try {
      # the text goes into the XML escaped, so a name never becomes a tag or a command
      # chữ đưa vào XML đã được thoát ký tự, nên tên người không thành thẻ XML hay lệnh
      $esc = { param($s) [Security.SecurityElement]::Escape($s) }
      # the badge of the person who waits takes the place of the app's logo, cut round like a chat app
      # ô tròn của người đang chờ thay chỗ logo của app, cắt tròn như ứng dụng nhắn tin
      $img = ''
      if ($who) { $a = Get-Avatar $who; if ($a) { $img = '<image placement="appLogoOverride" hint-crop="circle" src="{0}"/>' -f (& $esc ([Uri]$a).AbsoluteUri) } }
      $xml = '<toast launch="ai-worker-open:window" activationType="protocol"><visual><binding template="ToastGeneric"><text>{0}</text><text>{1}</text>{2}</binding></visual></toast>' -f (& $esc $title), (& $esc $body), $img
      $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
      $doc.LoadXml($xml)
      [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show((New-Object Windows.UI.Notifications.ToastNotification $doc))
      return
    } catch { $script:HasToasts = $false }
  }
  $tray.ShowBalloonTip(8000, $title, $body, 'None')
}

# The waits already notified, as a flat list. Windows PowerShell 5 hands a JSON array on as one item, so it is unrolled here;
# without that the check below never matched and the same person was notified again every minute. Names are read as UTF-8.
# Các lần chờ đã báo, thành một danh sách phẳng. Windows PowerShell 5 chuyển cả mảng JSON đi như một phần tử nên phải trải ra ở đây;
# thiếu bước này phép kiểm bên dưới không bao giờ khớp và cùng một người bị báo lại mỗi phút. Tên được đọc theo UTF-8.
function Read-Notified {
  if (-not (Test-Path $NotifiedFile)) { return @() }
  try { return @(Get-Content $NotifiedFile -Raw -Encoding UTF8 | ConvertFrom-Json | ForEach-Object { $_ } | ForEach-Object { [string]$_ }) } catch { return @() }
}

function Notify-Long($r) {
  # one balloon per wait that passed the limit; waits that ended are forgotten
  # mỗi lần chờ quá hạn chỉ báo một lần; quên những lần chờ đã xong
  $done = @(Read-Notified)
  $current = @(); $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  foreach ($p in $r.Waiting) {
    if (-not $p.since) { continue }
    $key = '{0}|{1}' -f $p.name, $p.since; $current += $key
    $minutes = [int](($nowMs - [long]$p.since) / 60000)
    if ($r.Notify -and $minutes -ge $r.NotifyMinutes -and $done -notcontains $key) {
      Send-Notification (T 'Waiting for an answer') ((T '{name} has waited {n} minutes').Replace('{name}', [string]$p.name).Replace('{n}', [string]$minutes)) ([string]$p.name)
      $done += $key
    }
  }
  Save-Private $NotifiedFile (ConvertTo-Json @($done | Where-Object { $current -contains $_ }) -Compress)
}

function Refresh {
  $r = Round
  $script:last = $r
  $old = $tray.Icon
  $tray.Icon = Make-Icon $r.State $r.Count
  if ($old) { $old.Dispose() }
  $tip = 'AI Worker: ' + $r.Text
  $tray.Text = $tip.Substring(0, [Math]::Min(63, $tip.Length))
  $itemText.Text = $r.Text
  if ($r.Waiting) { Notify-Long $r }
}

# What a click on the icon or on a notification does: refresh without a notification, then open the window (or the pairing page)
# Việc bấm biểu tượng hay bấm thông báo làm: làm mới không bật thông báo, rồi mở khung (hoặc trang ghép)
function Open-From-Tray {
  # the window opens right after this refresh and shows the list, so this refresh sends no notification
  # khung mở ngay sau lần làm mới này và hiện danh sách, nên lần này không bật thông báo
  $script:Opening = $true
  try { Refresh } finally { $script:Opening = $false }
  if ($script:last.Url) { Open-Window $script:last.Url }
  # not paired yet: open the pairing page, where the manager enters their own account and 6-digit code (the code sits after #)
  # chưa ghép: mở trang ghép, quản lý nhập tài khoản và mã 6 số của mình (mã nằm sau dấu #)
  elseif ($script:last.State -eq 'pair' -and $script:last.Code -match '^\d{8}$') { Open-Window ($Server + '/mini/pair#c=' + $script:last.Code) }
}
$tray.Add_MouseClick({
  param($sender, $e)
  if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Open-From-Tray }
})
# a click on a notification: the request file the ai-worker-open: link leaves, or the old balloon's own click
# bấm vào thông báo: file yêu cầu do đường dẫn ai-worker-open: để lại, hoặc cú bấm vào bong bóng cũ
$tray.Add_BalloonTipClicked({ Open-From-Tray })
$noticeTimer = New-Object System.Windows.Forms.Timer
$noticeTimer.Interval = 300
$noticeTimer.Add_Tick({ if (Test-Path $OpenRequest) { Remove-Item $OpenRequest -ErrorAction SilentlyContinue; Open-From-Tray } })
$noticeTimer.Start()

$script:HasToasts = Register-AppName
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 60000
$timer.Add_Tick({ Refresh })
$timer.Start()
Refresh
[System.Windows.Forms.Application]::Run()
