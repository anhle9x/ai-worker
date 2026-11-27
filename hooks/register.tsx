// Pixel office (browser view and pane): watches the ai-workers MCP calls (Gemini, ChatGPT, Gemma,
// Nano Banana) and the main turn, and draws who is working on what.
// Privacy: only a fixed kind label per task is kept; prompts and results never
// leave the hook.
// Văn phòng pixel (trang trình duyệt và khung): theo dõi các lệnh gọi MCP ai-workers (Gemini, ChatGPT, Gemma,
// Nano Banana) và lượt chính, rồi vẽ ai đang làm gì.
// Riêng tư: chỉ giữ một nhãn loại cố định cho mỗi việc; lời nhắc và kết quả không bao giờ
// rời khỏi hook.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ToolCallResult } from 'claude-code'

import type { Activity, BlockKind, Job, TeamState, WorkerId } from '../types'
import { MAX_SHOT_BYTES, applyPlan, describeTool, finishPlan, folderName, savedActivity, sayEntry, shotFile, shotName, staleSessionFiles, unusedShots, youEntry } from './activity'
import { EDIT_TOOLS, addUsage, buildFileEdit, compactKeepInstructions, compactedNotice, contextAdvice, contextFill, contextNoteForClaude, contextWarning, costDelta, formatUsd, shortCount, toUsage } from './edits'
import { answerModel, buildMachineSummary, PACE_MIN_MS, quotaWarning, HARDWARE_ID_PROBES, hardwareMark, LAN_IP_PROBES, mergeShare, mergeTeam, newDeviceId, OPEN_MS, parseHardwareId, parseLanIp, parseSessionFile, readShareConfig, SHARE_OFF, SHARE_WARN_MS, shareProblem, shareWarning, signedInEmail, toQuota } from './team'
import { chatTitle, cleanTitle, newTitles, nextTitle, notePrompt, noteRename, titleDue } from './titles'
import { lastCost, logSpend, readLedger, rememberCost, repairLedgerOnce, writeLedger, writeLongSpend, type LedgerIo } from './ledger'
import { DEVICE_KEY, send, type SendMem, type SendTarget } from './send'
import type { Store } from './io'
import type { ShareConfig } from './team'
import { DESKTOP_BUNDLE_ID, DETACH_PERL, LINUX_DETACH, LINUX_FIND_SCRIPT, LINUX_RESTART_SCRIPT, RESTART_SCRIPT, WINDOWS_FIND_SCRIPT, WINDOWS_HELPER, WINDOWS_RESTART_SCRIPT, WINDOWS_CLAUDE_SCRIPT, UNIX_CLAUDE_SCRIPT, claudeCandidate, isClaudeCodeVersion, findHostApp, parseLinuxHost, parseWindowsHost, parseHash, hasSigningKeys, parseSignatureResult, parseManifest, releaseKeys, shouldOfferUpdate, type SignatureResult, type Manifest } from './update'
import { AGY_BRAIN, IMAGE_DIR, IMAGE_SCHEMA, IMAGE_SETTLE_MS, OLLAMA_URL, PROMPT_LEVEL_SCHEMA, PROMPT_SCHEMA, WORKER_TIMEOUT_MS, imageArgv, imageTargets, newImages, safeImageName, sendingNeedsAsking, sendingRefusal, agyArgv, codexArgv, codexInput, isBatchLauncher, delegationRules, gemmaAnswer, gemmaRequest, mcpConfigured, ownTools, pickGemma } from './workers'
import type { OwnWorkers } from './workers'
import { pageLanguageScript, setLang, tx } from './lang'
import { BOARD_SCHEMA, BOARD_TOOL, boardToolDescription, boardUserAgent } from './board'
import { readBoard, readPairing, runBoard as runBoardOn, type BoardIo } from './boardtool'
import { buildHelp, skillLine } from './help'
import { voiceSettingsCommand, voiceSteps } from './voice'
import { dangerNote, dangerQuestion, destructiveCommand } from './guard'
import { findSecrets, secretRefusal } from './secrets'
import { commitIn, commitQuestion, diffCommand, newFileDiffCommand, secretsInDiff, untrackedCommand } from './commitscan'
import { trailNote, trailProblems } from './committrail'
import { OUTSIDE_TEXT_TOOL, findInjection, injectionNote, injectionToast } from './injection'
import { findRepoConfig, readRepoFiles, rememberRepo, repoKey, repoNews, repoNote, repoToast } from './repoconfig'
import type { RepoSeen } from './repoconfig'
import { answerFlags, answerNote, answerToast, checkAnswer } from './answers'
import { addDelegation, delegationTool, makeDelegation, newSalt, promptHash, recentDelegations } from './delegations'
import { handoffSection, newestNotes, noteName } from './handoff'
import type { HandoffNote } from './handoff'
import type { VoiceSystem } from './voice'
import type { SkillLine } from './help'
import { BADGE_MS, BRAND, FX_MS, WORKERS, applyConfig, setInstalled, buildOfficeSvg, clockLabel, dayLabel, formatSecs, workerView, assistantName } from './office'
import type { OfficeConfig } from './office'

const PANE = 'ai-worker'
const MAX_JOBS = 40
const MAX_EDITS = 30
const MAX_ACTIVITY = 80
const PLAN_TOOL = /(^|__)update_plan$/

/** Adds a feed line in time order: a step's text is stamped when the step began, so it lands before the tool calls that ran while it streamed. */
/** Thêm một dòng vào luồng hoạt động theo thứ tự thời gian: chữ của một bước được đóng dấu lúc bước bắt đầu, nên nó nằm trước các lệnh gọi công cụ chạy trong lúc nó đang phát. */
function pushActivity(s: TeamState, a: Activity): TeamState {
  const list = [...(s.activity ?? [])]
  let i = list.length
  while (i > 0 && (list[i - 1]?.at ?? 0) > a.at) i--
  list.splice(i, 0, a)
  return { ...s, activity: list.slice(-MAX_ACTIVITY) }
}
/** The question box a turn can end with (the desktop app's next-step ask). */
/** Hộp câu hỏi mà một lượt có thể kết thúc bằng nó (câu hỏi bước tiếp của app trên máy tính). */
const WRAP_UP = /(^|__)wrap_up$/

const initial: TeamState = { jobs: [], now: 0 }
const team = atom({ plugin: 'ai-worker', key: 'team' } as const, initial)

/** The label of a task, read when the task starts so it follows the language in use. */
/** Nhãn của một việc, đọc lúc việc bắt đầu để nó theo ngôn ngữ đang dùng. */
type Op = { worker: WorkerId; isAsk: boolean; kind: () => string }
const KIND_GEMINI = () => tx('Gemini task')
const KIND_IMAGE = () => tx('Drawing an image')
const KIND_REVIEW = () => tx('Code review')
const KIND_LOCAL = () => tx('Working on this computer')
const OPS: Record<string, Op> = {
  ask_gemini: { worker: 'gemini', isAsk: true, kind: KIND_GEMINI },
  generate_image: { worker: 'gemini', isAsk: true, kind: KIND_IMAGE },
  ask_chatgpt: { worker: 'chatgpt', isAsk: true, kind: KIND_REVIEW },
  ask_local: { worker: 'gemma', isAsk: true, kind: KIND_LOCAL },
  get_gemini_result: { worker: 'gemini', isAsk: false, kind: KIND_GEMINI },
  get_image_result: { worker: 'gemini', isAsk: false, kind: KIND_IMAGE },
  get_chatgpt_result: { worker: 'chatgpt', isAsk: false, kind: KIND_REVIEW },
  get_local_result: { worker: 'gemma', isAsk: false, kind: KIND_LOCAL },
}
const WORKER_TOOL = /^mcp__(?:ai-workers|ask-gemini|ai-worker)__([a-z_]+)$/
const OWN_TOOL = /^mcp__ai-worker__(ask_local|ask_chatgpt|ask_gemini|generate_image)$/
// helpers whose text leaves this computer, served by the plugin or by a separate ai-workers server
// các trợ lý mà chữ gửi cho chúng rời khỏi máy này, do plugin phục vụ hoặc do một server ai-workers riêng
const OUTSIDE_HELPER = /^mcp__ai-workers?__(ask_chatgpt|ask_gemini|generate_image)$/

// the question for a `git commit` whose added lines hold a secret, or undefined; asked once per command, since the
// permission box and the check both want it a moment apart
// câu hỏi cho một lệnh `git commit` mà các dòng thêm vào có bí mật, hoặc undefined; mỗi lệnh chỉ hỏi git một lần, vì
// hộp xin phép và bước kiểm đều cần nó cách nhau một lúc
const commitChecked = new Map<string, { at: number; question?: string }>()
async function commitSecretQuestion($: EngineInterface, command: string): Promise<string | undefined> {
  const run = commitIn(command)
  if (!run) return undefined
  const now = await $.clock.now()
  const seen = commitChecked.get(command)
  if (seen && now - seen.at < 15_000) return seen.question
  let question: string | undefined
  try {
    const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
    const dir = run.dir.startsWith('~') ? home + run.dir.slice(1) : run.dir
    const where = dir ? { cwd: dir } : {}
    let r = await $.process.run(diffCommand(run), { ...where, timeoutMs: 10_000 })
    // a repository with no commit yet has no HEAD: what is staged is then all there is
    // repo chưa có commit nào thì không có HEAD: khi đó chỉ có phần đã stage
    if (r.exitCode !== 0 && run.added) r = await $.process.run(diffCommand({ dir: run.dir, all: false }), { ...where, timeoutMs: 10_000 })
    let diff = r.exitCode === 0 ? r.stdout : ''
    // the new files an add earlier in the line will stage, each read as a diff that adds every line (at most 50)
    // các file mới mà lệnh add đứng trước trong dòng sẽ stage, mỗi file đọc như một diff thêm mọi dòng (tối đa 50)
    const listing = untrackedCommand(run)
    if (listing) {
      const list = await $.process.run(listing, { ...where, timeoutMs: 10_000 })
      const files = list.exitCode === 0 ? list.stdout.split('\0').filter(Boolean).slice(0, 50) : []
      for (const file of files) {
        // git diff --no-index ends with 1 when the two sides differ, which they always do here
        // git diff --no-index kết thúc với 1 khi hai bên khác nhau, ở đây luôn khác
        const one = await $.process.run(newFileDiffCommand(file), { ...where, timeoutMs: 10_000 })
        if (one.exitCode === 0 || one.exitCode === 1) diff += '\n' + one.stdout
      }
    }
    const found = secretsInDiff(diff)
    if (found.length) question = commitQuestion(found)
  } catch {
    // git could not be asked: the commit goes on as the rules beneath say
    // không hỏi được git: commit đi tiếp theo các quy tắc bên dưới
  }
  commitChecked.clear()
  commitChecked.set(command, { at: now, question })
  return question
}

// the commit message check (committrail.ts): HEAD before a git commit runs, then the new commit's message once it has
// kiểm lời commit (committrail.ts): HEAD trước khi một lệnh git commit chạy, rồi lời của commit mới khi nó đã chạy
type TrailStart = { where: { cwd?: string }; head: string }
async function trailStart($: EngineInterface, command: string): Promise<TrailStart | undefined> {
  const run = commitIn(command)
  if (!run) return undefined
  try {
    const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
    const dir = run.dir.startsWith('~') ? home + run.dir.slice(1) : run.dir
    const where = dir ? { cwd: dir } : {}
    const r = await $.process.run(['git', 'rev-parse', '--verify', '-q', 'HEAD'], { ...where, timeoutMs: 5_000 })
    // a repository with no commit yet has no HEAD: any commit made is new
    // repo chưa có commit nào thì không có HEAD: commit nào được tạo cũng là mới
    return { where, head: r.exitCode === 0 ? r.stdout.trim() : '' }
  } catch {
    return undefined
  }
}
async function trailEnd($: EngineInterface, start: TrailStart): Promise<string | undefined> {
  try {
    const head = await $.process.run(['git', 'rev-parse', '--verify', '-q', 'HEAD'], { ...start.where, timeoutMs: 5_000 })
    // no new commit (it failed, or nothing to commit): nothing to say
    // không có commit mới (hỏng, hoặc không có gì để commit): không có gì để nói
    if (head.exitCode !== 0 || head.stdout.trim() === start.head) return undefined
    const log = await $.process.run(['git', 'log', '-1', '--format=%B'], { ...start.where, timeoutMs: 5_000 })
    const problems = log.exitCode === 0 ? trailProblems(log.stdout) : []
    return problems.length ? trailNote(problems) : undefined
  } catch {
    return undefined
  }
}

const PENDING = /job_id:\s*([A-Za-z0-9_-]+)/

/** A label for a Gemini task from keywords only; the prompt itself is not kept. */
/** Nhãn cho một việc của Gemini chỉ từ từ khoá; chính lời nhắc không được giữ. */
function geminiKind(prompt: unknown): string {
  const p = typeof prompt === 'string' ? prompt.toLowerCase() : ''
  if (/phản biện|ý kiến|góp ý|đánh giá|critique|review|opinion|feedback|evaluate/.test(p)) return tx('Critique') // i18n-allow
  if (/tra cứu|tìm|search|nguồn|mới nhất|giá|phiên bản|look up|find|source|latest|price|version/.test(p)) return tx('Web research') // i18n-allow
  if (/tóm tắt|summar/.test(p)) return tx('Summary') // i18n-allow
  return KIND_GEMINI()
}

const CLAUDE_TOOLS = (): Record<string, string> => ({
  Read: tx('Read file'), Edit: tx('Edit file'), Write: tx('Write file'), Bash: tx('Run command'), Grep: tx('Search code'),
  Glob: tx('Find files'), WebSearch: tx('Web search'), WebFetch: tx('Read web page'), Agent: tx('Delegate to assistant'), Skill: tx('Open skill'),
  Artifact: tx('Publish page'), AskUserQuestion: tx('Ask you'),
})
function claudeLabel(tool: string): string {
  const known = CLAUDE_TOOLS()[tool]
  if (known) return known
  if (/firecrawl|search/i.test(tool)) return tx('Web search')
  if (/Browser|browser|playwright|chrome/.test(tool)) return tx('Use browser')
  return tx('Working')
}
/** What Claude is doing while it starts a subagent: the helper by its type and the model asked for, when the call names one. */
/** Claude đang làm gì khi khởi tạo một trợ lý con: trợ lý theo loại và mô hình được yêu cầu, khi lệnh gọi có nêu. */
function agentLabel(args: Record<string, unknown>): string {
  const type = typeof args.subagent_type === 'string' ? args.subagent_type.trim().slice(0, 40) : ''
  const name = assistantName(type || 'general-purpose', typeof args.model === 'string' ? args.model : undefined)
  return name === 'general-purpose' ? tx('Delegate to assistant') : tx('Handing work to {worker}', { worker: name })
}
const WORKER_NAME: Record<WorkerId, string> = { claude: 'Claude', gemini: 'Gemini', chatgpt: 'ChatGPT', gemma: 'Gemma' }

// The browser view reads these files; they hold kind labels, times, token
// counts and edited-file diffs (secret-looking files by name only).
// Each session writes sessions/<id>.js; sessions.js lists the ids.
// Trang trình duyệt đọc các file này; chúng chứa nhãn loại việc, thời gian, số
// token và phần khác biệt của file đã sửa (file trông như chứa bí mật chỉ có tên).
// Mỗi phiên ghi sessions/<id>.js; sessions.js liệt kê các id.
const WEB_DIR = '/.local/share/ai-worker'
const UPDATE_KEY = 'update'
const sharedRules = () => [
  tx('# How to work with the user'),
  tx('- When guiding the user through steps, every step must say: where to do it (which app, link or computer), what to click, and what the right result looks like. Explain any technical word right away in plain words.'),
  tx('- Do not send to outside AI services (ChatGPT, Gemini...): names or personal information, internal documents, unpublished company figures, keys, passwords, internal addresses.'),
  tx('- Split work across many assistants that check each other only when the task is large or hard to undo, and first ask the user one question with buttons saying what the task is, why, and that it uses a lot of quota; once agreed, run exactly that task. Do not make the user turn on the Ultracode switch.'),
  tx('- If the user pastes something that looks like a password, a key or someone else\'s personal data, point it out before going on.'),
  tx('- When the user wants to speak instead of typing, or asks how to dictate in Vietnamese or another language: tell them to type `/ai-worker:voice`. It opens the dictation settings of their computer and shows the steps; do not walk them through the settings yourself.'),
  tx('- After changing an interface, open the real page and look at both the desktop and the phone size before saying it is done; if you could not look, say clearly that you did not.'),
  tx('- Facts such as prices, dates, versions and rules: open at least one original source to check and name the source; if you could not check, say clearly "not verified".'),
  tx('- End with one clear recommendation and the reason for it, not just a list of options for the user to choose from.'),
].join('\n')
const UPDATE_EVERY_MS = 4 * 3_600_000
const UPDATE_RETRY_MS = 30 * 60_000
const LIST_EVERY_MS = 30_000
let webDir: string | undefined
let me: { id: string; name: string } | undefined
/** Images pasted into the prompt being submitted, until its turn starts. */
/** Số ảnh được dán vào lời nhắc đang gửi, cho tới khi lượt của nó bắt đầu. */
let pastedImages = 0
/** The copies of those images kept for the page on this computer, by name in `shots/`. */
/** Các bản sao của những ảnh đó được giữ cho trang trên máy này, theo tên trong `shots/`. */
let pastedShots: string[] = []
let listedAt = 0
/** When this session last did something (saved a change); a heartbeat keeps it, only `seenAt` moves. */
/** Lần cuối phiên này làm gì đó (lưu một thay đổi); nhịp tim giữ nó, chỉ `seenAt` đổi. */
let activeAt = 0

