# Show Codex, Cursor and Gemini CLI on the AI Worker board, on Windows. Claude Code is not needed.
# Cho Codex, Cursor và Gemini CLI hiện lên bảng AI Worker, trên Windows. Không cần có Claude Code.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1               asks what it needs
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall    takes everything out again
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Status       shows what is installed and what the board last answered
#   powershell -ExecutionPolicy Bypass -File install.ps1               hỏi những gì nó cần
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall    gỡ sạch mọi thứ
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Status       cho biết đã cài gì và lần gần nhất bảng trả lời gì
#
# Options, so it can run without asking: -Server URL  -Key KEY  -Name NAME  -Account EMAIL  -Tools codex,cursor,gemini  -Skills | -NoSkills
# Tuỳ chọn, để chạy không cần hỏi: -Server URL  -Key KEY  -Name NAME  -Account EMAIL  -Tools codex,cursor,gemini  -Skills | -NoSkills
#
# It adds its hooks to each tool's own settings and leaves every other line of them alone; a copy of the file
# as it was is kept next to it, ending in .ai-worker-backup.
# Nó thêm hook của mình vào cấu hình của từng công cụ và để nguyên mọi dòng khác; một bản sao của file
# như lúc trước được giữ ngay bên cạnh, tên kết thúc bằng .ai-worker-backup.
param([string]$Server = '', [string]$Key = '', [string]$Name = '', [string]$Account = '', [string]$Tools = '',
  [switch]$Skills, [switch]$NoSkills, [switch]$Uninstall, [switch]$Status)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Here = $PSScriptRoot
foreach ($f in @((Join-Path $Here '..\..\lang.ps1'), (Join-Path $Here '..\packaging\lang.ps1'), (Join-Path $Here 'lang.ps1'))) {
  if (Test-Path -LiteralPath $f) { . $f; break }
}
if (-not (Get-Command Say-Text -ErrorAction SilentlyContinue)) {
  function Say-Text([string]$En, [string]$Vi, [switch]$AsString, [switch]$NoNewline) { if ($AsString) { return $En }; Write-Host $En }
}

$UserHome = $env:USERPROFILE
$Dir = if ($env:AI_WORKER_CONNECTOR_DIR) { $env:AI_WORKER_CONNECTOR_DIR } else { Join-Path $UserHome '.local\share\ai-worker\connector' }
$Hook = Join-Path $Dir 'ai-worker-hook.ps1'
$SkillsDir = Join-Path $UserHome '.agents\skills'
# skills that work in any of these tools; two more lean on Claude Code and stay out
# các skill chạy được trong mọi công cụ này; còn hai skill dựa vào Claude Code nên không chép
$PortableSkills = 'browser-testing-with-devtools codebase-design diagnosing-bugs domain-modeling draw-flow grilling handoff interview-me lesson-generator meeting-notes qa-site qa-test security-audit tdd ui-ux-pro-max write-spec'
$Mark = 'ai-worker-hook'
$TomlBegin = '# >>> ai-worker connector: added by connectors/install.ps1, removed by install.ps1 -Uninstall >>>'
$TomlEnd = '# <<< ai-worker connector <<<'
$Utf8 = New-Object Text.UTF8Encoding($false)
$ToolNames = @{ codex = 'Codex'; gemini = 'Gemini CLI'; cursor = 'Cursor' }
# The events of each tool and what they mean here: "ToolEvent=ours". Ours: start, prompt, ask, tool, reply, stop, end.
# Các sự kiện của từng công cụ và nghĩa của chúng ở đây: "SựKiệnCủaCôngCụ=của ta". Của ta: start, prompt, ask, tool, reply, stop, end.
$Events = @{
  codex = 'SessionStart=start UserPromptSubmit=prompt PermissionRequest=ask PostToolUse=tool Stop=stop Interrupt=stop SessionEnd=end'
  gemini = 'SessionStart=start BeforeAgent=prompt Notification=ask AfterTool=tool AfterAgent=stop SessionEnd=end'
  cursor = 'sessionStart=start beforeSubmitPrompt=prompt afterAgentResponse=reply stop=stop sessionEnd=end'
}

