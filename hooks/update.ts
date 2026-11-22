// Updating the plugin from the company server: the signed manifest is what is trusted, never the server.
// Cập nhật plugin từ máy chủ công ty: manifest có chữ ký là thứ được tin, không bao giờ là máy chủ.

export type Manifest = { version: string; name: string; sha256: string; date: number }

/** A manifest in exactly the shape the release script writes; anything else is no manifest. */
/** Một manifest đúng dạng mà script phát hành ghi; bất cứ thứ gì khác đều không phải manifest. */
export function parseManifest(text: string): Manifest | undefined {
  try {
    const m = JSON.parse(text) as Record<string, unknown>
    const { version, name, sha256, date } = m
    if (typeof version !== 'string' || !/^[0-9A-Za-z.-]{1,20}$/.test(version)) return undefined
    if (typeof name !== 'string' || name !== `ai-worker-${version}.zip`) return undefined
    if (typeof sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(sha256)) return undefined
    if (typeof date !== 'number' || !Number.isInteger(date) || date <= 0) return undefined
    return { version, name, sha256, date }
  } catch {
    return undefined
  }
}

/** Offer it if it differs (an older version is how IT rolls back) and is no older than the last one accepted, so an old signed file cannot be replayed. */
/** Đưa ra nếu nó khác (bản cũ hơn là cách người quản trị quay lui) và không cũ hơn bản đã nhận lần trước, để file cũ có chữ ký không bị phát lại. */
export function shouldOfferUpdate(m: Manifest, current: string | undefined, lastAcceptedDate: number): boolean {
  return m.version !== current && m.date >= lastAcceptedDate
}

export type SignatureResult = 'valid' | 'invalid' | 'unsupported'

/** What ssh-keygen -Y verify said. An OpenSSH too old for -Y refuses the option: not the same as a bad signature. */
/** Kết quả của ssh-keygen -Y verify. OpenSSH quá cũ không hỗ trợ -Y sẽ từ chối tuỳ chọn đó: không giống một chữ ký sai. */
export function parseSignatureResult(r: { exitCode: number; stdout: string; stderr?: string }): SignatureResult {
  if (r.exitCode === 0) return 'valid'
  return /unknown option|illegal option|usage:/i.test(`${r.stdout}\n${r.stderr ?? ''}`) ? 'unsupported' : 'invalid'
}

/** Whether an allowed_signers file holds a key; a file of comments alone verifies nothing. */
/** Một file allowed_signers có chứa khoá hay không; file chỉ toàn dòng chú thích thì không xác minh được gì. */
export function hasSigningKeys(text: string): boolean {
  return text.split(/\r?\n/).some(line => line.trim() && !line.trim().startsWith('#'))
}

/** The keys to fetch a release with, in order: this computer's own key first, which a server lets through from any network when an admin allowed it, then the shared key of the install package. */
/** Các khoá để tải một bản phát hành, theo thứ tự: khoá riêng của máy này trước, khoá mà máy chủ cho qua từ mọi mạng khi quản trị đã cho phép, rồi khoá chung của gói cài. */
export function releaseKeys(own: unknown, shared: string): string[] {
  const mine = typeof own === 'string' && /^awd1(\.[A-Za-z0-9_-]{1,64}){7}$/.test(own) ? own : ''
  return [...new Set([mine, shared].filter(Boolean))]
}

/** The hash in shasum, sha256sum or certutil output; certutil may space its bytes. */
/** Mã băm trong kết quả của shasum, sha256sum hoặc certutil; certutil có thể chèn dấu cách giữa các byte. */
export function parseHash(out: string): string | undefined {
  for (const line of out.split(/\r?\n/)) {
    const m = /^([0-9a-fA-F]{2} ?){32}/.exec(line.trim())
    if (m) return m[0].replace(/ /g, '').toLowerCase()
  }
  return undefined
}

/** The Claude desktop app's bundle id on a Mac: only this app is ever closed and opened again. */
/** Mã bundle của app Claude trên Mac: chỉ app này mới được đóng rồi mở lại. */
export const DESKTOP_BUNDLE_ID = 'com.anthropic.claudefordesktop'

/**
 * The app a process runs in, from `ps -axo pid=,ppid=,comm=`: its topmost ancestor (the one launchd started),
 * when that is an app bundle's main program. A session in a terminal ends at the terminal app, so the caller
 * still checks the bundle id.
 */
