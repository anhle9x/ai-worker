// Turns an Edit / Write / NotebookEdit result into a capped record of the
// changed lines, and sums turn token counts. Pure: no `$`.
// Biến kết quả Edit / Write / NotebookEdit thành bản ghi giới hạn của các
// dòng đã đổi, và cộng số token của từng lượt. Hàm thuần: không dùng `$`.
import type { ContextFill, FileEdit, Ledger, Spend, Usage } from '../types'
import { getLang, tx } from './lang'

const MAX_LINES = 160
const MAX_LINE_CHARS = 200
/** Files whose changes are listed by name only, never by content. */
/** Các file mà thay đổi chỉ được liệt kê theo tên, không bao giờ theo nội dung. */
export const SECRET_FILE = /(^|\/)\.env($|\.)|secret|credential|password|token|\.pem$|\.key$|\.p12$|id_rsa|id_ed25519/i

export const EDIT_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit'])

type Hunk = { oldStart: number; oldLines: number; newStart: number; newLines: number; lines: string[] }
type EditResult = {
  filePath?: string
  structuredPatch?: Hunk[]
  type?: 'create' | 'update'
  content?: string
  new_source?: string
  staged?: boolean
}

export function buildFileEdit(tool: string, input: Record<string, unknown>, result: unknown, at: number, key: string): FileEdit | undefined {
  const r = (result && typeof result === 'object' ? result : {}) as EditResult
  if (r.staged) return undefined
  const path = String(r.filePath ?? input.file_path ?? input.notebook_path ?? '')
  if (!path) return undefined

  let raw: string[] = []
  if (r.structuredPatch?.length) {
    for (const h of r.structuredPatch) {
      raw.push(`@@ -${h.oldStart},${h.oldLines} +${h.newStart},${h.newLines} @@`)
      raw.push(...h.lines)
    }
  } else if (tool === 'Write' && typeof r.content === 'string') {
    raw = r.content.split('\n').map(l => `+${l}`)
  } else if (tool === 'NotebookEdit' && typeof input.new_source === 'string') {
    raw = input.new_source.split('\n').map(l => `+${l}`)
  }

  const added = raw.filter(l => l.startsWith('+')).length
  const removed = raw.filter(l => l.startsWith('-')).length
  const isHidden = SECRET_FILE.test(path)
  const kept = isHidden ? [] : raw.slice(0, MAX_LINES).map(l => (l.length > MAX_LINE_CHARS ? `${l.slice(0, MAX_LINE_CHARS)}…` : l))
  return {
    key,
    path,
    tool,
    at,
    added,
    removed,
    lines: kept,
    ...(isHidden ? { isHidden: true } : {}),
    ...(r.type === 'create' ? { isNew: true } : {}),
    ...(!isHidden && raw.length > MAX_LINES ? { isTruncated: true } : {}),
  }
}

export type TurnTokens = {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

export const EMPTY_USAGE: Usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, turns: 0 }

export function toUsage(t: TurnTokens, turns: number): Usage {
  return {
    input: t.input_tokens,
    output: t.output_tokens,
    cacheRead: t.cache_read_input_tokens,
    cacheWrite: t.cache_creation_input_tokens,
    turns,
  }
}

export function addUsage(a: Usage | undefined, b: Usage): Usage {
  const base = a ?? EMPTY_USAGE
  return {
    input: base.input + b.input,
    output: base.output + b.output,
    cacheRead: base.cacheRead + b.cacheRead,
    cacheWrite: base.cacheWrite + b.cacheWrite,
    turns: base.turns + b.turns,
  }
}

/** 1234567 → "1,2 tr", 45678 → "45,7 k", 512 → "512" in Vietnamese; "1.2M", "45.7k", "512" in English. */
/** 1234567 → "1,2 tr", 45678 → "45,7 k", 512 → "512" trong tiếng Việt; "1.2M", "45.7k", "512" trong tiếng Anh. */
export function shortCount(n: number): string {
  const vi = getLang() === 'vi'
  const num = (x: number) => (vi ? x.toFixed(1).replace('.', ',') : x.toFixed(1))
  if (n >= 1_000_000) return vi ? `${num(n / 1_000_000)} tr` : `${num(n / 1_000_000)}M`
  if (n >= 1_000) return vi ? `${num(n / 1_000)} k` : `${num(n / 1_000)}k`
  return String(n)
}

/** How many hours of spend the ledger keeps: a week plus a day, enough for "7 days" in any time zone. */
/** Sổ ghi chi phí giữ bao nhiêu giờ: một tuần cộng một ngày, để đủ cho "7 ngày" ở mọi múi giờ. */
export const LEDGER_HOURS = 8 * 24

/** Adds one turn's spend to its hour, dropping hours older than LEDGER_HOURS. */
/** Cộng chi phí của một lượt vào giờ của nó, bỏ các giờ cũ hơn LEDGER_HOURS. */
export function addSpend(ledger: Ledger | undefined, hour: number, d: Spend): Ledger {
  const out: Ledger = {}
  for (const [k, v] of Object.entries(ledger ?? {})) if (Number(k) > hour - LEDGER_HOURS) out[k] = v
  const was = out[hour] ?? { usd: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  out[hour] = {
    usd: was.usd + d.usd,
    input: was.input + d.input,
    output: was.output + d.output,
    cacheRead: was.cacheRead + d.cacheRead,
    cacheWrite: was.cacheWrite + d.cacheWrite,
  }
  return out
}

/** How many hours the long history keeps: five years, so quarters and years compare. It stays on this machine and is never sent. */
/** Lịch sử dài giữ bao nhiêu giờ: năm năm, để so sánh được các quý và các năm. Nó ở lại trên máy này và không bao giờ được gửi đi. */
export const LONG_HOURS = 5 * 366 * 24

/** Dollars by hour for the long ranges: the hourly ledger wins where they overlap, old hours drop off. */
/** Chi phí theo giờ cho các khoảng dài: sổ theo giờ được ưu tiên ở chỗ hai bên trùng nhau, các giờ cũ rơi ra. */
export function mergeLongSpend(long: Record<string, number> | undefined, ledger: Ledger, hour: number): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(long ?? {})) if (Number(k) > hour - LONG_HOURS) out[k] = v
  for (const [k, v] of Object.entries(ledger)) if (v.usd > 0) out[k] = Math.round(v.usd * 10000) / 10000
  return out
}

