# AI Worker connector for Windows: lets Codex, Cursor and Gemini CLI show on the AI Worker board.
# Bộ nối AI Worker cho Windows: cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker.
#
# Each tool runs this file as a hook:  powershell -File ai-worker-hook.ps1 <tool> <event>
# Mỗi công cụ chạy file này như một hook:  powershell -File ai-worker-hook.ps1 <tool> <event>
#   tool   codex | cursor | gemini
#   event  start | prompt | ask | tool | reply | stop | end
#
# It does the same as ai-worker-hook.sh: one line per open session in a small file on this computer,
# then three numbers per tool to the board: sessions open, working, waiting for the person.
# Nó làm đúng như ai-worker-hook.sh: mỗi phiên đang mở một dòng trong một file nhỏ trên máy này,
# rồi gửi lên bảng ba con số cho mỗi công cụ: số phiên đang mở, đang làm, đang chờ người dùng.
#
# What leaves this computer: the name and email typed at install, a random device id, the time
# and those numbers. Never the prompt, the answer, a file name, a folder or a project name.
# Thứ rời khỏi máy này: tên và email gõ lúc cài, một mã máy ngẫu nhiên, thời điểm
# và các con số đó. Không bao giờ có câu hỏi, câu trả lời, tên file, thư mục hay tên dự án.
#
# From the tool's event it reads the session id, which stays on this computer, and whether the tool's
# last message ends with a question mark. The message itself is not kept anywhere.
# Từ sự kiện của công cụ, nó đọc mã phiên, chỉ nằm trên máy này, và việc câu cuối của công cụ
# có kết thúc bằng dấu hỏi hay không. Bản thân câu đó không được lưu ở đâu cả.
param([string]$Tool = '', [string]$Kind = '')

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Dir = if ($env:AI_WORKER_CONNECTOR_DIR) { $env:AI_WORKER_CONNECTOR_DIR } else { Join-Path $env:USERPROFILE '.local\share\ai-worker\connector' }
# a session with no event for this long is no longer counted; the server keeps a report for the same time
# phiên không có sự kiện nào trong ngần này thì thôi không tính; máy chủ giữ một báo cáo cũng trong ngần đó
$SessionSeconds = 7200
# with nothing changed, send again after this long, so the board knows the computer is still there
# không có gì đổi thì sau ngần này gửi lại, để bảng biết máy vẫn còn đó
$ResendSeconds = 300
$Utf8 = New-Object Text.UTF8Encoding($false)

# Answer the tool first, so a slow network never holds it up. Codex wants nothing on stdout;
# Gemini CLI and Cursor read JSON, and Cursor sends the prompt only when told to continue.
# Trả lời công cụ trước, để mạng chậm không bao giờ giữ chân nó. Codex không muốn gì trên stdout;
# Gemini CLI và Cursor đọc JSON, và Cursor chỉ gửi câu hỏi khi được bảo tiếp tục.
if ($Kind -ne 'send') {
  if ($Tool -eq 'cursor' -and $Kind -eq 'prompt') { [Console]::Out.Write('{"continue":true}') }
  elseif ($Tool -eq 'cursor' -or $Tool -eq 'gemini') { [Console]::Out.Write('{}') }
  [Console]::Out.Flush()
}
if (@('codex', 'cursor', 'gemini') -notcontains $Tool) { exit 0 }
if (@('start', 'prompt', 'ask', 'tool', 'reply', 'stop', 'end', 'send') -notcontains $Kind) { exit 0 }
$ConfigFile = Join-Path $Dir 'config'
if (-not (Test-Path -LiteralPath $ConfigFile)) { exit 0 }
$SessionsFile = Join-Path $Dir 'sessions'

# one lock per connector folder, so two hooks never write the same file at once
# mỗi thư mục bộ nối một khoá, để hai hook không bao giờ ghi cùng một file một lúc
function Lock-Name([string]$part) {
  $hash = [Security.Cryptography.SHA1]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($Dir.ToLower()))
  'ai-worker-connector-' + $part + '-' + [BitConverter]::ToString($hash).Replace('-', '').Substring(0, 16)
}