function Ask([string]$question) {
  Write-Host "${question}: " -NoNewline
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { return '' }
  return $line
}

function Read-Text([string]$path) { if (Test-Path -LiteralPath $path) { return [IO.File]::ReadAllText($path, $Utf8) }; return '' }
function Write-Text([string]$path, [string]$text) { [IO.File]::WriteAllText($path, $text, $Utf8) }
function Config-Value([string]$name) {
  foreach ($line in ((Read-Text (Join-Path $Dir 'config')) -split "`r?`n")) { if ($line.StartsWith("$name=")) { return $line.Substring($name.Length + 1) } }
  return ''
}
function Json-Value([string]$path, [string]$name) {
  if ((Read-Text $path) -match ('"' + $name + '"\s*:\s*"([^"]*)"')) { return $Matches[1] }
  return ''
}
function Clean-Text([string]$text) { ((($text -replace '["\\]', '') -replace '[\x00-\x1f]', ' ')).Trim() }

function Settings-File([string]$tool) {
  if ($tool -eq 'codex') { return (Join-Path $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserHome '.codex' }) 'hooks.json') }
  if ($tool -eq 'gemini') { return (Join-Path $UserHome '.gemini\settings.json') }
  return (Join-Path $UserHome '.cursor\hooks.json')
}

function Tool-Found([string]$tool) {
  $folder = Split-Path -Parent (Settings-File $tool)
  $commands = @{ codex = @('codex'); gemini = @('gemini'); cursor = @('cursor', 'cursor-agent') }[$tool]
  foreach ($c in $commands) { if (Get-Command $c -ErrorAction SilentlyContinue) { return $true } }
  return (Test-Path -LiteralPath $folder)
}

# the command a tool runs for one event
# lệnh một công cụ chạy cho một sự kiện
function Hook-Command([string]$tool, [string]$ours) { 'powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" {1} {2}' -f $Hook, $tool, $ours }

# Codex gives the hooks of these two events 3 seconds at most
# Codex cho hook của hai sự kiện này nhiều nhất 3 giây
function Codex-Timeout([string]$toolEvent) { if ($toolEvent -eq 'SessionEnd' -or $toolEvent -eq 'Interrupt') { return 3 }; return 5 }

# our hooks alone, in the shape the tool's settings file wants
# riêng các hook của ta, đúng dạng file cấu hình của công cụ đó cần
function Our-Hooks([string]$tool) {
  $hooks = [ordered]@{}
  foreach ($pair in ($Events[$tool] -split ' ')) {
    $toolEvent, $ours = $pair -split '='
    $command = Hook-Command $tool $ours
    if ($tool -eq 'codex') { $entry = [ordered]@{ hooks = @([ordered]@{ type = 'command'; command = $command; timeout = (Codex-Timeout $toolEvent) }) } }
    elseif ($tool -eq 'gemini') { $entry = [ordered]@{ hooks = @([ordered]@{ name = "ai-worker-$ours"; type = 'command'; command = $command; timeout = 5000 }) } }
    else { $entry = [ordered]@{ command = $command; timeout = 5 } }
    $hooks[$toolEvent] = @($entry)
  }
  return $hooks
}

function Our-Toml {
  $lines = @($TomlBegin)
  foreach ($pair in ($Events['codex'] -split ' ')) {
    $toolEvent, $ours = $pair -split '='
    $lines += "[[hooks.$toolEvent]]", "[[hooks.$toolEvent.hooks]]", 'type = "command"', ("command = '" + (Hook-Command 'codex' $ours) + "'"), ('timeout = ' + (Codex-Timeout $toolEvent))
  }
  return ($lines + $TomlEnd)
}

# JSON read into ordered tables and lists, so the file keeps its order and a list of one stays a list
# JSON đọc thành bảng có thứ tự và danh sách, để file giữ nguyên thứ tự và danh sách một phần tử vẫn là danh sách
function To-Tree($node) {
  if ($null -eq $node) { return $null }
  if ($node -is [string] -or $node -is [ValueType]) { return $node }
  if ($node -is [Collections.IEnumerable] -and $node -isnot [Collections.IDictionary]) {
    $list = New-Object Collections.ArrayList
    foreach ($item in $node) { [void]$list.Add((To-Tree $item)) }
    return , $list
  }
  $table = [ordered]@{}
  foreach ($p in $node.PSObject.Properties) { $table[$p.Name] = To-Tree $p.Value }
  return $table
}