/** App mà một tiến trình chạy trong đó, đọc từ `ps -axo pid=,ppid=,comm=`: tổ tiên trên cùng (cái launchd khởi động), khi đó là chương trình chính của một app. Phiên chạy trong terminal thì dừng ở app terminal, nên nơi gọi vẫn phải kiểm mã bundle. */
export function findHostApp(psTable: string, fromPid: number): { pid: number; app: string } | undefined {
  const rows = new Map<number, { ppid: number; comm: string }>()
  for (const line of psTable.split(/\r?\n/)) {
    const m = /^\s*(\d+)\s+(\d+)\s+(.+?)\s*$/.exec(line)
    if (m) rows.set(Number(m[1]), { ppid: Number(m[2]), comm: m[3]! })
  }
  let pid = fromPid
  // a table that loops (it never should) must not hang the session
  // bảng bị vòng lặp (không bao giờ nên có) cũng không được làm treo phiên
  for (let hops = 0; hops < 64; hops++) {
    const row = rows.get(pid)
    if (!row) return undefined
    if (row.ppid === 1) {
      const m = /^(\/.+\.app)\/Contents\/MacOS\/[^/]+$/.exec(row.comm)
      return m ? { pid, app: m[1]! } : undefined
    }
    pid = row.ppid
  }
  return undefined
}

/**
 * Runs the rest of its arguments as a program of its own session, with no input or output, and returns at once:
 * the program outlives the app that started it.
 */
/** Chạy phần tham số còn lại thành một chương trình có phiên riêng, không có đầu vào hay đầu ra, rồi trả về ngay: chương trình sống lâu hơn app đã khởi động nó. */
export const DETACH_PERL = 'exit 0 if fork; POSIX::setsid(); open STDIN, "</dev/null"; open STDOUT, ">/dev/null"; open STDERR, ">/dev/null"; exec @ARGV'

/**
 * Asks the app ($1, a process id) to quit the way Cmd+Q does, waits for it to go, then opens it again ($2, the
 * app's folder). An app still open after 30 seconds is asking the person something: it is left alone.
 */
/** Bảo app ($1, mã tiến trình) thoát như khi bấm Cmd+Q, chờ nó thoát hẳn, rồi mở lại ($2, thư mục của app). App còn mở sau 30 giây là đang hỏi người dùng điều gì đó: để yên. */
export const RESTART_SCRIPT = 'sleep 2; kill -TERM "$1" 2>/dev/null; i=0; while kill -0 "$1" 2>/dev/null && [ $i -lt 60 ]; do sleep 0.5; i=$((i+1)); done; kill -0 "$1" 2>/dev/null && exit 0; sleep 1; exec /usr/bin/open "$2"'

/**
 * On Linux: prints `<pid>\t<program>\t<launcher>` for the Claude desktop app this shell runs in, or nothing.
 * The app is the topmost ancestor whose program file the `claude-desktop` package owns (asked of dpkg, so no
 * install path is assumed); the launcher is the package's own `claude-desktop` command, else that program.
 */
/** Trên Linux: in ra `<pid>\t<chương trình>\t<lệnh mở>` của app Claude desktop mà shell này chạy trong đó, hoặc không in gì. App là tổ tiên trên cùng có file chương trình thuộc gói `claude-desktop` (hỏi dpkg, nên không giả định đường dẫn cài); lệnh mở là lệnh `claude-desktop` của chính gói, không có thì là chương trình đó. */
export const LINUX_FIND_SCRIPT = [
  'owned() { case "$(dpkg-query -S "$1" 2>/dev/null)" in claude-desktop:*) return 0 ;; esac; return 1; }',
  'p=$PPID; pid=; exe=',
  'while [ "${p:-0}" -gt 1 ]; do',
  '  e=$(readlink "/proc/$p/exe" 2>/dev/null) || break',
  '  if owned "$e"; then pid=$p; exe=$e; fi',
  '  p=$(sed -n "s/^PPid:[[:space:]]*//p" "/proc/$p/status" 2>/dev/null)',
  'done',
  '[ -n "$pid" ] || exit 0',
  'l=$(command -v claude-desktop 2>/dev/null)',
  'if [ -z "$l" ] || ! owned "$l"; then l=$exe; fi',
  'printf "%s\\t%s\\t%s" "$pid" "$exe" "$l"',
].join('\n')

