// Format v: 2 of a send to the server: only the hours that changed since the server last took a send (docs/DATA-MODEL.md, "Format v: 2").
// Định dạng v: 2 của một lần gửi lên máy chủ: chỉ các giờ đã đổi kể từ lần gửi gần nhất máy chủ đã nhận (docs/DATA-MODEL.vi.md, "Định dạng v: 2").
import { sha256Hex, type MachineSummary } from './team'

/** The hour books of a send, as the server names them. */
/** Các sổ giờ của một lần gửi, theo tên máy chủ dùng. */
export const HOUR_KINDS = ['ledger', 'tasks', 'blocks'] as const
export type HourKind = (typeof HOUR_KINDS)[number]

/** A short mark of each hour's value, per book: two hours with the same mark hold the same numbers. */
/** Dấu ngắn của giá trị từng giờ, theo từng sổ: hai giờ cùng dấu thì cùng số liệu. */
export type HourMarks = Record<HourKind, Record<string, string>>

/**
 * What this computer knows about the server it sends to, kept across sessions: whether it reads `v: 2`, the marks of the hours it last
 * took, which start of the server that was, when the next whole book is due, and whether the server asked for it.
 */
/** Những gì máy này biết về máy chủ nó gửi tới, giữ qua các phiên: máy chủ có đọc `v: 2` không, dấu của các giờ nó nhận lần gần nhất, đó là lần khởi động nào của máy chủ, khi nào tới hạn gửi cả sổ, và máy chủ có xin cả sổ không. */
export type SendState = { v2?: boolean; acked?: HourMarks; boot?: string; fullAfter?: number; needFull?: boolean }

/** A whole book once an hour at least (the server merges one sent sooner), spread up to a quarter of an hour so the computers do not send it together. */
/** Cả sổ ít nhất mỗi giờ một lần (máy chủ ghép sổ gửi sớm hơn), lệch tới mười lăm phút để các máy không gửi cùng lúc. */
export const FULL_EVERY_MS = 60 * 60_000
export const FULL_SPREAD_MS = 15 * 60_000
/** After the server started again (or another server answered), the hours of the last two days go up again, in case its last seconds were not written. */
/** Sau khi máy chủ khởi động lại (hoặc một máy chủ khác trả lời), các giờ của hai ngày gần nhất được gửi lại, phòng khi những giây cuối của nó chưa kịp ghi. */
export const RESEND_HOURS = 48

export type V2Packet = Omit<MachineSummary, 'v' | 'ledger' | 'tasks' | 'blocks'> & {
  v: 2
  full: boolean
  hours: Record<HourKind, Record<string, unknown>>
}

/** One send: what goes up, whether it holds the whole book, and the marks of every hour the computer holds now. */
/** Một lần gửi: thứ được gửi, nó có mang cả sổ không, và dấu của mọi giờ máy đang giữ lúc này. */
export type Packet = { body: MachineSummary | V2Packet; full: boolean; marks: HourMarks }

function books(m: MachineSummary): Record<HourKind, Record<string, unknown>> {
  return { ledger: m.ledger ?? {}, tasks: m.tasks ?? {}, blocks: m.blocks ?? {} }
}

function empty(table: unknown): boolean {
  return !table || (typeof table === 'object' && Object.keys(table as object).length === 0)
}

/** The marks of the hours a summary holds; an empty hour is no hour, as the server reads it. */
/** Dấu của các giờ trong bản tóm tắt; giờ rỗng coi như không có, đúng như máy chủ đọc. */
export function hourMarks(m: MachineSummary): HourMarks {
  const out: HourMarks = { ledger: {}, tasks: {}, blocks: {} }
  const b = books(m)
  for (const kind of HOUR_KINDS) {
    for (const [hour, table] of Object.entries(b[kind])) if (!empty(table)) out[kind][hour] = sha256Hex(JSON.stringify(table)).slice(0, 16)
  }
  return out
}

/**
 * What to send: `v: 1` until the server said it reads `v: 2`; then the whole book when the server has none of it (no marks, or it asked),
 * or once the hour is due; else only the hours whose mark changed, and an empty table for each hour the computer no longer holds.
 */
/** Gửi gì: `v: 1` cho tới khi máy chủ nói nó đọc `v: 2`; sau đó cả sổ khi máy chủ chưa có gì (chưa có dấu, hoặc nó xin), hoặc khi tới hạn mỗi giờ; còn lại chỉ các giờ có dấu đổi, và một bảng rỗng cho mỗi giờ máy không còn giữ. */
export function packetFor(m: MachineSummary, state: SendState | undefined, now: number): Packet {
  const marks = hourMarks(m)
  if (!state?.v2) return { body: m, full: true, marks }
  const { v: _v, ledger: _l, tasks: _t, blocks: _b, ...rest } = m
  const b = books(m)
  const full = !state.acked || !!state.needFull || now >= (state.fullAfter ?? 0)
  const hours: V2Packet['hours'] = { ledger: {}, tasks: {}, blocks: {} }
  for (const kind of HOUR_KINDS) {
    for (const hour of Object.keys(marks[kind])) {
      if (full || state.acked![kind]?.[hour] !== marks[kind][hour]) hours[kind][hour] = b[kind][hour]
    }
    if (!full) for (const hour of Object.keys(state.acked![kind] ?? {})) if (!(hour in marks[kind])) hours[kind][hour] = {}
  }
  return { body: { ...rest, v: 2, full, hours }, full, marks }
}

/**
 * What the computer knows after the server took a send (a 2xx answer): whether it reads `v: 2` (`accepts`), and the marks it now holds,
 * which are the marks of this send, since the hours not sent were already the same. `needFull` drops them so the next send is the whole
 * book; a new `boot` drops the last two days so they go up again.
 */
/** Máy biết gì sau khi máy chủ nhận một lần gửi (trả 2xx): máy chủ có đọc `v: 2` không (`accepts`), và dấu máy chủ đang giữ, chính là dấu của lần gửi này, vì các giờ không gửi vốn đã giống. `needFull` bỏ hết dấu để lần sau gửi cả sổ; `boot` mới bỏ dấu của hai ngày gần nhất để chúng được gửi lại. */
export function afterAnswer(state: SendState | undefined, answer: string, sent: Packet, now: number, random: () => number = Math.random): SendState {
  let o: { accepts?: unknown; needFull?: unknown; boot?: unknown }
  try {
    o = (JSON.parse(answer) ?? {}) as typeof o
  } catch {
    o = {}
  }
  // an older server answers only {"ok": true}: back to v: 1, which it reads whole
  // máy chủ cũ chỉ trả {"ok": true}: quay về v: 1, loại nó đọc trọn
  if (!Array.isArray(o.accepts) || !o.accepts.includes(2)) return {}
  const boot = typeof o.boot === 'string' ? o.boot : undefined
  if (o.needFull === true) return { v2: true, boot, needFull: true }
  const acked: HourMarks = { ledger: { ...sent.marks.ledger }, tasks: { ...sent.marks.tasks }, blocks: { ...sent.marks.blocks } }
  if (state?.boot && boot && boot !== state.boot && !sent.full) {
    const from = Math.floor(now / 3_600_000) - RESEND_HOURS
    for (const kind of HOUR_KINDS) for (const hour of Object.keys(acked[kind])) if (Number(hour) >= from) delete acked[kind][hour]
  }
  const fullAfter = sent.full ? now + FULL_EVERY_MS + Math.round(random() * FULL_SPREAD_MS) : state?.fullAfter
  return { v2: true, acked, boot, ...(fullAfter !== undefined ? { fullAfter } : {}) }
}