function Read-Json([string]$path) {
  $text = Read-Text $path
  # newer PowerShell reads JSON with comments and would then write the file back without them: such a file is left alone
  # PowerShell bản mới đọc được JSON có chú thích rồi sẽ ghi file lại không còn chú thích: file như vậy được để nguyên
  if ($text -match '(?m)^\s*(//|/\*)') { throw 'not plain JSON' }
  $tree = To-Tree ($text | ConvertFrom-Json)
  if ($tree -isnot [Collections.IDictionary]) { throw 'not a JSON object' }
  if ($tree.Contains('hooks') -and $tree['hooks'] -isnot [Collections.IDictionary]) { throw 'hooks is not an object' }
  return $tree
}

function Is-Ours($entry) { return ($entry -is [Collections.IDictionary] -and $entry['command'] -is [string] -and $entry['command'].Contains($Mark)) }

# One event's list without our hooks. Codex and Gemini CLI keep hooks inside groups, Cursor keeps them flat.
# A group is dropped only when taking our hook out left it empty.
# Danh sách của một sự kiện sau khi bỏ hook của ta. Codex và Gemini CLI để hook trong nhóm, Cursor để phẳng.
# Một nhóm chỉ bị bỏ khi việc gỡ hook của ta làm nó rỗng.
function Without-Ours($list) {
  $out = New-Object Collections.ArrayList
  foreach ($entry in $list) {
    if (Is-Ours $entry) { continue }
    if ($entry -is [Collections.IDictionary] -and $entry['hooks'] -is [Collections.IList] -and @($entry['hooks'] | Where-Object { Is-Ours $_ }).Count) {
      $rest = New-Object Collections.ArrayList
      foreach ($h in $entry['hooks']) { if (-not (Is-Ours $h)) { [void]$rest.Add($h) } }
      if ($rest.Count) { $entry['hooks'] = $rest; [void]$out.Add($entry) }
      continue
    }
    [void]$out.Add($entry)
  }
  return , $out
}

# take our hooks out of the tree; with $ours given, put the fresh ones in
# gỡ hook của ta khỏi cây; có $ours thì đặt các hook mới vào
function Merge-Hooks($tree, $ours) {
  if (-not $tree.Contains('hooks')) { $tree['hooks'] = [ordered]@{} }
  $hooks = $tree['hooks']
  foreach ($toolEvent in @($hooks.Keys)) {
    if ($hooks[$toolEvent] -isnot [Collections.IList]) { continue }
    $hooks[$toolEvent] = Without-Ours $hooks[$toolEvent]
    if (-not $hooks[$toolEvent].Count) { $hooks.Remove($toolEvent) }
  }
  if ($ours) {
    foreach ($toolEvent in $ours.Keys) {
      $list = New-Object Collections.ArrayList
      if ($hooks.Contains($toolEvent) -and $hooks[$toolEvent] -is [Collections.IList]) { foreach ($e in $hooks[$toolEvent]) { [void]$list.Add($e) } }
      foreach ($e in $ours[$toolEvent]) { [void]$list.Add($e) }
      $hooks[$toolEvent] = $list
    }
  } elseif (-not $hooks.Count) { $tree.Remove('hooks') }
  return $tree
}

function Write-Json([string]$path, $tree) { Write-Text $path (($tree | ConvertTo-Json -Depth 30) + "`n") }

function Keep-Backup([string]$path) {
  if ((Test-Path -LiteralPath $path) -and -not (Test-Path -LiteralPath "$path.ai-worker-backup")) { Copy-Item -LiteralPath $path -Destination "$path.ai-worker-backup" }
}

# config.toml without our block, and without the empty line the installer put in front of it
# config.toml không có khối của ta, và không có dòng trống mà bộ cài đặt trước khối đó
function Newline-Of([string]$text) { if ($text.Contains("`r`n")) { return "`r`n" }; return "`n" }