async function webFolder($: EngineInterface): Promise<string> {
  // HOME on macOS and Linux, USERPROFILE on Windows
  // HOME trên macOS và Linux, USERPROFILE trên Windows
  webDir ??= `${(await $.env.get('HOME')) ?? (await $.env.get('USERPROFILE')) ?? ''}${WEB_DIR}`
  return webDir
}

// ---- the chat's title, renewed as the talk moves on (hooks/titles.ts) ----------------------------
// ---- tiêu đề cuộc trò chuyện, làm mới khi cuộc nói chuyện đi tiếp (hooks/titles.ts) ----------------------------
const titles = newTitles()

/** Asks a small model for a short title that fits what the person has been asking lately. */
/** Nhờ một mô hình nhỏ đặt tiêu đề ngắn hợp với những gì người dùng hỏi gần đây. */
async function makeTitle($: EngineInterface) {
  if (!titleDue(titles)) return
  try {
    const r = await $.model.complete({
      model: 'haiku',
      maxTokens: 40,
      system: tx('You write short titles for a work chat session. Reply with the title only, no explanation.'),
      prompt: `${tx('The most recent questions from the user in the session (oldest first, newest last):')}\n${titles.recent.map(p => '- ' + p).join('\n')}\n\n${tx('Write a title of 3 to 7 words, in the language the questions are written in, naming the main topic of the session and favoring the newer questions. Do not use quotation marks and no full stop at the end.')}`,
    })
    if (!r.isAnswered) return
    const title = cleanTitle(r.text)
    if (title && title !== titles.session) titles.pending = title
  } catch {
    // a missing title is no loss
    // thiếu tiêu đề cũng không mất gì
  }
}

/** Keeps the chat's title when an event brings a new one, and rewrites this session's file. */
/** Giữ tiêu đề cuộc trò chuyện khi một sự kiện mang tiêu đề mới tới, và ghi lại file của phiên này. */
async function takeTitle($: EngineInterface, title: unknown) {
  const t = chatTitle(title)
  if (t && t !== titles.session) {
    titles.session = t
    await save($, await read($, team))
  }
}

/** This session's id, and its name: "folder/chat title", or just the folder until the title is known. */
/** Id của phiên này và tên của nó: "thư mục/tiêu đề cuộc trò chuyện", hoặc chỉ thư mục cho tới khi biết tiêu đề. */
async function whoAmI($: EngineInterface): Promise<{ id: string; name: string }> {
  const id = (me ??= { id: await $.session.id(), name: '' }).id
  const folder = folderName(await $.session.cwd())
  // the desktop app's folderless sessions run in scratch-<date>-<code>
  // các phiên không thư mục của app trên máy tính chạy trong scratch-<ngày>-<mã>
  const place = folder.startsWith('scratch-')
    ? (titles.session ? tx('no folder') : tx('Session with no folder ({code})', { code: folder.slice(-6) }))
    : folder || id.slice(0, 8)
  return { id, name: titles.session ? `${place}/${titles.session}` : place }
}

const LIST_FILE = (dir: string) => `${dir}/sessions.js`

