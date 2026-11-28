// Delegating from a staff machine without the ai-workers MCP server: the plugin's own tools
// (mcp__ai-worker__ask_local / ask_chatgpt / ask_gemini) run Gemma through Ollama, ChatGPT through
// the Codex CLI (read-only sandbox) and Gemini through the Antigravity CLI (agy), all on this machine;
// a machine too weak for Gemma asks the Gemma of a server it was given the address of.
// Pure helpers here; register.tsx finds the programs and runs them.
// Giao việc từ máy nhân viên không có máy chủ MCP ai-workers: các công cụ riêng của plugin
// (mcp__ai-worker__ask_local / ask_chatgpt / ask_gemini) chạy Gemma qua Ollama, ChatGPT qua
// Codex CLI (sandbox chỉ đọc) và Gemini qua Antigravity CLI (agy), tất cả trên máy này;
// máy quá yếu cho Gemma thì hỏi Gemma của một máy chủ mà nó được cho địa chỉ.
// Ở đây chỉ có các hàm thuần; register.tsx tìm các chương trình và chạy chúng.
import type { WorkerId } from '../types'
import { tx } from './lang'

export const OLLAMA_URL = 'http://127.0.0.1:11434'
/** A worker may take this long before the call gives up (the engine allows ten minutes at most). */
/** Một trợ lý được phép mất chừng này trước khi lệnh gọi bỏ cuộc (engine cho phép tối đa mười phút). */
export const WORKER_TIMEOUT_MS = 9 * 60_000
/** Gemma's context window: room for a long document. */
/** Cửa sổ ngữ cảnh của Gemma: đủ chỗ cho một tài liệu dài. */
export const LOCAL_CTX = 32768

export const LOCAL_GUARD = () =>
  [
    tx('Mandatory rule: rely only on the content given in this request.'),
    tx('Do NOT invent information, reasons, numbers or names that are not in the original text; if information is missing, say clearly that it is missing.'),
    tx('Answer in the language of the request, unless asked otherwise.'),
  ].join(' ') + '\n\n'
export const CHATGPT_GUARD = () =>
  [
    tx('Mandatory rule: work only with the content given in this request.'),
    tx('Do NOT read files on this computer, do NOT run commands, do NOT access the network.'),
    tx('If you are not sure, say clearly that you are not sure.'),
  ].join(' ') + '\n\n'
export const GEMINI_GUARD = () =>
  [
    tx('Mandatory rule: ONLY use your own web search and reading tools.'),
    tx('Do NOT run terminal commands, do NOT create, edit or delete files.'),
    tx('If you are not sure, say clearly that you are not sure.'),
    tx('Give the source URL when you look something up on the web.'),
  ].join(' ') + '\n\n'
export const IMAGE_GUARD = () =>
  [
    tx('Mandatory rule: use the image tool (Nano Banana) to create exactly the number of images asked for (1 image by default).'),
    tx('Do NOT run terminal commands, do NOT search the web, do NOT create, edit or delete any file other than the images.'),
    tx('At the end, print the full path of every image file you created.'),
  ].join(' ') + '\n\n'

/** agy's image tool saves under this folder of the home directory, not in its working folder. */
/** Công cụ tạo ảnh của agy lưu vào thư mục này trong thư mục home, không phải thư mục làm việc của nó. */
export const AGY_BRAIN = '.gemini/antigravity-cli/brain'
/** Where the plugin puts finished images, under the home directory. */
/** Nơi plugin đặt ảnh đã xong, trong thư mục home. */
export const IMAGE_DIR = 'Pictures/AI Worker'
export const IMAGE_EXT = /\.(png|jpe?g|webp)$/i
/** agy sometimes exits before its image subagent has written the file: wait this long for it. */
/** Đôi khi agy thoát trước khi trợ lý con vẽ ảnh ghi xong file: chờ chừng này. */
export const IMAGE_SETTLE_MS = 60_000

/** Level Claude picks by difficulty: ChatGPT changes its reasoning effort, Gemini its Flash tier (the plan offers only Flash). */
/** Mức Claude chọn theo độ khó: ChatGPT đổi mức suy luận, Gemini đổi bậc Flash (gói chỉ có Flash). */
export type Level = 'nhanh' | 'vua' | 'ky'
const LEVELS: Record<Level, { codex: string; agy: string }> = {
  nhanh: { codex: 'low', agy: 'gemini-3.8-flash-low' },
  vua: { codex: 'medium', agy: 'gemini-3.8-flash-medium' },
  ky: { codex: 'high', agy: 'gemini-3.8-flash-high' },
}
export const levelOf = (v: unknown) => LEVELS[(typeof v === 'string' && v in LEVELS ? v : 'vua') as Level]