function Without-Toml-Block([string]$path) {
  $out = New-Object Collections.ArrayList
  $skip = $false
  $text = Read-Text $path
  foreach ($line in ($text -split "`r?`n")) {
    if ($line -eq $TomlBegin) {
      $skip = $true
      if ($out.Count -and $out[$out.Count - 1] -eq '') { $out.RemoveAt($out.Count - 1) }
    }
    if (-not $skip) { [void]$out.Add($line) }
    if ($line -eq $TomlEnd) { $skip = $false }
  }
  return ($out -join (Newline-Of $text))
}

function Has-Toml-Block([string]$path) { return ((Read-Text $path) -split "`r?`n") -contains $TomlBegin }

function Install-Tool([string]$tool) {
  $file = Settings-File $tool
  $folder = Split-Path -Parent $file
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  $toolName = $ToolNames[$tool]
  if ($tool -eq 'codex') {
    $toml = Join-Path $folder 'config.toml'
    # hooks already live in config.toml: ours go there too, because Codex warns when it finds hooks in both files
    # hook đã nằm sẵn trong config.toml: hook của ta cũng vào đó, vì Codex cảnh báo khi thấy hook ở cả hai file
    if (-not (Test-Path -LiteralPath $file) -and ((Read-Text $toml) -match '(?m)^\s*\[\[hooks\.')) {
      Keep-Backup $toml
      $nl = Newline-Of (Read-Text $toml)
      $text = (Without-Toml-Block $toml).TrimEnd("`r", "`n")
      Write-Text $toml ($text + $nl + $nl + ((Our-Toml) -join $nl) + $nl)
      Say-Text "  Codex: hooks added to $toml" "  Codex: đã thêm hook vào $toml"
      return $true
    }
    # hooks of ours left in config.toml by an earlier install would run twice
    # hook của ta còn trong config.toml từ lần cài trước sẽ chạy hai lần
    if (Has-Toml-Block $toml) { Write-Text $toml (Without-Toml-Block $toml) }
  }
  $ours = Our-Hooks $tool
  if (-not (Test-Path -LiteralPath $file) -or -not (Read-Text $file).Trim()) {
    $tree = [ordered]@{}
    if ($tool -eq 'cursor') { $tree['version'] = 1 }
    $tree['hooks'] = $ours
    Write-Json $file $tree
  } else {
    try { $tree = Read-Json $file } catch {
      Say-Text "  Could not change $file safely. Add these hooks to it by hand, next to what is already there:" "  Không sửa $file một cách an toàn được. Hãy tự thêm các hook này vào file, bên cạnh những gì đã có:"
      Write-Host (([ordered]@{ hooks = $ours }) | ConvertTo-Json -Depth 30)
      return $false
    }
    Keep-Backup $file
    if ($tool -eq 'cursor' -and -not $tree.Contains('version')) { $tree['version'] = 1 }
    Write-Json $file (Merge-Hooks $tree $ours)
  }
  Say-Text "  ${toolName}: hooks added to $file" "  ${toolName}: đã thêm hook vào $file"
  return $true
}

function Remove-Tool([string]$tool) {
  $file = Settings-File $tool
  $toolName = $ToolNames[$tool]
  if ($tool -eq 'codex') {
    $toml = Join-Path (Split-Path -Parent $file) 'config.toml'
    if (Has-Toml-Block $toml) {
      Write-Text $toml (Without-Toml-Block $toml)
      Say-Text "  Codex: hooks removed from $toml" "  Codex: đã gỡ hook khỏi $toml"
    }
  }
  if (-not (Read-Text $file).Contains($Mark)) { return }
  try { $tree = Merge-Hooks (Read-Json $file) $null } catch {
    Say-Text "  Could not change $file safely. Remove by hand the hooks in it whose command holds $Mark." "  Không sửa $file một cách an toàn được. Hãy tự gỡ các hook trong đó có lệnh chứa $Mark."
    return
  }
  # a file that held our hooks and nothing else was made by this installer: it goes away whole
  # file chỉ chứa hook của ta thì do chính bộ cài này tạo: bỏ cả file
  if (-not @($tree.Keys | Where-Object { $_ -ne 'version' -and $_ -ne 'description' }).Count) {
    Remove-Item -LiteralPath $file -Force
    # and the folder too when the installer made it and nothing else is in it
    # và cả thư mục khi chính bộ cài tạo ra nó và trong đó không còn gì khác
    $folder = Split-Path -Parent $file
    if (-not @(Get-ChildItem -LiteralPath $folder -Force).Count) { Remove-Item -LiteralPath $folder -Force }
  } else { Write-Json $file $tree }
  Say-Text "  ${toolName}: hooks removed from $file" "  ${toolName}: đã gỡ hook khỏi $file"
}

