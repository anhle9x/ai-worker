// A manager's computer paired with the company board, so Claude can answer questions about the team's numbers.
// The plugin pairs the way the manager browser extension does: it asks the server for an 8-digit code, an admin approves
// the code on the Admin page, and the plugin gets a key that reads only the wall view: names, states, cost and quota,
// never an email or an IP. The key stays on this computer; an admin can revoke it at any time.
// Máy của quản lý ghép với bảng công ty, để Claude trả lời được câu hỏi về số liệu của cả đội.
// Plugin ghép theo đúng cách của tiện ích trình duyệt cho quản lý: xin máy chủ một mã 8 số, quản trị duyệt mã đó ở trang
// Quản trị, rồi plugin nhận một khoá chỉ đọc được phần treo tường: tên, trạng thái, chi phí và hạn mức,
// không bao giờ có email hay IP. Khoá nằm lại trên máy này; quản trị thu hồi được bất cứ lúc nào.
import { tx } from './lang'

export const BOARD_TOOL = 'office_board'
export const BOARD_KEY = 'board-pairing'
export const BOARD_SCHEMA = { type: 'object', properties: {} } as const
// the server keeps a code this long; a little less here, so a code about to lapse is not shown again
// máy chủ giữ mã ngần này; ở đây ngắn hơn một chút, để mã sắp hết hạn không được đưa ra lần nữa
export const BOARD_CODE_MS = 9 * 60_000

export type BoardPairing = { token?: string; name?: string; pending?: { key: string; code: string; at: number } }

/** How the plugin names itself to the server: the Admin page shows it as a Claude plugin, apart from TVs and extensions. */
/** Cách plugin tự xưng tên với máy chủ: trang Quản trị hiện nó là plugin Claude, tách khỏi TV và tiện ích. */
export function boardUserAgent(version: string | undefined, system: string): string {
  return `AI-Worker-Plugin/${version || '0'} (${system})`
}

export function boardToolDescription(): string {
  return [
    tx("Read the company board's live numbers for this team's use of Claude: who is working, who is waiting for an answer and for how long, cost today and over 7 days, quota left, per person and per office."),
    tx('Use it when the user asks about the team, an office or a person on the board. It takes no input and only reads.'),
  ].join(' ')
}

type Person = {
  name?: unknown; branch?: unknown; status?: unknown; waitingSince?: unknown; usdToday?: unknown; usd7d?: unknown
  quota?: { windows?: { kind?: unknown; pct?: unknown }[] } | null; models?: Record<string, unknown> | null
}
type Board = { updatedAt?: unknown; tzOffsetHours?: unknown; tasks24?: unknown; people?: Person[]; branches?: { id?: unknown; name?: unknown }[] }

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const money = (v: number): string => v.toFixed(2)
const STATE: Record<string, string> = { working: 'working', waiting: 'waiting for an answer', open: 'idle', offline: 'offline' }

/** `claude-fable-5-2` reads as `Fable 5.2`; any other name is kept as it is. */
/** `claude-fable-5-2` đọc thành `Fable 5.2`; tên khác thì giữ nguyên. */
export function modelLabel(id: string): string {
  const m = /^claude-([a-z]+)-(\d+)-(\d+)/.exec(id)
  return m ? `${m[1]![0]!.toUpperCase()}${m[1]!.slice(1)} ${m[2]}.${m[3]}` : id
}

