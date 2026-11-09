// Delegating from a staff machine without the ai-workers MCP server: the plugin's own tools
// (mcp__ai-worker__ask_local / ask_chatgpt / ask_gemini) run Gemma through Ollama, ChatGPT through
// the Codex CLI (read-only sandbox) and Gemini through the Antigravity CLI (agy), all on this machine.
// Pure helpers here; register.tsx finds the programs and runs them.
// Giao việc từ máy nhân viên không có máy chủ MCP ai-workers: các công cụ riêng của plugin
// (mcp__ai-worker__ask_local / ask_chatgpt / ask_gemini) chạy Gemma qua Ollama, ChatGPT qua
// Codex CLI (sandbox chỉ đọc) và Gemini qua Antigravity CLI (agy), tất cả trên máy này.
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

/** Which helpers this machine can run: the Gemma model's tag, and the program paths. */
/** Máy này chạy được những trợ lý nào: tag của mô hình Gemma, và đường dẫn các chương trình. */
export type OwnWorkers = { gemma?: string; chatgpt?: string; gemini?: string }

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

/** Gemma sizes, largest first: a machine runs the largest it has pulled. */
/** Các cỡ Gemma, lớn nhất trước: máy chạy cỡ lớn nhất mà nó đã tải. */
const GEMMA_ORDER = ['31b', '26b', '12b', 'e4b', 'e2b']

/** The Gemma model to use among Ollama's installed models (`/api/tags`); undefined when none is a Gemma. */
/** Mô hình Gemma cần dùng trong các mô hình Ollama đã cài (`/api/tags`); undefined khi không có cái nào là Gemma. */
export function pickGemma(tagsJson: string): string | undefined {
  let names: string[] = []
  try {
    const models = (JSON.parse(tagsJson) as { models?: { name?: unknown }[] }).models ?? []
    names = models.map(m => (typeof m.name === 'string' ? m.name : '')).filter(n => /^gemma/i.test(n))
  } catch {
    return undefined
  }
  if (!names.length) return undefined
  const rank = (n: string) => {
    const i = GEMMA_ORDER.findIndex(size => n.includes(`:${size}`))
    return i < 0 ? GEMMA_ORDER.length : i
  }
  return [...names].sort((a, b) => rank(a) - rank(b))[0]
}

/** The JSON body for Ollama's /api/chat. */
/** Phần thân JSON cho /api/chat của Ollama. */
export function gemmaRequest(model: string, prompt: string): string {
  return JSON.stringify({
    model,
    stream: false,
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
  return { text: tx('Gemma did not answer (Ollama is not running or it timed out).'), isError: true }
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
export type OwnTool = { name: string; worker: WorkerId; description: string; inputSchema: typeof PROMPT_SCHEMA | typeof PROMPT_LEVEL_SCHEMA | typeof IMAGE_SCHEMA }
export function ownTools(own: OwnWorkers): OwnTool[] {
  const tools: OwnTool[] = []
  if (own.gemma)
    tools.push({
      name: 'ask_local',
      worker: 'gemma',
      inputSchema: PROMPT_SCHEMA,
      description:
        [
          tx('Hand work to Gemma ({model}), which runs right on this computer through Ollama: the data does NOT leave the computer.', { model: own.gemma }),
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
  if (own.gemma)
    lines.push(
      tx('- Gemma (tool ask_local, {model}, runs on this computer): work with sensitive data (people names, internal documents, company figures) that needs summarizing, sorting or extracting information.', { model: own.gemma }) +
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
    tx('Never send to ChatGPT or Gemini: names or personal information, internal documents, unpublished company figures, passwords/API keys/tokens/.env files, internal domains/IPs. Work that needs that data goes to Gemma, or Claude does it itself.'),
    tx('Write prompts for the assistants with enough background (they cannot see the conversation) and paste the exact text to look at; do not tell them to read files on this computer.'),
  ].join('\n')
}

/** Text for ChatGPT or Gemini leaves this computer: anything short of a clear allow goes to the person. Gemma stays here. */
/** Chữ gửi cho ChatGPT hay Gemini rời khỏi máy này: chưa được cho phép rõ ràng thì hỏi người dùng. Gemma ở lại trên máy. */
export function sendingNeedsAsking(decision: 'allow' | 'ask' | 'deny', worker: string | undefined): boolean {
  return decision === 'ask' && worker !== undefined
}

/** Why a call is refused, or undefined to go ahead. A question that fails or gets no answer counts as no. */
/** Lý do từ chối một lệnh gọi, hoặc undefined để chạy tiếp. Câu hỏi lỗi hoặc không được trả lời thì tính là không. */
export function sendingRefusal(decision: 'allow' | 'ask' | 'deny', answer: string | undefined, yes: string): string | undefined {
  if (decision === 'deny') return tx('Your permission settings do not allow this.')
  if (answer !== undefined && answer !== yes) return tx('The user chose not to send this.')
  return undefined
}