function Tool-Installed([string]$tool) {
  if ((Read-Text (Settings-File $tool)).Contains($Mark)) { return $true }
  return ($tool -eq 'codex' -and (Has-Toml-Block (Join-Path (Split-Path -Parent (Settings-File 'codex')) 'config.toml')))
}

# send what the session file says right now, and tell the person what the board answered
# gửi đúng những gì file phiên đang ghi, và cho người dùng biết bảng trả lời gì
function Send-Now([switch]$Quiet) {
  $sent = Join-Path $Dir 'sent'
  $failed = Join-Path $Dir 'last-error'
  foreach ($f in @($sent, $failed)) { if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force } }
  $env:AI_WORKER_CONNECTOR_DIR = $Dir
  & (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File $Hook codex send | Out-Null
  if ($Quiet) { return }
  if (Test-Path -LiteralPath $sent) {
    Say-Text 'The board answered: received.' 'Bảng trả lời: đã nhận.'
    return
  }
  $code = ''
  if ((Read-Text $failed) -match 'http=(\S+)') { $code = $Matches[1] }
  if ($code -eq '401') {
    Say-Text 'The board refused the send key (401). Check the key and run this again.' 'Bảng từ chối khoá gửi (401). Kiểm tra lại khoá rồi chạy lại.'
  } elseif ($code -eq '409') {
    Say-Text 'The board says this computer is tied to another name (409). Ask the admin to forget this device, or use the same name and email as before.' 'Bảng báo máy này đã gắn với một tên khác (409). Nhờ quản trị viên xoá máy này khỏi bảng, hoặc dùng đúng tên và email như trước.'
  } elseif ($code -eq '429' -or $code -eq '507') {
    Say-Text "The board has reached a limit ($code). Try again tomorrow, or ask the admin." "Bảng đã chạm giới hạn ($code). Thử lại vào ngày mai, hoặc hỏi quản trị viên."
  } else {
    Say-Text "The board could not be reached (answer: $code). The hooks are installed and will try again at the next event." "Chưa tới được bảng (trả lời: $code). Hook đã cài và sẽ thử lại ở sự kiện kế tiếp."
  }
}

if ($Status) {
  if (-not (Test-Path -LiteralPath (Join-Path $Dir 'config'))) {
    Say-Text 'The connector is not installed on this computer.' 'Bộ nối chưa được cài trên máy này.'
    exit 0
  }
  Say-Text "Board: $(Config-Value 'url') · name: $(Config-Value 'name')" "Bảng: $(Config-Value 'url') · tên: $(Config-Value 'name')"
  foreach ($tool in @('codex', 'cursor', 'gemini')) {
    $toolName = $ToolNames[$tool]
    if (Tool-Installed $tool) {
      Say-Text "  ${toolName}: hooks installed" "  ${toolName}: đã cài hook"
    }
  }
  $failedText = (Read-Text (Join-Path $Dir 'last-error')).Trim()
  if ($failedText) {
    Say-Text "Last send failed: $failedText" "Lần gửi gần nhất hỏng: $failedText"
  }
  $sentText = (Read-Text (Join-Path $Dir 'sent')).Trim()
  if ($sentText) {
    $when = [DateTimeOffset]::FromUnixTimeSeconds([long]($sentText -split ' ')[0]).LocalDateTime
    Say-Text "Last send received by the board: $when" "Lần gửi gần nhất bảng đã nhận: $when"
  }
  exit 0
}