/**
 * Which helpers this machine can use: the Gemma model's tag and the program paths. `gemmaServer` is the server's name when
 * ask_local goes there first instead of here. `gemmaAlso` is a server a computer that runs Gemma itself may use as well, Claude
 * choosing per task (`where`). `gemmaBackup` says this computer runs Gemma too, so a server that fails is answered for here.
 */
/** Máy này dùng được những trợ lý nào: tag của mô hình Gemma và đường dẫn các chương trình. `gemmaServer` là tên máy chủ khi ask_local gọi tới đó trước thay vì chạy ở đây. `gemmaAlso` là máy chủ mà một máy tự chạy được Gemma cũng dùng thêm được, Claude chọn theo từng việc (`where`). `gemmaBackup` cho biết máy này cũng tự chạy Gemma, nên máy chủ hỏng thì máy này trả lời thay. */
export type OwnWorkers = { gemma?: string; gemmaServer?: string; gemmaAlso?: { host: string; model: string }; gemmaBackup?: boolean; chatgpt?: string; gemini?: string }

/**
 * Whether an MCP config file (Claude Desktop's claude_desktop_config.json, or ~/.claude.json) names the ai-workers
 * server: it may connect after the plugin starts, so its own tools must not be registered meanwhile.
 */
/** File cấu hình MCP (claude_desktop_config.json của Claude Desktop, hoặc ~/.claude.json) có nêu máy chủ ai-workers hay không: nó có thể kết nối sau khi plugin khởi động, nên công cụ riêng của plugin không được đăng ký trong lúc đó. */
export function mcpConfigured(configJson: string): boolean {
  try {
    const c = JSON.parse(configJson) as { mcpServers?: Record<string, unknown>; projects?: Record<string, { mcpServers?: Record<string, unknown> }> }
    const sets = [c.mcpServers, ...Object.values(c.projects ?? {}).map(p => p?.mcpServers)]
    return sets.some(s => !!s && typeof s === 'object' && 'ai-workers' in s)
  } catch {
    return false
  }
}

/** The one Gemma a computer runs itself. A computer too weak for it runs none and asks a server instead: the small sizes are no longer used. */
/** Bản Gemma duy nhất mà một máy tự chạy. Máy quá yếu thì không chạy bản nào mà hỏi máy chủ: các bản nhỏ không còn được dùng. */
export const GEMMA_MODEL = 'gemma4:26b'
/** The Gemma a server runs unless its settings name another model: a server has the room for the larger one. */
/** Bản Gemma mà máy chủ chạy, trừ khi thiết lập của nó nêu mô hình khác: máy chủ đủ chỗ cho bản lớn hơn. */
export const GEMMA_SERVER_MODEL = 'gemma4:31b'

/** GEMMA_MODEL when Ollama's installed models (`/api/tags`) hold it; undefined otherwise, a smaller Gemma included. */
/** GEMMA_MODEL khi các mô hình Ollama đã cài (`/api/tags`) có nó; undefined trong mọi trường hợp khác, kể cả khi chỉ có bản Gemma nhỏ hơn. */
export function pickGemma(tagsJson: string): string | undefined {
  try {
    const models = (JSON.parse(tagsJson) as { models?: { name?: unknown }[] }).models ?? []
    return models.some(m => m.name === GEMMA_MODEL) ? GEMMA_MODEL : undefined
  } catch {
    return undefined
  }
}

/** A server that runs Gemma for computers too weak to: its address, its name for the messages, and a key when it is not the dashboard that checks the computer. */
/** Máy chủ chạy Gemma cho máy quá yếu: địa chỉ, tên để đưa vào thông báo, và một khoá khi bên kiểm máy không phải là bảng tổng. */
export type GemmaServer = { url: string; host: string; model: string; key?: string }

const LOCAL_HOSTS = ['127.0.0.1', 'localhost', '[::1]']

/**
 * The Gemma server in force. Lowest first: the one the company dashboard announced (`board`, https only, see gemmaServerIn), then
 * the package's company.json and this computer's config.js (`open`), then its gemma-server.json (`secret`); the last one set wins, so
 * an address written on this computer always beats the dashboard's. Only https, since the text crosses a network; plain http only to
 * this computer itself. No user:password@ part and no query. The key is read from `secret` alone (gemma-server.json, beside the web
 * folder and not in it), and is never sent to an address the dashboard announced: a key in a file the office page can read is ignored.
 */
