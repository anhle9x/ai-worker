// The team board: what one machine shares into the common folder, and how the
// manager's machine merges every file there. Numbers only: never chat titles,
// prompts, file names or folders. Pure: no `$`.
// Bảng cả team: một máy chia sẻ gì vào thư mục chung, và máy của người
// quản lý gộp mọi file ở đó ra sao. Chỉ có con số: không bao giờ có tiêu đề cuộc trò chuyện,
// lời nhắc, tên file hay thư mục. Hàm thuần: không dùng `$`.
import type { Ledger, Spend, TeamState, Quota } from '../types'
import { LEDGER_HOURS } from './edits'
import { tx } from './lang'

/** The `chiaSe` block of config.js, as the IT team fills it in on each machine. */
/** Khối `chiaSe` của config.js, do phòng IT điền trên từng máy. */
export type ShareConfig = {
  /** This machine writes its summary to the common folder. */
  /** Máy này ghi bản tóm tắt của nó vào thư mục chung. */
  enabled: boolean
  /** Who uses this machine, as the board shows them. */
  /** Ai dùng máy này, như bảng hiển thị họ. */
  name: string
  /** Their Claude account (email): one row per account, however many machines. */
  /** Tài khoản Claude của họ (email): mỗi tài khoản một hàng, dù có bao nhiêu máy. */
  account: string
  /**
   * The common folder: a NAS share mounted on the machine (/Volumes/..., a mapped Z:), or a synced
   * Drive/OneDrive folder. Several paths may be listed (one per system); the first that exists is used.
   */
  /** Thư mục chung: một thư mục NAS được gắn vào máy (/Volumes/..., một ổ Z: đã ánh xạ), hoặc một thư mục Drive/OneDrive đồng bộ. Có thể liệt kê nhiều đường dẫn (mỗi hệ thống một cái); cái đầu tiên tồn tại sẽ được dùng. */
  folders: string[]
  /** This machine reads the whole folder (or the webhook's board) and shows the team board. */
  /** Máy này đọc cả thư mục (hoặc bảng của webhook) và hiện bảng cả team. */
  viewBoard: boolean
  /**
   * A webhook on the company's server (server/webhook.py), e.g. http://192.168.1.10:8788: when set,
   * summaries go there instead of to a folder, and nobody has to mount anything.
   */
  /** Một webhook trên máy chủ của công ty (server/webhook.py), ví dụ http://192.168.1.10:8788: khi đặt, các bản tóm tắt gửi tới đó thay vì tới thư mục, và không ai phải gắn gì cả. */
  webhook: string
  /** The webhook's key to send with: in every machine's package. */
  /** Khoá của webhook để gửi: có trong gói của mọi máy. */
  ingestKey: string
  /** The webhook's key to read the board with: only on the manager's machine. */
  /** Khoá của webhook để đọc bảng: chỉ có trên máy của người quản lý. */
  viewCode: string
}

export const SHARE_OFF: ShareConfig = { enabled: false, name: '', account: '', folders: [], viewBoard: false, webhook: '', ingestKey: '', viewCode: '' }

export function readShareConfig(raw: unknown, home: string): ShareConfig {
  const c = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const text = (v: unknown) => (typeof v === 'string' ? v.trim() : '')
  const folders = (Array.isArray(c.folders) ? c.folders : [c.folders])
    .map(v => text(v).replace(/[\\/]+$/, ''))
    // a drive root keeps its separator: Z: alone would mean Z's current folder
    // gốc ổ đĩa giữ dấu phân cách: chỉ Z: sẽ có nghĩa là thư mục hiện tại của Z
    .map(p => (/^[A-Za-z]:$/.test(p) ? `${p}\\` : p))
    .map(p => (p === '~' || p.startsWith('~/') || p.startsWith('~\\') ? home + p.slice(1) : p))
    // a \\server\share path cannot be reached from a plugin: mount the share (or map a drive letter) instead
    // đường dẫn \\server\share không với tới được từ plugin: hãy gắn thư mục chia sẻ (hoặc ánh xạ một ký tự ổ đĩa) thay vào đó
    .filter(p => p && !p.startsWith('\\\\') && !p.startsWith('//'))
  const webhook = /^https?:\/\/[^\s/]+/.test(text(c.webhook)) ? text(c.webhook).replace(/\/+$/, '') : ''
  return {
    enabled: c.enabled === true,
    name: text(c.name),
    account: text(c.account).toLowerCase(),
    folders,
    viewBoard: c.viewBoard === true,
    webhook,
    ingestKey: text(c.ingestKey),
    viewCode: text(c.viewCode),
  }
}

