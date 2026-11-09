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
  const short = tool.startsWith('mcp__') ? tool.split('__').slice(-1)[0] ?? tool : tool
  return { verb: 'other', text: short }
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