function Now-Seconds { [long][DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }

function Read-Sessions {
  if (Test-Path -LiteralPath $SessionsFile) { @([IO.File]::ReadAllLines($SessionsFile, $Utf8) | Where-Object { $_.Trim() }) } else { @() }
}

# the sessions still counted, per tool: sessions open, working, waiting
# các phiên còn được tính, theo từng công cụ: số phiên mở, đang làm, đang chờ
function Count-Sessions([long]$now) {
  $counts = [ordered]@{}
  foreach ($line in (Read-Sessions | Sort-Object)) {
    $p = $line.Trim() -split '\s+'
    if ($p.Count -lt 4 -or ($now - [long]$p[3]) -ge $SessionSeconds) { continue }
    if (-not $counts.Contains($p[0])) { $counts[$p[0]] = [ordered]@{ openSessions = 0; working = 0; waiting = 0 } }
    $counts[$p[0]]['openSessions'] += 1
    if ($p[2] -eq 'working') { $counts[$p[0]]['working'] += 1 }
    if ($p[2] -eq 'waiting') { $counts[$p[0]]['waiting'] += 1 }
  }
  return $counts
}

function Clean-Text([string]$text) { ($text -replace '["\\]', '') -replace '[\x00-\x1f]', '' }

function Send-Report {
  $cfg = @{}
  foreach ($line in [IO.File]::ReadAllLines($ConfigFile, $Utf8)) {
    $i = $line.IndexOf('=')
    if ($i -gt 0) { $cfg[$line.Substring(0, $i)] = $line.Substring($i + 1) }
  }
  if (-not $cfg['url'] -or -not $cfg['key']) { return }
  $deviceFile = Join-Path $Dir 'device'
  $device = ''
  if (Test-Path -LiteralPath $deviceFile) { $device = ([IO.File]::ReadAllText($deviceFile)).Trim() }
  if ($device -notmatch '^device-[a-z0-9]{1,40}$') {
    $chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    $bytes = New-Object byte[] 16
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $device = 'device-' + (-join ($bytes | ForEach-Object { $chars[$_ % 36] }))
    [IO.File]::WriteAllText($deviceFile, $device + "`n", $Utf8)
  }
  $sentFile = Join-Path $Dir 'sent'
  $keyFile = Join-Path $Dir 'device-key'
  $errorFile = Join-Path $Dir 'last-error'
  $mutex = New-Object Threading.Mutex($false, (Lock-Name 'send'))
  $held = $false
  try { $held = $mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $held = $true }
  if (-not $held) { return }
  try {
    for ($round = 0; $round -lt 3; $round++) {
      $now = Now-Seconds
      $counts = Count-Sessions $now
      $signature = (@($counts.Keys | ForEach-Object { '{0} {1} {2} {3}' -f $_, $counts[$_]['openSessions'], $counts[$_]['working'], $counts[$_]['waiting'] }) -join ';')
      $sentAt = [long]0
      $sentSignature = ''
      if (Test-Path -LiteralPath $sentFile) {
        $line = ([IO.File]::ReadAllText($sentFile)).TrimEnd("`r", "`n")
        $i = $line.IndexOf(' ')
        if ($i -gt 0) { $sentAt = [long]$line.Substring(0, $i); $sentSignature = $line.Substring($i + 1) }
      }
      if ($signature -eq $sentSignature -and ($now - $sentAt) -lt $ResendSeconds) { break }
      $open = 0; $working = 0; $waiting = 0
      foreach ($k in $counts.Keys) { $open += $counts[$k]['openSessions']; $working += $counts[$k]['working']; $waiting += $counts[$k]['waiting'] }
      $report = [ordered]@{
        v = 1; device = $device; name = (Clean-Text $cfg['name']); account = (Clean-Text $cfg['account']); updatedAt = $now * 1000
        openSessions = $open; working = $working; waiting = $waiting; tools = $counts
      }
      $json = $report | ConvertTo-Json -Compress -Depth 5
      $code = ''
      try {
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
        # this computer's own key once the server has given it one, else the key of the install package
        # khoá riêng của máy này khi máy chủ đã cấp, nếu không thì khoá của gói cài
        $sendKey = $cfg['key']
        if (Test-Path -LiteralPath $keyFile) {
          $own = ([IO.File]::ReadAllText($keyFile)).Trim()
          if ($own -like 'awd1.*') { $sendKey = $own }
        }
        $answer = Invoke-WebRequest -UseBasicParsing -Method Post -Uri ($cfg['url'] + '/ingest') -Headers @{ Authorization = 'Bearer ' + $sendKey } `
          -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 8
        $code = [string][int]$answer.StatusCode
        # a key of its own in the answer: kept in this user's folder, used from the next send on
        # khoá riêng trong câu trả lời: cất trong thư mục của người dùng này, dùng từ lần gửi sau
        # an answer without a text Content-Type comes as bytes, not a string: read it as UTF-8 either way, like the sh connector
        # câu trả lời không có Content-Type dạng chữ thì tới dưới dạng byte, không phải chuỗi: luôn đọc thành UTF-8, như bộ nối sh
        $body = $answer.Content
        if ($body -is [byte[]]) { $body = $Utf8.GetString($body) }
        if ([string]$body -match '"deviceKey": *"(awd1\.[A-Za-z0-9._-]+)"') { [IO.File]::WriteAllText($keyFile, $Matches[1] + "`n", $Utf8) }
      } catch {
        try { $code = [string][int]$_.Exception.Response.StatusCode } catch { $code = '' }
        # its own key refused (too old, or the server was set up again): drop it, so the next send asks for a new one
        # khoá riêng bị từ chối (quá cũ, hoặc máy chủ được cài lại): bỏ nó, để lần gửi sau xin khoá mới
        if ($code -eq '401' -and $sendKey -ne $cfg['key'] -and (Test-Path -LiteralPath $keyFile)) { Remove-Item -LiteralPath $keyFile -Force }
      }
      if ($code -eq '200') {
        [IO.File]::WriteAllText($sentFile, ('{0} {1}' -f $now, $signature) + "`n", $Utf8)
        if (Test-Path -LiteralPath $errorFile) { Remove-Item -LiteralPath $errorFile -Force }
      } else {
        # kept for the person looking into a board that stays empty: the time and the server's answer, nothing else
        # giữ lại cho người tìm hiểu vì sao bảng vẫn trống: thời điểm và câu trả lời của máy chủ, không gì khác
        if (-not $code) { $code = 'none' }
        [IO.File]::WriteAllText($errorFile, ('{0} http={1}' -f $now, $code) + "`n", $Utf8)
        break
      }
    }
  } finally { $mutex.ReleaseMutex() }
}

try {
  if ($Kind -eq 'send') {
    Send-Report
    exit 0
  }

  $raw = ''
  if ([Console]::IsInputRedirected) {
    try { [Console]::InputEncoding = $Utf8 } catch { }
    $raw = [Console]::In.ReadToEnd()
  }
  $data = $null
  try { $data = $raw | ConvertFrom-Json } catch { }
  # one text field of the event, or nothing
  # một trường chữ của sự kiện, hoặc không có gì
  function Field([string]$name) {
    if ($data -and $data.PSObject.Properties[$name] -and $data.$name -is [string]) { return $data.$name }
    return ''
  }

  $session = ''
  if ($Tool -eq 'codex') { $session = Field 'session_id' }
  elseif ($Tool -eq 'cursor') { $session = Field 'conversation_id' }
  elseif ($env:GEMINI_SESSION_ID) { $session = $env:GEMINI_SESSION_ID }
  else { $session = Field 'session_id' }
  $session = $session -replace '[^A-Za-z0-9_.-]', ''
  if ($session.Length -gt 64) { $session = $session.Substring(0, 64) }
  if (-not $session) { $session = 'unknown' }

  # whether the tool's last message ends with a question mark, allowing for the marks that may follow it
  # câu cuối của công cụ có kết thúc bằng dấu hỏi hay không, tính cả các ký hiệu có thể đứng sau
  $replyField = @{ codex = 'last_assistant_message'; gemini = 'prompt_response'; cursor = 'text' }[$Tool]
  $asked = 0
  if (($Kind -eq 'reply' -or $Kind -eq 'stop') -and ((Field $replyField) -match '[?？][\s*_`)"]*$')) { $asked = 1 }

  # One line per session: tool, session id, state, time of the last event, and a mark: 1 when its last message asked
  # something, 2 when it is waiting for an approval.
  # start opens a session; prompt means working; ask means the tool wants an approval; tool means the approved step ran;
  # reply notes a question; stop ends the turn: waiting when a question is open, idle when not; end closes the session.
  # Mỗi phiên một dòng: công cụ, mã phiên, trạng thái, thời điểm sự kiện cuối, và một dấu: 1 khi câu cuối của nó có hỏi,
  # 2 khi nó đang chờ duyệt.
  # start mở một phiên; prompt là đang làm; ask là công cụ xin duyệt; tool là bước được duyệt đã chạy;
  # reply ghi nhận một câu hỏi; stop kết thúc lượt: đang chờ khi còn câu hỏi, rảnh khi không; end đóng phiên.
  function Next-Line([string]$state, [int]$mark, [long]$now) {
    if ($Kind -eq 'prompt') { $state = 'working'; $mark = 0 }
    elseif ($Kind -eq 'ask') { $state = 'waiting'; $mark = 2 }
    elseif ($Kind -eq 'tool') { if ($state -eq 'waiting' -and $mark -eq 2) { $state = 'working'; $mark = 0 } }
    elseif ($Kind -eq 'reply') { $mark = $asked }
    elseif ($Kind -eq 'stop') { if ($asked -eq 1 -or $mark -eq 1) { $state = 'waiting' } else { $state = 'idle' }; $mark = 0 }
    return ('{0} {1} {2} {3} {4}' -f $Tool, $session, $state, $now, $mark)
  }

  $mutex = New-Object Threading.Mutex($false, (Lock-Name 'state'))
  $held = $false
  try { $held = $mutex.WaitOne(3000) } catch [Threading.AbandonedMutexException] { $held = $true }
  if (-not $held) { exit 0 }
  try {
    $now = Now-Seconds
    $lines = New-Object 'Collections.Generic.List[string]'
    $seen = $false
    foreach ($line in Read-Sessions) {
      $p = $line.Trim() -split '\s+'
      if ($p.Count -lt 4 -or ($now - [long]$p[3]) -ge $SessionSeconds) { continue }
      if ($p[0] -eq $Tool -and $p[1] -eq $session) {
        $seen = $true
        $mark = 0
        if ($p.Count -ge 5) { $mark = [int]$p[4] }
        if ($Kind -ne 'end') { $lines.Add((Next-Line $p[2] $mark $now)) }
        continue
      }
      $lines.Add($line.Trim())
    }
    if (-not $seen -and $Kind -ne 'end') { $lines.Add((Next-Line 'idle' 0 $now)) }
    [IO.File]::WriteAllText($SessionsFile, (($lines | ForEach-Object { $_ + "`n" }) -join ''), $Utf8)
  } finally { $mutex.ReleaseMutex() }

  # send in the background, in a process of its own, so the hook returns at once
  # gửi ở nền, trong một tiến trình riêng, để hook trả về ngay
  $exe = (Get-Process -Id $PID).Path
  Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), $Tool, 'send') | Out-Null
} catch {
  # a hook must never get in the tool's way: whatever went wrong here stays here
  # hook không bao giờ được cản trở công cụ: mọi trục trặc ở đây dừng lại ở đây
}
exit 0