/**
 * The sharing settings in force: the package's (the company's NAS), then this machine's config.js,
 * each key only where set; the name and account the installer asked for fill in what neither gives.
 */
/** Thiết lập chia sẻ đang có hiệu lực: của gói (NAS của công ty), rồi config.js của máy này, mỗi khoá chỉ ở chỗ có đặt; tên và tài khoản mà trình cài đặt hỏi điền vào chỗ cả hai không cho. */
export function mergeShare(shipped: unknown, mine: unknown, person: unknown): Record<string, unknown> {
  const obj = (v: unknown) => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {})
  const set = (o: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== '' && !(Array.isArray(v) && !v.length)))
  const p = obj(person)
  return { ...set({ name: p.name, account: p.account }), ...set(obj(shipped)), ...set(obj(mine)) }
}

export type WorkerCount = { gemini: number; chatgpt: number; gemma: number }

/** One machine's file in the common folder. */
/** File của một máy trong thư mục chung. */
export type MachineSummary = {
  v: 1
  device: string
  name: string
  account: string
  updatedAt: number
  openSessions: number
  working: number
  waiting: number
  ledger: Ledger
  /** Tasks handed to each worker, by hour since the epoch (UTC). */
  /** Số việc giao cho từng trợ lý, theo giờ kể từ epoch (UTC). */
  tasks: Record<string, WorkerCount>
  /** The machine's own address on the office network, as it reports it (the webhook adds the address it sees as `ip`). */
  /** Địa chỉ của chính máy trên mạng văn phòng, như nó tự báo (webhook thêm địa chỉ nó thấy thành `ip`). */
  lanIp?: string
  /** The email typed at install when it differs from the account actually signed in (`account`). */
  /** Email gõ lúc cài khi nó khác với tài khoản đang thực sự đăng nhập (`account`). */
  enteredAccount?: string
  /** Tasks each helper is working on right now, across the open sessions (the team office animates them). */
  /** Số việc mỗi trợ lý đang làm ngay lúc này, qua các phiên đang mở (văn phòng của team làm hoạt cảnh cho chúng). */
  delegating?: WorkerCount
  /** Subagents running now, per agent type, e.g. { "general-purpose": 2 }. Never the task they were given. */
  /** Các trợ lý con đang chạy, theo loại, ví dụ { "general-purpose": 2 }. Không bao giờ có việc đã giao cho chúng. */
  subagents?: Record<string, number>
  /** Open sessions per Claude model, e.g. { "claude-opus-5-5": 2 }. */
  /** Số phiên đang mở theo mô hình Claude, ví dụ { "claude-opus-5-5": 2 }. */
  models?: Record<string, number>
  /** Helpers installed on this machine: the Gemma model, and whether ChatGPT (Codex) / Gemini can be reached. */
  /** Các trợ lý cài trên máy này: mô hình Gemma, và liệu có với tới ChatGPT (Codex) / Gemini được không. */
  assistants?: Assistants
  /** The account's rate-limit windows, the latest reading among this machine's sessions. */
  /** Các cửa sổ giới hạn của tài khoản, lần đọc mới nhất trong các phiên của máy này. */
  quota?: Quota
  /** The plugin's version on this machine: the board shows who has not updated. */
  /** Phiên bản plugin trên máy này: bảng hiện ai chưa cập nhật. */
  pluginVersion?: string
  /** One-way hash of the computer's own hardware id: a reinstalled plugin gets a new `device` but the same mark. */
  /** Dấu phần cứng của máy đã băm một chiều: cài lại plugin có `device` mới nhưng vẫn cùng dấu. */
  hardwareMark?: string
}