/** Máy chủ Gemma đang có hiệu lực. Thấp nhất trước: máy chủ do bảng tổng của công ty báo (`board`, chỉ https, xem gemmaServerIn), rồi company.json của gói và config.js của máy này (`open`), rồi gemma-server.json của nó (`secret`); cái đặt sau cùng thắng, nên địa chỉ ghi trên máy này luôn thắng địa chỉ của bảng tổng. Chỉ https, vì chữ đi qua mạng; http thường chỉ tới chính máy này. Không có phần user:password@ và không có query. Khoá chỉ đọc từ `secret` (gemma-server.json, nằm cạnh thư mục web chứ không ở trong), và không bao giờ gửi tới địa chỉ do bảng tổng báo: khoá nằm trong file mà trang văn phòng đọc được thì bị bỏ qua. */
export function readGemmaServer(open: unknown[], secret?: unknown, board?: unknown): GemmaServer | undefined {
  const obj = (v: unknown) => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {})
  let found: GemmaServer | undefined
  let announced = false
  const sources: [unknown, boolean][] = [[board, true], ...open.map((x): [unknown, boolean] => [x, false]), [secret, false]]
  for (const [source, fromBoard] of sources) {
    const raw = obj(source).url
    if (typeof raw !== 'string' || !raw.trim()) continue
    const m = /^(https?):\/\/([a-z0-9.-]+|\[[0-9a-f:]+\])(:\d{1,5})?(\/[^\s?#@\\]*)?$/i.exec(raw.trim())
    if (!m) continue
    const host = (m[2] ?? '').toLowerCase()
    const scheme = (m[1] ?? '').toLowerCase()
    if (scheme === 'http' && (fromBoard || !LOCAL_HOSTS.includes(host))) continue
    // the model beside the address, when the server runs another one than GEMMA_SERVER_MODEL
    // mô hình ghi cạnh địa chỉ, khi máy chủ chạy bản khác GEMMA_SERVER_MODEL
    const model = obj(source).model
    found = { url: raw.trim().replace(/\/+$/, ''), host, model: typeof model === 'string' && /^[a-z0-9][a-z0-9._:-]{0,59}$/i.test(model.trim()) ? model.trim() : GEMMA_SERVER_MODEL }
    announced = fromBoard
  }
  const key = obj(secret).key
  if (found && !announced && typeof key === 'string' && /^[\x21-\x7e]{16,200}$/.test(key.trim())) found.key = key.trim()
  return found
}

/**
 * The Gemma server in the answer to a send: an object to keep, null when the dashboard took it away, undefined when the answer
 * says nothing (an older dashboard, or the Go receiver), which keeps what is held.
 */
/** Máy chủ Gemma trong câu trả lời cho một lần gửi: một đối tượng để giữ, null khi bảng tổng đã bỏ nó, undefined khi câu trả lời không nói gì (bảng tổng cũ hơn, hoặc bộ nhận Go), khi đó giữ cái đang có. */
export function gemmaServerIn(answer: string): { url: string; model?: string } | null | undefined {
  let g: unknown
  try {
    const d = JSON.parse(answer) as Record<string, unknown>
    if (!d || typeof d !== 'object' || !('gemmaServer' in d)) return undefined
    g = d.gemmaServer
  } catch {
    return undefined
  }
  if (g === null) return null
  const server = readGemmaServer([], undefined, g)
  if (!server) return undefined
  const model = (g as { model?: unknown }).model
  return { url: server.url, ...(typeof model === 'string' && model === server.model ? { model } : {}) }
}

/**
 * Where Gemma runs for this computer. `local` is what its own Ollama says now: it has GEMMA_MODEL, it answers without it, or it does
 * not answer. A computer that has run Gemma itself (`ranHere`) and whose Ollama is merely off stays 'here', and the call says to
 * open Ollama: switching to the server by itself would send sensitive text off the computer without the person knowing.
 */
/** Gemma chạy ở đâu cho máy này. `local` là điều Ollama của chính máy nói lúc này: có GEMMA_MODEL, trả lời nhưng không có nó, hoặc không trả lời. Máy đã từng tự chạy Gemma (`ranHere`) mà Ollama chỉ đang tắt thì vẫn là 'here', và lệnh gọi sẽ bảo mở Ollama: tự chuyển sang máy chủ là gửi chữ nhạy cảm ra khỏi máy mà người dùng không biết. */
export function gemmaPlace(local: 'has' | 'lacks' | 'off', ranHere: boolean, server: GemmaServer | undefined): 'here' | 'server' | 'none' {
  if (local === 'has' || (local === 'off' && ranHere)) return 'here'
  return server ? 'server' : 'none'
}

/** How a computer that runs Gemma itself uses a Gemma server it was also given: Claude picks per task, never the server, or the server first. */
/** Máy tự chạy được Gemma dùng máy chủ Gemma được cho thêm như thế nào: Claude chọn theo từng việc, không bao giờ dùng máy chủ, hoặc máy chủ trước. */
export type GemmaMode = 'auto' | 'here' | 'server'
export const readGemmaMode = (v: unknown): GemmaMode => (v === 'here' || v === 'server' ? v : 'auto')

/** After the server fails once, a computer that can answer itself does so for this long before trying the server again. */
/** Sau một lần máy chủ hỏng, máy tự trả lời được sẽ tự làm trong chừng này rồi mới thử lại máy chủ. */
export const GEMMA_REST_MS = 5 * 60_000

/**
 * Gemma for this computer, from what its Ollama says, whether it ran Gemma before, the server it was given and the mode in
 * config.js (`gemmaMode`). A computer that runs Gemma itself and has a server too gets both, Claude choosing per task; set to
 * 'server' it asks the server first and answers itself when the server fails. A computer that cannot run Gemma has the server
 * alone, with nothing to fall back on.
 */
/** Gemma cho máy này, từ điều Ollama của nó nói, việc nó đã từng tự chạy Gemma chưa, máy chủ được cho và chế độ trong config.js (`gemmaMode`). Máy tự chạy được Gemma mà có cả máy chủ thì được cả hai, Claude chọn theo từng việc; đặt 'server' thì nó hỏi máy chủ trước và tự trả lời khi máy chủ hỏng. Máy không tự chạy được Gemma thì chỉ có máy chủ, không có đường lui. */
export function gemmaWorkers(local: 'has' | 'lacks' | 'off', ranHere: boolean, server: GemmaServer | undefined, mode: GemmaMode): OwnWorkers {
  const place = gemmaPlace(local, ranHere, server)
  if (place === 'none') return {}
  if (place === 'server' && server) return { gemma: server.model, gemmaServer: server.host }
  if (!server || mode === 'here') return { gemma: GEMMA_MODEL }
  if (mode === 'server') return { gemma: server.model, gemmaServer: server.host, gemmaBackup: true }
  return { gemma: GEMMA_MODEL, gemmaAlso: { host: server.host, model: server.model } }
}

/** Where one call of ask_local goes: the server when that is this computer's Gemma, or when Claude asked for it on a computer that has both. */
/** Một lệnh gọi ask_local đi tới đâu: máy chủ khi đó là Gemma của máy này, hoặc khi Claude yêu cầu trên máy có cả hai. */
export const gemmaTarget = (own: OwnWorkers, where: unknown): 'here' | 'server' => (own.gemmaServer || (own.gemmaAlso && where === 'server') ? 'server' : 'here')

/** Whether this computer can answer itself when the server fails. The text then never leaves it, so nobody needs to be asked. */
/** Máy này có tự trả lời được khi máy chủ hỏng không. Khi đó chữ không rời máy, nên không cần hỏi ai. */
export const gemmaFallsBack = (own: OwnWorkers) => !!own.gemmaAlso || !!own.gemmaBackup

/** The answer given here in place of the server's, opening with one line that says so and why. */
/** Câu trả lời do máy này đưa ra thay cho máy chủ, mở đầu bằng một dòng nói rõ điều đó và lý do. */
export function gemmaFellBack(why: string, local: { text: string; isError: boolean }): { text: string; isError: boolean } {
  if (local.isError) return { text: `${why}\n${tx('Gemma on this computer could not answer either:')} ${local.text}`, isError: true }
  return { text: `${tx('[Answered by Gemma on this computer ({model}), not by the server.]', { model: GEMMA_MODEL })} ${why}\n\n${local.text}`, isError: false }
}

/** What a computer says of its Gemma to the dashboard: the model, marked when it runs on a server. No address. */
/** Điều một máy nói với bảng tổng về Gemma của nó: mô hình, có đánh dấu khi chạy trên máy chủ. Không có địa chỉ. */
export const gemmaLabel = (own: OwnWorkers) => (own.gemma ? (own.gemmaServer ? `${own.gemma} (server)` : own.gemma) : undefined)

/** curl's arguments for asking Gemma on a server: the key from a file (a command line can be read by any process), the HTTP code on a last line of its own. */
/** Tham số của curl để hỏi Gemma trên máy chủ: khoá lấy từ file (dòng lệnh thì tiến trình nào cũng đọc được), mã HTTP nằm riêng ở dòng cuối. */
export function gemmaServerArgv(server: GemmaServer, headerFile: string, seconds: number): string[] {
  return ['curl', '-s', '-m', String(seconds), '-H', `@${headerFile}`, '-H', 'Content-Type: application/json', '-w', '\n%{http_code}', `${server.url}/api/chat`, '-d', '@-']
}

/** The server's answer (curl's output ending in the HTTP code) as Gemma's answer, or what went wrong in words the person can act on. */
/** Câu trả lời của máy chủ (đầu ra của curl, kết thúc bằng mã HTTP) thành câu trả lời của Gemma, hoặc lỗi nói bằng lời để người dùng biết làm gì. */
export function gemmaServerAnswer(stdout: string, host: string): { text: string; isError: boolean } {
  const cut = stdout.lastIndexOf('\n')
  const code = Number(stdout.slice(cut + 1).trim()) || 0
  const body = cut < 0 ? '' : stdout.slice(0, cut)
  if (code === 401 || code === 403)
    return { text: tx('The Gemma server {host} refused this computer: it is not allowed to use Gemma there (or not from this network). Ask your admin. Nothing was processed; Claude can do this work itself.', { host }), isError: true }
  if (code === 503 || code === 429)
    return { text: tx('The Gemma server {host} is busy right now. Try again in a few minutes, or Claude can do this work itself.', { host }), isError: true }
  if (code === 0)
    return { text: tx('Could not reach the Gemma server {host} (it is off, the network is down, or it took too long). Try again later, or Claude can do this work itself.', { host }), isError: true }
  const g = gemmaAnswer(body)
  return g.isError && !/"error"/.test(body) ? { text: tx('The Gemma server {host} gave no usable answer (code {code}). Tell your admin.', { host, code }), isError: true } : g
}

/**
 * The JSON body for Ollama's /api/chat. Thinking is off: Gemma 4 would otherwise first write an outline in English that nobody
 * reads, which takes about as long as the answer; for summarizing and sorting it adds little. Ollama ignores the field for a
 * model that cannot think.
 */
/** Phần thân JSON cho /api/chat của Ollama. Tắt chế độ suy nghĩ: nếu không Gemma 4 sẽ viết trước một dàn ý bằng tiếng Anh mà không ai đọc, tốn thời gian gần bằng câu trả lời; với việc tóm tắt và phân loại thì nó ít giúp. Ollama bỏ qua trường này với mô hình không có chế độ suy nghĩ. */
export function gemmaRequest(model: string, prompt: string): string {
  return JSON.stringify({
    model,
    stream: false,
    think: false,
    messages: [{ role: 'user', content: LOCAL_GUARD() + prompt }],
    options: { num_ctx: LOCAL_CTX },
  })
}

/** Gemma's answer from Ollama's reply, or an error in words. */
/** Câu trả lời của Gemma từ phản hồi của Ollama, hoặc một lỗi bằng lời. */
export function gemmaAnswer(reply: string): { text: string; isError: boolean } {
  try {
    const r = JSON.parse(reply) as { message?: { content?: unknown }; error?: unknown }
    if (typeof r.message?.content === 'string' && r.message.content.trim()) return { text: r.message.content.trim(), isError: false }
    if (typeof r.error === 'string') return { text: tx('Gemma reported an error: {error}', { error: r.error }), isError: true }
  } catch {
    // not JSON: Ollama not running, or cut off
    // không phải JSON: Ollama không chạy, hoặc bị cắt ngang
  }
  return { text: tx('Gemma did not answer: Ollama on this computer is not running, or it timed out. Open Ollama and try again.'), isError: true }
}

/** Codex in a read-only sandbox, its last message written to `outFile`. The text goes through stdin (`codexInput`): a Windows .cmd launcher starts through cmd, which would run commands hidden in an argument. */
/** Codex trong sandbox chỉ đọc, tin nhắn cuối của nó ghi vào `outFile`. Chữ đi qua stdin (`codexInput`): bộ khởi chạy .cmd của Windows chạy qua cmd, và cmd sẽ chạy lệnh giấu trong tham số. */
export function codexArgv(codex: string, outFile: string, level?: unknown): string[] {
  return [
    codex, 'exec', '--ignore-user-config', '-c', `model_reasoning_effort="${levelOf(level).codex}"`,
    '-s', 'read-only', '--skip-git-repo-check', '--ephemeral', '--color', 'never', '-o', outFile, '-',
  ]
}

export const codexInput = (prompt: string) => CHATGPT_GUARD() + prompt

/** A Windows .cmd or .bat launcher: it starts through cmd, so free text must never be one of its arguments. */
/** Bộ khởi chạy .cmd hoặc .bat của Windows: nó chạy qua cmd, nên chữ tự do không bao giờ được làm tham số của nó. */
export const isBatchLauncher = (program: string) => /\.(cmd|bat)$/i.test(program)

/** agy takes its text only as an argument, so register.tsx refuses to run it through a batch launcher. */
/** agy chỉ nhận chữ qua tham số, nên register.tsx từ chối chạy nó qua bộ khởi chạy batch. */
export function agyArgv(agy: string, prompt: string, level?: unknown): string[] {
  return [agy, '-p', GEMINI_GUARD() + prompt, '--model', levelOf(level).agy]
}

/** agy asked for an image: Gemini picks its own image model, so no level here. */
/** agy được nhờ vẽ ảnh: Gemini tự chọn mô hình ảnh, nên không có mức ở đây. */
export function imageArgv(agy: string, prompt: string): string[] {
  return [agy, '-p', IMAGE_GUARD() + prompt]
}

/** A file name the user asked for, safe to use: letters, digits, dot, dash, underscore; '' when nothing is left. */
/** Tên file người dùng yêu cầu, đã làm sạch để dùng được: chữ, số, dấu chấm, gạch ngang, gạch dưới; '' khi không còn gì. */
export function safeImageName(v: unknown): string {
  return String(typeof v === 'string' ? v : '')
    .trim()
    .replace(/\.(png|jpe?g|webp)$/i, '')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/\.{2,}/g, '-')
    .replace(/^[.-]+/, '')
    .slice(0, 80)
}