async function readList($: EngineInterface, dir: string): Promise<string[]> {
  try {
    const raw = await $.fs.read(LIST_FILE(dir))
    const ids: unknown = JSON.parse(/\[[\s\S]*\]/.exec(raw)?.[0] ?? '[]')
    return Array.isArray(ids) ? ids.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Adds or removes this session in sessions.js; re-added now and then in case another session's write dropped it. */
/** Thêm hoặc bớt phiên này trong sessions.js; thêm lại thỉnh thoảng phòng khi lần ghi của phiên khác làm mất nó. */
async function list($: EngineInterface, isIn: boolean) {
  const dir = await webFolder($)
  const { id } = await whoAmI($)
  const ids = (await readList($, dir)).filter(x => x !== id)
  const next = isIn ? [...ids, id].slice(-30) : ids
  await $.fs.write(LIST_FILE(dir), `window.__aiWorkerList = ${JSON.stringify(next)};\n`)
  listedAt = await $.clock.now()
}

async function save($: EngineInterface, s: TeamState) {
  try {
    const dir = await webFolder($)
    const { id, name } = await whoAmI($)
    const now = await $.clock.now()
    activeAt = now
    const body = JSON.stringify({ ...s, name, updatedAt: now, seenAt: now })
    await $.fs.write(`${dir}/sessions/${id}.js`, `window.__aiWorkerIn && window.__aiWorkerIn(${JSON.stringify(id)}, ${body});\n`)
    if (now - listedAt > LIST_EVERY_MS) await list($, true)
    shareAfterChange($, now)
  } catch {
    // the browser view is optional; the pane still works
    // trang trình duyệt là tuỳ chọn; khung vẫn chạy
  }
}

/**
 * The heartbeat: every 30 seconds an open session says it is still open (`seenAt`),
 * so the page lists it even while idle, and drops it a couple of minutes after it closes.
 */
/** Nhịp tim: cứ 30 giây một phiên đang mở báo là nó vẫn mở (`seenAt`), để trang liệt kê nó kể cả khi rảnh, và bỏ nó vài phút sau khi nó đóng. */
async function beat($: EngineInterface) {
  try {
    const dir = await webFolder($)
    const { id, name } = await whoAmI($)
    const now = await $.clock.now()
    const s = await read($, team)
    const body = JSON.stringify({ ...s, name, updatedAt: activeAt || now, seenAt: now })
    await $.fs.write(`${dir}/sessions/${id}.js`, `window.__aiWorkerIn && window.__aiWorkerIn(${JSON.stringify(id)}, ${body});\n`)
    await list($, true)
  } catch {
    // the browser view is optional
    // trang trình duyệt là tuỳ chọn
  }
  await shareTeam($)
}

let heartbeat: { cancel(): void } | undefined

function ensureHeartbeat($: EngineInterface) {
  if (!heartbeat) heartbeat = $.clock.every(LIST_EVERY_MS, () => void beat($))
}

/** Removes office files of sessions closed over a week ago (the chats themselves are untouched). */
/** Xoá file văn phòng của các phiên đã đóng hơn một tuần (bản thân các cuộc trò chuyện không bị động tới). */
/** No delete on $.fs: rm on macOS and Linux, del on Windows. */
/** $.fs không có lệnh xoá: rm trên macOS và Linux, del trên Windows. */
async function removeFiles($: EngineInterface, paths: string[]) {
  if (paths.length === 0) return
  for (const argv of [['rm', '-f', ...paths], ['cmd', '/c', 'del', '/q', ...paths.map(p => p.replaceAll('/', '\\'))]]) {
    try {
      if ((await $.process.run(argv)).exitCode === 0) return
    } catch {
      // not this system's command; try the next
      // không phải lệnh của hệ thống này; thử lệnh kế tiếp
    }
  }
}

/**
 * Keeps a copy of each image pasted into the prompt being submitted, for the Activity tab of the page on this
 * computer. The engine hands the bytes over only while the prompt is being submitted, and writes text only, so
 * each copy is a small script the page loads. Nothing of it is sent anywhere.
 */
/** Giữ một bản sao của từng ảnh dán vào lời nhắc đang gửi, cho tab Hoạt động của trang trên máy này. Engine chỉ đưa dữ liệu ảnh trong lúc lời nhắc đang được gửi, và chỉ ghi được chữ, nên mỗi bản sao là một script nhỏ mà trang nạp. Không phần nào của nó được gửi đi đâu. */
async function keepShots($: EngineInterface, attachments: readonly { type: string; id?: string }[]): Promise<string[]> {
  const kept: string[] = []
  try {
    const dir = `${await webFolder($)}/shots`
    const { id: session } = await whoAmI($)
    const at = await $.clock.now()
    let index = 0
    for (const item of attachments) {
      if (item.type !== 'image') continue
      index++
      if (!item.id) continue
      let base64 = ''
      let mediaType = ''
      let offset: number | undefined
      for (let slice = 0; slice < 8; slice++) {
        const part = await $.prompt.media(offset === undefined ? { id: item.id } : { id: item.id, offset })
        if (part.base64 === undefined || part.size > MAX_SHOT_BYTES) { base64 = ''; break }
        base64 += part.base64
        mediaType = part.mediaType
        offset = part.next
        if (offset === undefined) break
      }
      const name = shotName(session, at, index)
      const file = offset === undefined ? shotFile(name, mediaType, base64) : undefined
      if (!file) continue
      await $.fs.write(`${dir}/${name}.js`, file)
      kept.push(name)
    }
  } catch {
    // the line still says how many images there were
    // dòng vẫn ghi có bao nhiêu ảnh
  }
  return kept
}

/** Removes the copies of pasted images no line shows any more, and those older than a week. */
/** Xoá các bản sao ảnh dán mà không dòng nào còn hiện, và các bản cũ hơn một tuần. */
async function pruneShots($: EngineInterface) {
  try {
    const dir = `${await webFolder($)}/shots`
    if (!(await $.fs.exists(dir))) return
    const { id } = await whoAmI($)
    const old = unusedShots(await $.fs.list(dir), await $.clock.now(), id, (await read($, team)).activity ?? [])
    await removeFiles($, old.map(n => `${dir}/${n}`))
  } catch {
    // tidying is optional
    // dọn dẹp là tuỳ chọn
  }
}

async function pruneOld($: EngineInterface) {
  try {
    const dir = `${await webFolder($)}/sessions`
    const { id } = await whoAmI($)
    const old = staleSessionFiles(await $.fs.list(dir), await $.clock.now(), id).map(n => `${dir}/${n}`)
    if (old.length === 0) return
    // no delete on $.fs: rm on macOS and Linux, del on Windows
    // $.fs không có lệnh xoá: rm trên macOS và Linux, del trên Windows
    for (const argv of [['rm', '-f', ...old], ['cmd', '/c', 'del', '/q', ...old.map(p => p.replaceAll('/', '\\'))]]) {
      try {
        if ((await $.process.run(argv)).exitCode === 0) return
      } catch {
        // not this system's command; try the next
        // không phải lệnh của hệ thống này; thử lệnh kế tiếp
      }
    }
  } catch {
    // tidying is optional
    // dọn dẹp là tuỳ chọn
  }
}

/** The session's cost in dollars as the status line has it; undefined where the engine prices nothing. */
/** Chi phí của phiên bằng đô la như thanh trạng thái hiển thị; undefined khi engine không tính giá gì. */
async function sessionCost($: EngineInterface): Promise<number | undefined> {
  try {
    return (await $.session.usage()).cost?.usd
  } catch {
    return undefined
  }
}

/** The ledger's store and the page's folder (hooks/ledger.ts). */
/** Kho của sổ chi phí và thư mục của trang (hooks/ledger.ts). */
function ledgerIo($: EngineInterface): LedgerIo {
  return {
    store: storeOf($),
    writePage: async (name, text) => {
      await $.fs.write(`${await webFolder($)}/${name}`, text)
    },
  }
}
const sessionId = ($: EngineInterface) => async () => (await whoAmI($)).id

// ---- the team board: numbers only, to a common folder, when IT switches it on ----
// ---- bảng cả team: chỉ có con số, gửi vào một thư mục chung, khi người quản trị bật nó ----
/** The `chiaSe` block of config.js; off until IT fills it in. */
/** Khối `chiaSe` của config.js; tắt cho tới khi người quản trị điền vào. */
let share: ShareConfig = SHARE_OFF
const MERGE_EVERY_MS = 60_000
/** A machine whose file is older than this shows as offline on the board. */
/** Máy có file cũ hơn mức này sẽ hiện là ngoại tuyến trên bảng. */
const OFFLINE_MS = 12 * 60_000
let boardCleared = false
let mergedAt = 0
/** The gap of the last answer, in this session's memory too, for the timer of the next send (hooks/send.ts keeps the store's keys). */
/** Khoảng cách của câu trả lời gần nhất, giữ cả trong bộ nhớ của phiên này, cho bộ hẹn giờ của lần gửi sau (hooks/send.ts giữ các khoá của kho). */
const sendMem: SendMem = { gapMs: PACE_MIN_MS }
/** A change is sent this long after it is saved, so the changes a turn makes together (cost, then state) leave in one send. */
/** Một thay đổi được gửi sau khi lưu chừng này, để các thay đổi một lượt làm cùng lúc (chi phí, rồi trạng thái) đi chung một lần gửi. */
const SHARE_GATHER_MS = 1_000
/** The least time between two sends prompted by changes; the heartbeat still sends every 30 seconds when nothing changes. */
/** Khoảng cách ít nhất giữa hai lần gửi do có thay đổi; khi không có gì đổi, nhịp tim vẫn gửi mỗi 30 giây. */
const SHARE_MIN_MS = 2_000
let shareStartedAt = 0
let shareSoon: { cancel(): void } | undefined

/** A change was saved: send it within a few seconds instead of waiting for the next heartbeat, so the board shows it at once. Changes that come close together leave in one send, at most one every SHARE_MIN_MS. */
/** Một thay đổi vừa được lưu: gửi nó trong vài giây thay vì chờ nhịp tim kế tiếp, để bảng hiện ngay. Các thay đổi đến sát nhau đi chung một lần gửi, nhiều nhất một lần mỗi SHARE_MIN_MS. */
function shareAfterChange($: EngineInterface, now: number) {
  if (shareSoon || share === SHARE_OFF || !share.enabled) return
  const gap = Math.max(SHARE_MIN_MS, sendMem.gapMs)
  const wait = Math.max(SHARE_GATHER_MS, gap - (now - shareStartedAt))
  shareSoon = $.clock.after(wait, () => {
    shareSoon = undefined
    void (async () => {
      // another send (the heartbeat, the start of the session) may have gone out meanwhile: keep the gap from that one too
      // một lần gửi khác (nhịp tim, lúc mở phiên) có thể đã đi trong lúc chờ: giữ khoảng cách với cả lần đó
      const now = await $.clock.now()
      if (now - shareStartedAt < Math.max(SHARE_MIN_MS, sendMem.gapMs)) shareAfterChange($, now)
      else await shareTeam($)
    })()
  })
}
let account: { at: number; email: string } | undefined
// someone may sign out and in with another account: read it again every few minutes
// có thể ai đó đăng xuất rồi đăng nhập tài khoản khác: đọc lại mỗi vài phút
const ACCOUNT_EVERY_MS = 5 * 60_000

/** This machine's random id, kept across sessions: one file per machine in the common folder. */
/** Id ngẫu nhiên của máy này, giữ qua các phiên: mỗi máy một file trong thư mục chung. */
async function machineId($: EngineInterface): Promise<string> {
  const had = await $.store.get('deviceId')
  // the server takes device-... only; versions before 0.25.0 made may-... ids that it refused: keep the same suffix
  // máy chủ chỉ nhận device-...; bản trước 0.25.0 tạo mã may-... bị từ chối: giữ nguyên phần đuôi
  if (typeof had === 'string' && /^device-[a-z0-9]{1,40}$/.test(had)) return had
  const old = typeof had === 'string' ? /^may-([a-z0-9]{1,40})$/.exec(had) : null
  // an id already made is kept, whatever its length: a new id would show the same computer twice on the board
  // mã đã tạo thì giữ, dài ngắn thế nào cũng vậy: mã mới sẽ làm cùng một máy hiện hai lần trên bảng
  const id = old ? `device-${old[1]}` : newDeviceId()
  await $.store.set('deviceId', id)
  return id
}

/**
 * The account this machine is signed in with: from the engine where the organization's managed install allows it,
 * else from Claude's settings file; the email typed at install only when neither gives one.
 * `typed` is that email when it differs from the real one, so the board can show the mismatch.
 */
/** Tài khoản mà máy này đang đăng nhập: lấy từ engine nếu bản cài do tổ chức quản lý cho phép, nếu không thì lấy từ file cài đặt của Claude; email gõ lúc cài chỉ dùng khi cả hai đều không có. `typed` là email đó khi nó khác với email thật, để bảng hiện được chỗ không khớp. */
async function accountEmail($: EngineInterface, now: number): Promise<{ email: string; typed?: string }> {
  if (!account || now - account.at > ACCOUNT_EVERY_MS) {
    let email = ''
    try {
      const who = (await $.session.identity()) as { email?: unknown }
      if (typeof who.email === 'string') email = who.email.trim().toLowerCase()
    } catch {
      // not a managed install
      // không phải bản cài do tổ chức quản lý
    }
    if (!email) {
      const dir = (await $.env.get('CLAUDE_CONFIG_DIR')) || (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
      try {
        email = signedInEmail(await $.fs.read(`${dir}/.claude.json`))
      } catch {
        // no file: never signed in on this machine
        // không có file: chưa bao giờ đăng nhập trên máy này
      }
    }
    account = { at: now, email }
  }
  if (!account.email) return { email: share.account }
  return share.account && share.account !== account.email ? { email: account.email, typed: share.account } : { email: account.email }
}

/** Writes this machine's numbers to the common folder; on the manager's machine, merges the folder for the page. */
/** Ghi số liệu của máy này vào thư mục chung; trên máy của người quản lý thì gộp thư mục đó cho trang. */
/** The first listed common folder present on this machine; undefined while none is (the NAS not mounted). */
/** Thư mục chung đầu tiên trong danh sách có mặt trên máy này; undefined khi chưa có thư mục nào (NAS chưa được gắn). */
async function commonFolder($: EngineInterface): Promise<string | undefined> {
  for (const p of share.folders) {
    try {
      if ((await $.fs.stat(p)).kind === 'dir') return p
    } catch {
      // not on this system, or not mounted now
      // không có trên hệ thống này, hoặc lúc này chưa được gắn
    }
  }
  return undefined
}

/** True while a share is under way: a slow network (away from the office) must not stack the beats up. */
/** Đúng khi đang có một lần chia sẻ: mạng chậm (khi ở ngoài văn phòng) không được làm các nhịp chồng lên nhau. */
let sharing = false

async function shareTeam($: EngineInterface) {
  if (sharing) return
  sharing = true
  shareStartedAt = await $.clock.now()
  try {
    await shareOnce($)
  } finally {
    sharing = false
  }
}

/** Sends this machine's numbers (to the webhook, else the common folder); the manager's machine also reads the board. */
/** Gửi số liệu của máy này (tới webhook, nếu không thì thư mục chung); máy của người quản lý còn đọc cả bảng. */
// the office address changes rarely (another Wi-Fi, a cable): ask the system again every few minutes
// địa chỉ văn phòng hiếm khi đổi (Wi-Fi khác, đổi dây): hỏi lại hệ thống mỗi vài phút
const LAN_IP_EVERY_MS = 5 * 60 * 1000
let lanIp: { at: number; ip?: string } | undefined

/** This machine's address on the office network, from the interface carrying the default route. */
/** Địa chỉ của máy này trên mạng văn phòng, lấy từ giao diện mang tuyến mặc định. */
async function officeAddress($: EngineInterface, now: number): Promise<string | undefined> {
  if (lanIp && now - lanIp.at < LAN_IP_EVERY_MS) return lanIp.ip
  let ip: string | undefined
  for (const argv of LAN_IP_PROBES) {
    try {
      const r = await $.process.run(argv)
      if (r.exitCode === 0) ip = parseLanIp(r.stdout)
    } catch {
      // not this system's command; try the next
      // không phải lệnh của hệ thống này; thử lệnh kế tiếp
    }
    if (ip) break
  }
  lanIp = { at: now, ip }
  return ip
}

/** Sending has failed since `since` (undefined while it works); the page shows it, the app toasts it once per outage. */
/** Việc gửi đã lỗi từ `since` (undefined khi đang chạy được); trang hiện nó, app báo một lần cho mỗi đợt sự cố. */
let shareFail: { since: number; error: string } | undefined
let shareToastFor = 0

async function noteShare($: EngineInterface, dir: string, now: number, err?: unknown) {
  shareFail = err === undefined ? undefined : { since: shareFail?.since ?? now, error: shareProblem(err) }
  const text = shareWarning(shareFail, now)
  if (text && shareFail && shareToastFor !== shareFail.since) {
    shareToastFor = shareFail.since
    $.ui.toast(text)
  }
  const data = shareFail ? { ...shareFail, updatedAt: now, warnAfterMs: SHARE_WARN_MS } : null
  try {
    await $.fs.write(`${dir}/share-state.js`, `window.__aiWorkerShare = ${JSON.stringify(data)};\n`)
  } catch {
    // the page just misses the warning
    // trang chỉ thiếu lời cảnh báo
  }
}

/**
 * ai-workers may connect after this session started (it did when the app was reopened): look again until it shows up,
 * then let it serve the delegation (the plugin's own rules drop out of the prompt) and report what it offers.
 */
/** ai-workers có thể kết nối sau khi phiên này bắt đầu (từng xảy ra khi app được mở lại): nhìn lại cho tới khi nó xuất hiện, rồi để nó phụ trách việc giao việc (quy tắc riêng của plugin rời khỏi lời nhắc) và báo những gì nó cung cấp. */
let mcpLookedAt = 0
/** ai-workers' tools have been seen in this session (viaMcp alone may come from its config, before it connects). */
/** Đã thấy công cụ của ai-workers trong phiên này (chỉ viaMcp có thể đến từ cấu hình của nó, trước khi nó kết nối). */
let mcpSeen = false
async function lookForMcp($: EngineInterface, now: number) {
  if (mcpSeen || now - mcpLookedAt < 60_000) return
  mcpLookedAt = now
  try {
    const names = (await $.tool.list()).map(t => t.name)
    if (!names.some(n => n.startsWith('mcp__ai-workers__'))) return
    viaMcp = mcpSeen = true
    // the plugin's own tools were registered before ai-workers connected: tuck them away
    // công cụ riêng của plugin đã được đăng ký trước khi ai-workers kết nối: cất chúng đi
    await tuckOwnTools($, names)
    own = {
      ...(own?.gemma ? { gemma: own.gemma } : {}),
      ...(names.includes('mcp__ai-workers__ask_chatgpt') ? { chatgpt: 'ai-workers' } : {}),
      ...(names.includes('mcp__ai-workers__ask_gemini') ? { gemini: 'ai-workers' } : {}),
    }
    await writeOwnWorkers($)
  } catch {
    // try again next beat
    // thử lại ở nhịp sau
  }
}

const OWN_ASK = /^mcp__ai-worker__(ask_chatgpt|ask_gemini|ask_local|generate_image)$/

/**
 * ai-workers serves the delegation but this session still lists the plugin's own ask_* tools (registered
 * before it connected, or kept across /reload-plugins): register them again, behind ToolSearch and pointing
 * at ai-workers' tools. A name registered again replaces the old one; there is no way to drop it.
 */
/** ai-workers phụ trách việc giao việc nhưng phiên này vẫn liệt kê các công cụ ask_* riêng của plugin (đăng ký trước khi nó kết nối, hoặc còn lại sau /reload-plugins): đăng ký chúng lại, sau ToolSearch và trỏ tới công cụ của ai-workers. Một tên đăng ký lại sẽ thay tên cũ; không có cách nào bỏ nó. */
async function tuckOwnTools($: EngineInterface, names?: string[]) {
  try {
    names ??= (await $.tool.list()).map(t => t.name)
    for (const n of names) {
      const m = OWN_ASK.exec(n)
      if (!m) continue
      await $.tool.register({
        name: m[1]!,
        description: tx('Duplicate of mcp__ai-workers__{tool}: use that tool instead of this one.', { tool: m[1]! }),
        inputSchema: m[1] === 'ask_local' ? PROMPT_SCHEMA : m[1] === 'generate_image' ? IMAGE_SCHEMA : PROMPT_LEVEL_SCHEMA,
        isDeferred: true,
      })
    }
  } catch {
    // they stay as they are; tool.describe still tucks them where it can
    // chúng giữ nguyên; tool.describe vẫn cất chúng ở chỗ nào có thể
  }
  $.ui.invalidate('tool.describe')
}

let mark: string | undefined
/** This computer's hardware mark, read once per start: never the id itself, only its salted hash. '' when no probe works. */
/** Dấu phần cứng của máy, đọc một lần mỗi lần chạy: không bao giờ gửi mã gốc, chỉ bản băm có muối. '' khi không lệnh nào chạy được. */
async function machineMark($: EngineInterface): Promise<string | undefined> {
  if (mark === undefined) {
    mark = ''
    for (const argv of HARDWARE_ID_PROBES) {
      try {
        const r = await $.process.run(argv)
        const id = r.exitCode === 0 ? parseHardwareId(r.stdout) : undefined
        if (id) {
          mark = hardwareMark(id)
          break
        }
      } catch {
        // not this system's command; try the next
        // không phải lệnh của hệ này; thử lệnh sau
      }
    }
  }
  return mark || undefined
}

let version: string | undefined
/** This plugin's version from its manifest, read once. */
/** Phiên bản của plugin này theo manifest, đọc một lần. */
async function pluginVersion($: EngineInterface): Promise<string | undefined> {
  if (version === undefined) {
    try {
      const v = (JSON.parse(await $.fs.read(`${$.plugin.root}/.claude-plugin/plugin.json`)) as { version?: unknown }).version
      version = typeof v === 'string' ? v.slice(0, 20) : ''
    } catch {
      version = ''
    }
  }
  return version || undefined
}

/** The plugin's store for a module that takes it as a parameter (hooks/io.ts): the engine reads `$` only where it is called. */
/** Kho của plugin cho một module nhận nó qua tham số (hooks/io.ts): engine chỉ đọc `$` tại chỗ gọi. */
function storeOf($: EngineInterface): Store {
  return {
    get: k => $.store.get(k),
    set: async (k, v) => {
      await $.store.set(k, v)
    },
    delete: async k => {
      await $.store.delete(k)
    },
  }
}

async function shareOnce($: EngineInterface) {
  const viaWeb = share.webhook !== ''
  if (!viaWeb && !share.folders.length) return
  const folder = viaWeb ? '' : await commonFolder($)
  // away from the office: nothing is lost, the ledger keeps 8 days and goes up on the next send
  // ở ngoài văn phòng: không mất gì, sổ giữ 8 ngày và sẽ gửi lên ở lần gửi sau
  if (!viaWeb && !folder) return
  const dir = await webFolder($)
  const now = await $.clock.now()
  await lookForMcp($, now)
  const { email: account, typed: enteredAccount } = await accountEmail($, now)
  if (share.enabled && (share.name || account)) {
    try {
      const sessions = []
      for (const f of await $.fs.list(`${dir}/sessions`)) {
        if (f.kind !== 'file' || !f.name.endsWith('.js')) continue
        const s = parseSessionFile(await $.fs.read(`${dir}/sessions/${f.name}`))
        if (s) sessions.push(s)
      }
      const ledger = await readLedger(storeOf($))
      const device = await machineId($)
      const lanIp = await officeAddress($, now)
      const summary = buildMachineSummary(sessions, ledger, now, {
        device, name: share.name, account, lanIp, enteredAccount, pluginVersion: await pluginVersion($), hardwareMark: await machineMark($),
        ...(own
          ? {
              assistants: {
                ...(own.gemma ? { gemma: own.gemma } : {}),
                // a machine whose helper has answered has it, even where the program was not found by name
                // một máy mà trợ lý đã trả lời thì có trợ lý đó, kể cả khi không tìm thấy chương trình theo tên
                chatgpt: !!own.chatgpt || !!helperModels.chatgpt,
                gemini: !!own.gemini || !!helperModels.gemini,
                ...(helperModels.chatgpt ? { chatgptModel: helperModels.chatgpt } : {}),
                ...(helperModels.gemini ? { geminiModel: helperModels.gemini } : {}),
              },
            }
          : {}),
      // the records of work handed to helpers go to a server's audit log only, never into a folder others can read
      // biên bản giao việc chỉ gửi vào nhật ký của máy chủ, không bao giờ ghi vào thư mục người khác đọc được
      }, viaWeb ? recentDelegations(sessions, now) : [])
      const target: SendTarget = viaWeb
        ? { kind: 'web', webhook: share.webhook, ingestKey: share.ingestKey, ingestHosts: share.ingestHosts }
        : { kind: 'folder', write: async json => {
          await $.fs.write(`${folder}/${device}.json`, json)
        } }
      const sent = await send({ store: storeOf($), fetch: (url, init) => $.http.fetch(url, init) }, target, sendMem, summary, now)
      // put off to the webhook: nothing was sent, the next beat after the wait sends it
      // hoãn sang webhook: chưa gửi gì, nhịp sau khi hết chờ sẽ gửi
      if (sent.kind === 'putOff') return
      if (sent.kind === 'failed') throw new Error(`webhook ${sent.status}`)
      if (sent.kind === 'sent' && viaWeb) await noteShare($, dir, now)
    } catch (err) {
      // the server or folder is out of reach: try again next beat, and say so once it lasts
      // máy chủ hoặc thư mục ngoài tầm với: thử lại ở nhịp sau, và báo một lần khi nó kéo dài
      if (viaWeb) await noteShare($, dir, now, err)
    }
  }
  if (viaWeb) await pollNewVersion($, now).catch(() => undefined)
  // with a webhook the board lives on the server (OTP); only a common folder is merged here
  // có webhook thì bảng nằm trên máy chủ (OTP); ở đây chỉ gộp thư mục chung
  if (viaWeb && !boardCleared) {
    boardCleared = true
    // a board merged by an older version would stay on the page: empty it once
    // bảng do bản cũ gộp sẽ còn lại trên trang: làm trống một lần
    await $.fs.write(`${dir}/team-total.js`, '').catch(() => undefined)
  }
  if (share.viewBoard && !viaWeb && now - mergedAt > MERGE_EVERY_MS) {
    mergedAt = now
    try {
      const files: unknown[] = []
      for (const f of await $.fs.list(folder)) {
        if (f.kind !== 'file' || !f.name.endsWith('.json') || f.size > 512 * 1024) continue
        try {
          files.push(JSON.parse(await $.fs.read(`${folder}/${f.name}`)))
        } catch {
          // a file half-synced or not ours
          // một file đồng bộ dở hoặc không phải của ta
        }
      }
      const board = { updatedAt: now, openMs: OPEN_MS, offlineMs: OFFLINE_MS, members: mergeTeam(files, now, OFFLINE_MS) }
      await $.fs.write(`${dir}/team-total.js`, `window.__aiWorkerTeam = ${JSON.stringify(board)};\n`)
    } catch {
      // as above
      // như trên
    }
  }
}

// ---- helpers on this machine (staff without the ai-workers MCP server) ----------
// ---- các trợ lý trên máy này (máy nhân viên không có máy chủ MCP ai-workers) ----------
/** What this machine can delegate to; undefined until looked for, `viaMcp` when ai-workers serves the delegation. */
/** Máy này có thể giao việc cho ai; undefined cho tới khi đi tìm, `viaMcp` khi ai-workers phụ trách giao việc. */
let own: OwnWorkers | undefined
let viaMcp = false
/** The model that last answered for ChatGPT / Gemini on this machine, kept across sessions. */
/** Mô hình trả lời gần nhất cho ChatGPT / Gemini trên máy này, giữ qua các phiên. */
let helperModels: { chatgpt?: string; gemini?: string } = {}
const HELPER_MODELS_KEY = 'helperModels'
let chatgptSlot = 0
/** Images already handed to an earlier call, so a later one never picks them up again. */
/** Ảnh đã giao cho một lệnh gọi trước, để lệnh sau không nhặt lại. */
const takenImages = new Set<string>()
/** One image at a time, so each call can tell which new files are its own. */
/** Mỗi lần một ảnh, để mỗi lệnh gọi biết file mới nào là của mình. */
let imageQueue: Promise<unknown> = Promise.resolve()

/** Image files under agy's folder (three levels down), with when each was written. */
/** Các file ảnh dưới thư mục của agy (sâu tới ba cấp), kèm lúc mỗi file được ghi. */
async function listImages($: EngineInterface, dir: string, depth = 0): Promise<{ path: string; mtimeMs: number }[]> {
  const out: { path: string; mtimeMs: number }[] = []
  let entries: Awaited<ReturnType<EngineInterface['fs']['list']>> = []
  try {
    entries = await $.fs.list(dir)
  } catch {
    return out
  }
  for (const e of entries) {
    const p = `${dir}/${e.name}`
    if (e.kind === 'dir' && depth < 3) out.push(...(await listImages($, p, depth + 1)))
    else if (e.kind === 'file') out.push({ path: p, mtimeMs: e.mtimeMs })
  }
  return out
}

/** Copies a file byte for byte (the plugin writes only text): cp, or PowerShell on Windows with the paths in variables, never in the command. */
/** Chép file từng byte (plugin chỉ ghi được chữ): cp, hoặc PowerShell trên Windows với đường dẫn để trong biến, không bao giờ trong câu lệnh. */
async function copyFile($: EngineInterface, src: string, dst: string, windows: boolean): Promise<boolean> {
  const r = windows
    ? await $.process.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', 'Copy-Item -LiteralPath $env:AIW_SRC -Destination $env:AIW_DST'], {
        env: { AIW_SRC: src, AIW_DST: dst },
        timeoutMs: 30_000,
      })
    : await $.process.run(['cp', src, dst], { timeoutMs: 30_000 })
  return r.exitCode === 0
}

/** Gemini draws through agy; the newest new file is its final answer, copied with any drafts into ~/Pictures/AI Worker. */
/** Gemini vẽ qua agy; file mới nhất là bản chốt của nó, được chép cùng các bản nháp vào ~/Pictures/AI Worker. */
async function drawImage($: EngineInterface, agy: string, prompt: string, fileName: unknown, work: string): Promise<{ text: string; isError: boolean }> {
  const windows = (await $.env.get('OS')) === 'Windows_NT'
  const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
  const brain = `${home}/${AGY_BRAIN}`
  const since = await $.clock.now()
  // agy and the wait for its file share the call's time
  // agy và lúc chờ file của nó dùng chung thời gian của lệnh gọi
  const r = await runHelper($, imageArgv(agy, prompt), { cwd: work, stdin: '', timeoutMs: WORKER_TIMEOUT_MS - IMAGE_SETTLE_MS })
  let images = newImages(await listImages($, brain), since, takenImages)
  for (const until = (await $.clock.now()) + IMAGE_SETTLE_MS; !images.length && (await $.clock.now()) < until; ) {
    await $.clock.sleep(2000)
    images = newImages(await listImages($, brain), since, takenImages)
  }
  if (!images.length) return { text: tx('Gemini could not create the image (exit code {code}). {details}', { code: r.exitCode, details: `${r.stdout}\n${r.stderr}`.trim().slice(-800) }), isError: true }
  images.forEach(p => takenImages.add(p))
  const dir = `${home}/${IMAGE_DIR}`
  await (windows
    ? $.process.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', 'New-Item -ItemType Directory -Force -Path $env:AIW_DST | Out-Null'], { env: { AIW_DST: dir }, timeoutMs: 30_000 })
    : $.process.run(['mkdir', '-p', dir], { timeoutMs: 30_000 })
  ).catch(() => undefined)
  const existing = new Set((await $.fs.list(dir).catch(() => [])).map(e => `${dir}/${e.name}`))
  const targets = imageTargets(images, dir, safeImageName(fileName), p => existing.has(p))
  const saved: string[] = []
  for (const [i, src] of images.entries()) {
    const to = targets[i] ?? src
    saved.push(to !== src && (await copyFile($, src, to, windows).catch(() => false)) ? to : src)
  }
  const final = saved[saved.length - 1]
  const lines = [tx('Nano Banana (Gemini) created the image. Final version (the last one Gemini made):'), `- ${final}`]
  if (saved.length > 1) lines.push(tx('Drafts Gemini made earlier (they may not match the request):'), ...saved.slice(0, -1).map(p => `- ${p}`))
  return { text: `${lines.join('\n')}\n\n${tx("Gemini's notes:")}\n${r.stdout.trim().slice(0, 1500)}`, isError: false }
}

/** Runs `argv`; a Windows .cmd/.bat launcher (an npm install) needs cmd to start it. */
/** Chạy `argv`; bộ khởi chạy .cmd/.bat của Windows (bản cài npm) cần cmd để chạy. */
async function runHelper($: EngineInterface, argv: string[], init: { cwd?: string; stdin?: string; timeoutMs?: number } = {}) {
  const wrapped = isBatchLauncher(argv[0] ?? '') ? ['cmd', '/d', '/c', ...argv] : argv
  return $.process.run(wrapped, init)
}

/** The first of `names` that runs (`--version` exits 0), looked up on PATH then in the usual install folders. */
/** Chương trình đầu tiên trong `names` chạy được (`--version` thoát với mã 0), tìm trên PATH rồi trong các thư mục cài thường gặp. */
async function findProgram($: EngineInterface, names: string[], folders: string[], windows: boolean): Promise<string | undefined> {
  const tries: string[] = []
  for (const n of names) {
    try {
      const r = await $.process.run(windows ? ['where', n] : ['sh', '-lc', `command -v ${n}`], { timeoutMs: 10_000 })
      if (r.exitCode === 0) tries.push(...r.stdout.split(/\r?\n/).map(l => l.trim()).filter(Boolean))
    } catch {
      // no shell or no such program
      // không có shell hoặc không có chương trình đó
    }
    for (const f of folders) tries.push(`${f}/${n}`, ...(windows ? [`${f}\\${n}.exe`, `${f}\\${n}.cmd`] : []))
  }
  for (const t of tries) {
    try {
      if ((await runHelper($, [t, '--version'], { timeoutMs: 20_000 })).exitCode === 0) return t
    } catch {
      // not there
      // không có ở đó
    }
  }
  return undefined
}

async function findOwnWorkers($: EngineInterface): Promise<OwnWorkers> {
  let mcp: string[] = []
  try {
    mcp = (await $.tool.list()).map(t => t.name).filter(n => n.startsWith('mcp__ai-workers__'))
  } catch {
    // list unavailable: look for the programs
    // không liệt kê được: đi tìm các chương trình
  }
  if (mcp.length) {
    // ai-workers delegates on this machine: report what it offers, find only Gemma's model
    // ai-workers giao việc trên máy này: báo những gì nó cung cấp, chỉ tìm mô hình của Gemma
    viaMcp = mcpSeen = true
    const found: OwnWorkers = {}
    try {
      const r = await $.http.fetch(`${OLLAMA_URL}/api/tags`)
      if (r.ok) found.gemma = pickGemma(r.text)
    } catch {
      // Ollama not running
      // Ollama không chạy
    }
    if (mcp.includes('mcp__ai-workers__ask_chatgpt')) found.chatgpt = 'ai-workers'
    if (mcp.includes('mcp__ai-workers__ask_gemini')) found.gemini = 'ai-workers'
    return found
  }
  const windows = (await $.env.get('OS')) === 'Windows_NT'
  const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
  // ai-workers is set up but not connected yet (it starts after the plugin): leave the delegation to it, lookForMcp fills in the rest
  // ai-workers đã được cài nhưng chưa kết nối (nó khởi động sau plugin): để nó phụ trách giao việc, lookForMcp sẽ điền phần còn lại
  const appData = (await $.env.get('APPDATA')) || `${home}/Library/Application Support`
  const configs = [`${appData}/Claude/claude_desktop_config.json`]
  // the Claude app installed from the Microsoft Store (MSIX) keeps its settings in %LOCALAPPDATA%\Claude-Data\<package>\
  // app Claude cài từ Microsoft Store (MSIX) để thiết lập trong %LOCALAPPDATA%\Claude-Data\<gói>\
  const localAppData = await $.env.get('LOCALAPPDATA')
  if (localAppData) {
    try {
      for (const e of await $.fs.list(`${localAppData}/Claude-Data`)) {
        if (e.kind === 'dir') configs.push(`${localAppData}/Claude-Data/${e.name}/claude_desktop_config.json`)
      }
    } catch {
      // no Store app on this computer
      // máy này không có app bản Store
    }
  }
  configs.push(`${home}/.claude.json`)
  for (const f of configs) {
    try {
      if (!mcpConfigured(await $.fs.read(f))) continue
    } catch {
      continue
    }
    viaMcp = true
    const found: OwnWorkers = {}
    try {
      const r = await $.http.fetch(`${OLLAMA_URL}/api/tags`)
      if (r.ok) found.gemma = pickGemma(r.text)
    } catch {
      // Ollama not running
      // Ollama không chạy
    }
    return found
  }
  const found: OwnWorkers = {}
  try {
    const r = await $.http.fetch(`${OLLAMA_URL}/api/tags`)
    if (r.ok) found.gemma = pickGemma(r.text)
  } catch {
    // Ollama not installed or not running
    // Ollama chưa cài hoặc không chạy
  }
  const unixBins = [`${home}/.local/bin`, `${home}/.local/node/bin`, `${home}/.codex/bin`, '/opt/homebrew/bin', '/usr/local/bin']
  const winBins = [`${home}\\.local\\bin`, `${home}\\AppData\\Roaming\\npm`, `${home}\\AppData\\Local\\Programs\\OpenAI\\Codex\\bin`]
  found.chatgpt = await findProgram($, ['codex'], windows ? winBins : unixBins, windows)
  found.gemini = await findProgram($, ['agy'], windows ? winBins : unixBins, windows)
  return found
}

/** Whether this session has the /handoff skill: the plugin ships it (skills/handoff), or the machine has its own (~/.claude/skills/handoff). The context warning then points to it. */
/** Phiên này có skill /handoff không: plugin mang sẵn (skills/handoff), hoặc máy có bản riêng (~/.claude/skills/handoff). Cảnh báo ngữ cảnh khi đó sẽ trỏ tới nó. */
let handoffSkill: boolean | undefined
async function hasHandoffSkill($: EngineInterface): Promise<boolean> {
  if (handoffSkill !== undefined) return handoffSkill
  const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
  let found = false
  for (const dir of [`${$.plugin.root.replace(/[\\/]+$/, '')}/skills/handoff`, `${home}/.claude/skills/handoff`]) {
    try {
      if (await $.fs.read(`${dir}/SKILL.md`)) {
        found = true
        break
      }
    } catch {
      // not there: try the next place
      // không có ở đây: thử chỗ kế
    }
  }
  handoffSkill = found
  return handoffSkill
}

/** Writes which desks this machine can fill, for the page (a desk with no helper behind it is hidden). */
/** Ghi những bàn nào máy này có thể điền, cho trang (bàn không có trợ lý đứng sau thì bị ẩn). */
async function writeOwnWorkers($: EngineInterface) {
  const present = viaMcp || !own ? null : { gemma: !!own.gemma, chatgpt: !!own.chatgpt, gemini: !!own.gemini }
  setInstalled(present)
  try {
    await $.fs.write(`${await webFolder($)}/installed.js`, `window.__aiWorkerInstalled = ${JSON.stringify(present)};\n`)
  } catch {
    // the page keeps every desk
    // trang giữ mọi bàn
  }
}

// A tool call's own input, without the fields the event carries beside it (tool, tool_use_id, agentId).
// `$.tool.check` is given this: for Bash, whose rules read the command, the event's fields beside the input made the
// engine answer "ask" for a command it then let through. For the plugin's own tools the answer was the same either way.
// Đầu vào của chính lệnh gọi công cụ, không kèm các trường mà sự kiện mang theo (tool, tool_use_id, agentId).
// `$.tool.check` nhận đúng phần này: với Bash, nơi quy tắc đọc câu lệnh, các trường của sự kiện nằm cạnh đầu vào làm
// engine trả lời "ask" cho một lệnh mà sau đó nó vẫn cho chạy. Với công cụ riêng của plugin thì kết quả như nhau.
function toolInput(args: Record<string, unknown>): Record<string, unknown> {
  const { tool: _tool, tool_use_id: _id, agentId: _agent, ...input } = args
  return input
}

/** The plugin answers these tools itself, so the engine's permission step must be asked here. Text for ChatGPT or Gemini leaves this computer. */
/** Plugin tự trả lời các công cụ này, nên phải hỏi bước kiểm quyền của engine ở đây. Chữ gửi cho ChatGPT hay Gemini rời khỏi máy này. */
type Refused = { outcome?: 'refused' | 'declined'; found?: string[] }
async function refuseToSend($: EngineInterface, name: string, args: Record<string, unknown>, prompt: string, why: Refused): Promise<string | undefined> {
  const tool = `mcp__ai-worker__${name}`
  const verdict = await $.tool.check({ tool, input: toolInput(args) }).catch(() => ({ decision: 'ask' as const }))
  const worker = name === 'ask_chatgpt' ? 'ChatGPT' : name === 'ask_gemini' || name === 'generate_image' ? 'Gemini' : undefined
  // a key, a token or a password in the text stops it here, before anyone is asked: it never leaves, whatever the mode
  // khoá, token hay mật khẩu trong chữ thì dừng ở đây, trước khi hỏi ai: nó không bao giờ rời máy, ở mọi chế độ
  const secrets = worker ? findSecrets(prompt) : []
  if (worker && secrets.length) {
    await noteBlock($, 'secret', prompt.slice(0, 200))
    why.outcome = 'refused'
    why.found = secrets.map(x => x.kind)
    return secretRefusal(secrets, worker)
  }
  const answer = sendingNeedsAsking(verdict.decision, worker, !!(verdict as { rule?: unknown }).rule)
    ? await $.ui.ask(tx('Send this text to {worker}?\n\n{preview}', { worker: worker ?? '', preview: prompt.slice(0, 600) }), {
        options: [tx('Send'), tx('Do not send')],
        header: tx('Send out'),
      }).catch(() => '')
    : undefined
  const refusal = sendingRefusal(verdict.decision, answer, tx('Send'))
  if (refusal) why.outcome = 'declined'
  return refusal
}

async function serveOwn($: EngineInterface, name: string, args: Record<string, unknown>, why: Refused = {}): Promise<ToolCallResult> {
  const prompt = typeof args.prompt === 'string' ? args.prompt : ''
  const answer = (text: string, isError = false) => ({ result: text, isError }) as unknown as ToolCallResult
  if (!prompt.trim()) return answer(tx('The prompt is missing.'), true)
  const refusal = await refuseToSend($, name, args, prompt, why)
  if (refusal) return answer(refusal, true)
  const work = `${await webFolder($)}/viec`
  try {
    if (name === 'ask_local') {
      if (!own?.gemma) return answer(tx('This computer has no Gemma yet (Ollama is not installed or the model is not downloaded).'), true)
      const r = await $.process.run(['curl', '-s', '-m', String(WORKER_TIMEOUT_MS / 1000), `${OLLAMA_URL}/api/chat`, '-d', '@-'], {
        stdin: gemmaRequest(own.gemma, prompt),
        timeoutMs: WORKER_TIMEOUT_MS + 30_000,
      })
      const g = gemmaAnswer(r.stdout)
      return answer(g.text, g.isError)
    }
    if (name === 'ask_chatgpt') {
      if (!own?.chatgpt) return answer(tx('The Codex CLI is not installed on this computer.'), true)
      // a few answer files in turn (calls may overlap); emptied after reading, the plugin cannot delete files
      // vài file trả lời lần lượt (các lệnh gọi có thể chồng nhau); làm trống sau khi đọc, vì plugin không xoá được file
      const out = `${work}/chatgpt-${(chatgptSlot = (chatgptSlot + 1) % 8)}.txt`
      await $.fs.write(out, '')
      const r = await runHelper($, codexArgv(own.chatgpt, out, args.level), { cwd: work, stdin: codexInput(prompt), timeoutMs: WORKER_TIMEOUT_MS })
      const text = (await $.fs.read(out).catch(() => '')).trim()
      await $.fs.write(out, '').catch(() => undefined)
      // codex prints its settings to stderr before answering: "model: gpt-..."
      // codex in cài đặt của nó ra stderr trước khi trả lời: "model: gpt-..."
      const effort = /^reasoning effort:\s*(\S+)/m.exec(r.stderr)?.[1]
      const name = /^model:\s*(\S+)/m.exec(r.stderr)?.[1]
      const model = name && effort ? `${name} (${effort})` : name
      if (text) return answer(model ? `${text}\n\n${tx('(model: {model})', { model })}` : text)
      const why = `${r.stderr}\n${r.stdout}`
      if (/log ?in|auth|sign in|401/i.test(why)) return answer(tx('Codex is not logged in: open Terminal, type codex login, and sign in with the company ChatGPT account.'), true)
      return answer(tx('ChatGPT did not answer (exit code {code}). {details}', { code: r.exitCode, details: why.trim().slice(-500) }), true)
    }
    if (name === 'generate_image') {
      if (!own?.gemini) return answer(tx('Gemini (Antigravity CLI) is not installed on this computer.'), true)
      if (isBatchLauncher(own.gemini)) return answer(tx('Gemini was not started: this computer runs it through a .cmd or .bat launcher, which is not safe for this text. Ask your admin to install the standard Antigravity CLI.'), true)
      const agy = own.gemini
      const job = imageQueue.then(() => drawImage($, agy, prompt, args.file_name, work))
      imageQueue = job.catch(() => undefined)
      const g = await job
      return answer(g.text, g.isError)
    }
    if (name === 'ask_gemini') {
      if (!own?.gemini) return answer(tx('Gemini (Antigravity CLI) is not installed on this computer.'), true)
      if (isBatchLauncher(own.gemini)) return answer(tx('Gemini was not started: this computer runs it through a .cmd or .bat launcher, which is not safe for this text. Ask your admin to install the standard Antigravity CLI.'), true)
      const r = await runHelper($, agyArgv(own.gemini, prompt, args.level), { cwd: work, stdin: '', timeoutMs: WORKER_TIMEOUT_MS })
      const text = r.stdout.trim()
      if (r.exitCode === 0 && text) {
        // agy does not print its model; its run log names it
        // agy không in mô hình của nó; nhật ký chạy của nó có tên
        const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || ''
        const log = await $.fs.read(`${home}/.gemini/antigravity-cli/cli.log`).catch(() => '')
        const all = [...log.matchAll(/model override to backend: label="([^"]+)"/g)]
        const model = all.length ? all[all.length - 1]![1] ?? '' : ''
        return answer(model ? `${text}\n\n${tx('(model: {model})', { model })}` : text)
      }
      return answer(tx('Gemini did not answer (exit code {code}). {details}', { code: r.exitCode, details: `${r.stderr}`.trim().slice(-500) }), true)
    }
  } catch (err) {
    return answer(tx('Could not run: {reason}', { reason: String((err as Error)?.message ?? err) }), true)
  }
  return answer(tx('No such tool.'), true)
}

/** The language in use: AI_WORKER_LANG first, then what the person saved, then the system's own (the hook sandbox has no process.env). */
/** Ngôn ngữ đang dùng: trước hết là AI_WORKER_LANG, rồi tới lựa chọn người dùng đã lưu, rồi tới của hệ thống (sandbox của hook không có process.env). */
async function chosenLanguage($: EngineInterface, saved: unknown): Promise<unknown> {
  const forced = await $.env.get('AI_WORKER_LANG')
  if (forced) return forced
  if (saved === 'en' || saved === 'vi') return saved
  const locale = (await $.env.get('LC_ALL')) || (await $.env.get('LC_MESSAGES')) || (await $.env.get('LANG')) || ''
  return /^vi(?![a-z])/i.test(locale) ? 'vi' : undefined
}

/** Reads the team's config.js (a JSON object after `=`) into the drawing's words and names. */
/** Đọc config.js của nhóm (một đối tượng JSON sau dấu `=`) thành chữ và tên cho hình vẽ. */
async function loadConfig($: EngineInterface, dir: string) {
  const readJs = async (path: string): Promise<(OfficeConfig & { sharing?: Record<string, unknown>; language?: unknown }) | undefined> => {
    try {
      const raw = await $.fs.read(path)
      return JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1))
    } catch {
      // a missing or broken file leaves the defaults
      // file thiếu hoặc hỏng thì giữ nguyên mặc định
      return undefined
    }
  }
  const mine = await readJs(`${dir}/config.js`)
  // a company package ships its sharing settings (the NAS) in company.json; this machine's config.js overrides them
  // gói công ty mang sẵn thiết lập chia sẻ (NAS) trong company.json; config.js của máy này ghi đè chúng
  const shipped = await readJs(`${$.plugin.root}/web/company.json`)
  let person: Record<string, unknown> = {}
  try {
    person = JSON.parse(await $.fs.read(`${dir}/user.json`))
  } catch {
    // the installer writes it only for a company package
    // trình cài đặt chỉ ghi nó cho gói công ty
  }
  // the language first (user.json, then config.js), so every message from here on uses it
  // ngôn ngữ trước (user.json, rồi config.js), để mọi thông báo từ đây trở đi dùng nó
  setLang(await chosenLanguage($, person.language || mine?.language))
  // the page follows this choice too, unless its visitor picked with the EN / VI buttons
  // trang cũng theo lựa chọn này, trừ khi người xem đã chọn bằng nút EN / VI
  await $.fs.write(`${dir}/language.js`, pageLanguageScript((await $.env.get('AI_WORKER_LANG')) || person.language || mine?.language)).catch(() => undefined)
  applyConfig(mine ?? {})
  // on unless this computer's config.js says false: someone who writes code all day may turn the question off
  // bật, trừ khi config.js của máy này ghi false: người viết code cả ngày có thể tắt câu hỏi
  askBeforeDestructive = (mine as Record<string, unknown> | undefined)?.askBeforeDestructive !== false
  // off unless this computer's config.js says true: a team that wants each commit to state its cause and what was measured
  // tắt, trừ khi config.js của máy này ghi true: nhóm muốn mỗi commit ghi nguyên nhân và thứ đã đo
  commitTrail = (mine as Record<string, unknown> | undefined)?.commitTrail === true
  share = readShareConfig(mergeShare(shipped?.sharing, mine?.sharing, person), dir.slice(0, -WEB_DIR.length))
}