if ($Uninstall) {
  Say-Text '== Removing the AI Worker connector ==' '== Gỡ bộ nối AI Worker =='
  foreach ($tool in @('codex', 'cursor', 'gemini')) { Remove-Tool $tool }
  # tell the board that no session is open here any more, so the person does not stay "waiting" for two hours
  # báo cho bảng biết ở đây không còn phiên nào mở, để người dùng không bị hiện "đang chờ" suốt hai giờ
  if ((Test-Path -LiteralPath (Join-Path $Dir 'config')) -and (Test-Path -LiteralPath $Hook)) {
    Write-Text (Join-Path $Dir 'sessions') ''
    try { Send-Now -Quiet } catch { }
  }
  $listFile = Join-Path $Dir 'skills-installed'
  if (Test-Path -LiteralPath $listFile) {
    foreach ($skill in ((Read-Text $listFile) -split "`r?`n")) {
      if ($skill -notmatch '^[a-z0-9][a-z0-9-]*$') { continue }
      $target = Join-Path $SkillsDir $skill
      if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    }
    foreach ($folder in @($SkillsDir, (Split-Path -Parent $SkillsDir))) {
      if ((Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force).Count) { Remove-Item -LiteralPath $folder -Force }
    }
    Say-Text "  Skills removed from $SkillsDir" "  Đã gỡ các skill khỏi $SkillsDir"
  }
  if (Test-Path -LiteralPath $Dir) { Remove-Item -LiteralPath $Dir -Recurse -Force }
  Say-Text 'Done. Codex, Cursor and Gemini CLI no longer send anything to the board.' 'Xong. Codex, Cursor và Gemini CLI không còn gửi gì lên bảng.'
  $backups = @('codex', 'cursor', 'gemini' | ForEach-Object { (Settings-File $_) + '.ai-worker-backup' }) + (Join-Path (Split-Path -Parent (Settings-File 'codex')) 'config.toml.ai-worker-backup')
  foreach ($f in $backups) {
    if (Test-Path -LiteralPath $f) {
      Say-Text "A copy of your settings from before the install is still at $f; delete it when you no longer need it." "Bản sao cấu hình của bạn từ trước khi cài vẫn còn ở $f; xoá đi khi không cần nữa."
    }
  }
  exit 0
}

Say-Text '== AI Worker: show Codex, Cursor and Gemini CLI on the board ==' '== AI Worker: cho Codex, Cursor và Gemini CLI hiện lên bảng =='
Say-Text 'What is sent: your name and email, a random id for this computer, and for each tool how many sessions are open, working or waiting.' 'Thứ được gửi: tên và email của bạn, một mã ngẫu nhiên của máy này, và với mỗi công cụ là số phiên đang mở, đang làm, đang chờ.'
Say-Text 'Never sent: prompts, answers, file names, folders or project names.' 'Không bao giờ gửi: câu hỏi, câu trả lời, tên file, thư mục hay tên dự án.'
Write-Host ''

# the board and its send key: what was given, else what an earlier install saved, else the company package this file came in
# bảng và khoá gửi: thứ được truyền vào, không có thì lấy của lần cài trước, không có nữa thì lấy trong gói công ty chứa file này
if (-not $Server) { $Server = if ($env:AI_WORKER_URL) { $env:AI_WORKER_URL } else { Config-Value 'url' } }
if (-not $Key) { $Key = if ($env:AI_WORKER_KEY) { $env:AI_WORKER_KEY } else { Config-Value 'key' } }
foreach ($f in @((Join-Path $Here '..\web\company.json'), (Join-Path $UserHome 'claude-plugins-ai-worker\ai-worker\web\company.json'))) {
  if (-not $Server) { $Server = Json-Value $f 'webhook' }
  if (-not $Key) { $Key = Json-Value $f 'ingestKey' }
}
if (-not $Server) {
  $Server = Ask (
    Say-Text -AsString 'Address of the board (for example https://board.example.com)' 'Địa chỉ của bảng (ví dụ https://board.example.com)')
}
$Server = (($Server -replace '\s', '') -replace '/+$', '')
if ($Server -notmatch '^https?://') {
  Say-Text 'The address must start with http:// or https://' 'Địa chỉ phải bắt đầu bằng http:// hoặc https://'
  exit 1
}
if (-not $Key) {
  $Key = Ask (
    Say-Text -AsString 'Send key of the board (ask the person who runs it)' 'Khoá gửi của bảng (hỏi người quản trị bảng)')
}
$Key = $Key -replace '[\s"\\]', ''
if (-not $Key) {
  Say-Text 'A send key is needed.' 'Cần có khoá gửi.'
  exit 1
}

