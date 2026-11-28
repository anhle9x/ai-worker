import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'

type Engine = Parameters<TestBody>[0]

const TAGS = JSON.stringify({ models: [{ name: 'gemma4:26b' }] })
const SMALL = JSON.stringify({ models: [{ name: 'gemma4:e4b' }] })
const KEY = 'awd1.this-computers-own-key'

type Setup = {
  /** What this computer's own Ollama answers to /api/tags; undefined when it is off. */
  /** Ollama của chính máy này trả lời gì cho /api/tags; undefined khi nó đang tắt. */
  tags?: string
  /** The Gemma server written in this computer's config.js. */
  /** Máy chủ Gemma ghi trong config.js của máy này. */
  server?: string
  answer?: string
  /** `gemmaMode` in this computer's config.js. */
  /** `gemmaMode` trong config.js của máy này. */
  mode?: string
  /** What curl prints for a call to the Gemma server, in place of an answer: '\n000' is a server that cannot be reached. */
  /** curl in ra gì cho một lệnh gọi tới máy chủ Gemma, thay cho câu trả lời: '\n000' là máy chủ không tới được. */
  serverSays?: string
  /** Ollama on this computer does not answer a call. */
  /** Ollama trên máy này không trả lời lệnh gọi. */
  hereFails?: boolean
  /** This computer shares its numbers with the company dashboard. */
  /** Máy này gửi số liệu lên bảng tổng của công ty. */
  sharing?: boolean
  /** What the plugin's store already holds. */
  /** Kho của plugin đã có sẵn những gì. */
  kept?: Record<string, unknown>
}