// ---- updating the plugin: the server only hands out files; the signature and hash decide ----
// ---- cập nhật plugin: máy chủ chỉ phát file; chữ ký và mã băm quyết định ----
/** Checks a signature with this package's own public keys; the Windows system copy where ssh-keygen is not on the PATH. */
/** Kiểm tra chữ ký bằng khoá công khai riêng của gói này; bản sao hệ thống của Windows khi ssh-keygen không có trong PATH. */
const signersPath = ($: EngineInterface) => `${$.plugin.root}/keys/allowed_signers`

async function checkSignature($: EngineInterface, manifest: string, sigPath: string): Promise<SignatureResult> {
  const allowed = signersPath($)
  for (const exe of ['ssh-keygen', 'C:\\Windows\\System32\\OpenSSH\\ssh-keygen.exe']) {
    try {
      return parseSignatureResult(await $.process.run([exe, '-Y', 'verify', '-f', allowed, '-I', 'ai-worker', '-n', 'ai-worker', '-s', sigPath], { stdin: manifest, timeoutMs: 30_000 }))
    } catch {
      // not this one
      // không phải cái này
    }
  }
  return 'unsupported'
}

/** This computer's own key when it has one, then the shared key: a server that knows the office networks lets only the own key of a computer allowed to send from any network through from outside. */
/** Khoá riêng của máy này khi có, rồi khoá chung: máy chủ biết các mạng văn phòng chỉ cho khoá riêng của máy được gửi từ mọi mạng đi qua từ bên ngoài. */
const keysForReleases = async ($: EngineInterface) => releaseKeys(await $.store.get(DEVICE_KEY).catch(() => undefined), share.ingestKey)