# the name and email: the same ones the Claude Code plugin uses on this computer, so one person stays one row on the board
# tên và email: đúng cặp mà plugin Claude Code dùng trên máy này, để một người vẫn là một dòng trên bảng
$UserFile = Join-Path $UserHome '.local\share\ai-worker\user.json'
if (-not $Name) { $Name = Config-Value 'name' }
if (-not $Name) { $Name = Json-Value $UserFile 'name' }
if (-not $Account) { $Account = Config-Value 'account' }
if (-not $Account) { $Account = Json-Value $UserFile 'account' }
if (-not $Name) {
  while (-not $Name.Trim()) {
    $Name = Ask (
      Say-Text -AsString 'Your full name, as the board should show it' 'Họ tên của bạn, như bảng sẽ hiện')
  }
  if (-not $Account) {
    $Account = Ask (
      Say-Text -AsString 'Your work email (Enter to skip)' 'Email công việc của bạn (Enter để bỏ qua)')
  }
}
$Name = Clean-Text $Name
$Account = ((Clean-Text $Account) -replace '\s', '').ToLower()
if (-not $Name) {
  Say-Text 'A name is needed.' 'Cần có tên.'
  exit 1
}

# which tools: the ones named, else ask about each one found on this computer
# công cụ nào: những cái được nêu tên, không có thì hỏi về từng cái tìm thấy trên máy này
$Chosen = @()
if ($Tools) {
  foreach ($tool in ($Tools -split '[,\s]+' | Where-Object { $_ })) {
    if (@('codex', 'cursor', 'gemini') -notcontains $tool) {
      Say-Text "Unknown tool: $tool" "Công cụ không rõ: $tool"
      exit 2
    }
    $Chosen += $tool
  }
} else {
  foreach ($tool in @('codex', 'cursor', 'gemini')) {
    $toolName = $ToolNames[$tool]
    if (Tool-Found $tool) {
      $reply = Ask (
        Say-Text -AsString "Show $toolName on the board? (Enter = yes, type n = no)" "Cho $toolName hiện lên bảng? (Enter = có, gõ n = không)")
      if ($reply.Trim().ToLower() -ne 'n') { $Chosen += $tool }
    } else {
      Say-Text "${toolName}: not found on this computer, skipped." "${toolName}: không thấy trên máy này, bỏ qua."
    }
  }
}
if (-not $Chosen.Count) {
  Say-Text 'No tool chosen: nothing was changed.' 'Không chọn công cụ nào: không có gì thay đổi.'
  exit 0
}

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Copy-Item -LiteralPath (Join-Path $Here 'ai-worker-hook.ps1') -Destination $Hook -Force
# a copy of this installer stays with the hook, so removing still works after the package it came in is gone
# một bản sao của bộ cài này nằm cạnh hook, để việc gỡ vẫn chạy được sau khi gói chứa nó đã bị xoá
if ((Resolve-Path -LiteralPath $Here).Path -ne (Resolve-Path -LiteralPath $Dir).Path) {
  Copy-Item -LiteralPath (Join-Path $Here 'install.ps1') -Destination (Join-Path $Dir 'install.ps1') -Force
  foreach ($f in @((Join-Path $Here '..\..\lang.ps1'), (Join-Path $Here '..\packaging\lang.ps1'))) {
    if (Test-Path -LiteralPath $f) { Copy-Item -LiteralPath $f -Destination (Join-Path $Dir 'lang.ps1') -Force; break }
  }
}
# the send key is the only secret here; the folder sits in the person's own profile, which other accounts cannot read
# khoá gửi là thứ bí mật duy nhất ở đây; thư mục nằm trong hồ sơ riêng của người dùng, tài khoản khác không đọc được
Write-Text (Join-Path $Dir 'config') ("url=$Server`nkey=$Key`nname=$Name`naccount=$Account`n")
if (-not (Test-Path -LiteralPath (Join-Path $Dir 'sessions'))) { Write-Text (Join-Path $Dir 'sessions') '' }