/** What LINUX_FIND_SCRIPT printed: the app's process and the command that opens it again. */
/** Kết quả LINUX_FIND_SCRIPT in ra: tiến trình của app và lệnh mở lại nó. */
export function parseLinuxHost(out: string): { pid: number; app: string; launcher: string } | undefined {
  const m = /^(\d+)\t(\/[^\t\n]+)\t(\/[^\t\n]+)$/.exec(out.trim())
  if (!m) return undefined
  const pid = Number(m[1])
  return pid > 1 ? { pid, app: m[2]!, launcher: m[3]! } : undefined
}

/**
 * The Linux twin of RESTART_SCRIPT: $1 the app's process id, $2 the command that opens it. The variables the app
 * gave this session (CLAUDE...) are dropped first, so the new app does not start with an old session's settings.
 */
/** Bản Linux của RESTART_SCRIPT: $1 là mã tiến trình của app, $2 là lệnh mở nó. Các biến app đã trao cho phiên này (CLAUDE...) được bỏ trước, để app mới không khởi động với thiết lập của một phiên cũ. */
export const LINUX_RESTART_SCRIPT =
  'sleep 2; kill -TERM "$1" 2>/dev/null; i=0; while kill -0 "$1" 2>/dev/null && [ $i -lt 60 ]; do sleep 0.5; i=$((i+1)); done; kill -0 "$1" 2>/dev/null && exit 0; sleep 1; ' +
  'for v in $(env | sed -n "s/^\\(CLAUDE[A-Za-z0-9_]*\\)=.*/\\1/p"); do unset "$v"; done; exec "$2"'

/** Runs $0 (a script) with $1 and $2 in a session of its own, with no input or output, and returns at once. */
/** Chạy $0 (một script) với $1 và $2 trong một phiên riêng, không có đầu vào hay đầu ra, rồi trả về ngay. */
export const LINUX_DETACH = 'setsid -f /bin/sh -c "$0" sh "$1" "$2" </dev/null >/dev/null 2>&1'

/** The package family of the Claude app from the Microsoft Store (MSIX): its name and Anthropic's publisher id. */
/** Họ gói của app Claude cài từ Microsoft Store (MSIX): tên gói và mã nhà phát hành Anthropic. */
export const STORE_FAMILY = 'Claude_pzs8sxrjxfjjc'

/**
 * On Windows (PowerShell): prints `<pid>\t<program>\t<launcher>` for the Claude desktop app this shell runs in, or
 * nothing. The app is the topmost ancestor whose program is the product "Claude" with a valid Anthropic signature,
 * wherever it is installed. A parent older than its child is the real parent (Windows reuses process ids). The
 * launcher is the installer's own stub next to an `app-<version>` folder when there is one.
 * The app from the Microsoft Store runs from WindowsApps, whose files are not read: its program must sit at the
 * package's own `app\Claude.exe` for the family STORE_FAMILY, and when Windows can list the person's packages, the
 * package must be signed by the Store or its publisher (not a folder registered in developer mode) and name that
 * program. Its launcher is `shell:AppsFolder\<family>!<app id>`, which only opens what Windows registered under that family.
 */
