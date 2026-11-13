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