/** The rate-limit windows worth keeping from a reading: the known kinds, the percent clamped, the reset as ms. */
/** Các cửa sổ giới hạn đáng giữ từ một lần đọc: các loại đã biết, phần trăm bị chặn trong khoảng, thời điểm đặt lại tính bằng ms. */
export function toQuota(limits: readonly { kind: string; percentUsed: number; resetsAt?: string }[], now: number): Quota | undefined {
  const windows = limits
    .filter(l => typeof l.kind === 'string' && /^[a-z_]{1,30}$/.test(l.kind) && Number.isFinite(l.percentUsed))
    .map(l => {
      const resetsAt = l.resetsAt ? Date.parse(l.resetsAt) : NaN
      return { kind: l.kind, pct: Math.round(Math.min(Math.max(l.percentUsed, 0), 999) * 10) / 10, ...(Number.isFinite(resetsAt) ? { resetsAt } : {}) }
    })
  return windows.length ? { readAt: now, windows } : undefined
}

/** Window names as people read them. */
/** Tên các cửa sổ như người dùng đọc. */
export const QUOTA_WINDOW_LABELS = (): Record<string, string> => ({ five_hour: tx('5-hour'), seven_day: tx('7-day'), seven_day_opus: tx('7-day Opus'), seven_day_sonnet: tx('7-day Sonnet'), spend_limit: tx('spending') })

/** "21:20" today, "21:20 07/11" another day, in the machine's own time zone. */
/** "21:20" nếu là hôm nay, "21:20 07/11" nếu là ngày khác, theo múi giờ của chính máy. */
export function resetLabel(resetsAt: number, now: number): string {
  const d = new Date(resetsAt)
  const p = (n: number) => String(n).padStart(2, '0')
  const timeText = `${p(d.getHours())}:${p(d.getMinutes())}`
  return d.toDateString() === new Date(now).toDateString() ? timeText : `${timeText} ${p(d.getDate())}/${p(d.getMonth() + 1)}`
}

/**
 * The account's fullest window when it is at 80% or more: level 80 (suggest a lighter model) or 95 (about to stop).
 * A window past its reset counts as empty. `key` changes with the level and the window's reset, so a warning
 * hidden or toasted once comes back only when things get worse or a new window fills up.
 */
/** Cửa sổ đầy nhất của tài khoản khi nó ở mức 80% trở lên: mức 80 (gợi ý mô hình nhẹ hơn) hoặc 95 (sắp dừng). Cửa sổ đã qua lúc đặt lại coi như trống. `key` đổi theo mức và lúc đặt lại của cửa sổ, nên một cảnh báo đã ẩn hoặc đã báo chỉ quay lại khi mọi thứ tệ hơn hoặc một cửa sổ mới đầy lên. */
export function quotaWarning(quota: Quota | undefined, now: number, model?: string):
  { level: 80 | 95; key: string; text: string; shortText: string } | undefined {
  if (!quota || now - quota.readAt > QUOTA_MAX_AGE_MS) return undefined
  let worst: Quota['windows'][number] | undefined
  for (const c of quota.windows) {
    if (c.resetsAt !== undefined && c.resetsAt < now) continue
    if (!worst || c.pct > worst.pct) worst = c
  }
  if (!worst || worst.pct < 80) return undefined
  const level = worst.pct >= 95 ? 95 : 80
  const windowLabel = QUOTA_WINDOW_LABELS()[worst.kind] ?? worst.kind
  const resetText = worst.resetsAt !== undefined ? resetLabel(worst.resetsAt, now) : ''
  const pct = `${Math.round(worst.pct)}%`
  // Opus burns the limit fastest; on Sonnet / Haiku there is nothing lighter to suggest
  // Opus tiêu hạn mức nhanh nhất; với Sonnet / Haiku thì không có gì nhẹ hơn để gợi ý
  const isLightModel = !!model && /sonnet|haiku/i.test(model)
  const shortText = resetText
    ? tx('Quota ({window}): {pct} · resets {time}', { window: windowLabel, pct, time: resetText })
    : tx('Quota ({window}): {pct}', { window: windowLabel, pct })
  const text = level === 95
    ? tx('Your Claude account is nearly out of its {window} quota ({pct}): when it runs out you must stop{until}. Save your work{lighter}.', {
        window: windowLabel,
        pct,
        until: resetText ? tx(' until {time}', { time: resetText }) : '',
        lighter: isLightModel ? '' : tx(', and move light work to Sonnet (type /model sonnet)'),
      })
    : tx('Your Claude account has used {pct} of its {window} quota{reset}.{advice}', {
        pct,
        window: windowLabel,
        reset: resetText ? tx(' (resets {time})', { time: resetText }) : '',
        advice: isLightModel ? tx(' Use it sparingly until the reset.') : tx(' Move light work to Sonnet: type /model sonnet.'),
      })
  return { level, key: `${worst.kind}:${worst.resetsAt ?? 0}:${level}`, text, shortText }
}