/** Trên Windows (PowerShell): in ra `<pid>\t<chương trình>\t<lệnh mở>` của app Claude desktop mà shell này chạy trong đó, hoặc không in gì. App là tổ tiên trên cùng có chương trình là sản phẩm "Claude" với chữ ký Anthropic hợp lệ, cài ở đâu cũng được. Tiến trình cha phải cũ hơn tiến trình con mới là cha thật (Windows dùng lại mã tiến trình). Lệnh mở là file khởi động của bộ cài nằm cạnh thư mục `app-<phiên bản>` khi có. App cài từ Microsoft Store chạy trong WindowsApps, nơi không đọc file: chương trình của nó phải nằm đúng ở `app\Claude.exe` của gói thuộc họ STORE_FAMILY, và khi Windows liệt kê được các gói của người dùng thì gói phải do Store hoặc nhà phát hành ký (không phải thư mục đăng ký ở chế độ nhà phát triển) và khai đúng chương trình đó. Lệnh mở của nó là `shell:AppsFolder\<họ gói>!<mã app>`, chỉ mở thứ Windows đã đăng ký dưới họ gói đó. */
export const WINDOWS_FIND_SCRIPT = [
  "$ErrorActionPreference = 'Stop'",
  "if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage') { exit }",
  'function Signed($f) { $s = Get-AuthenticodeSignature -LiteralPath $f; return ($s.Status -eq \'Valid\' -and $s.SignerCertificate.Subject -match \'O="Anthropic, PBC"\') }',
  // $looked: whether Windows listed the packages; $pkgs: what it listed, with each package's apps
  // $looked: Windows có liệt kê được các gói không; $pkgs: những gì nó liệt kê, kèm các app của từng gói
  'function StoreLauncher($exe, $looked, $pkgs) {',
  `  if ($exe -notmatch '\\\\WindowsApps\\\\${STORE_FAMILY.split('_')[0]}_[0-9.]+_[a-z0-9]+__${STORE_FAMILY.split('_')[1]}\\\\app\\\\Claude\\.exe$') { return $null }`,
  `  if (-not $looked) { return 'shell:AppsFolder\\${STORE_FAMILY}!Claude' }`,
  '  foreach ($k in $pkgs) {',
  `    if ($k.PackageFamilyName -ne '${STORE_FAMILY}' -or $k.IsDevelopmentMode -or @('Store', 'Developer') -notcontains [string]$k.SignatureKind) { continue }`,
  "    $root = ([string]$k.InstallLocation).TrimEnd('\\') + '\\'",
  '    if (-not $exe.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { continue }',
  `    foreach ($a in $k.Apps) { if (($root + $a.Executable) -eq $exe -and $a.Id -match '^[A-Za-z0-9.]+$') { return 'shell:AppsFolder\\${STORE_FAMILY}!' + $a.Id } }`,
  '  }',
  '  return $null',
  '}',
  '$all = @{}; Get-CimInstance Win32_Process | ForEach-Object { $all[[int]$_.ProcessId] = $_ }',
  '$chain = @(); $child = $all[[int]$PID]',
  'for ($n = 0; $n -lt 64 -and $child; $n++) {',
  '  $parent = $all[[int]$child.ParentProcessId]',
  '  if (-not $parent -or $parent.CreationDate -gt $child.CreationDate) { break }',
  '  $chain += $parent; $child = $parent',
  '}',
  '[array]::Reverse($chain)',
  'foreach ($p in $chain) {',
  '  $exe = $p.ExecutablePath',
  '  if (-not $exe) { continue }',
  "  if ($exe -like '*\\WindowsApps\\*') {",
  // a failure here (no Appx module, a package context that refuses) must not stop the walk
  // lỗi ở đây (không có module Appx, ngữ cảnh gói từ chối) không được làm dừng việc dò
  '    try {',
  "      $pkgs = @(Get-AppxPackage -Name Claude | ForEach-Object { [pscustomobject]@{ PackageFamilyName = $_.PackageFamilyName; SignatureKind = [string]$_.SignatureKind; IsDevelopmentMode = $_.IsDevelopmentMode; InstallLocation = $_.InstallLocation; Apps = @((Get-AppxPackageManifest $_).Package.Applications.Application | ForEach-Object { [pscustomobject]@{ Id = $_.Id; Executable = $_.Executable } }) } })",
  '      $looked = $true',
  '    } catch { $pkgs = @(); $looked = $false }',
  '    $launcher = StoreLauncher $exe $looked $pkgs',
  '    if (-not $launcher) { continue }',
  '  } else {',
  "    if ((Get-Item -LiteralPath $exe).VersionInfo.ProductName -ne 'Claude' -or -not (Signed $exe)) { continue }",
  '    $launcher = $exe; $dir = Split-Path -Parent $exe',
  "    if ((Split-Path -Leaf $dir) -like 'app-*') {",
  '      $stub = Join-Path (Split-Path -Parent $dir) (Split-Path -Leaf $exe)',
  '      if ((Test-Path -LiteralPath $stub) -and (Signed $stub)) { $launcher = $stub }',
  '    }',
  '  }',
  '  [Console]::Out.Write("$($p.ProcessId)`t$exe`t$launcher"); exit',
  '}',
].join('\n')