/** Above this, a first sight of a session's total is a resumed session's old spend, not one turn. */
/** Quá mức này, lần đầu thấy tổng của một phiên là chi phí cũ của phiên được mở lại, không phải của một lượt. */
export const FIRST_SIGHT_MAX_USD = 5

/**
 * The dollars a turn added: the session's total now less what it was; a total that went down started over.
 * With nothing remembered (the app reopened a session), a large total is what the session spent before: not this turn's.
 */
/** Số đô la mà một lượt đã thêm: tổng của phiên bây giờ trừ đi tổng trước đó; tổng giảm đi nghĩa là phiên bắt đầu lại. Khi chưa nhớ gì (app mở lại một phiên), một tổng lớn là số phiên đã tiêu trước đó: không phải của lượt này. */
export function costDelta(before: number | undefined, now: number): number {
  if (before === undefined) return now > FIRST_SIGHT_MAX_USD ? 0 : now
  return now >= before ? now - before : now
}

/**
 * Repairs hours inflated by a resumed session's whole total landing in one hour: an hour costing over
 * 5 times the ledger's usual dollars per token (and over $20) is repriced at the usual rate. An estimate.
 */
/** Sửa các giờ bị phình do cả tổng của một phiên được mở lại rơi vào một giờ: một giờ tốn hơn 5 lần số đô la thường có trên mỗi token của sổ (và trên 20 đô la) được tính lại theo mức thường. Chỉ là ước tính. */
export function repairInflatedHours(ledger: Ledger): Ledger {
  const weight = (v: Ledger[string]) => v.input + v.output + v.cacheRead + v.cacheWrite
  const rates = Object.values(ledger).filter(v => v.usd > 0 && weight(v) > 0).map(v => v.usd / weight(v)).sort((a, b) => a - b)
  if (rates.length < 3) return ledger
  const usual = rates[Math.floor(rates.length / 2)]!
  const out: Ledger = {}
  for (const [k, v] of Object.entries(ledger)) {
    out[k] = v.usd > 20 && weight(v) > 0 && v.usd / weight(v) > usual * 5 ? { ...v, usd: weight(v) * usual } : v
  }
  return out
}

/** 0.4213 → "$0,42"; under a cent → "$0,004". */
/** 0.4213 → "$0,42"; dưới một cent → "$0,004". */
export function formatUsd(usd: number): string {
  const digits = usd > 0 && usd < 0.01 ? 3 : 2
  const text = usd.toFixed(digits)
  return `$${getLang() === 'vi' ? text.replace('.', ',') : text}`
}

/** Context fill from the engine's figures, or undefined before the first response of the live window. */
/** Mức đầy của ngữ cảnh theo số liệu của engine, hoặc undefined trước phản hồi đầu tiên của cửa sổ đang chạy. */
export function contextFill(c: { tokens?: number; window: number; percent?: number } | undefined): ContextFill | undefined {
  if (!c || c.percent === undefined || c.tokens === undefined) return undefined
  return { percent: Math.round(c.percent), tokens: c.tokens, window: c.window }
}

/** When to open a fresh session: past 60% answers slow down and cost more, near 80% auto-compact drops detail. */
/** Khi nào nên mở phiên mới: quá 60% thì trả lời chậm đi và tốn hơn, gần 80% thì tự nén làm mất chi tiết. */
export function contextAdvice(percent: number): string {
  return percent >= 80 ? tx('start a new session') : percent >= 60 ? tx('getting full') : ''
}

/** The warning to give once the fill climbs past a level not yet warned about; the level drops back after a compact. */
/** Cảnh báo đưa ra khi mức đầy vượt một ngưỡng chưa được cảnh báo; ngưỡng hạ xuống sau khi nén. */
export function contextWarning(percent: number, warned: number, handoff = false): { level: number; text?: string } {
  const level = percent >= 80 ? 80 : percent >= 60 ? 60 : 0
  if (level <= warned) return { level }
  // a machine with the /handoff skill writes a handoff note first, so the next session picks up where this one stopped
  // máy có skill /handoff thì ghi ghi chú bàn giao trước, để phiên sau làm tiếp từ chỗ phiên này dừng
  const first = handoff ? tx('Type /handoff to write a handoff note, then open a new session') : tx('Open a new session (or type /compact)')
  return {
    level,
    text: level === 80
      ? tx('This session has used {percent}% of its context, almost full. {first} before Claude compacts it on its own and loses detail.', { percent, first })
      : handoff
        ? tx('This session has used {percent}% of its context, getting full. When you finish what you are doing, type /handoff and then open a new session.', { percent })
        : tx('This session has used {percent}% of its context, getting full. When you finish what you are doing, open a new session.', { percent }),
  }
}