/** The images in a listing made at or after `since`, oldest first: the last one is Gemini's final answer, earlier ones drafts. */
/** Các ảnh trong một danh sách lập từ lúc `since` trở đi, cũ nhất trước: ảnh cuối là bản chốt của Gemini, các ảnh trước là bản nháp. */
export function newImages(files: { path: string; mtimeMs: number }[], since: number, taken: Set<string>): string[] {
  return files
    .filter(f => IMAGE_EXT.test(f.path) && f.mtimeMs >= since && !taken.has(f.path))
    .sort((a, b) => a.mtimeMs - b.mtimeMs)
    .map(f => f.path)
}

/** Where each image is copied: the final one under the asked name (or its own), drafts with -draft-N; never over an existing file. */
/** Mỗi ảnh được chép tới đâu: bản chốt mang tên được yêu cầu (hoặc tên của nó), bản nháp thêm -draft-N; không bao giờ đè lên file có sẵn. */
export function imageTargets(images: string[], dir: string, name: string, exists: (p: string) => boolean): string[] {
  const used = new Set<string>()
  const free = (stem: string, ext: string) => {
    let p = `${dir}/${stem}${ext}`
    for (let n = 2; exists(p) || used.has(p); n++) p = `${dir}/${stem}-${n}${ext}`
    used.add(p)
    return p
  }
  return images.map((src, i) => {
    const base = src.split(/[\\/]/).pop() ?? 'image.png'
    const ext = (/\.[^.]+$/.exec(base)?.[0] ?? '.png').toLowerCase()
    const stem = name || base.slice(0, base.length - ext.length)
    return free(i === images.length - 1 ? stem : `${stem}-draft-${i + 1}`, ext)
  })
}

