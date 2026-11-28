// What Claude is doing, as the app's transcript shows it: short tool summaries,
// the text Claude says between steps, and the task plan. Pure: no `$`.
// Việc Claude đang làm, như bản ghi của app hiển thị: tóm tắt ngắn các công cụ,
// lời Claude nói giữa các bước, và kế hoạch công việc. Hàm thuần: không dùng `$`.
import type { Activity, PlanItem, Verb } from '../types'
import { tx } from './lang'

const MAX_TEXT = 600

import { SECRET_FILE } from './edits'

const MEDIA_EXT = /\.(png|jpe?g|gif|webp|svg|mp4|mov|m4v|webm)$/i
const PREVIEW_EXT = /\.(png|jpe?g|gif|webp|svg|mp4|mov|m4v|webm|pdf)$/i
/** `@"a b.mp4"` or `@a.png` at a word start: a file the prompt attaches. */
/** `@"a b.mp4"` hoặc `@a.png` ở đầu một từ: một file mà lời nhắc đính kèm. */
const MENTION = /(?:^|\s)@(?:"([^"]+)"|(\S+))/g
/** A bare absolute path to an image or video, as a pasted path reads. */
/** Một đường dẫn tuyệt đối trần tới ảnh hoặc video, như khi dán đường dẫn. */
const BARE = /(?:^|\s)(\/[^\s"'`]+)/g

export const isMedia = (p: unknown): p is string => typeof p === 'string' && p.startsWith('/') && MEDIA_EXT.test(p)
/** A file worth showing when Claude opens it: an image, a video or a PDF. */
/** Một file đáng hiện khi Claude mở nó: ảnh, video hoặc PDF. */
export const isPreview = (p: unknown): p is string => typeof p === 'string' && p.startsWith('/') && PREVIEW_EXT.test(p)

const tidy = (p: string | undefined) => p?.replace(/[),.;:!?]+$/, '')
const hasExt = (p: string) => /\.[A-Za-z0-9]{1,8}$/.test(p.split('/').pop() ?? '')

/**
 * The files a prompt names: every @-attached file, and bare paths to images
 * and videos. Relative paths resolve against `cwd`. A secret-looking file is
 * left out, so its content never shows.
 */
/** Các file mà lời nhắc nêu tên: mọi file đính kèm bằng @, và đường dẫn trần tới ảnh và video. Đường dẫn tương đối được tính từ `cwd`. File trông như chứa bí mật bị bỏ ra, để nội dung của nó không bao giờ hiện. */
export function mediaPaths(text: string, cwd = ''): string[] {
  const out: string[] = []
  const add = (p: string) => { if (!SECRET_FILE.test(p) && !out.includes(p)) out.push(p) }
  for (const m of text.matchAll(MENTION)) {
    const raw = tidy(m[1] ?? m[2])
    if (!raw || !hasExt(raw)) continue
    add(raw.startsWith('/') ? raw : raw.startsWith('~/') ? raw : `${cwd.replace(/\/$/, '')}/${raw.replace(/^\.\//, '')}`)
  }
  for (const m of text.matchAll(BARE)) {
    const p = tidy(m[1])
    if (isMedia(p)) add(p)
  }
  return out.slice(0, 8)
}

/** Blocks the app or the engine puts into a message: reminders, results of background work, events. Not the person's words. */
/** Các khối mà app hoặc engine chèn vào tin nhắn: lời nhắc, kết quả việc chạy nền, sự kiện. Không phải lời của người dùng. */
const INSERTED = 'system-reminder|task-notification|agent-message|cross-session-message|scheduled-task|side-sessions-event|ci-monitor-event|local-command-stdout|local-command-stderr|local-command-caveat'
const INSERTED_BLOCK = new RegExp(`<(${INSERTED})\\b[^>]*>[\\s\\S]*?(?:</\\1>|$)`, 'g')

/** Whole messages the app sends by itself, with no tag around them: the one that resumes a session after the app was closed. */
/** Các tin nhắn trọn vẹn mà app tự gửi, không có thẻ bao quanh: câu cho phiên làm tiếp sau khi app bị đóng. */
const APP_SENT = new Set(['The app was quit while you were working. Please continue from where you left off.'])

/**
 * What the person typed, without the blocks the app inserted around it. A
 * block left open runs to the end of the message. Empty when the whole
 * message came from the app.
 */
/** Điều người dùng đã gõ, bỏ các khối app chèn quanh nó. Khối không đóng thì kéo tới hết tin nhắn. Rỗng khi cả tin nhắn là của app. */
export function ownWords(text: string): string {
  const own = text.replace(INSERTED_BLOCK, '\n').replace(/\n{3,}/g, '\n\n').trim()
  return APP_SENT.has(own) ? '' : own
}

const MAX_ASKED = 300

/** The feed line for a message the person sent, or undefined when nothing in it is theirs. */
/** Dòng hoạt động cho một tin nhắn người dùng gửi, hoặc undefined khi không có gì trong đó là của họ. */
export function youEntry(text: string, at: number, cwd = '', pasted = 0, shots: readonly string[] = []): Activity | undefined {
  const asked = ownWords(text)
  if (!asked && !pasted) return undefined
  const you: Activity = { at, kind: 'you', text: asked.length > MAX_ASKED ? `${asked.slice(0, MAX_ASKED - 1)}…` : asked }
  const media = mediaPaths(asked, cwd)
  if (media.length) you.media = media
  if (pasted) you.pasted = pasted
  if (shots.length) you.shots = [...shots]
  return you
}

/** `mcp__basic-memory__edit_note` reads as `basic-memory: edit note`, so the line says whose tool it is. */
/** `mcp__basic-memory__edit_note` đọc thành `basic-memory: edit note`, để dòng nói rõ công cụ của ai. */
function toolName(tool: string): string {
  const m = /^mcp__(.+?)__(.+)$/.exec(tool)
  if (!m) return tool.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase()
  const server = m[1]!.replace(/^plugin_[^_]+_/, '').replace(/^ccd_.*/, 'Claude app').replace(/^Claude_/, '').replace(/_/g, ' ')
  return `${server}: ${m[2]!.replace(/_/g, ' ')}`
}

const base = (p: unknown) => (typeof p === 'string' ? p.split('/').filter(Boolean).pop() ?? p : '')
const clip = (t: unknown, n = 90) => {
  const s = typeof t === 'string' ? t.replace(/\s+/g, ' ').trim() : ''
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

/** Tools that only steer the session and add nothing to read in a feed. */
/** Các công cụ chỉ điều khiển phiên và không có gì để đọc trong luồng hoạt động. */
const QUIET = /^(ToolSearch|mcp__ccd_turn__update_plan|mcp__ccd_turn__wrap_up)$/

const WORKER: Record<string, string> = {
  ask_gemini: 'Gemini', generate_image: 'Gemini', ask_chatgpt: 'ChatGPT', ask_local: 'Gemma',
  get_gemini_result: 'Gemini', get_image_result: 'Gemini', get_chatgpt_result: 'ChatGPT', get_local_result: 'Gemma',
}
/** The tools that draw images: Gemini's name carries what it is doing. */
/** Các công cụ vẽ ảnh: tên của Gemini cho biết nó đang làm gì. */
const IMAGE_TOOL = new Set(['generate_image', 'get_image_result'])
const workerName = (tool: string) => (IMAGE_TOOL.has(tool) ? tx('Gemini (drawing images)') : WORKER[tool]!)

/** One line for a tool call, or undefined for one not worth a line. */
/** Một dòng cho một lệnh gọi công cụ, hoặc undefined nếu không đáng có một dòng. */
export function describeTool(tool: string, args: Record<string, unknown>): { verb: Verb; text: string; media?: string[] } | undefined {
  if (QUIET.test(tool)) return undefined
  switch (tool) {
    case 'Bash':
      return { verb: 'run', text: clip(args.description) || clip(args.command, 60) }
    case 'Read':
      return isPreview(args.file_path) && !SECRET_FILE.test(args.file_path)
        ? { verb: 'read', text: base(args.file_path), media: [args.file_path] }
        : { verb: 'read', text: base(args.file_path) }
    case 'Edit':
    case 'Write':
    case 'NotebookEdit':
      return { verb: 'edit', text: base(args.file_path ?? args.notebook_path) }
    case 'Grep':
    case 'Glob':
      return { verb: 'search', text: clip(args.pattern, 60) }
    case 'WebSearch':
      return { verb: 'web', text: clip(args.query, 70) }
    case 'WebFetch':
      return { verb: 'web', text: clip(args.url, 70) }
    case 'Agent':
      return { verb: 'delegate', text: clip(args.description, 70) || tx('assistant') }
    case 'Skill':
      return { verb: 'other', text: tx('skill {name}', { name: clip(args.skill, 40) }) }
    case 'AskUserQuestion':
      return { verb: 'ask', text: tx('asks you') }
  }
  const worker = /^mcp__(?:ai-workers|ask-gemini)__([a-z_]+)$/.exec(tool)?.[1]
  if (worker && WORKER[worker]) {
    return { verb: 'delegate', text: worker.startsWith('get_') ? tx('waiting for the result from {worker}', { worker: workerName(worker) }) : tx('handing work to {worker}', { worker: workerName(worker) }) }
  }
  if (/firecrawl|search/i.test(tool)) return { verb: 'web', text: clip(args.query ?? args.url, 70) || tx('web lookup') }
  if (/Browser|browser|playwright|chrome/.test(tool)) return { verb: 'browser', text: clip(args.url, 60) || tx('browser action') }
  return { verb: 'other', text: toolName(tool) }
}

export function sayEntry(text: string, at: number): Activity | undefined {
  const t = text.trim()
  if (!t) return undefined
  return { at, kind: 'say', text: t.length > MAX_TEXT ? `${t.slice(0, MAX_TEXT - 1)}…` : t }
}

type PlanArgs = {
  items?: { content?: unknown; status?: unknown }[]
  advance?: unknown
  done?: unknown
  start?: unknown
}

const STATUSES = new Set(['pending', 'in_progress', 'completed'])

/** Applies one update_plan call the way the app's task list does. */
/** Áp dụng một lệnh update_plan giống cách danh sách việc của app làm. */
export function applyPlan(plan: PlanItem[] | undefined, raw: Record<string, unknown>): PlanItem[] {
  const a = raw as PlanArgs
  if (Array.isArray(a.items)) {
    return a.items.map(i => ({
      content: clip(i.content, 120),
      status: (STATUSES.has(String(i.status)) ? i.status : 'pending') as PlanItem['status'],
    }))
  }
  let next = (plan ?? []).map(i => ({ ...i }))
  if (Array.isArray(a.done)) {
    for (const n of a.done) if (typeof n === 'number' && next[n - 1]) next[n - 1]!.status = 'completed'
  }
  if (typeof a.start === 'number' && next[a.start - 1]) {
    next = next.map(i => (i.status === 'in_progress' ? { ...i, status: 'completed' } : i))
    next[a.start - 1]!.status = 'in_progress'
  }
  if (a.advance === true) {
    const cur = next.findIndex(i => i.status === 'in_progress')
    if (cur >= 0) next[cur]!.status = 'completed'
    const after = next.findIndex(i => i.status === 'pending')
    if (after >= 0) next[after]!.status = 'in_progress'
  }
  return next
}

/** At the end of the work (wrap-up) every step counts as done. */
/** Khi kết thúc công việc (wrap-up), mọi bước đều tính là xong. */
export function finishPlan(plan: PlanItem[] | undefined): PlanItem[] | undefined {
  return plan?.map(i => ({ ...i, status: 'completed' }))
}

/** The image types a browser draws as a picture and nothing else; no SVG, which can carry script. */
/** Các loại ảnh mà trình duyệt vẽ thành hình và không gì khác; không có SVG, thứ có thể mang script. */
const SHOT_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
/** A pasted image larger than this (decoded) is not copied: its line keeps the count only. */
/** Ảnh dán lớn hơn mức này (sau giải mã) thì không chép: dòng của nó chỉ giữ con số. */
export const MAX_SHOT_BYTES = 6 * 1024 * 1024

/** The name of the copy of pasted image `index` of a message sent at `at`: letters, digits, dots and dashes only. */
/** Tên bản sao của ảnh dán thứ `index` trong tin nhắn gửi lúc `at`: chỉ gồm chữ, số, dấu chấm và gạch nối. */
export function shotName(session: string, at: number, index: number): string {
  return `${session.replace(/[^A-Za-z0-9-]/g, '')}.${Math.trunc(at)}.${Math.trunc(index)}`
}

/**
 * The file that holds one pasted image for the page on this computer: a
 * script the page loads, since the engine writes text only. Undefined for a
 * type the page will not draw or for bytes that are not base64.
 */
/** File giữ một ảnh dán cho trang trên máy này: một script mà trang nạp, vì engine chỉ ghi được chữ. Undefined với loại ảnh trang không vẽ hoặc với dữ liệu không phải base64. */
export function shotFile(name: string, mediaType: string, base64: string): string | undefined {
  if (!SHOT_TYPES.has(mediaType) || !base64 || !/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) return undefined
  return `window.__aiWorkerShot && window.__aiWorkerShot(${JSON.stringify(name)}, ${JSON.stringify(`data:${mediaType};base64,${base64}`)});\n`
}

/**
 * Copies of pasted images to remove from `shots/`: this session's own that no
 * line of its feed shows any more, and anyone's older than STALE_MS.
 */
/** Các bản sao ảnh dán cần xoá khỏi `shots/`: của chính phiên này mà không dòng nào trong luồng còn hiện, và của bất kỳ phiên nào cũ hơn STALE_MS. */
export function unusedShots(
  entries: readonly { name: string; kind: string; mtimeMs: number }[],
  now: number,
  session: string,
  activity: readonly Activity[],
): string[] {
  const shown = new Set(activity.flatMap(a => a.shots ?? []).map(n => `${n}.js`))
  const mine = `${session.replace(/[^A-Za-z0-9-]/g, '')}.`
  return entries
    .filter(f => f.kind === 'file' && f.name.endsWith('.js') && (now - f.mtimeMs > STALE_MS || (f.name.startsWith(mine) && !shown.has(f.name))))
    .map(f => f.name)
}

const KINDS = new Set(['you', 'say', 'tool'])

/**
 * The feed lines kept in a session's own file (`sessions/<id>.js`), for a
 * session that starts again with an empty memory: after an update or when the
 * app is reopened. Anything that is not a well-formed line is left out.
 */
/** Các dòng hoạt động còn trong file của chính phiên (`sessions/<id>.js`), cho phiên bắt đầu lại với bộ nhớ rỗng: sau khi cập nhật hoặc khi app mở lại. Thứ gì không phải một dòng đúng dạng thì bỏ ra. */
export function savedActivity(file: string, max = 80): Activity[] {
  try {
    const from = file.indexOf(', {')
    const to = file.lastIndexOf(')')
    if (from < 0 || to < from) return []
    const data = JSON.parse(file.slice(from + 2, to)) as { activity?: unknown }
    if (!Array.isArray(data.activity)) return []
    return (data.activity as Activity[])
      .filter(a => a && typeof a.at === 'number' && KINDS.has(a.kind) && typeof a.text === 'string')
      .slice(-max)
  } catch {
    return []
  }
}

/**
 * The feed after a session started again: the lines its file kept, then the
 * lines its memory already holds. A kept line the memory has too counts once,
 * and one newer than the memory's first line is left out, so nothing is doubled.
 */
/** Luồng hoạt động sau khi một phiên bắt đầu lại: các dòng file của nó còn giữ, rồi tới các dòng bộ nhớ đang có. Dòng mà bộ nhớ cũng có thì tính một lần, và dòng mới hơn dòng đầu của bộ nhớ thì bỏ ra, để không gì bị lặp. */
export function mergeActivity(kept: readonly Activity[], now: readonly Activity[], max = 80): Activity[] {
  const first = now[0]?.at ?? Infinity
  return [...kept.filter(a => a.at < first), ...now].slice(-max)
}

/** The last folder of a working directory, on macOS, Linux (`/`) or Windows (`\`). */
/** Thư mục cuối của một thư mục làm việc, trên macOS, Linux (`/`) hoặc Windows (`\`). */
export function folderName(cwd: string): string {
  return cwd.split(/[\\/]/).filter(Boolean).pop() ?? ''
}

/** Office files of sessions untouched this long are cleared; an open session rewrites its own every 30 s. */
/** File văn phòng của phiên bị bỏ không động tới quá lâu này sẽ bị xoá; phiên đang mở tự ghi lại file của mình mỗi 30 giây. */
export const STALE_MS = 7 * 24 * 60 * 60 * 1000

/** Names of session files in `sessions/` older than STALE_MS, never `keep` (this session's own). */
/** Tên các file phiên trong `sessions/` cũ hơn STALE_MS, không bao giờ gồm `keep` (file của chính phiên này). */
export function staleSessionFiles(
  entries: readonly { name: string; kind: string; mtimeMs: number }[],
  now: number,
  keep: string,
): string[] {
  return entries
    .filter(f => f.kind === 'file' && f.name.endsWith('.js') && f.name !== `${keep}.js` && now - f.mtimeMs > STALE_MS)
    .map(f => f.name)
}