/** The server refused the network this computer is on: its front door, or the server itself for a computer not let send from any network. A wrong key gets 401 and a missing file 200, so 403 is never either. */
/** Máy chủ từ chối mạng mà máy này đang dùng: cửa trước của nó, hoặc chính máy chủ với máy chưa được gửi từ mọi mạng. Sai khoá nhận 401 và thiếu file nhận 200, nên 403 không bao giờ là một trong hai. */
class NetworkRefused extends Error {}

/** What /update says when the network is refused: what happened, what to do, and one line for the admin. No error code up front. */
/** Điều /update nói khi mạng bị từ chối: chuyện gì xảy ra, cần làm gì, và một dòng cho quản trị viên. Không đưa mã lỗi ra trước. */
const networkRefusedText = () => [
  tx('The network you are on is not allowed to reach the company server, so the new version could not be checked. Nothing is wrong with this computer.'),
  tx('The server answers only the networks your admin has added, usually the office one. Back on that network, type /update again.'),
  tx('Working somewhere else for a while? Ask your admin to let this computer send from any network on the Admin page. (For the admin: the server answered 403.)'),
].join('\n')

/** The newest signed manifest, if the server has one and it should be offered; says in state what it found. */
/** Manifest có chữ ký mới nhất, nếu máy chủ có và nên đưa ra; ghi vào trạng thái những gì nó tìm thấy. */
async function checkNewVersion($: EngineInterface): Promise<{ m?: Manifest; signature?: SignatureResult; text?: string }> {
  // a package with no signing key of its own can never verify an update, so there is nothing to offer
  // gói không có khoá ký riêng thì không bao giờ xác minh được một bản cập nhật, nên không có gì để đưa ra
  if (!hasSigningKeys(await $.fs.read(signersPath($)).catch(() => ''))) return {}
  const dir = `${await webFolder($)}/update`
  const keys = await keysForReleases($)
  const fetchRelease = async (name: string) => {
    // a refused own key is not dropped here: only a send may drop it, since the server says why there (hooks above, at /ingest)
    // khoá riêng bị từ chối thì không bỏ ở đây: chỉ lần gửi mới được bỏ nó, vì ở đó máy chủ nói rõ lý do (ở /ingest phía trên)
    for (const [i, key] of keys.entries()) {
      const r = await $.http.fetch(`${share.webhook}/releases/${name}`, { headers: { Authorization: `Bearer ${key}` } })
      if ((r.status === 401 || r.status === 403) && i < keys.length - 1) continue
      if (r.status === 403) throw new NetworkRefused('403')
      if (!r.ok) throw new Error(tx('server returned {code}', { code: r.status }))
      return r.text
    }
    throw new Error(tx('server returned {code}', { code: 401 }))
  }
  const raw = await fetchRelease('latest.json')
  const m = parseManifest(raw)
  if (!m) return {}
  const saved = ((await $.store.get(UPDATE_KEY)) as { date?: number; checkedAt?: number } | undefined) ?? {}
  if (!shouldOfferUpdate(m, await pluginVersion($), saved.date ?? 0)) return {}
  await $.fs.write(`${dir}/latest.sig`, await fetchRelease('latest.json.sig'))
  const signature = await checkSignature($, raw, `${dir}/latest.sig`)
  if (signature === 'invalid') {
    const wrongSignature = tx('The update on the server has a wrong signature, so it was not installed. Tell your admin.')
    $.ui.toast(wrongSignature)
    return { signature, text: wrongSignature }
  }
  await commit($, s => ({ ...s, update: { version: m.version, auto: signature === 'valid' } }))
  return { m, signature }
}

/** Looks at most every few hours, from the heartbeat; a server out of reach waits for the next look. */
/** Nhìn nhiều nhất vài giờ một lần, từ nhịp tim; máy chủ ngoài tầm với thì chờ lần nhìn sau. */
async function pollNewVersion($: EngineInterface, now: number) {
  if (!share.enabled || !share.webhook || !share.ingestKey || (await $.fs.exists(`${$.plugin.root}/.git`))) return
  const saved = ((await $.store.get(UPDATE_KEY)) as { date?: number; checkedAt?: number } | undefined) ?? {}
  if (now - (saved.checkedAt ?? 0) < UPDATE_EVERY_MS) return
  // a failed look is tried again soon, not after hours, yet not every beat: the server counts repeated errors as probing
  // một lần nhìn lỗi thì thử lại sớm, không phải sau nhiều giờ, nhưng cũng không mỗi nhịp: máy chủ coi lỗi lặp lại là dò quét
  const succeeded = await checkNewVersion($).then(() => true, () => false)
  await $.store.set(UPDATE_KEY, { ...saved, checkedAt: succeeded ? now : now - UPDATE_EVERY_MS + UPDATE_RETRY_MS })
}

/** PowerShell running the script in AIW_SCRIPT: the command line only names that variable. */
/** PowerShell chạy script trong AIW_SCRIPT: dòng lệnh chỉ nêu tên biến đó. */
const WINDOWS_POWERSHELL = ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', 'Invoke-Expression $env:AIW_SCRIPT']

/** The Claude Code that runs this plugin (it answers `--version` as Claude Code), else `claude` on the PATH; undefined when neither does. */
/** Claude Code đang chạy plugin này (nó trả lời `--version` là Claude Code), nếu không thì `claude` trong PATH; undefined khi không cái nào như vậy. */
async function claudeCodeProgram($: EngineInterface): Promise<string | undefined> {
  const found: string[] = []
  try {
    const r = (await $.env.get('OS')) === 'Windows_NT'
      ? await $.process.run(WINDOWS_POWERSHELL, { env: { AIW_SCRIPT: WINDOWS_CLAUDE_SCRIPT }, timeoutMs: 30_000 })
      : await $.process.run(['/bin/sh', '-c', UNIX_CLAUDE_SCRIPT])
    const program = r.exitCode === 0 ? claudeCandidate(r.stdout) : undefined
    if (program) found.push(program)
  } catch {
    // the PATH is still tried
    // vẫn thử PATH
  }
  found.push('claude')
  for (const program of found) {
    const v = await $.process.run([program, '--version'], { timeoutMs: 15_000 }).catch(() => undefined)
    if (v?.exitCode === 0 && isClaudeCodeVersion(v.stdout)) return program
  }
  return undefined
}

/**
 * Claude Code loads the plugin from its own copy, made when the plugin was installed, not from the folder /update
 * replaces: has it copy that folder again, the way `/plugin` updates a plugin. False when that could not be done.
 */
/** Claude Code nạp plugin từ bản chép riêng của nó, làm lúc cài plugin, không phải từ thư mục mà /update thay: nhờ nó chép lại thư mục đó, như cách `/plugin` cập nhật một plugin. False khi không làm được. */
async function refreshClaudeCopy($: EngineInterface): Promise<boolean> {
  const program = await claudeCodeProgram($)
  if (!program) return false
  for (const args of [['plugin', 'marketplace', 'update', 'ai-worker'], ['plugin', 'update', 'ai-worker@ai-worker']]) {
    const r = await $.process.run([program, ...args], { timeoutMs: 120_000 }).catch(() => undefined)
    if (r?.exitCode !== 0) return false
  }
  return true
}

/** What /update says when Claude Code could not take the new version in by itself. */
/** Điều /update nói khi Claude Code không tự nhận được bản mới. */
const refreshByHand = () => tx('If the old version still runs after that, type /plugin, choose ai-worker and update it, then reopen the app.')

/**
 * The Claude desktop app this session runs in, with the command that closes it and opens it again;
 * undefined in a terminal, an editor, or when the app cannot be told for certain.
 */
/** App Claude desktop mà phiên này đang chạy trong đó, kèm lệnh đóng rồi mở lại nó; undefined khi ở terminal, trình soạn mã, hoặc khi không nhận ra chắc chắn được app. */
async function findRestartTarget($: EngineInterface): Promise<{ pid: number; app: string; restart: string[]; env?: Record<string, string> } | undefined> {
  try {
    if (!(await $.session.surfaces()).some(s => s === 'desktop')) return undefined
    if ((await $.env.get('OS')) === 'Windows_NT') {
      // each script travels in a variable and the command line only names that variable: no quoting can break it,
      // and nothing read from the machine is ever part of a command line
      // mỗi script đi trong một biến và dòng lệnh chỉ nêu tên biến đó: không cách đặt dấu nháy nào làm hỏng được,
      // và không thứ gì đọc từ máy trở thành một phần dòng lệnh
      const powershell = WINDOWS_POWERSHELL
      const found = await $.process.run(powershell, { env: { AIW_SCRIPT: WINDOWS_FIND_SCRIPT }, timeoutMs: 30_000 })
      const host = found.exitCode === 0 ? parseWindowsHost(found.stdout) : undefined
      if (!host) return undefined
      return { pid: host.pid, app: host.app, restart: powershell, env: { AIW_SCRIPT: WINDOWS_RESTART_SCRIPT, AIW_HELPER: WINDOWS_HELPER, AIW_PID: String(host.pid), AIW_LAUNCHER: host.launcher } }
    }
    const system = (await $.process.run(['uname', '-s'])).stdout.trim()
    if (system === 'Linux') {
      // the script starts from its own parent, the program that runs this plugin
      // script đi từ tiến trình cha của nó, là chương trình đang chạy plugin này
      const found = await $.process.run(['/bin/sh', '-c', LINUX_FIND_SCRIPT])
      const host = found.exitCode === 0 ? parseLinuxHost(found.stdout) : undefined
      if (!host) return undefined
      return { pid: host.pid, app: host.app, restart: ['/bin/sh', '-c', LINUX_DETACH, LINUX_RESTART_SCRIPT, String(host.pid), host.launcher] }
    }
    if (system !== 'Darwin') return undefined
    // the shell's parent is the program that runs this plugin
    // tiến trình cha của shell là chương trình đang chạy plugin này
    const self = Number((await $.process.run(['/bin/sh', '-c', 'echo $PPID'])).stdout.trim())
    if (!Number.isInteger(self) || self <= 1) return undefined
    const host = findHostApp((await $.process.run(['ps', '-axo', 'pid=,ppid=,comm='])).stdout, self)
    if (!host) return undefined
    const id = await $.process.run(['/usr/bin/plutil', '-extract', 'CFBundleIdentifier', 'raw', '-o', '-', `${host.app}/Contents/Info.plist`])
    if (id.exitCode !== 0 || id.stdout.trim() !== DESKTOP_BUNDLE_ID) return undefined
    return { ...host, restart: ['/usr/bin/perl', '-MPOSIX', '-e', DETACH_PERL, '/bin/sh', '-c', RESTART_SCRIPT, 'sh', String(host.pid), host.app] }
  } catch {
    return undefined
  }
}

/**
 * After an update the person asked for: offers to close the Claude app and open it again, and does it on a yes.
 * Returns what to say then, or undefined when the app is not one it can reopen or the person said later.
 */
/** Sau một lần cập nhật do người dùng yêu cầu: hỏi có đóng app Claude rồi mở lại không, và làm khi được đồng ý. Trả về câu cần nói khi đó, hoặc undefined khi không phải app nó mở lại được hay người dùng chọn để sau. */
async function offerRestart($: EngineInterface, version: string): Promise<string | undefined> {
  const host = await findRestartTarget($)
  if (!host) return undefined
  const yes = tx('Reopen now')
  const answer = await $.ui
    .ask(tx('Version {version} is installed. Close the Claude app and open it again now? Sessions that are still working will stop.', { version }), {
      options: [yes, tx('Later')],
      header: tx('Update'),
    })
    .catch(() => '')
  if (answer !== yes) return undefined
  // a program of its own: the app cannot open itself again once it has quit
  // một chương trình riêng: app đã thoát thì không tự mở lại mình được
  const started = await $.process.run(host.restart, { timeoutMs: 30_000, ...(host.env ? { env: host.env } : {}) }).catch(() => undefined)
  return started?.exitCode === 0 ? tx('Updated to version {version}. The Claude app closes and opens again in a few seconds.', { version }) : undefined
}

/** Updates the plugin when the person asks (/update, the Update button), then offers to reopen the app. Returns what to tell the person. */
/** Cập nhật plugin khi người dùng yêu cầu (/update, nút Cập nhật), rồi hỏi có mở lại app không. Trả về điều cần nói với người dùng. */
async function updatePlugin($: EngineInterface): Promise<string> {
  const done = await installUpdate($)
  return (done.version && (await offerRestart($, done.version))) || done.text
}

/** Downloads, checks and swaps in the new version; keeps the old one beside it as `.old`. Returns what to tell the person, and the version when it went in. */
/** Tải, kiểm tra và đổi sang bản mới; giữ bản cũ bên cạnh dưới tên `.old`. Trả về điều cần nói với người dùng, và số phiên bản khi đã đổi xong. */
async function installUpdate($: EngineInterface): Promise<{ text: string; version?: string }> {
  const root = $.plugin.root.replace(/[\\/]+$/, '')
  if (await $.fs.exists(`${root}/.git`)) return { text: tx('This is a source code folder, so it does not update itself.') }
  if (!share.webhook || !share.ingestKey) return { text: tx('This computer has no server set up, so it cannot update.') }
  const { m, signature, text } = await checkNewVersion($)
  if (text) return { text }
  if (!m) return { text: tx('This computer already has the latest version.') }
  // an earlier /update already put it in, and this app still runs the old one until it is reopened: do not download it again
  // một lần /update trước đã cài nó, và app này vẫn chạy bản cũ cho tới khi mở lại: không tải lại nữa
  const onDisk = await $.fs.read(`${root}/.claude-plugin/plugin.json`).then(t => (JSON.parse(t) as { version?: unknown }).version, () => undefined)
  if (onDisk === m.version) {
    const taken = await refreshClaudeCopy($)
    const text = tx('Version {version} is already installed, but the Claude app is still running the old one. Quit the Claude app completely (Mac: Cmd+Q; Windows: right-click the Claude icon next to the clock, then Exit) and open it again.', { version: m.version })
    return { text: taken ? text : `${text}\n${refreshByHand()}`, version: m.version }
  }
  if (signature !== 'valid') return { text: tx('Version {version} is available, but this computer cannot check its signature, so it will not install it. Ask your admin for the install package.', { version: m.version }) }
  const win = (await $.env.get('OS')) === 'Windows_NT'
  const newDir = `${root}.new`
  const oldDir = `${root}.old`
  const dir = `${await webFolder($)}/update`
  const zip = `${dir}/${m.name}`
  const removeDir = (p: string) => $.process.run(win ? ['cmd', '/d', '/c', 'rmdir', '/s', '/q', p] : ['rm', '-rf', p])
  const moveDir = (a: string, b: string) => $.process.run(win ? ['cmd', '/d', '/c', 'move', '/y', a, b] : ['mv', a, b])
  // the key goes in a file: on a command line any process on the machine could read it
  // khoá đi vào một file: trên dòng lệnh, mọi tiến trình trên máy đều đọc được nó
  const headerFile = `${dir}/dau.txt`
  // the own key first, as for the manifest; a refused one falls back to the shared key
  // khoá riêng trước, như với manifest; bị từ chối thì quay về khoá chung
  let download = { exitCode: 1 }
  for (const key of await keysForReleases($)) {
    await $.fs.write(headerFile, `Authorization: Bearer ${key}\n`)
    download = await $.process.run(['curl', '-fsS', '-m', '120', '-H', `@${headerFile}`, '-o', zip, `${share.webhook}/releases/${m.name}`], { timeoutMs: 130_000 })
    await $.fs.write(headerFile, '')
    // only a refusal by the server (curl's 22) is worth the other key; a network that does not answer would not answer it either
    // chỉ lần máy chủ từ chối (mã 22 của curl) mới đáng thử khoá kia; mạng không trả lời thì cũng không trả lời khoá đó
    if (download.exitCode !== 22) break
  }
  if (download.exitCode !== 0) return { text: tx('Could not download the new version. Try again later, or tell your admin if this computer is away from the office.') }
  let bam: string | undefined
  for (const argv of [['shasum', '-a', '256', zip], ['sha256sum', zip], ['certutil', '-hashfile', zip, 'SHA256']]) {
    bam = await $.process.run(argv).then(r => (r.exitCode === 0 ? parseHash(r.stdout) : undefined)).catch(() => undefined)
    if (bam) break
  }
  if (bam !== m.sha256) return { text: tx('The downloaded package does not match its check code, so it was not installed. Tell your admin.') }
  await removeDir(newDir)
  await $.fs.write(`${newDir}/.installing`, '')
  const extracted = await $.process.run(['tar', '-xf', zip, '-C', newDir], { timeoutMs: 120_000 })
  if (extracted.exitCode !== 0) return { text: tx('Could not unpack the new version. Tell your admin.') }
  const installedVersion = (JSON.parse(await $.fs.read(`${newDir}/.claude-plugin/plugin.json`)) as { version?: unknown }).version
  if (installedVersion !== m.version) return { text: tx('The downloaded package is not the right version, so it was not installed. Tell your admin.') }
  // the company's settings and key are not in the update
  // thiết lập và khoá của công ty không có trong bản cập nhật
  const companyFile = `${root}/web/company.json`
  if (await $.fs.exists(companyFile)) await $.fs.write(`${newDir}/web/company.json`, await $.fs.read(companyFile))
  await removeDir(oldDir)
  if ((await moveDir(root, oldDir)).exitCode !== 0) return { text: tx('Could not replace the plugin folder. Quit the app completely and type /update again.') }
  if ((await moveDir(newDir, root)).exitCode !== 0) {
    await moveDir(oldDir, root)
    return { text: tx('Could not replace the plugin folder, so the old version was kept. Tell your admin.') }
  }
  const saved = ((await $.store.get(UPDATE_KEY)) as { checkedAt?: number } | undefined) ?? {}
  await $.store.set(UPDATE_KEY, { ...saved, date: m.date })
  await commit($, s => ({ ...s, update: undefined }))
  const taken = await refreshClaudeCopy($)
  return { text: tx('Updated to version {version}. Quit the Claude app completely (Mac: Cmd+Q; Windows: right-click the Claude icon next to the clock, then Exit) and open it again to use the new version.', { version: m.version }) + (taken ? '' : `\n${refreshByHand()}`), version: m.version }
}