/** The tools to register, one per helper this machine has. */
/** Các công cụ cần đăng ký, mỗi trợ lý mà máy này có một công cụ. */
export type OwnTool = { name: string; worker: WorkerId; description: string; inputSchema: typeof PROMPT_SCHEMA | typeof PROMPT_WHERE_SCHEMA | typeof PROMPT_LEVEL_SCHEMA | typeof IMAGE_SCHEMA }
export function ownTools(own: OwnWorkers): OwnTool[] {
  const tools: OwnTool[] = []
  if (own.gemma)
    tools.push({
      name: 'ask_local',
      worker: 'gemma',
      inputSchema: own.gemmaAlso ? PROMPT_WHERE_SCHEMA : PROMPT_SCHEMA,
      description:
        [
          own.gemmaAlso
            ? tx('Hand work to Gemma. By default ({model}) it runs right on this computer through Ollama and the data does NOT leave the computer. With where "server" it runs on the server {host} ({serverModel}) instead: the text then leaves this computer and the user is asked before the send; if the server fails, Gemma on this computer answers and the answer says so.', { model: own.gemma, host: own.gemmaAlso.host, serverModel: own.gemmaAlso.model })
            : own.gemmaServer
            ? tx('Hand work to Gemma ({model}), which runs on the server {host}, NOT on this computer: the text leaves this computer for that server, and the user is asked before each send.', { model: own.gemma, host: own.gemmaServer })
            : tx('Hand work to Gemma ({model}), which runs right on this computer through Ollama: the data does NOT leave the computer.', { model: own.gemma }),
          tx('Use it for summarizing, sorting, extracting information, and anonymizing internal documents or documents with people names.'),
          tx('Paste the exact text to process into the prompt. It can take a few minutes.'),
        ].join(' '),
    })
  if (own.chatgpt)
    tools.push({
      name: 'ask_chatgpt',
      worker: 'chatgpt',
      inputSchema: PROMPT_LEVEL_SCHEMA,
      description:
        [
          tx('Ask ChatGPT through the Codex CLI (read-only mode, no web lookup): code review, finding bugs, suggesting tests, critiquing a technical design.'),
          tx('What you send goes to OpenAI: do NOT send names or personal information, internal documents, company figures, passwords/API keys/.env, internal domains/IPs.'),
          tx('Paste the exact code to review into the prompt. It can take a few minutes.'),
        ].join(' '),
    })
  if (own.gemini)
    tools.push({
      name: 'ask_gemini',
      worker: 'gemini',
      inputSchema: PROMPT_LEVEL_SCHEMA,
      description:
        [
          tx('Ask Gemini through the Antigravity CLI (the free Google account of the user): web research from many sources, recent information.'),
          tx('Send ONLY general knowledge questions: do NOT send code, documents, figures or people names of the company. It can take a few minutes.'),
        ].join(' '),
    })
  if (own.gemini)
    tools.push({
      name: 'generate_image',
      worker: 'gemini',
      inputSchema: IMAGE_SCHEMA,
      description:
        [
          tx('Ask Gemini to create an image with Nano Banana (through the Antigravity CLI) and save it in the folder ~/{dir}. Returns the path of the image file.', { dir: IMAGE_DIR }),
          tx('Use it for illustrations, icons, images for slides/posts/documents, simple mockups.'),
          tx('What you send goes to Google: do NOT include names, photos or information of real people, documents, figures, or unpublished internal logos.'),
          tx('Describe it concretely: subject, style, colors, layout, background, aspect ratio, text on the image (give it verbatim, or say "no text").'),
          tx('Once you have the image, open it to check it matches the description and the text is spelled correctly before reporting; say clearly the image was made by Nano Banana. Each image takes about 30-80 seconds.'),
        ].join(' '),
    })
  return tools
}

