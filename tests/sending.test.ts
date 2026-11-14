import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'

type Engine = Parameters<TestBody>[0]

type Setup = { verdict: { decision: 'allow' | 'ask' | 'deny'; rule?: string }; answer?: string }

/** A staff computer whose only helper is the Codex CLI (ChatGPT): returns the questions put to the person and whether text was sent. */
function computer(on: On, s: Setup) {
  const seen = { asked: [] as string[], sent: 0 }
  mock.clock(on)
  mock.store(on)
  mock.env(on, { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.list', () => ({ value: [] }) as never)
  on('fs.read', (_, e) => {
    if (/chatgpt-\d+\.txt$/.test(e.path)) return { value: 'an answer from ChatGPT' }
    if (e.path.includes('/web/')) return { value: '' }
    // no MCP config names an ai-workers server: the plugin serves the tools itself
    throw new Error('no such file')
  })
  on('http.fetch', () => ({ value: { ok: false, status: 0, headers: {}, text: '' } }))
  on('tool.register', (_, e) => ({ value: { tool: (e as unknown as { name: string }).name } }))
  on('process.run', (_, e) => {
    const out = (exitCode: number, stdout = '') => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (e.argv[0] === 'uname') return out(0, 'Darwin\n')
    if (e.argv[0] === 'sh' && String(e.argv[2]).endsWith('command -v codex')) return out(0, '/bin/codex\n')
    if (e.argv[0] === '/bin/codex' && e.argv[1] === '--version') return out(0, 'codex 1.0\n')
    if (e.argv[0] === '/bin/codex' && e.argv[1] === 'exec') {
      seen.sent++
      return out(0)
    }
    return out(1)
  })
  on('tool.check', () => s.verdict as never)
  on('tool.call', (_, e) => {
    const call = e as unknown as { tool: string; questions?: { question: string }[] }
    if (call.tool !== 'AskUserQuestion') return { result: 'not the plugin' } as never
    const question = call.questions![0]!.question
    seen.asked.push(question)
    if (s.answer === undefined) throw new Error('dismissed')
    return { result: { questions: call.questions, answers: { [question]: s.answer } } } as never
  })
  return seen
}

const send = async ($: Engine) =>
  (await $.tool.call({ tool: 'mcp__ai-worker__ask_chatgpt', prompt: 'review this function' } as never)) as unknown as { result: string; isError: boolean }

test('in a permission mode that asks nothing, text for ChatGPT is still put to the person first', async ($, on) => {
  const seen = computer(on, { verdict: { decision: 'allow' }, answer: 'Send' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await send($)
  expect(seen.asked.length).toBe(1)
  expect(seen.asked[0]).toContain('Send this text to ChatGPT?')
  expect(seen.asked[0]).toContain('review this function')
  expect(seen.sent).toBe(1)
  expect(r.isError).toBe(false)
})

test('in that mode a no, or nobody to answer, keeps the text on this computer', async ($, on) => {
  const seen = computer(on, { verdict: { decision: 'allow' }, answer: 'Do not send' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await send($)
  expect(seen.asked.length).toBe(1)
  expect(seen.sent).toBe(0)
  expect(r.isError).toBe(true)
  expect(r.result).toContain('chose not to send')
})

test('an allow rule the person set for ChatGPT sends without a question', async ($, on) => {
  const seen = computer(on, { verdict: { decision: 'allow', rule: 'mcp__ai-worker__ask_chatgpt' } })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await send($)
  expect(seen.asked).toEqual([])
  expect(seen.sent).toBe(1)
  expect(r.isError).toBe(false)
})