/**
 * On Windows (PowerShell): prints the program of the nearest of this shell's three closest ancestors named
 * `claude.exe` that is not the desktop app's own program (WindowsApps, AnthropicClaude), or nothing: the Claude Code
 * that runs this plugin, which the Store app keeps off the PATH.
 */
/** Trên Windows (PowerShell): in ra chương trình của tổ tiên gần nhất (trong ba tổ tiên gần nhất của shell này) tên `claude.exe` mà không phải chương trình của chính app desktop (WindowsApps, AnthropicClaude), hoặc không in gì: đó là Claude Code đang chạy plugin này, thứ mà app Store không đặt vào PATH. */
export const WINDOWS_CLAUDE_SCRIPT = [
  "$ErrorActionPreference = 'Stop'",
  '$all = @{}; Get-CimInstance Win32_Process | ForEach-Object { $all[[int]$_.ProcessId] = $_ }',
  '$child = $all[[int]$PID]',
  'for ($n = 0; $n -lt 3 -and $child; $n++) {',
  '  $parent = $all[[int]$child.ParentProcessId]',
  '  if (-not $parent -or $parent.CreationDate -gt $child.CreationDate) { break }',
  '  $exe = $parent.ExecutablePath',
  "  if ($exe -and (Split-Path -Leaf $exe) -ieq 'claude.exe' -and $exe -notlike '*\\WindowsApps\\*' -and $exe -notlike '*\\AnthropicClaude\\*') { [Console]::Out.Write($exe); exit }",
  '  $child = $parent',
  '}',
].join('\n')

/** On macOS and Linux: prints the program of the shell's parent, the one that runs this plugin. */
/** Trên macOS và Linux: in ra chương trình của tiến trình cha của shell, là chương trình đang chạy plugin này. */
export const UNIX_CLAUDE_SCRIPT = 'readlink "/proc/$PPID/exe" 2>/dev/null || ps -o comm= -p "$PPID"'

/** A program found by those scripts that may be asked `--version`: a full path, never a desktop app's own program. */
/** Một chương trình do các script đó tìm ra mà được phép hỏi `--version`: đường dẫn đầy đủ, không bao giờ là chương trình của app desktop. */
export function claudeCandidate(out: string): string | undefined {
  const p = out.trim()
  if (/^[A-Za-z]:\\[^\r\n\t]+\.exe$/i.test(p)) return /\\(WindowsApps|AnthropicClaude)\\/i.test(p) ? undefined : p
  if (/^\/[^\r\n\t]+$/.test(p)) return p.includes('.app/Contents/MacOS/') ? undefined : p
  return undefined
}

/** Whether a `--version` answer comes from Claude Code itself, as in "2.1.330 (Claude Code)". */
/** Câu trả lời `--version` có phải của chính Claude Code không, như "2.1.330 (Claude Code)". */
export function isClaudeCodeVersion(out: string): boolean {
  return /^\d+\.\d+\.\d+\S* \(Claude Code\)$/.test(out.trim())
}

/** What WINDOWS_FIND_SCRIPT printed: the app's process and the program, or the Store app's entry, that opens it again. */
/** Kết quả WINDOWS_FIND_SCRIPT in ra: tiến trình của app và chương trình, hoặc mục của app Store, mở lại nó. */
export function parseWindowsHost(out: string): { pid: number; app: string; launcher: string } | undefined {
  const m = /^(\d+)\t([A-Za-z]:\\[^\t\r\n]+\.exe)\t([A-Za-z]:\\[^\t\r\n]+\.exe|shell:AppsFolder\\Claude_pzs8sxrjxfjjc![A-Za-z0-9.]+)$/i.exec(out.trim())
  if (!m) return undefined
  const pid = Number(m[1])
  return pid > 4 ? { pid, app: m[2]!, launcher: m[3]! } : undefined
}

/**
 * The helper that closes and reopens the app on Windows, `{pid}` and `{launcher}` filled in by
 * WINDOWS_RESTART_SCRIPT. Closing the window only hides the app in the tray, so the helper asks the way Windows
 * does at sign-out: it sends "may this session end?" to the app's windows, and "it ends" only to a window that
 * agreed. An app still running after 30 seconds is left alone. The Store app opens again through the shell.
 */