const PROMPT_FIELD = {
  type: 'string',
  get description() {
    return tx('The task, with enough background (the assistant cannot see the conversation), including the exact text to process.')
  },
} as const

/** Gemma takes a prompt; ChatGPT and Gemini also take a level by difficulty. */
/** Gemma nhận một lời nhắc; ChatGPT và Gemini còn nhận thêm một mức theo độ khó. */
export const PROMPT_SCHEMA = { type: 'object', properties: { prompt: PROMPT_FIELD }, required: ['prompt'] } as const
/** On a computer that runs Gemma itself and has a Gemma server too, Claude also says where this task runs. */
/** Trên máy tự chạy được Gemma mà có cả máy chủ Gemma, Claude nói thêm việc này chạy ở đâu. */
export const PROMPT_WHERE_SCHEMA = {
  type: 'object',
  properties: {
    prompt: PROMPT_FIELD,
    where: {
      type: 'string',
      enum: ['here', 'server'],
      get description() {
        return [
          tx('Where Gemma runs for this task (default here). here: anything with sensitive data (people names, internal documents, company figures), short tasks, and whenever you are not sure the text is free of sensitive data.'),
          tx('server: only text with NO sensitive data that is long, needs more care, or comes as a batch.'),
        ].join(' ')
      },
    },
  },
  required: ['prompt'],
} as const
export const PROMPT_LEVEL_SCHEMA = {
  type: 'object',
  properties: {
    prompt: PROMPT_FIELD,
    level: {
      type: 'string',
      enum: ['nhanh', 'vua', 'ky'],
      get description() {
        return [
          tx('Level by difficulty (default vua). nhanh: short question, one quick lookup. vua: most work.'),
          tx('ky: long code review, hard bugs, critique of an important design or plan, multi-step research. A higher level costs more quota and time.'),
        ].join(' ')
      },
    },
  },
  required: ['prompt'],
} as const