/** Copies the browser view's page and drawing code next to the session files. */
/** Chép trang và mã vẽ của trang trình duyệt vào cạnh các file phiên. */
async function installWeb($: EngineInterface) {
  try {
    const dir = await webFolder($)
    for (const name of ['index.html', 'i18n.js', 'index.vi.js', 'ops.vi.js', 'ops.js', 'ops.css', 'ops3d.js', 'three.js', 'three.LICENSE']) {
      await $.fs.write(`${dir}/${name}`, await $.fs.read(`${$.plugin.root}/web/${name}`))
    }
    // the team's own words: written once, never over their edits
    // chữ riêng của nhóm: ghi một lần, không bao giờ đè lên chỗ họ đã sửa
    if (!(await $.fs.exists(`${dir}/config.js`))) {
      await $.fs.write(`${dir}/config.js`, await $.fs.read(`${$.plugin.root}/web/config.js`))
    }
    await loadConfig($, dir)
  } catch {
    // as above
    // như trên
  }
}

/** Opens the browser view in the default browser; false where that cannot run. */
/** Mở trang trình duyệt bằng trình duyệt mặc định; false khi không chạy được. */
/** Opens the page in the default browser: macOS `open`, then Linux `xdg-open`, then Windows `start`. */
/** Mở trang bằng trình duyệt mặc định: `open` của macOS, rồi `xdg-open` của Linux, rồi `start` của Windows. */
async function openWeb($: EngineInterface): Promise<boolean> {
  // the copy is otherwise refreshed only when a session starts, so /reload-plugins alone left an old page
  // bản sao nếu không thì chỉ được làm mới khi một phiên bắt đầu, nên chỉ /reload-plugins sẽ để lại trang cũ
  await installWeb($)
  const page = `${await webFolder($)}/index.html`
  for (const argv of [['open', page], ['xdg-open', page], ['cmd', '/c', 'start', '', page]]) {
    try {
      const r = await $.process.run(argv)
      if (r.exitCode === 0) return true
    } catch {
      // not this system's opener; try the next
      // không phải lệnh mở của hệ thống này; thử lệnh kế tiếp
    }
  }
  return false
}

// the salt of the prompts' fingerprints, made once on this computer and never sent
// muối của dấu vân tay đề bài, tạo một lần trên máy này và không bao giờ gửi đi
const SALT_KEY = 'delegationSalt'
let salt: string | undefined
async function delegationSalt($: EngineInterface): Promise<string> {
  if (salt) return salt
  const had = await $.store.get(SALT_KEY).catch(() => undefined)
  if (typeof had === 'string' && /^[0-9a-f]{32}$/.test(had)) return (salt = had)
  salt = newSalt()
  await $.store.set(SALT_KEY, salt).catch(() => undefined)
  return salt
}

// a record of work handed to a helper, kept with the session and sent with the machine's numbers; a record that
// cannot be kept changes nothing about the work itself
// biên bản của một việc giao cho trợ lý, giữ cùng phiên và gửi kèm số liệu của máy; biên bản không ghi được thì không
// đổi gì ở chính việc đó
async function noteDelegation($: EngineInterface, p: Omit<Parameters<typeof makeDelegation>[0], 'promptChars' | 'promptHash' | 'at'> & { prompt: string }): Promise<void> {
  try {
    const { prompt, ...rest } = p
    const record = makeDelegation({ ...rest, promptChars: prompt.length, promptHash: promptHash(await delegationSalt($), prompt), at: await $.clock.now() })
    await commit($, s => addDelegation(s, record))
  } catch {
    // nothing to do
    // không có gì phải làm
  }
}

// one stop or question of ai-worker, for the counts the board shows; the same one seen twice in a moment (the permission
// box and the check both ask) is counted once
// một lần chặn hay hỏi của ai-worker, cho các con số bảng hiện; cùng một lần thấy hai lần trong chốc lát (hộp xin phép và
// bước kiểm đều hỏi) chỉ đếm một
const MAX_BLOCKS = 200
let lastBlock = { key: '', at: 0 }
async function noteBlock($: EngineInterface, kind: BlockKind, key: string): Promise<void> {
  try {
    const at = await $.clock.now()
    if (lastBlock.key === kind + key && at - lastBlock.at < 20_000) return
    lastBlock = { key: kind + key, at }
    await commit($, s => ({ ...s, blocks: [...(s.blocks ?? []), { at, kind }].slice(-MAX_BLOCKS) }))
  } catch {
    // a count that cannot be kept changes nothing about the stop itself
    // con số không ghi được thì không đổi gì ở chính lần chặn
  }
}

async function commit($: EngineInterface, fn: (s: TeamState) => TeamState): Promise<TeamState> {
  const s = await update($, team, fn)
  await save($, s)
  return s
}

// The ticker keeps elapsed times moving while anything is busy or a badge shows.
// Bộ đếm giữ thời gian trôi chạy chừng nào còn thứ đang bận hoặc còn huy hiệu hiện.
let ticker: { cancel(): void } | undefined

function isLively(s: TeamState, now: number): boolean {
  if (s.claudeBusySince !== undefined) return true
  if (s.subagents?.length) return true
  return s.jobs.some(j => j.endedAt === undefined || now - j.endedAt < Math.max(BADGE_MS, FX_MS))
}

// Subagents have no end event of their own here: read the engine's list while anything is lively.
// Trợ lý con ở đây không có sự kiện kết thúc riêng: đọc danh sách của engine chừng nào còn thứ đang sôi động.
const ASSISTANTS_EVERY_MS = 5000
let assistantsAt = 0

/** The model each subagent runs on, by its id, as its spawn answered: the engine's list does not say. */
/** Mô hình mà mỗi trợ lý con chạy, theo mã của nó, như lúc khởi tạo trả lời: danh sách của engine không nói. */
const agentModels = new Map<string, string>()

async function refreshAssistants($: EngineInterface, now: number) {
  assistantsAt = now
  try {
    const agents = await $.agent.list()
    const currentAgents = agents
      .filter(a => a.status === 'pending' || a.status === 'running' || a.status === 'waiting')
      .map(a => ({ name: assistantName(a.type, agentModels.get(a.id)), description: a.description.slice(0, 80) }))
      .slice(0, 20)
    const s = await read($, team)
    if (JSON.stringify(s.subagents ?? []) !== JSON.stringify(currentAgents)) await commit($, st => ({ ...st, subagents: currentAgents }))
  } catch {
    // an engine without the list: the office simply shows no names
    // engine không có danh sách này: văn phòng đơn giản là không hiện tên
  }
}

async function tick($: EngineInterface) {
  const now = await $.clock.now()
  if (now - assistantsAt >= ASSISTANTS_EVERY_MS) await refreshAssistants($, now)
  const s = await commit($, st => ({ ...st, now }))
  if (!isLively(s, now)) {
    ticker?.cancel()
    ticker = undefined
  }
}

function ensureTicker($: EngineInterface) {
  if (!ticker) ticker = $.clock.every(1000, () => void tick($))
}

/** Rules for technical work, in every session: they go with the coding and testing skills and the `planner` assistant the plugin ships. */
/** Quy tắc cho việc kỹ thuật, trong mọi phiên: đi kèm các skill viết code, kiểm thử và trợ lý `planner` mà plugin mang theo. */
const techRules = () => [
  tx('# Rules for technical work'),
  tx('- After changing the interface, open the real page and check both the desktop and the phone size before saying it is done. If you cannot check, say clearly that you have not.'),
  tx('- When the user says "split sessions": make a plan first, then evaluate. Only split when there are at least 2 large parts that can be done independently without touching the same file; otherwise give the reason in one sentence and work in the current session. If you split, show the assignment table and then create the sessions right away: mechanical parts use Sonnet, read-only parts use Haiku, design and checking stay in the main session. When done, check each session result before reporting. Commit only when the user says so. When the user says "split anyway", split the parts that can be separated and say clearly which parts cannot be.'),
  tx('- Call the `planner` assistant only after the user has agreed, because it uses a lot of quota; use it for big decisions that are hard to undo. It runs on Claude Opus: when this session itself runs on Opus or a stronger model (Fable, Mythos), do not ask about it and do not call it; plan the decision yourself and show the user the plan.'),
  tx('- The skill `improve-codebase-architecture` starts only when the user types its name. When the user asks, in any words, to look over or improve the structure of a whole project, do not do that scan yourself, and do not first ask for a folder or read any file: answer at once by telling them to type `/ai-worker:improve-codebase-architecture`, and say in one line that it reads the whole project and takes a while. A remark that some code is messy, or a request about one function, file or module, is not that: just help with it.'),
].join('\n')

/** /ai-worker:help: what the plugin gives on this computer, read from the plugin's own folder and this session. */
/** /ai-worker:help: những gì plugin có trên máy này, đọc từ thư mục của chính plugin và từ phiên này. */
const BOARD_TOOL_NAME = /^mcp__ai-worker__office_board$/

/** Which system this computer runs, in the plugin's own words for it. */
/** Máy này chạy hệ nào, theo cách gọi của plugin. */
async function hostSystem($: EngineInterface): Promise<VoiceSystem> {
  if ((await $.env.get('OS')) === 'Windows_NT') return 'Windows'
  try {
    return (await $.process.run(['uname', '-s'])).stdout.trim() === 'Darwin' ? 'Mac' : 'Linux'
  } catch {
    return 'Linux'
  }
}

/** What the board (hooks/boardtool.ts) needs from this computer, read where the engine allows: at each call. */
/** Những gì bảng (hooks/boardtool.ts) cần từ máy này, đọc ở chỗ engine cho phép: tại mỗi lần gọi. */
function boardIo($: EngineInterface): BoardIo {
  return {
    store: storeOf($),
    fetch: (url, init) => $.http.fetch(url, init),
    webhook: share.webhook,
    userAgent: async () => {
      const system = await hostSystem($)
      return boardUserAgent(await pluginVersion($), system)
    },
    now: () => $.clock.now(),
    registerTool: () => registerBoardTool($),
  }
}

/** Put the board tool in this session's list. Called once the computer is paired, never before: an unpaired computer carries no extra tool. */
/** Đưa công cụ đọc bảng vào danh sách của phiên này. Chỉ gọi khi máy đã ghép: máy chưa ghép không mang thêm công cụ nào. */
async function registerBoardTool($: EngineInterface) {
  try {
    await $.tool.register({ name: BOARD_TOOL, description: boardToolDescription(), inputSchema: BOARD_SCHEMA, isDeferred: false })
  } catch {
    // the tool stays off this session; the next session registers it
    // công cụ vắng mặt trong phiên này; phiên sau sẽ đăng ký
  }
}

/** /ai-worker:board (hooks/boardtool.ts). */
/** /ai-worker:board (hooks/boardtool.ts). */
function runBoard($: EngineInterface, args: string): Promise<{ text: string }> {
  return runBoardOn(boardIo($), args)
}

/** The board tool: the wall view as plain lines. It reads from the company server into this conversation and sends nothing out. */
/** Công cụ đọc bảng: phần treo tường thành các dòng chữ. Nó đọc từ máy chủ công ty vào cuộc trò chuyện này và không gửi gì ra ngoài. */
async function serveBoard($: EngineInterface, args: Record<string, unknown>): Promise<ToolCallResult> {
  const answer = (text: string, isError = false) => ({ result: text, isError }) as unknown as ToolCallResult
  const verdict = await $.tool.check({ tool: `mcp__ai-worker__${BOARD_TOOL}`, input: toolInput(args) }).catch(() => ({ decision: 'ask' as const }))
  if (verdict.decision === 'deny') return answer(tx('Your permission settings do not allow this.'), true)
  const r = await readBoard(boardIo($))
  return answer(r.text, r.isError)
}

async function runHelp($: EngineInterface): Promise<{ text: string }> {
  const root = $.plugin.root.replace(/[\\/]+$/, '')
  const skills: SkillLine[] = []
  try {
    for (const entry of await $.fs.list(`${root}/skills`)) {
      if (entry.kind !== 'dir') continue
      let text = ''
      try {
        text = await $.fs.read(`${root}/skills/${entry.name}/SKILL.md`)
      } catch {
        // a folder with no skill in it
        // một thư mục không có skill bên trong
      }
      const line = skillLine(text, entry.name)
      if (line) skills.push(line)
    }
  } catch {
    // no skills folder: the list says none
    // không có thư mục skills: danh sách ghi là không có
  }
  skills.sort((a, b) => a.name.localeCompare(b.name))
  return { text: buildHelp({ title: BRAND.title, version: await pluginVersion($), skills, workers: own, viaMcp, sharing: share.enabled }) }
}

/** /ai-worker:voice: opens the settings page of the computer's own dictation and shows the steps. It changes no setting. */
/** /ai-worker:voice: mở trang cài đặt của tính năng đọc chính tả có sẵn trên máy và hiện các bước. Không đổi cài đặt nào. */
async function runVoice($: EngineInterface): Promise<{ text: string }> {
  const system = await hostSystem($)
  const argv = voiceSettingsCommand(system)
  let opened = false
  if (argv) {
    try {
      opened = (await $.process.run(argv, { timeoutMs: 15_000 })).exitCode === 0
    } catch {
      // the page did not open: the steps then say how to get there by hand
      // trang không mở được: khi đó các bước chỉ cách tự đi tới
    }
  }
  return { text: voiceSteps(system, opened) }
}

let askBeforeDestructive = true
let commitTrail = false

// what a session is told about the handoff notes on this computer; read once, when the session starts
// điều một phiên được báo về các ghi chú bàn giao trên máy này; đọc một lần, khi phiên bắt đầu
let handoffNotes: string | undefined

/** Lists the handoff folder (names and dates only) and keeps what the session will be told. No folder, no note: nothing is added. */
/** Liệt kê thư mục bàn giao (chỉ tên và ngày) và giữ lại điều phiên sẽ được báo. Không có thư mục, không có ghi chú: không thêm gì. */
async function readHandoffNotes($: EngineInterface) {
  const folder = `${await webFolder($)}/handoff`
  const notes: HandoffNote[] = []
  try {
    for (const entry of (await $.fs.list(folder)).slice(0, 200)) {
      const name = entry.kind === 'file' ? noteName(entry.name) : undefined
      if (!name) continue
      const stat = await $.fs.stat(`${folder}/${entry.name}`).catch(() => undefined)
      if (stat) notes.push({ name, at: stat.mtimeMs })
    }
  } catch {
    // no handoff folder yet
    // chưa có thư mục bàn giao
  }
  handoffNotes = handoffSection(newestNotes(notes), folder)
}
const SHELL_TOOL = /^(Bash|PowerShell)$/

// what Claude is told about the repository's AI settings, and the root it was read for; read when the session starts
// and again when /cd moves the session to another root
// điều Claude được báo về các thiết lập AI của repo, và gốc đã đọc; đọc khi phiên bắt đầu và đọc lại khi /cd đưa
// phiên sang gốc khác
const REPO_SEEN_KEY = 'repoConfigSeen'
let repoConfigNote: string | undefined
let repoConfigRoot: string | undefined