// The board's numbers as plain lines for Claude to answer from: the team, each office, then each person.
// English with fixed column names; Claude answers the user in the user's own language.
// Số liệu của bảng thành các dòng chữ thường để Claude dựa vào mà trả lời: cả đội, từng văn phòng, rồi từng người.
// Tiếng Anh với tên cột cố định; Claude trả lời người dùng bằng ngôn ngữ của họ.
export function summarizeBoard(data: Board, now: number): string {
  const people = Array.isArray(data.people) ? data.people : []
  const offices = new Map<string, string>()
  for (const b of Array.isArray(data.branches) ? data.branches : []) if (typeof b.id === 'string') offices.set(b.id, String(b.name ?? b.id))
  const officeOf = (p: Person) => offices.get(String(p.branch ?? '')) ?? 'no office (mobile or not assigned)'
  const state = (p: Person) => (typeof p.status === 'string' && STATE[p.status] ? p.status : 'offline')
  const count = (list: Person[], s: string) => list.filter(p => state(p) === s).length
  const sum = (list: Person[], k: 'usdToday' | 'usd7d') => list.reduce((a, p) => a + num(p[k]), 0)
  const offset = num(data.tzOffsetHours)
  const at = num(data.updatedAt) || now
  const stamp = new Date(at + offset * 3_600_000).toISOString().slice(0, 16).replace('T', ' ')
  const tasks = Array.isArray(data.tasks24) ? (data.tasks24 as unknown[]).map(row => (Array.isArray(row) ? row.reduce((a: number, v) => a + num(v), 0) : 0)) : []
  const lines = [
    `AI Worker board at ${stamp} (UTC${offset >= 0 ? '+' : ''}${offset}). Amounts are US dollars at API prices.`,
    `Team: ${people.length} people, ${count(people, 'working')} working, ${count(people, 'waiting')} waiting for an answer, ${count(people, 'open')} idle, ${count(people, 'offline')} offline. Cost today ${money(sum(people, 'usdToday'))}, last 7 days ${money(sum(people, 'usd7d'))}.`,
  ]
  if (tasks.length === 3) lines.push(`Tasks handed to helper assistants in the last 24 hours: Gemini ${tasks[0]}, ChatGPT ${tasks[1]}, Gemma ${tasks[2]}.`)
  const names = [...new Set(people.map(officeOf))]
  if (names.length) {
    lines.push('', 'Offices (people | working | waiting | cost today | cost 7 days):')
    for (const name of names) {
      const here = people.filter(p => officeOf(p) === name)
      lines.push(`- ${name} | ${here.length} | ${count(here, 'working')} | ${count(here, 'waiting')} | ${money(sum(here, 'usdToday'))} | ${money(sum(here, 'usd7d'))}`)
    }
  }
  if (people.length) {
    lines.push('', 'People (office | state | minutes waiting | cost today | cost 7 days | quota used in 5 hours % | quota used in 7 days % | model):')
    for (const p of people) {
      const waited = state(p) === 'waiting' && num(p.waitingSince) ? String(Math.max(0, Math.round((now - num(p.waitingSince)) / 60_000))) : '-'
      const quota = (kind: string) => {
        const w = (p.quota?.windows ?? []).find(x => x.kind === kind)
        return w && typeof w.pct === 'number' ? String(Math.round(w.pct)) : '-'
      }
      const top = Object.entries(p.models ?? {}).sort((a, b) => num(b[1]) - num(a[1]))[0]
      lines.push(
        `- ${String(p.name ?? '?')} | ${officeOf(p)} | ${STATE[state(p)]} | ${waited} | ${money(num(p.usdToday))} | ${money(num(p.usd7d))} | ${quota('five_hour')} | ${quota('seven_day')} | ${top ? modelLabel(top[0]) : '-'}`,
      )
    }
  }
  return lines.join('\n')
}

/** What to say when the server did not give the numbers. */
/** Nói gì khi máy chủ không đưa số liệu. */
export function boardUnreachable(status: number): string {
  if (status === 403) return tx('The board refused this network (403): it answers only from the office network.')
  if (status === 429) return tx('The board is busy with too many pairing requests. Try again in a few minutes.')
  return tx('The board could not be reached (status {status}). Check the network and try again.', { status })
}

/** The steps shown with a fresh code: who approves it, where, and what Claude can read once it is approved. */
/** Các bước hiện kèm một mã mới: ai duyệt, ở đâu, và Claude đọc được gì sau khi được duyệt. */
export function pairingSteps(code: string, server: string): string {
  return [
    tx('Pairing code: {code} (good for 10 minutes).', { code: `${code.slice(0, 4)}-${code.slice(4)}` }),
    '',
    tx('1. An admin of the board opens {server}/admin, goes to "TV screens", types the code and clicks "View request", then "Approve".', { server }),
    tx('2. Type /ai-worker:board here again to finish.'),
    '',
    tx('Once paired, Claude on this computer can read the board when you ask about the team: names, states, cost and quota, never an email or an IP. An admin can revoke it on the same page.'),
  ].join('\n')
}

export function pairedText(name: string): string {
  return [
    tx('This computer is paired with the board as "{name}".', { name }),
    tx('Ask Claude in your own words, for example: who is waiting longest right now? Which office spent the most this week?'),
    tx('To stop: /ai-worker:board unpair'),
  ].join('\n')
}