Say-Text "Installing for: $($Chosen -join ' ')" "Cài cho: $($Chosen -join ' ')"
$Failed = @()
$Done = @()
foreach ($tool in @('codex', 'cursor', 'gemini')) {
  if ($Chosen -contains $tool) {
    if (Install-Tool $tool) { $Done += $tool } else { $Failed += $tool }
  } else { Remove-Tool $tool }
}

# the skills: only when asked for, and never over a folder this installer did not put there
# các skill: chỉ khi được yêu cầu, và không bao giờ đè lên thư mục không do bộ cài này đặt vào
$SkillsSource = Join-Path $Here '..\skills'
$WantSkills = [bool]$Skills
if (-not $Skills -and -not $NoSkills -and (Test-Path -LiteralPath $SkillsSource) -and -not [Console]::IsInputRedirected) {
  $reply = Ask (
    Say-Text -AsString "Also copy the AI Worker skills to $SkillsDir, where Codex, Cursor and Gemini CLI read skills? (type y = yes, Enter = no)" "Chép thêm các skill của AI Worker vào $SkillsDir, nơi Codex, Cursor và Gemini CLI đọc skill? (gõ y = có, Enter = không)")
  $WantSkills = ($reply.Trim().ToLower() -eq 'y')
}
if ($WantSkills -and (Test-Path -LiteralPath $SkillsSource)) {
  New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
  $listFile = Join-Path $Dir 'skills-installed'
  $mine = @((Read-Text $listFile) -split "`r?`n" | Where-Object { $_ })
  $copied = 0
  foreach ($skill in ($PortableSkills -split ' ')) {
    $source = Join-Path $SkillsSource $skill
    if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) { continue }
    $target = Join-Path $SkillsDir $skill
    if ((Test-Path -LiteralPath $target) -and ($mine -notcontains $skill)) {
      Say-Text "  Skill ${skill}: a folder with this name is already there, left as it is." "  Skill ${skill}: đã có thư mục cùng tên, để nguyên."
      continue
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    $copied++
    if ($mine -notcontains $skill) { $mine += $skill }
  }
  Write-Text $listFile (($mine -join "`n") + "`n")
  Say-Text "  $copied skills copied to $SkillsDir" "  Đã chép $copied skill vào $SkillsDir"
}

Write-Host ''
Send-Now
Write-Host ''
if ($Done -contains 'codex') {
  Say-Text 'One more step for Codex, which runs a hook only after you have looked at it:' 'Còn một bước với Codex, vì Codex chỉ chạy hook sau khi bạn đã xem qua:'
  Say-Text '  1. Open a terminal and type: codex' '  1. Mở cửa sổ lệnh và gõ: codex'
  Say-Text '  2. In Codex type /hooks and press Enter. You see seven hooks whose command holds ai-worker-hook.ps1.' '  2. Trong Codex gõ /hooks rồi nhấn Enter. Bạn thấy bảy hook có lệnh chứa ai-worker-hook.ps1.'
  Say-Text '  3. Trust each of them. From then on your Codex sessions show on the board.' '  3. Bấm tin cậy từng hook. Từ đó các phiên Codex của bạn hiện trên bảng.'
}
if ($Done -contains 'cursor' -or $Done -contains 'gemini') {
  Say-Text 'Cursor and Gemini CLI pick the hooks up at their next start: close and reopen them.' 'Cursor và Gemini CLI nhận hook ở lần mở kế tiếp: hãy đóng rồi mở lại.'
}
Say-Text "To remove everything later: powershell -ExecutionPolicy Bypass -File `"$Dir\install.ps1`" -Uninstall" "Muốn gỡ sạch sau này: powershell -ExecutionPolicy Bypass -File `"$Dir\install.ps1`" -Uninstall"
if ($Failed.Count) { exit 1 }
exit 0