/** A staff computer with no ChatGPT and no Gemini: returns the questions put to the person, each curl sent to a Gemma, and what the key file held. */
/** Một máy nhân viên không có ChatGPT, không có Gemini: trả về các câu hỏi đưa cho người dùng, từng lệnh curl gửi tới Gemma, và file khoá đã chứa gì. */
function computer(on: On, s: Setup) {
  const seen = { asked: [] as string[], curls: [] as string[][], headers: [] as string[], models: [] as unknown[], tools: [] as { name: string; description: string }[] }
  const clock = mock.clock(on)
  mock.store(on, s.kept ?? {})
  mock.env(on, { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.exists', () => ({ value: false }))
  on('fs.write', (_, e) => {
    if (/gemma-\d+\.txt$/.test(e.path)) seen.headers.push(e.text)
    return { value: undefined }
  })
  on('fs.list', () => ({ value: [] }) as never)
  on('fs.read', (_, e) => {
    if ((s.server || s.sharing) && e.path === '/Users/an/.local/share/ai-worker/config.js')
      return { value: `window.__aiWorkerConfig = ${JSON.stringify({ ...(s.server ? { gemmaServer: { url: s.server } } : {}), ...(s.mode ? { gemmaMode: s.mode } : {}), ...(s.sharing ? { sharing: { enabled: true, webhook: 'https://aiworker.example.com', ingestKey: 'k'.repeat(32) } } : {}) })};` }
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('http.fetch', (_, e) => {
    if (s.tags !== undefined && e.url === 'http://127.0.0.1:11434/api/tags') return { value: { ok: true, status: 200, headers: {}, text: s.tags } }
    return { value: { ok: false, status: 0, headers: {}, text: '' } }
  })
  on('tool.register', (_, e) => {
    const t = e as unknown as { name: string; description: string }
    seen.tools.push({ name: t.name, description: t.description })
    return { value: { tool: t.name } }
  })
  on('process.run', (_, e) => {
    const out = (exitCode: number, stdout = '') => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (e.argv[0] === 'uname') return out(0, 'Darwin\n')
    if (e.argv[0] === 'curl' && e.argv.some(a => a.endsWith('/api/chat'))) {
      seen.curls.push([...e.argv])
      seen.models.push(JSON.parse(e.init?.stdin ?? '{}').model)
      const reply = '{"message":{"content":"a summary from Gemma"}}'
      if (e.argv.includes('-w')) return out(0, s.serverSays ?? `${reply.replace('Gemma', 'the server')}\n200`)
      return s.hereFails ? out(7) : out(0, reply)
    }
    return out(1)
  })
  on('tool.check', () => ({ decision: 'allow' }) as never)
  on('tool.call', (_, e) => {
    const call = e as unknown as { tool: string; questions?: { question: string }[] }
    if (call.tool !== 'AskUserQuestion') return { result: 'not the plugin' } as never
    const question = call.questions![0]!.question
    seen.asked.push(question)
    if (s.answer === undefined) throw new Error('dismissed')
    return { result: { questions: call.questions, answers: { [question]: s.answer } } } as never
  })
  return Object.assign(seen, { clock, set: (next: Partial<Setup>) => Object.assign(s, next) })
}

const start = ($: Engine) => $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
const ask = async ($: Engine, prompt = 'summarise the notes on Lan and Minh', where?: string) =>
  (await $.tool.call({ tool: 'mcp__ai-worker__ask_local', prompt, ...(where ? { where } : {}) } as never)) as unknown as { result: string; isError: boolean }
const target = (argv: string[]) => argv.find(a => a.endsWith('/api/chat'))

test('a computer that has gemma4:26b runs Gemma itself, even with a Gemma server set, and nobody is asked', async ($, on) => {
  const seen = computer(on, { tags: TAGS, server: 'https://gemma.example.com' })
  await start($)
  expect(seen.tools.find(t => t.name === 'ask_local')?.description).toContain('does NOT leave the computer')
  const r = await ask($)
  expect(r.result).toBe('a summary from Gemma')
  expect(seen.curls.map(target)).toEqual(['http://127.0.0.1:11434/api/chat'])
  expect(seen.asked).toEqual([])
  expect(seen.headers).toEqual([])
  expect(seen.models).toEqual(['gemma4:26b'])
})

test('a computer without it asks the Gemma server, with its own key in a file, after the person says yes', async ($, on) => {
  const seen = computer(on, { server: 'https://gemma.example.com', answer: 'Send', kept: { deviceKey: KEY } })
  await start($)
  expect(seen.tools.find(t => t.name === 'ask_local')?.description).toContain('runs on the server gemma.example.com, NOT on this computer')
  const r = await ask($)
  expect(r.result).toBe('a summary from the server')
  expect(seen.asked.length).toBe(1)
  expect(seen.asked[0]).toContain('Send this text to Gemma on the server gemma.example.com?')
  expect(seen.curls.map(target)).toEqual(['https://gemma.example.com/api/chat'])
  // the server runs the larger Gemma
  // máy chủ chạy bản Gemma lớn hơn
  expect(seen.models).toEqual(['gemma4:31b'])
  // the key went through a file, then the file was emptied; it is nowhere on the command line
  // khoá đi qua một file, rồi file được làm trống; nó không nằm ở đâu trên dòng lệnh
  expect(seen.curls[0]!.join(' ')).not.toContain(KEY)
  expect(seen.headers).toEqual([`Authorization: Bearer ${KEY}\n`, ''])
})

test('a small Gemma left from an earlier install does not count: the server is asked', async ($, on) => {
  const seen = computer(on, { tags: SMALL, server: 'https://gemma.example.com', answer: 'Send', kept: { deviceKey: KEY } })
  await start($)
  await ask($)
  expect(seen.curls.map(target)).toEqual(['https://gemma.example.com/api/chat'])
})

test('the person says no, or the text holds a secret: nothing goes to the Gemma server', async ($, on) => {
  const seen = computer(on, { server: 'https://gemma.example.com', answer: 'Do not send', kept: { deviceKey: KEY } })
  await start($)
  expect((await ask($)).isError).toBe(true)
  // built from parts, so the scan that guards commits does not take this line for a real key
  // ghép từ nhiều phần, để lớp quét canh commit không coi dòng này là khoá thật
  const secret = await ask($, `summarise this: const ${'PACE' + '_KEY'} = 'Zq8wLp3nVb7x'`)
  expect(secret.isError).toBe(true)
  expect(secret.result).toContain('Not sent to Gemma on the server gemma.example.com')
  expect(seen.curls).toEqual([])
})

test('a computer that ran Gemma itself and whose Ollama is off does not move to the server by itself', async ($, on) => {
  const seen = computer(on, { server: 'https://gemma.example.com', answer: 'Send', kept: { deviceKey: KEY, gemmaRanHere: true } })
  await start($)
  expect(seen.tools.find(t => t.name === 'ask_local')?.description).toContain('does NOT leave the computer')
  await ask($)
  expect(seen.curls.map(target)).toEqual(['http://127.0.0.1:11434/api/chat'])
  expect(seen.asked).toEqual([])
})

test('a weak computer with no Gemma server has no Gemma tool', async ($, on) => {
  const none = computer(on, {})
  await start($)
  expect(none.tools.some(t => t.name === 'ask_local')).toBe(false)
})

test('a computer the dashboard has given no key yet sends nothing to the Gemma server', async ($, on) => {
  const seen = computer(on, { server: 'https://gemma.example.com', answer: 'Send' })
  await start($)
  const r = await ask($)
  expect(r.isError).toBe(true)
  expect(r.result).toContain('no key of its own')
  expect(seen.curls).toEqual([])
})

const BOTH = { tags: TAGS, server: 'https://gemma.example.com', answer: 'Send', kept: { deviceKey: KEY } }
const DOWN = '\n000'

test('a computer that runs Gemma and has a server too: here by default, the server only when Claude asks for it, and then the person is asked', async ($, on) => {
  const seen = computer(on, BOTH)
  await start($)
  const tool = seen.tools.find(t => t.name === 'ask_local')
  expect(tool?.description).toContain('does NOT leave the computer')
  expect(tool?.description).toContain('where "server"')
  expect((await ask($)).result).toBe('a summary from Gemma')
  expect((await ask($, 'summarise', 'here')).result).toBe('a summary from Gemma')
  expect(seen.asked).toEqual([])
  expect((await ask($, 'summarise this public manual', 'server')).result).toBe('a summary from the server')
  expect(seen.asked.length).toBe(1)
  expect(seen.curls.map(target)).toEqual(['http://127.0.0.1:11434/api/chat', 'http://127.0.0.1:11434/api/chat', 'https://gemma.example.com/api/chat'])
  expect(seen.models).toEqual(['gemma4:26b', 'gemma4:26b', 'gemma4:31b'])
})

test('the server fails: Gemma on this computer answers, says so, and the server is left alone for five minutes', async ($, on) => {
  const seen = computer(on, BOTH)
  await start($)
  // unreachable, busy, refused, cut off mid-answer, an error page: each one ends with an answer from here
  // không tới được, bận, bị từ chối, đứt giữa câu trả lời, trang lỗi: lần nào cũng kết thúc bằng câu trả lời từ máy này
  for (const serverSays of [DOWN, 'busy\n503', 'Forbidden\n403', '{"message":{"content":"half an ans\n200', '<html>\n502']) {
    seen.set({ serverSays })
    seen.curls.length = seen.asked.length = 0
    const r = await ask($, 'summarise this public manual', 'server')
    expect([serverSays, r.isError]).toEqual([serverSays, false])
    expect(r.result).toContain('[Answered by Gemma on this computer (gemma4:26b), not by the server.')
    expect(r.result).toContain('gemma.example.com')
    expect(r.result.endsWith('a summary from Gemma')).toBe(true)
    expect(seen.curls.map(target)).toEqual(['https://gemma.example.com/api/chat', 'http://127.0.0.1:11434/api/chat'])
    // within five minutes the server is not tried and nobody is asked: nothing leaves this computer
    // trong năm phút không thử máy chủ và không hỏi ai: không gì rời máy này
    seen.set({ serverSays: undefined })
    const again = await ask($, 'summarise this public manual', 'server')
    expect(again.result).toContain('failed a few minutes ago')
    expect(seen.curls.length).toBe(3)
    expect(target(seen.curls[2]!)).toBe('http://127.0.0.1:11434/api/chat')
    expect(seen.asked.length).toBe(1)
    // after that the server is tried again
    // sau đó máy chủ được thử lại
    await seen.clock.advance(5 * 60_000 + 1)
    expect((await ask($, 'summarise this public manual', 'server')).result).toBe('a summary from the server')
    expect(seen.asked.length).toBe(2)
  }
})

test('set to always here, a computer that runs Gemma never asks the server, whatever Claude passes', async ($, on) => {
  const seen = computer(on, { ...BOTH, mode: 'here' })
  await start($)
  expect(seen.tools.find(t => t.name === 'ask_local')?.description).not.toContain('gemma.example.com')
  await ask($, 'summarise', 'server')
  expect(seen.curls.map(target)).toEqual(['http://127.0.0.1:11434/api/chat'])
  expect(seen.asked).toEqual([])
})

test('set to always the server, it asks the server first and still answers here when the server fails', async ($, on) => {
  const seen = computer(on, { ...BOTH, mode: 'server' })
  await start($)
  expect((await ask($)).result).toBe('a summary from the server')
  seen.set({ serverSays: DOWN })
  await seen.clock.advance(1)
  const r = await ask($)
  expect(r.isError).toBe(false)
  expect(r.result).toContain('[Answered by Gemma on this computer')
  expect(seen.asked.length).toBe(2)
  // both down: both errors are told
  // cả hai cùng hỏng: báo cả hai lỗi
  await seen.clock.advance(5 * 60_000 + 1)
  seen.set({ hereFails: true })
  const both = await ask($)
  expect(both.isError).toBe(true)
  expect(both.result).toContain('Could not reach the Gemma server gemma.example.com')
  expect(both.result).toContain('Gemma on this computer could not answer either')
})

test('a weak computer has nothing to fall back on: a server that fails is reported, and tried again next time', async ($, on) => {
  const seen = computer(on, { server: 'https://gemma.example.com', answer: 'Send', kept: { deviceKey: KEY }, serverSays: DOWN })
  await start($)
  const r = await ask($)
  expect(r.isError).toBe(true)
  expect(r.result).toContain('Could not reach the Gemma server gemma.example.com')
  await ask($)
  expect(seen.curls.map(target)).toEqual(['https://gemma.example.com/api/chat', 'https://gemma.example.com/api/chat'])
})

test('the other way never happens by itself: Gemma on this computer fails and nothing goes to the server', async ($, on) => {
  const seen = computer(on, { ...BOTH, hereFails: true })
  await start($)
  const r = await ask($, 'summarise the notes on Lan and Minh')
  expect(r.isError).toBe(true)
  expect(r.result).toContain('Ollama on this computer is not running')
  expect(seen.curls.map(target)).toEqual(['http://127.0.0.1:11434/api/chat'])
  expect(seen.asked).toEqual([])
})

test('a weak computer uses the Gemma server the company dashboard announced, and an address set on it wins', async ($, on) => {
  const board = { url: 'https://aiworker.example.com/gemma', model: 'gemma4:26b' }
  const seen = computer(on, { sharing: true, answer: 'Send', kept: { deviceKey: KEY, gemmaFromBoard: board } })
  await start($)
  expect(seen.tools.find(t => t.name === 'ask_local')?.description).toContain('runs on the server aiworker.example.com')
  await ask($)
  expect(seen.curls.map(target)).toEqual(['https://aiworker.example.com/gemma/api/chat'])
  expect(seen.models).toEqual(['gemma4:26b'])
})

test('an address the dashboard announced is ignored when this computer does not share with it', async ($, on) => {
  const seen = computer(on, { kept: { deviceKey: KEY, gemmaFromBoard: { url: 'https://aiworker.example.com/gemma' } } })
  await start($)
  expect(seen.tools.some(t => t.name === 'ask_local')).toBe(false)
})

test('an address set on this computer beats the announced one', async ($, on) => {
  const seen = computer(on, { sharing: true, server: 'https://mine.example.com', answer: 'Send', kept: { deviceKey: KEY, gemmaFromBoard: { url: 'https://aiworker.example.com/gemma' } } })
  await start($)
  await ask($)
  expect(seen.curls.map(target)).toEqual(['https://mine.example.com/api/chat'])
})