/** Looks at the AI settings a repository carries and tells the person and Claude what is new or changed since the last look. Never blocks. */
/** Xem các thiết lập AI mà repo mang theo và báo người dùng cùng Claude những gì mới hoặc đã đổi kể từ lần xem trước. Không bao giờ chặn. */
async function checkRepoConfig($: EngineInterface, root: string): Promise<void> {
  repoConfigRoot = root
  repoConfigNote = undefined
  try {
    const home = ((await $.env.get('HOME')) || (await $.env.get('USERPROFILE')) || '').replace(/[\\/]+$/, '')
    // the home folder's .claude is the person's own settings, not a repository's
    // .claude ở thư mục nhà là thiết lập của chính người dùng, không phải của một repo
    const bare = root.replace(/[\\/]+$/, '')
    if (!bare || bare === home) return
    const found = findRepoConfig(await readRepoFiles($, bare))
    const key = repoKey(bare)
    const seen = ((await $.store.get(REPO_SEEN_KEY).catch(() => undefined)) ?? {}) as RepoSeen
    const at = await $.clock.now()
    const news = repoNews(found, seen[key]?.marks, at)
    const before = seen[key]?.marks ?? []
    if (found.length !== before.length || found.some(f => !before.includes(f.mark))) await $.store.set(REPO_SEEN_KEY, rememberRepo(seen, key, found, at))
    if (!news.length) return
    repoConfigNote = repoNote(news)
    await Promise.resolve($.ui.toast(repoToast(news))).catch(() => undefined)
  } catch {
    // a repository that cannot be read is not checked
    // repo không đọc được thì không kiểm
  }
}

/** /office: the dashboard in the browser, or the side panel when no browser opens. */
/** /office: bảng trong trình duyệt, hoặc khung bên cạnh khi không mở được trình duyệt. */
async function runOffice($: EngineInterface): Promise<{ text: string }> {
  if (await openWeb($)) return { text: tx('Opened {title} in the browser.', { title: BRAND.title }) }
  await $.ui.open({ id: PANE, title: BRAND.title })
  return { text: tx('Could not open the browser; opened {title} in the side panel.', { title: BRAND.title }) }
}

/** /update: checks for a new version, installs it and says what happened. */
/** /update: kiểm tra bản mới, cài nó và báo điều đã xảy ra. */
async function runUpdate($: EngineInterface): Promise<{ text: string }> {
  return {
    text: await updatePlugin($).catch(err =>
      err instanceof NetworkRefused
        ? networkRefusedText()
        : tx('Could not check for a new version ({reason}). Try again later, or tell your admin if this computer is away from the office.', { reason: String(err instanceof Error ? err.message : err) }),
    ),
  }
}