/** Chương trình phụ đóng rồi mở lại app trên Windows, `{pid}` và `{launcher}` do WINDOWS_RESTART_SCRIPT điền vào. Đóng cửa sổ chỉ làm app ẩn xuống khay, nên chương trình phụ hỏi theo cách Windows làm lúc đăng xuất: gửi "phiên này kết thúc được không?" tới các cửa sổ của app, và chỉ gửi "phiên kết thúc" cho cửa sổ đã đồng ý. App còn chạy sau 30 giây thì để yên. App Store được mở lại qua shell. */
export const WINDOWS_HELPER = [
  "$ErrorActionPreference = 'SilentlyContinue'",
  "$app = {pid}; $launcher = '{launcher}'",
  'Add-Type -TypeDefinition @"',
  'using System; using System.Runtime.InteropServices;',
  'public static class AiwEnd {',
  '  public delegate bool EnumProc(IntPtr h, IntPtr l);',
  '  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);',
  '  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);',
  '  [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr w, IntPtr l, uint flags, uint ms, out IntPtr res);',
  '  public static void Ask(uint target) {',
  '    EnumWindows(delegate (IntPtr h, IntPtr l) {',
  '      uint p; GetWindowThreadProcessId(h, out p);',
  '      if (p == target) {',
  '        IntPtr yes = IntPtr.Zero, r;',
  '        if (SendMessageTimeout(h, 0x0011, IntPtr.Zero, (IntPtr)1, 2, 5000, out yes) != IntPtr.Zero && yes != IntPtr.Zero)',
  '          SendMessageTimeout(h, 0x0016, (IntPtr)1, (IntPtr)1, 2, 5000, out r);',
  '      }',
  '      return true; }, IntPtr.Zero);',
  '  }',
  '}',
  '"@',
  // the Store app opens through the shell by its entry, the installed one by its program
  // app Store mở qua shell theo mục của nó, app cài thường mở bằng chương trình của nó
  "function Open($launcher) { if ($launcher -like 'shell:AppsFolder\\*') { Start-Process -FilePath 'explorer.exe' -ArgumentList $launcher } else { Start-Process -FilePath $launcher } }",
  'Start-Sleep -Seconds 2',
  '[AiwEnd]::Ask([uint32]$app)',
  'for ($i = 0; $i -lt 60 -and (Get-Process -Id $app); $i++) { Start-Sleep -Milliseconds 500 }',
  'if (Get-Process -Id $app) { exit }',
  // the Store app's other processes may outlive the main one for a moment: opening before they go may meet the old app's lock
  // các tiến trình khác của app Store có thể sống lâu hơn tiến trình chính một lúc: mở trước khi chúng đi có thể gặp khoá của app cũ
  `if ($launcher -like 'shell:AppsFolder\\*') { for ($i = 0; $i -lt 20 -and (Get-Process | Where-Object { $_.Path -like '*\\WindowsApps\\${STORE_FAMILY.split('_')[0]}_*__${STORE_FAMILY.split('_')[1]}\\*' }); $i++) { Start-Sleep -Milliseconds 500 } }`,
  'Start-Sleep -Seconds 1',
  'Open $launcher',
].join('\n')

/**
 * On Windows (PowerShell): starts WINDOWS_HELPER for the app in AIW_PID with the launcher in AIW_LAUNCHER, through
 * WMI, so the helper is not a child of the app (it gets a fresh set of variables and outlives the app), with no
 * window of its own. Exits 0 once the helper has started.
 */
/** Trên Windows (PowerShell): khởi động WINDOWS_HELPER cho app trong AIW_PID với lệnh mở trong AIW_LAUNCHER, qua WMI, để chương trình phụ không phải con của app (nó nhận bộ biến mới và sống lâu hơn app), không có cửa sổ riêng. Thoát với mã 0 khi chương trình phụ đã khởi động. */
export const WINDOWS_RESTART_SCRIPT = [
  "$ErrorActionPreference = 'Stop'",
  "$helper = $env:AIW_HELPER.Replace('{pid}', [string][int]$env:AIW_PID).Replace('{launcher}', $env:AIW_LAUNCHER.Replace(\"'\", \"''\"))",
  '$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($helper))',
  "$hidden = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }",
  "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = \"powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded\"; ProcessStartupInformation = $hidden }",
  'if ($r.ReturnValue -ne 0) { exit 1 }',
].join('\n')