/** A reading older than this says nothing about the account now (the longest window is seven days). */
/** Số đọc cũ hơn mức này không nói gì về tài khoản bây giờ (cửa sổ dài nhất là bảy ngày). */
export const QUOTA_MAX_AGE_MS = 7 * 24 * 3_600_000

export type Assistants = { gemma?: string; chatgpt: boolean; gemini: boolean; chatgptModel?: string; geminiModel?: string }

/** The model named on a helper's answer: ai-workers and the plugin end it with "(model: …)". */
/** Mô hình được nêu trong câu trả lời của một trợ lý: ai-workers và plugin kết thúc nó bằng "(model: …)" hoặc "(mô hình: …)". */
export function answerModel(text: string): string | undefined {
  // the name may carry its own brackets: "Gemini 3.8 Flash (High)"
  // tên có thể có dấu ngoặc riêng: "Gemini 3.8 Flash (High)"
  const m = /\n\((?:mô hình|model): ([^\n]{1,60})\)\s*$/.exec(text) // i18n-allow
  return m?.[1]?.trim()
}

/**
 * Commands that print the address of the interface carrying the default route, tried in turn:
 * Linux `ip route`, macOS `route` + `ipconfig`, Windows `route print`. None sends anything out.
 */
/** Các lệnh in địa chỉ của giao diện mang tuyến mặc định, thử lần lượt: `ip route` của Linux, `route` + `ipconfig` của macOS, `route print` của Windows. Không lệnh nào gửi gì ra ngoài. */
export const LAN_IP_PROBES: string[][] = [
  ['ip', '-4', 'route', 'get', '1.1.1.1'],
  ['sh', '-c', 'ipconfig getifaddr "$(route -n get default 2>/dev/null | awk \'/interface:/{print $2}\')"'],
  ['route', 'print', '-4', '0.0.0.0'],
]

/** Commands that print the computer's own fixed id: macOS, Windows, Linux. Each fails quietly on the others. */
/** Các lệnh in mã cố định của máy: macOS, Windows, Linux. Lệnh nào không thuộc hệ đó thì lặng lẽ thất bại. */
export const HARDWARE_ID_PROBES: string[][] = [
  ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
  ['reg', 'query', 'HKLM\\SOFTWARE\\Microsoft\\Cryptography', '/v', 'MachineGuid'],
  ['cat', '/etc/machine-id'],
]

/** The id in an ioreg IOPlatformUUID line, a MachineGuid line or /etc/machine-id; lower case. */
/** Mã trong dòng IOPlatformUUID của ioreg, dòng MachineGuid hoặc /etc/machine-id; chữ thường. */
export function parseHardwareId(out: string): string | undefined {
  const mac = /"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]{32,36})"/.exec(out)?.[1]
  const win = /MachineGuid\s+REG_SZ\s+([0-9A-Fa-f-]{32,36})/.exec(out)?.[1]
  const linux = /^\s*([0-9a-f]{32})\s*$/.exec(out)?.[1]
  const id = (mac ?? win ?? linux)?.toLowerCase()
  return id && /[1-9a-f]/.test(id) ? id : undefined
}

/** What the machine sends instead of its id: the first 32 hex of a salted SHA-256, so the id cannot be read back. */
/** Thứ máy gửi thay cho mã gốc: 32 ký tự hex đầu của SHA-256 có muối, không đọc ngược ra mã được. */
export function hardwareMark(id: string): string {
  return sha256Hex(`ai-worker-hardware-mark|${id}`).slice(0, 32)
}