export const IMAGE_SCHEMA = {
  type: 'object',
  properties: {
    prompt: {
      type: 'string',
      get description() {
        return tx('The description of the image to create, written in full because Gemini cannot see the conversation.')
      },
    },
    file_name: {
      type: 'string',
      get description() {
        return tx('Wanted file name, without the extension (for example: course-banner). By default the name Gemini chose is kept.')
      },
    },
  },
  required: ['prompt'],
} as const

/** The system-prompt section telling Claude when to hand work to which helper. */
/** Phần của lời nhắc hệ thống nói cho Claude biết khi nào giao việc cho trợ lý nào. */
export function delegationRules(own: OwnWorkers): string | undefined {
  const lines: string[] = []
  if (own.gemma && own.gemmaAlso)
    lines.push(
      tx('- Gemma on this computer (tool ask_local, {model}): work with sensitive data (people names, internal documents, company figures) that needs summarizing, sorting or extracting information, and short tasks. The data does not leave the computer.', { model: own.gemma }),
      tx('- Gemma on the server {host} (tool ask_local with where "server", {model}): only text with NO sensitive data that is long, needs more care, or comes as a batch. The text leaves this computer and the user is asked before each send. When you are not sure the text is free of sensitive data, treat it as sensitive and keep it on this computer.', { host: own.gemmaAlso.host, model: own.gemmaAlso.model }) +
        ' ' +
        tx('If the server fails, Gemma on this computer answers instead and the answer opens with a line saying so: pass that on to the user.') +
        ' ' +
        tx('Gemma is weaker than Claude and may invent details: check its result against the original text before using it.'),
    )
  else if (own.gemma)
    lines.push(
      (own.gemmaServer
        ? tx('- Gemma (tool ask_local, {model}, runs on the server {host}, not on this computer): work with sensitive data (people names, internal documents, company figures) that needs summarizing, sorting or extracting information.', { model: own.gemma, host: own.gemmaServer }) +
          ' ' +
          tx('The text leaves this computer for that server and the user is asked before each send: say so when you propose it, and never send passwords, keys or tokens.')
        : tx('- Gemma (tool ask_local, {model}, runs on this computer): work with sensitive data (people names, internal documents, company figures) that needs summarizing, sorting or extracting information.', { model: own.gemma })) +
        ' ' +
        tx('Gemma is weaker than Claude and may invent details: check its result against the original text before using it.'),
    )
  if (own.chatgpt)
    lines.push(
      tx('- ChatGPT (ask_chatgpt): code review, finding bugs, suggesting test cases. Send only code or technical questions with no private data; remove passwords, keys and internal domains/IPs before sending.') +
        ' ' +
        tx('When ChatGPT reports a bug, read the code again to check it; do not trust it right away.'),
    )
  if (own.gemini) {
    lines.push(tx('- Gemini (ask_gemini): web research that needs many sources, or very recent information. Send only general questions, nothing from the company.'))
    lines.push(tx('- Gemini drawing images (generate_image, Nano Banana): when the user needs an illustration, icon or slide image. Describe it with no real people, data or internal logos; once you have the image, open it and check it before handing it over.'))
  }
  if (own.chatgpt || own.gemini)
    lines.push(tx('- When delegating to ChatGPT or Gemini, choose muc by difficulty: nhanh for short questions, vua for most work, ky for long code reviews, hard bugs, design critique, multi-step research.'))
  if (!lines.length) return undefined
  return [
    tx('# Delegating to AI assistants on this computer'),
    tx('Claude does the main part itself; delegate side work only when it fits, and always tell the user which part was done by whom.'),
    ...lines,
    own.gemma
      ? tx('Never send to ChatGPT or Gemini: names or personal information, internal documents, unpublished company figures, passwords/API keys/tokens/.env files, internal domains/IPs. Work that needs that data goes to Gemma, or Claude does it itself.')
      : tx('Never send to ChatGPT or Gemini: names or personal information, internal documents, unpublished company figures, passwords/API keys/tokens/.env files, internal domains/IPs. This computer has no Gemma, so Claude does work that needs that data itself.'),
    tx('Write prompts for the assistants with enough background (they cannot see the conversation) and paste the exact text to look at; do not tell them to read files on this computer.'),
  ].join('\n')
}