/** /office-pane: the virtual office in a panel next to the chat. */
/** /office-pane: văn phòng ảo trong một khung cạnh cuộc trò chuyện. */
async function runOfficePane($: EngineInterface): Promise<{ text: string }> {
  await $.ui.open({ id: PANE, title: BRAND.title })
  return { text: tx('Opened {title}.', { title: BRAND.title }) }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // installWeb reads the language from user.json and config.js, so the commands below are described in it
    // installWeb đọc ngôn ngữ từ user.json và config.js, nên các lệnh bên dưới được mô tả bằng ngôn ngữ đó
    await installWeb($)
    await $.command.register({ name: 'office', description: tx('Open the dashboard of the sessions on this computer in the browser') })
    await $.command.register({ name: 'office-pane', description: tx('Open the virtual office in a panel next to the chat') })
    await $.command.register({ name: 'update', description: tx('Check for and install a new version of the plugin from the company server') })
    await $.command.register({ name: 'board', description: tx('For managers: pair this computer with the company board, so Claude can answer questions about the team') })
    try {
      await writeLedger(ledgerIo($), await readLedger(storeOf($)))
    } catch {
      // as above
      // như trên
    }
    // the feed lives in this session's memory, which is empty again after an update or when the app is reopened:
    // the lines its own file still holds are taken back before that file is written over
    // luồng hoạt động nằm trong bộ nhớ của phiên, vốn lại rỗng sau khi cập nhật hoặc khi app mở lại:
    // các dòng mà file của chính phiên còn giữ được lấy lại trước khi file đó bị ghi đè
    try {
      if (!(await read($, team)).activity?.length) {
        const kept = savedActivity(await $.fs.read(`${await webFolder($)}/sessions/${(await whoAmI($)).id}.js`), MAX_ACTIVITY)
        if (kept.length) await update($, team, s => (s.activity?.length ? s : { ...s, activity: kept }))
      }
    } catch {
      // a first start has no file yet
      // lần bắt đầu đầu tiên chưa có file
    }
    await save($, await read($, team))
    try {
      await list($, true)
    } catch {
      // as above
      // như trên
    }
    ensureHeartbeat($)
    await repairLedgerOnce(ledgerIo($))
    {
      const ledger = await readLedger(storeOf($)).catch(() => undefined)
      if (ledger) await writeLongSpend(ledgerIo($), ledger, Math.floor((await $.clock.now()) / 3_600_000))
    }
    void pruneOld($)
    void pruneShots($)
    void shareTeam($)
    // staff machines: the plugin's own delegation tools, one per helper installed here
    // máy nhân viên: các công cụ giao việc riêng của plugin, mỗi trợ lý cài ở đây một công cụ
    own = await findOwnWorkers($)
    const kept = (await $.store.get(HELPER_MODELS_KEY).catch(() => undefined)) as typeof helperModels | undefined
    if (kept && typeof kept === 'object') helperModels = { ...kept, ...helperModels }
    for (const t of viaMcp ? [] : ownTools(own)) {
      try {
        await $.tool.register({ name: t.name, description: t.description, inputSchema: t.inputSchema, isDeferred: false })
      } catch {
        // the tool stays off this session
        // công cụ đó vắng mặt trong phiên này
      }
    }
    if (viaMcp) await tuckOwnTools($)
    await readHandoffNotes($)
    await checkRepoConfig($, await $.session.root().catch(() => e.cwd))
    // a manager's computer already paired with the board: Claude can read it from the first message
    // máy của quản lý đã ghép với bảng: Claude đọc được bảng ngay từ tin nhắn đầu
    if ((await readPairing(storeOf($))).token) await registerBoardTool($)
    await writeOwnWorkers($)
    return next(e)
  })

  // when to hand work to which helper: only on machines whose plugin serves the tools itself
  // khi nào giao việc cho trợ lý nào: chỉ trên máy mà plugin tự phục vụ các công cụ
  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    const root = await $.session.root().catch(() => repoConfigRoot)
    if (root && root !== repoConfigRoot) await checkRepoConfig($, root)
    const text = own && !viaMcp ? delegationRules(own) : undefined
    const extra = [
      { id: 'ai-worker:tech-rules', text: techRules(), scope: 'session' as const },
      ...(text ? [{ id: 'ai-worker:delegation', text, scope: 'session' as const }] : []),
      // only a company package carries these
      // chỉ gói công ty mới có những thứ này
      ...(share.enabled ? [{ id: 'ai-worker:work-rules', text: sharedRules(), scope: 'session' as const }] : []),
      ...(handoffNotes ? [{ id: 'ai-worker:handoff-notes', text: handoffNotes, scope: 'session' as const }] : []),
      ...(repoConfigNote ? [{ id: 'ai-worker:repo-config', text: repoConfigNote, scope: 'session' as const }] : []),
    ]
    return { ...r, sections: [...r.sections, ...extra] }
  })

  // a long conversation about to be compacted: the summarizer is also told what the work depends on, and after an
  // automatic compaction the person is told nothing broke. A subagent's own transcript is left alone.
  // một cuộc trò chuyện dài sắp bị nén: bộ tóm tắt được dặn thêm những thứ công việc phụ thuộc vào, và sau một lần
  // nén tự động người dùng được báo là không có gì hỏng. Bản ghi riêng của trợ lý con thì để nguyên.
  on('session.compact', async ($, e, next) => {
    if (e.agentId) return next(e)
    const r = await next({ ...e, instructions: [e.instructions, compactKeepInstructions()].filter(Boolean).join('\n\n') })
    // `precompute` installs nothing and a skip changes nothing: there is nothing to tell
    // `precompute` không cài gì và một lần bỏ qua không đổi gì: không có gì để báo
    if (e.trigger === 'auto' && r.messages) await Promise.resolve($.ui.toast(compactedNotice())).catch(() => undefined)
    return r
  })

  // the context window's fill, pushed after each turn: the page shows when to open a fresh session
  // mức đầy của cửa sổ ngữ cảnh, đẩy sau mỗi lượt: trang hiện khi nào nên mở phiên mới
  on('session.measure', async ($, e, next) => {
    const context = contextFill(e.context)
    const s0 = await read($, team)
    // the model can change mid-session (/model): read it after each turn
    // mô hình có thể đổi giữa phiên (/model): đọc lại sau mỗi lượt
    let model = s0.model
    try {
      model = await $.session.model()
    } catch {
      // keep the last known one
      // giữ cái biết lần cuối
    }
    if (model && model !== s0.model) await commit($, s => ({ ...s, model }))
    // the account's 5-hour / 7-day windows: the team board shows how close each account is to its limit
    // (read on every measure, not only when `changed` names it: after a reload the engine does not report it again)
    // các cửa sổ 5 giờ / 7 ngày của tài khoản: bảng cả team hiện mỗi tài khoản gần chạm hạn mức tới đâu
    // (đọc ở mỗi lần đo, không chỉ khi `changed` nêu nó: sau khi tải lại, engine không báo nữa)
    const quota = toQuota(e.rateLimits, await $.clock.now())
    if (quota && (JSON.stringify(quota.windows) !== JSON.stringify(s0.quota?.windows) || quota.readAt - (s0.quota?.readAt ?? 0) > 3_600_000)) await commit($, s => ({ ...s, quota }))
    // the account near its limit: toast each level once per window, the band above the prompt stays until hidden
    // tài khoản gần chạm hạn mức: báo mỗi mức một lần cho mỗi cửa sổ, dải phía trên ô nhập ở lại cho tới khi ẩn
    const warning = quotaWarning(quota ?? s0.quota, await $.clock.now(), model)
    if (warning && warning.key !== s0.quotaWarned) {
      $.ui.toast(warning.text)
      await commit($, s => ({ ...s, quotaWarned: warning.key }))
    }
    const warn = context ? contextWarning(context.percent, s0.contextWarned ?? 0, await hasHandoffSkill($)) : { level: s0.contextWarned ?? 0 }
    if (warn.text) $.ui.toast(warn.text)
    if (context?.percent !== s0.context?.percent || context?.tokens !== s0.context?.tokens || warn.level !== (s0.contextWarned ?? 0)) {
      await commit($, s => ({ ...s, context, contextWarned: warn.level }))
    }
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    heartbeat?.cancel()
    heartbeat = undefined
    try {
      await list($, false)
    } catch {
      // as above
      // như trên
    }
    return next(e)
  })

  // each command answers to two names: the bare one, registered when a session starts, and its file's
  // (commands/<name>.md, listed as ai-worker:<name>), which the app shows before any session has started
  // mỗi lệnh trả lời hai tên: tên trần, đăng ký khi một phiên bắt đầu, và tên của file
  // (commands/<name>.md, hiện là ai-worker:<name>), cái app liệt kê trước khi có phiên nào bắt đầu
  on('command.run', { command: 'office' }, $ => runOffice($))
  on('command.run', { command: 'ai-worker:office' }, $ => runOffice($))
  on('command.run', { command: 'update' }, $ => runUpdate($))
  on('command.run', { command: 'ai-worker:update' }, $ => runUpdate($))
  on('command.run', { command: 'office-pane' }, $ => runOfficePane($))
  on('command.run', { command: 'ai-worker:office-pane' }, $ => runOfficePane($))
  // no short name: /help is Claude Code's own
  // không có tên ngắn: /help là của chính Claude Code
  on('command.run', { command: 'ai-worker:help' }, $ => runHelp($))
  // no short name either: /voice is Claude Code's own dictation
  // cũng không có tên ngắn: /voice là tính năng đọc chính tả của chính Claude Code
  on('command.run', { command: 'ai-worker:voice' }, $ => runVoice($))
  on('command.run', { command: 'board' }, ($, e) => runBoard($, e.args))
  on('command.run', { command: 'ai-worker:board' }, ($, e) => runBoard($, e.args))

  // the chat's title rides on the settings hooks' session start and prompt events
  // tiêu đề cuộc trò chuyện đi theo các sự kiện bắt đầu phiên và gửi lời nhắc của các hook cài đặt
  on('classic.SessionStart', async ($, e, next) => {
    const done = await next(e)
    await takeTitle($, (e as { session_title?: unknown }).session_title)
    return done
  })
  on('classic.UserPromptSubmit', async ($, e, next) => {
    const done = await next(e)
    const ev = e as { session_title?: unknown; prompt?: unknown }
    // a title other than the one this plugin set means the person renamed the chat
    // một tiêu đề khác với tiêu đề plugin này đặt nghĩa là người dùng đã đổi tên cuộc trò chuyện
    noteRename(titles, ev.session_title)
    await takeTitle($, ev.session_title)
    notePrompt(titles, ev.prompt)
    const title = nextTitle(titles)
    if (title) {
      await takeTitle($, title)
      return { ...done, sessionTitle: title }
    }
    return done
  })


  // a message the person wrote (typed here, through the desktop app or from a phone), not a task's or a timer's
  // tin nhắn người dùng viết (gõ ở đây, qua app desktop hay từ điện thoại), không phải của một tác vụ hay bộ hẹn giờ
  const personsOwn = (o: { kind: string; asUser?: true } | undefined) =>
    !o || o.kind === 'composer' || o.kind === 'bridge' || o.kind === 'sdk' || o.kind === 'unclassified' || (o.kind === 'plugin' && o.asUser === true)
  on('prompt.submit', async ($, e, next) => {
    if (!e.command) pastedImages = e.attachments?.filter(a => a.type === 'image').length ?? 0
    if (!e.command) pastedShots = pastedImages ? await keepShots($, e.attachments ?? []) : []
    // the person's own message, once the context passed 80%: Claude is told too, once per climb, so it suggests a handoff
    // tin nhắn của chính người dùng, khi context đã vượt 80%: Claude cũng được báo, mỗi lần leo một lần, để đề nghị bàn giao
    if (!e.command && personsOwn(e.origin)) {
      try {
        const s = await read($, team)
        const percent = s.context?.percent ?? 0
        const level = percent >= 80 ? 80 : 0
        const told = s.contextToldClaude ?? 0
        if (level !== told) {
          await commit($, st => ({ ...st, contextToldClaude: level }))
          const note = level > told ? contextNoteForClaude(percent, await hasHandoffSkill($)) : undefined
          if (note) return next({ ...e, context: [...(e.context ?? []), note] })
        }
      } catch {
        // the message goes through as typed
        // tin nhắn đi qua như đã gõ
      }
    }
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    if (!e.agentId) {
      const now = await $.clock.now()
      const cwd = await $.session.cwd()
      const home = (await $.env.get('HOME')) ?? ''
      await commit($, s => {
        const st = { ...s, now, claudeBusySince: now, claudeTool: undefined, asking: false }
        const pasted = pastedImages
        pastedImages = 0
        const shots = pastedShots
        pastedShots = []
        const you = youEntry(e.text, now, cwd, pasted, shots)
        if (you?.media) you.media = you.media.map(p => (p.startsWith('~/') ? home + p.slice(1) : p))
        return you ? pushActivity(st, you) : st
      })
      ensureTicker($)
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    const isMain = !(e as { agentId?: string }).agentId
    // after a main turn, now and then, a fresh title is made; the next prompt applies it
    // sau một lượt chính, thỉnh thoảng, một tiêu đề mới được làm; lời nhắc kế tiếp áp dụng nó
    if (isMain) await makeTitle($)
    const turn = e.usage ? toUsage(e.usage, isMain ? 1 : 0) : undefined
    const now = await $.clock.now()
    const costUsd = await sessionCost($)
    const before = (await read($, team)).costUsd ?? (await lastCost(storeOf($), sessionId($)))
    if (turn || costUsd !== undefined) await logSpend(ledgerIo($), now, turn, costUsd === undefined ? 0 : costDelta(before, costUsd))
    if (costUsd !== undefined) await rememberCost(storeOf($), sessionId($), costUsd)
    await commit($, s => ({
      ...s,
      now,
      ...(turn ? { usage: addUsage(s.usage, turn) } : {}),
      ...(costUsd !== undefined ? { costUsd } : {}),
      ...(isMain ? { claudeBusySince: undefined, claudeTool: undefined, ...(turn ? { lastTurn: turn } : {}) } : {}),
    }))
    return done
  })

  on('turn.step', async function* ($, e, next) {
    const at = await $.clock.now()
    const step = yield* next(e)
    if (!e.agentId) {
      const said = sayEntry(step.answer ?? '', at)
      if (said) await commit($, s => pushActivity(s, said))
    }
    return step
  })

  // a shell command that destroys work (a whole folder, unsaved changes, the shared git server, untracked files) is
  // put to a person, in plain words, whatever the permission mode. A hook's "ask" is the person's to answer: no
  // automatic approval settles it, and where nobody can be asked the command is refused. A deny beneath stays a deny.
  // một lệnh shell phá huỷ công việc (cả thư mục, thay đổi chưa lưu, máy chủ git dùng chung, file chưa theo dõi) được
  // đưa cho một người trả lời, bằng lời thường, ở mọi chế độ quyền. "ask" của một hook là của người dùng: không có
  // bước tự duyệt nào trả lời thay, và ở nơi không hỏi được ai thì lệnh bị từ chối. Một lệnh đã bị cấm vẫn bị cấm.
  // A key, a token or a password in text for ChatGPT or Gemini, through the plugin's own tools or a separate ai-workers
  // server the person runs (mcp__ai-workers__ask_chatgpt and the like), is refused here, before the call, whatever the mode.
  // Khoá, token hay mật khẩu trong chữ gửi cho ChatGPT hay Gemini, qua công cụ của chính plugin hay một server ai-workers
  // riêng mà người dùng chạy (mcp__ai-workers__ask_chatgpt và tương tự), bị từ chối ở đây, trước lệnh gọi, ở mọi chế độ.
  on('tool.check', async ($, e, next) => {
    const outside = OUTSIDE_HELPER.exec(e.tool)
    const prompt = (e.input as Record<string, unknown> | undefined)?.prompt
    const found = outside && typeof prompt === 'string' ? findSecrets(prompt) : []
    if (outside && found.length) {
      await noteBlock($, 'secret', String(prompt).slice(0, 200))
      const tool = delegationTool(outside[1])
      if (tool) {
        const callId = (e as { tool_use_id?: string }).tool_use_id ?? `check-${e.tool}-${await $.clock.now()}`
        await noteDelegation($, { callId, tool, via: e.tool.startsWith('mcp__ai-workers__') ? 'ai-workers' : 'plugin', prompt: String(prompt), outcome: 'refused', found: found.map(f => f.kind) })
      }
      return { decision: 'deny' as const, reason: secretRefusal(found, outside[1] === 'ask_chatgpt' ? 'ChatGPT' : 'Gemini') }
    }
    const verdict = await next(e)
    if (!SHELL_TOOL.test(e.tool) || verdict.decision === 'deny') return verdict
    const command = (e.input as Record<string, unknown> | undefined)?.command
    if (typeof command !== 'string') return verdict
    const danger = askBeforeDestructive ? destructiveCommand(command) : undefined
    if (danger) {
      await noteBlock($, 'risky', command)
      return { decision: 'ask' as const, reason: dangerQuestion(danger) }
    }
    const secret = await commitSecretQuestion($, command)
    if (secret) await noteBlock($, 'commit', command)
    return secret ? { decision: 'ask' as const, reason: secret } : verdict
  })

  // a subagent's model is known once it starts: the office and the board name it by that
  // mô hình của trợ lý con được biết khi nó bắt đầu: văn phòng và bảng tổng gọi nó theo đó
  on('agent.spawn', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || !ran.agentId || !ran.model) return ran
    agentModels.set(ran.agentId, ran.model)
    if (agentModels.size > 200) agentModels.delete(agentModels.keys().next().value!)
    if (!e.parentAgentId) {
      const label = tx('Handing work to {worker}', { worker: assistantName(e.subagentType, ran.model) })
      await commit($, st => (st.claudeBusySince === undefined ? st : { ...st, claudeTool: label }))
    }
    await refreshAssistants($, await $.clock.now())
    ensureTicker($)
    return ran
  })

  on('tool.call', async ($, e, next) => {
    if (!e.agentId) {
      const args = e as unknown as Record<string, unknown>
      const line = describeTool(e.tool, args)
      const at = await $.clock.now()
      if (line) await commit($, s => pushActivity(s, { at, kind: 'tool', ...line }))
      if (PLAN_TOOL.test(e.tool)) await commit($, s => ({ ...s, plan: applyPlan(s.plan, args) }))
      if (WRAP_UP.test(e.tool)) await commit($, s => ({ ...s, plan: finishPlan(s.plan) }))
    }
    if (BOARD_TOOL_NAME.test(e.tool)) return serveBoard($, e as unknown as Record<string, unknown>)
    // the app's permission box shows a command's own description: a command that destroys work goes on with the
    // plain-words warning in that place (the office page above has already taken what Claude wrote)
    // hộp xin phép của app hiện phần mô tả của chính lệnh: một lệnh phá huỷ công việc đi tiếp với câu cảnh báo
    // bằng lời thường ở chỗ đó (trang văn phòng ở trên đã lấy điều Claude viết rồi)
    if (SHELL_TOOL.test(e.tool)) {
      const args = e as unknown as Record<string, unknown>
      const command = typeof args.command === 'string' ? args.command : ''
      const danger = askBeforeDestructive && command ? destructiveCommand(command) : undefined
      if (danger) e = { ...e, description: dangerNote(danger, args.description) } as typeof e
      else {
        const secret = command ? await commitSecretQuestion($, command) : undefined
        const note = typeof args.description === 'string' ? args.description.trim() : ''
        if (secret) e = { ...e, description: note ? `${secret} ${tx('Claude wrote: {note}', { note })}` : secret } as typeof e
      }
    }
    const match = WORKER_TOOL.exec(e.tool)
    const name = match?.[1]
    const op = name ? OPS[name] : undefined
    if (!op) {
      if (!e.agentId) {
        const label = e.tool === 'Agent' ? agentLabel(e as unknown as Record<string, unknown>) : claudeLabel(e.tool)
        const s = await read($, team)
        if (s.claudeTool !== label) await commit($, st => ({ ...st, claudeTool: label }))
      }
      const args = e as unknown as Record<string, unknown>
      if (e.tool === 'AskUserQuestion' && !e.agentId) {
        await commit($, st => ({ ...st, asking: true }))
        const answered = await next(e)
        await commit($, st => ({ ...st, asking: false }))
        return answered
      }
      const trail = commitTrail && SHELL_TOOL.test(e.tool) && typeof args.command === 'string' ? await trailStart($, args.command) : undefined
      const ran = await next(e)
      if (e.tool === 'Agent' && ran.deny === undefined) {
        await refreshAssistants($, await $.clock.now())
        ensureTicker($)
      }
      if (WRAP_UP.test(e.tool) && !e.agentId && typeof args.ask === 'string' && args.ask.trim() && ran.deny === undefined) {
        // the turn ends on a question: stays true until the person starts the next turn
        // lượt kết thúc bằng một câu hỏi: giữ đúng cho tới khi người dùng bắt đầu lượt kế tiếp
        await commit($, st => ({ ...st, asking: true }))
      }
      if (EDIT_TOOLS.has(e.tool) && ran.deny === undefined && !ran.isError) {
        const at = await $.clock.now()
        const edit = buildFileEdit(e.tool, args, ran.result, at, e.tool_use_id ?? `edit-${at}`)
        if (edit) await commit($, st => ({ ...st, edits: [...(st.edits ?? []), edit].slice(-MAX_EDITS) }))
      }
      // a page or a search that speaks to an AI: Claude is told it is data, the person is told what happened
      // một trang hay một lần tìm kiếm nói với AI: Claude được báo đó là dữ liệu, người dùng được báo chuyện gì đã xảy ra
      if (OUTSIDE_TEXT_TOOL.test(e.tool) && ran.deny === undefined && !ran.isError) {
        let text = ''
        try {
          text = typeof ran.text === 'string' ? ran.text : typeof ran.result === 'string' ? ran.result : JSON.stringify(ran.result ?? '')
        } catch {
          // a result that cannot be read as text is not checked
          // kết quả không đọc được thành chữ thì không kiểm
        }
        const found = findInjection(text)
        if (found.length) {
          await noteBlock($, 'page', `${e.tool}:${found.map(f => f.kind).join(',')}`)
          if (!e.agentId) await Promise.resolve($.ui.toast(injectionToast(found))).catch(() => undefined)
          return { ...ran, context: [...(ran.context ?? []), injectionNote(found, e.tool)] }
        }
      }
      // a commit Claude just made whose message lacks its cause or what was measured: Claude is told to amend it
      // một commit Claude vừa tạo mà lời commit thiếu nguyên nhân hay thứ đã đo: Claude được nhắc sửa lại
      if (trail && ran.deny === undefined) {
        const note = await trailEnd($, trail)
        if (note) return { ...ran, context: [...(ran.context ?? []), note] }
      }
      return ran
    }

    const args = e as unknown as Record<string, unknown>
    const startedAt = await $.clock.now()
    let key: string | undefined
    if (op.isAsk) {
      key = e.tool_use_id ?? `job-${startedAt}`
      const tool = delegationTool(name)
      const prompt = typeof args.prompt === 'string' ? args.prompt : ''
      const job: Job = {
        key,
        worker: op.worker,
        kind: op.worker === 'gemini' && op.kind === KIND_GEMINI ? geminiKind(args.prompt) : op.kind(),
        startedAt,
        ...(tool
          ? { brief: { tool, via: OWN_TOOL.test(e.tool) ? 'plugin' as const : 'ai-workers' as const, promptChars: prompt.length, promptHash: promptHash(await delegationSalt($), prompt) } }
          : {}),
      }
      await commit($, s => ({
        ...s,
        now: startedAt,
        claudeTool: tx('Handing work to {worker}', { worker: WORKER_NAME[op.worker] }),
        jobs: [...s.jobs, job].slice(-MAX_JOBS),
      }))
    } else {
      const jobId = typeof args.job_id === 'string' ? args.job_id.trim() : ''
      const s = await read($, team)
      key = s.jobs.find(j => j.jobId === jobId && j.endedAt === undefined)?.key
      if (key) await commit($, st => ({ ...st, claudeTool: tx('Waiting for {worker}', { worker: WORKER_NAME[op.worker] }) }))
    }
    ensureTicker($)

    const own = OWN_TOOL.exec(e.tool)
    const why: Refused = {}
    const ran0 = own ? await serveOwn($, own[1]!, args, why) : await next(e)
    if (!key) return ran0
    let ran = ran0

    const endedAt = await $.clock.now()
    const raw = ran.text ?? (typeof ran.result === 'string' ? ran.result : JSON.stringify(ran.result ?? ''))
    const helper = op.worker === 'chatgpt' || op.worker === 'gemini' ? op.worker : undefined
    const named = helper && !ran.isError ? answerModel(raw) : undefined
    if (helper && named && helperModels[helper] !== named) {
      helperModels = { ...helperModels, [helper]: named }
      await $.store.set(HELPER_MODELS_KEY, helperModels).catch(() => undefined)
    }
    const pending = ran.deny === undefined && !ran.isError ? PENDING.exec(raw) : null
    // the answer is read before Claude uses it; the record of the work is written once the work is over
    // câu trả lời được đọc trước khi Claude dùng; biên bản của việc được ghi khi việc đã xong
    if (!pending) {
      const job = (await read($, team)).jobs.find(j => j.key === key)
      const answered = ran.deny === undefined && !ran.isError && !why.outcome
      const checked = answered ? checkAnswer(raw) : undefined
      const flags = checked ? answerFlags(checked) : []
      if (checked && flags.length) {
        const worker = WORKER_NAME[op.worker]
        await noteBlock($, 'answer', `${key}:${flags.join(',')}`)
        if (!e.agentId) await Promise.resolve($.ui.toast(answerToast(checked, worker))).catch(() => undefined)
        const note = answerNote(checked, worker)
        if (note && ran.deny === undefined && !ran.isError) ran = { ...ran, context: [...(ran.context ?? []), note] }
      }
      if (job?.brief) {
        const outcome = why.outcome ?? (ran.deny !== undefined ? 'declined' : ran.isError ? 'error' : 'ok')
        try {
          const record = makeDelegation({ ...job.brief, callId: key, at: endedAt, outcome, answerChars: answered ? raw.length : 0, check: flags, found: why.found })
          await commit($, s => addDelegation(s, record))
        } catch {
          // a record that cannot be kept changes nothing about the work
          // biên bản không ghi được thì không đổi gì ở chính việc đó
        }
      }
    }
    await commit($, s => ({
      ...s,
      now: endedAt,
      jobs:
        ran.deny !== undefined
          ? s.jobs.filter(j => j.key !== key)
          : s.jobs.map(j => {
              if (j.key !== key) return j
              return pending ? { ...j, jobId: pending[1] } : { ...j, endedAt, ok: !ran.isError }
            }),
    }))
    ensureTicker($)
    return ran
  })

  // a band above the prompt while the account is at 80% / 95% of a window; "Hide" hides it until it gets worse
  // một dải phía trên ô nhập khi tài khoản ở mức 80% / 95% của một cửa sổ; "Ẩn" giấu nó cho tới khi tệ hơn
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const s = await read($, team)
    const warning = quotaWarning(s.quota, await $.clock.now(), s.model)
    const { Box, Button, Text } = $.ui.resolve(e)
    if (!warning || warning.key === s.quotaHidden) {
      // an update never interrupts a turn
      // một bản cập nhật không bao giờ ngắt một lượt
      const pending = s.update
      if (!pending || s.claudeBusySince) return next(e)
      const dismiss = () => commit($, x => ({ ...x, update: undefined }))
      if (!pending.auto) {
        return (
          <Box>
            <Text color="warning">{tx('Version {version} is available. This computer cannot install it itself; ask your admin for the install package. ', { version: pending.version })}</Text>
            <Button key="dismiss" label={tx('Got it')} onPress={dismiss} />
          </Box>
        )
      }
      return (
        <Box>
          <Text>{tx('A new version {version} of the AI Worker Office plugin is available. ', { version: pending.version })}</Text>
          <Button key="update" label={tx('Update')} onPress={async () => {
            const message = await updatePlugin($).catch(() => tx('Could not update. Try again later with /update.'))
            $.ui.toast(message)
          }} />
          <Button key="dismiss" label={tx('Later')} onPress={dismiss} />
        </Box>
      )
    }
    return (
      <Box>
        <Text color={warning.level === 95 ? 'error' : 'warning'}>{warning.level === 95 ? '⛔ ' : '⚠ '}{warning.text} </Text>
        <Button key="dismiss" label={tx('Hide')} onPress={() => commit($, x => ({ ...x, quotaHidden: warning.key }))} />
      </Box>
    )
  })

  // ai-workers connected after the plugin registered its own delegation tools: send the model to ai-workers' instead
  // ai-workers kết nối sau khi plugin đăng ký các công cụ giao việc riêng: chuyển mô hình sang công cụ của ai-workers
  on('tool.describe', async ($, e, next) => {
    const r = await next(e)
    const m = OWN_ASK.exec(e.tool)
    if (!m || !viaMcp) return r
    return { ...r, isDeferred: true, description: tx('Duplicate of mcp__ai-workers__{tool}: use that tool instead of this one.', { tool: m[1]! }) }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Text } = ui
    const s = await read($, team)
    const now = s.now || (await $.clock.now())

    const rows = WORKERS.map(w => {
      const v = workerView(s, w.id, now)
      const status =
        v.state === 'asking'
          ? tx('waiting for your answer')
          : v.state === 'working'
          ? tx('working on {kind} · {time}', { kind: v.kind ?? tx('a task'), time: formatSecs(v.secs ?? 0) })
          : v.state === 'done'
            ? tx('{kind} done · {time}', { kind: v.kind ?? '', time: formatSecs(v.secs ?? 0) })
            : v.state === 'error'
              ? tx('failed: {kind}', { kind: v.kind ?? tx('the task') })
              : tx('currently idle')
      return (
        <Box flexDirection="row" gap={1}>
          <Text color={w.shirt} bold>
            {w.name.padEnd(8)}
          </Text>
          <Text dimColor={v.state === 'idle'} color={v.state === 'error' ? 'red' : v.state === 'asking' ? 'yellow' : undefined}>
            {status}
          </Text>
        </Box>
      )
    })

    // one heading per day, so each row keeps just the time and stays on one line
    // mỗi ngày một tiêu đề, để mỗi hàng chỉ giữ giờ và nằm gọn một dòng
    const recent: JSX.Element[] = []
    let lastDay = ''
    for (const j of s.jobs.filter(j => j.endedAt !== undefined).slice(-6).reverse()) {
      const day = dayLabel(j.startedAt, now)
      if (day !== lastDay) recent.push(<Text bold dimColor>{day}</Text>), lastDay = day
      const secs = Math.max(0, Math.round(((j.endedAt ?? j.startedAt) - j.startedAt) / 1000))
      recent.push(
        <Text dimColor>
          {clockLabel(j.startedAt)} {WORKER_NAME[j.worker]} · {j.kind} · {formatSecs(secs)} · {j.ok ? tx('done') : tx('failed')}
        </Text>
      )
    }

    const working = WORKERS.filter(w => workerView(s, w.id, now).state === 'working').map(w => w.name)
    // a broad pane gets the office in one row; a narrow one stacks it
    // khung rộng thì văn phòng nằm trên một hàng; khung hẹp thì xếp chồng
    const cols = (e.props as { bodyColumns?: number } | undefined)?.bodyColumns ?? 0
    const layout = cols >= 110 ? 'wide' : 'tall'
    const alt = working.length ? tx('{title}: {names} working', { title: BRAND.title, names: working.join(', ') }) : tx('{title}: the whole team is idle', { title: BRAND.title })

    return (
      <Box flexDirection="column" gap={1}>
        {'Svg' in ui ? <ui.Svg source={buildOfficeSvg(s, now, layout)} alt={alt} isInteractive /> : <Text>{alt}</Text>}
        <Box flexDirection="column">{rows}</Box>
        <Box flexDirection="column">
          <Text>
            {tx('Tokens this session: {input} in · {cache} from cache · {output} out', { input: shortCount(s.usage?.input ?? 0), cache: shortCount(s.usage?.cacheRead ?? 0), output: shortCount(s.usage?.output ?? 0) })}
            {s.costUsd !== undefined ? ` · ≈ ${formatUsd(s.costUsd)}` : ''}
          </Text>
          {s.context ? (
            <Text color={s.context.percent >= 80 ? 'red' : s.context.percent >= 60 ? 'yellow' : undefined}>
              Context: {s.context.percent}% ({shortCount(s.context.tokens)} / {shortCount(s.context.window)})
              {contextAdvice(s.context.percent) ? ` · ${contextAdvice(s.context.percent)}` : ''}
            </Text>
          ) : null}
          <Text dimColor>{tx('Files Claude edited: {n} times (see details on the web page)', { n: s.edits?.length ?? 0 })}</Text>
        </Box>
        <Box flexDirection="column">
          <Text bold>{tx('Recent tasks')}</Text>
          {recent.length ? recent : <Text dimColor>{tx('No tasks handed off in this session yet.')}</Text>}
        </Box>
      </Box>
    )
  })
}