/** SHA-256 of a string's UTF-8 bytes, in hex. Plain code: the plugin engine has no crypto module. */
/** SHA-256 của chuỗi (byte UTF-8), dạng hex. Viết tay vì engine plugin không có thư viện mã hoá. */
export function sha256Hex(text: string): string {
  const bytes = Array.from(new TextEncoder().encode(text))
  const bits = bytes.length * 8
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (bits >>> (i * 8)) & 0xff)
  const k = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]
  const h: [number, number, number, number, number, number, number, number] = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n))
  const w = new Array<number>(64)
  for (let off = 0; off < bytes.length; off += 64) {
    // every index below is in range (bytes is padded to whole 64-byte blocks), hence the `!`
    // mọi chỉ số dưới đây đều nằm trong mảng (bytes đã đệm đủ khối 64 byte), nên dùng `!`
    for (let i = 0; i < 16; i++) {
      const p = off + 4 * i
      w[i] = (bytes[p]! << 24) | (bytes[p + 1]! << 16) | (bytes[p + 2]! << 8) | bytes[p + 3]!
    }
    for (let i = 16; i < 64; i++) {
      const x = w[i - 15]!
      const y = w[i - 2]!
      const s0 = rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)
      const s1 = rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10)
      w[i] = (w[i - 16]! + s0 + w[i - 7]! + s1) | 0
    }
    let [a, b, c, d, e, f, g, hh] = h
    for (let i = 0; i < 64; i++) {
      const t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i]! + w[i]!) | 0
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
      hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
    }
    h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0
    h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + hh) | 0
  }
  return h.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('')
}

const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/

/** A usable IPv4 address: four parts under 256, not loopback, link-local or unset. */
/** Một địa chỉ IPv4 dùng được: bốn phần dưới 256, không phải loopback, link-local hay chưa đặt. */
export function isLanIp(ip: unknown): ip is string {
  const m = typeof ip === 'string' ? IPV4.exec(ip) : null
  if (!m || m.slice(1).some(p => Number(p) > 255)) return false
  return !/^(127\.|169\.254\.|0\.)/.test(ip as string)
}

/** The office address from any probe's output, or undefined. */
/** Địa chỉ văn phòng từ kết quả của bất kỳ lệnh dò nào, hoặc undefined. */
export function parseLanIp(out: string): string | undefined {
  const src = /\bsrc (\d+\.\d+\.\d+\.\d+)/.exec(out)?.[1]
  if (isLanIp(src)) return src
  // Windows: "0.0.0.0  0.0.0.0  <gateway>  <interface>  <metric>"; the lowest metric wins
  // Windows: "0.0.0.0  0.0.0.0  <gateway>  <interface>  <metric>"; metric thấp nhất thắng
  let best: { ip: string; metric: number } | undefined
  for (const m of out.matchAll(/^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)/gm)) {
    if (isLanIp(m[1]) && (!best || Number(m[2]) < best.metric)) best = { ip: m[1], metric: Number(m[2]) }
  }
  if (best) return best.ip
  const bare = out.trim()
  return isLanIp(bare) ? bare : undefined
}

/** A session is open while its heartbeat (every 30 s) is this recent; the page uses the same rule. */
/** Một phiên đang mở khi nhịp tim của nó (mỗi 30 giây) gần đây đến mức này; trang dùng cùng quy tắc. */
export const OPEN_MS = 2 * 60 * 1000

/** Reads `window.__aiWorkerIn("id", {...});` back into the session's state; undefined if broken. */
/** Đọc ngược `window.__aiWorkerIn("id", {...});` thành trạng thái của phiên; undefined nếu hỏng. */
export function parseSessionFile(raw: string): (TeamState & { seenAt?: number; updatedAt?: number }) | undefined {
  const start = raw.indexOf(', {')
  const end = raw.lastIndexOf(');')
  if (start < 0 || end < start) return undefined
  try {
    return JSON.parse(raw.slice(start + 2, end))
  } catch {
    return undefined
  }
}

/** This machine's numbers, from its session files and its hourly ledger. */
/** Số liệu của máy này, từ các file phiên và sổ theo giờ của nó. */
/** A helper's job older than this without an end is taken as abandoned. */
/** Việc của một trợ lý cũ hơn mức này mà không có kết thúc thì coi là bị bỏ dở. */
const BUSY_MS = 15 * 60_000