// Text for ChatGPT or Gemini leaves this computer, so the person is asked unless a rule of theirs allows this very tool.
// A permission mode that asks nothing ("allow" with no rule behind it) does not count: the person chose not to be asked
// about commands, not to send their text out. Gemma on this computer stays here and is never asked about; Gemma on a server
// is asked about like the other two (register.tsx names it as the worker).
// Chữ gửi cho ChatGPT hay Gemini rời khỏi máy này, nên người dùng được hỏi, trừ khi một quy tắc của họ cho phép đúng công cụ này.
// Chế độ quyền không hỏi gì ("allow" mà không có quy tắc nào đứng sau) thì không tính: người dùng chọn không bị hỏi
// về các lệnh, chứ không chọn gửi chữ của mình ra ngoài. Gemma trên máy này ở lại đây và không bao giờ bị hỏi; Gemma trên máy chủ
// thì bị hỏi như hai trợ lý kia (register.tsx nêu nó là trợ lý nhận).
export function sendingNeedsAsking(decision: 'allow' | 'ask' | 'deny', worker: string | undefined, byRule = false): boolean {
  return worker !== undefined && (decision === 'ask' || (decision === 'allow' && !byRule))
}

/** Why a call is refused, or undefined to go ahead. A question that fails or gets no answer counts as no. */
/** Lý do từ chối một lệnh gọi, hoặc undefined để chạy tiếp. Câu hỏi lỗi hoặc không được trả lời thì tính là không. */
export function sendingRefusal(decision: 'allow' | 'ask' | 'deny', answer: string | undefined, yes: string): string | undefined {
  if (decision === 'deny') return tx('Your permission settings do not allow this.')
  if (answer !== undefined && answer !== yes) return tx('The user chose not to send this.')
  return undefined
}