export function buildMachineSummary(
  sessions: readonly (TeamState & { seenAt?: number })[],
  ledger: Ledger | undefined,
  now: number,
  who: { device: string; name: string; account: string; lanIp?: string; enteredAccount?: string; assistants?: Assistants; pluginVersion?: string; hardwareMark?: string },
): MachineSummary {
  const fromHour = Math.floor(now / 3_600_000) - LEDGER_HOURS
  const tasks: Record<string, WorkerCount> = {}
  let openSessions = 0
  let working = 0
  let waiting = 0
  const delegating: WorkerCount = { gemini: 0, chatgpt: 0, gemma: 0 }
  const models: Record<string, number> = {}
  const subagents: Record<string, number> = {}
  let quota: Quota | undefined
  for (const s of sessions) {
    if (s.quota && now - s.quota.readAt < QUOTA_MAX_AGE_MS && (!quota || s.quota.readAt > quota.readAt)) quota = s.quota
    if (s.seenAt && now - s.seenAt < OPEN_MS) {
      openSessions++
      if (typeof s.model === 'string' && s.model) models[s.model] = (models[s.model] ?? 0) + 1
      for (const a of s.subagents ?? []) if (/^[A-Za-z0-9:_.-]{1,40}$/.test(a.name)) subagents[a.name] = (subagents[a.name] ?? 0) + 1
      if (s.asking) waiting++
      else if (s.claudeBusySince) working++
      // a job left open by a session that crashed stops counting after a while
      // một việc bị bỏ dở bởi phiên đã sập thì sau một lúc thôi không được tính
      for (const j of s.jobs ?? []) if (j.worker !== 'claude' && j.endedAt === undefined && now - j.startedAt < BUSY_MS) delegating[j.worker]++
    }
    for (const j of s.jobs ?? []) {
      if (j.worker === 'claude') continue
      const hour = Math.floor(j.startedAt / 3_600_000)
      if (hour <= fromHour) continue
      const c = (tasks[hour] ??= { gemini: 0, chatgpt: 0, gemma: 0 })
      c[j.worker]++
    }
  }
  const { lanIp, enteredAccount, assistants, pluginVersion, hardwareMark, ...id } = who
  return {
    v: 1, ...id, ...(lanIp ? { lanIp } : {}), ...(enteredAccount ? { enteredAccount } : {}), ...(assistants ? { assistants } : {}), ...(quota ? { quota } : {}),
    ...(pluginVersion ? { pluginVersion } : {}),
    ...(hardwareMark ? { hardwareMark } : {}),
    ...(Object.keys(subagents).length ? { subagents } : {}),
    updatedAt: now, openSessions, working, waiting, delegating, models, ledger: ledger ?? {}, tasks,
  }
}

/** The same summary ignoring when it was written: rewrite the shared file only when this changes. */
/** Cùng bản tóm tắt đó bỏ qua lúc nó được ghi: chỉ ghi lại file chung khi cái này đổi. */
export function summarySignature(m: MachineSummary): string {
  return JSON.stringify({ ...m, updatedAt: 0 })
}

/** One row of the board: an account, its machines' numbers together. */
/** Một hàng của bảng: một tài khoản, số liệu các máy của nó gộp lại. */
export type TeamMember = {
  key: string
  name: string
  account: string
  deviceCount: number
  /** machine IPs as seen by the webhook (never sent by the machine itself) */
  /** IP của máy như webhook thấy (máy không bao giờ tự gửi) */
  ip: string[]
  /** office-network IPs the machines report themselves */
  /** IP trong mạng văn phòng mà các máy tự báo */
  lanIp: string[]
  /** emails typed at install that differ from the account signed in */
  /** email gõ lúc cài khác với tài khoản đang đăng nhập */
  enteredAccount: string[]
  updatedAt: number
  openSessions: number
  working: number
  waiting: number
  ledger: Ledger
  tasks: Record<string, WorkerCount>
}

const EMPTY_SPEND: Spend = { usd: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }

/** Merges machine files by person: an account shared by several people stays one row per person; broken or foreign files are skipped. */
/** Gộp file các máy theo từng người: một tài khoản dùng chung bởi nhiều người vẫn là mỗi người một hàng; file hỏng hoặc của nơi khác bị bỏ qua. */
export function mergeTeam(files: readonly unknown[], now: number, offlineMs: number): TeamMember[] {
  const by = new Map<string, TeamMember>()
  for (const f of files) {
    const m = f as Partial<MachineSummary>
    if (!m || m.v !== 1 || typeof m.device !== 'string' || typeof m.updatedAt !== 'number') continue
    const ip = typeof (m as { ip?: unknown }).ip === 'string' ? (m as { ip: string }).ip : ''
    const lanIp = isLanIp(m.lanIp) ? m.lanIp : ''
    const key = `${m.account ?? ''}|${m.name || lanIp || ip || m.device}`.toLowerCase()
    const isLive = now - m.updatedAt < offlineMs
    const row = by.get(key) ?? { key, name: m.name || m.account || lanIp || ip || m.device, account: m.account ?? '', deviceCount: 0, ip: [], lanIp: [], enteredAccount: [], updatedAt: 0, openSessions: 0, working: 0, waiting: 0, ledger: {}, tasks: {} }
    row.deviceCount++
    if (ip && !row.ip.includes(ip)) row.ip.push(ip)
    if (lanIp && !row.lanIp.includes(lanIp)) row.lanIp.push(lanIp)
    const typed = typeof m.enteredAccount === 'string' ? m.enteredAccount : ''
    if (typed && !row.enteredAccount.includes(typed)) row.enteredAccount.push(typed)
    row.updatedAt = Math.max(row.updatedAt, m.updatedAt)
    if (isLive) {
      row.openSessions += m.openSessions ?? 0
      row.working += m.working ?? 0
      row.waiting += m.waiting ?? 0
    }
    for (const [h, v] of Object.entries(m.ledger ?? {})) {
      const was = row.ledger[h] ?? EMPTY_SPEND
      row.ledger[h] = {
        usd: was.usd + (Number(v.usd) || 0),
        input: was.input + (Number(v.input) || 0),
        output: was.output + (Number(v.output) || 0),
        cacheRead: was.cacheRead + (Number(v.cacheRead) || 0),
        cacheWrite: was.cacheWrite + (Number(v.cacheWrite) || 0),
      }
    }
    for (const [h, v] of Object.entries(m.tasks ?? {})) {
      const was = row.tasks[h] ?? { gemini: 0, chatgpt: 0, gemma: 0 }
      row.tasks[h] = { gemini: was.gemini + (v.gemini || 0), chatgpt: was.chatgpt + (v.chatgpt || 0), gemma: was.gemma + (v.gemma || 0) }
    }
    by.set(key, row)
  }
  return [...by.values()].sort((a, b) => a.name.localeCompare(b.name, 'vi'))
}

/** Failing this long to send counts as a problem worth telling the user (a short drop is not). */
/** Gửi lỗi lâu chừng này thì được coi là vấn đề đáng báo người dùng (rớt ngắn thì không). */
export const SHARE_WARN_MS = 10 * 60_000

/** What went wrong sending to the webhook, in words for the user. */
/** Điều gì sai khi gửi tới webhook, bằng lời cho người dùng. */
export function shareProblem(err: unknown): string {
  const m = /webhook (\d+)/.exec(String((err as { message?: unknown })?.message ?? err))
  if (!m) return tx('Could not reach the team board server.')
  if (m[1] === '401') return tx('The team board server refused the key (old install or the key changed).')
  return tx('The team board server reported error {code}.', { code: m[1]! })
}

/** The warning for a send failing since `since`, once it has lasted SHARE_WARN_MS; undefined before. */
/** Cảnh báo cho việc gửi lỗi từ `since`, một khi nó đã kéo dài SHARE_WARN_MS; trước đó là undefined. */
export function shareWarning(fail: { since: number; error: string } | undefined, now: number): string | undefined {
  if (!fail || now - fail.since < SHARE_WARN_MS) return undefined
  const mins = Math.round((now - fail.since) / 60_000)
  const span = mins < 120 ? tx('{n} min', { n: mins }) : tx('{n} hours', { n: Math.round(mins / 60) })
  return tx('{error} Data from this computer has not reached the team board for {span}. If you are at the company, tell your IT team; away from the company this is normal, and the computer sends it again when you are back.', { error: fail.error, span })
}

/**
 * The email of the account Claude is signed in with, from Claude's own settings file (~/.claude.json,
 * `oauthAccount.emailAddress`); '' when signed out, signed in with an API key, or the file reads otherwise.
 */
/** Email của tài khoản Claude đang đăng nhập, lấy từ file cài đặt của chính Claude (~/.claude.json, `oauthAccount.emailAddress`); '' khi đã đăng xuất, đăng nhập bằng API key, hoặc file đọc ra khác đi. */
export function signedInEmail(raw: string): string {
  try {
    const e = (JSON.parse(raw) as { oauthAccount?: { emailAddress?: unknown } })?.oauthAccount?.emailAddress
    return typeof e === 'string' && /^[^\s@]+@[^\s@]+$/.test(e.trim()) ? e.trim().toLowerCase() : ''
  } catch {
    return ''
  }
}
