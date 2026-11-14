import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { boardUserAgent, modelLabel, summarizeBoard } from '../hooks/board'

type Engine = Parameters<TestBody>[0]

const AT = Date.UTC(2026, 10, 14, 7, 5)
// what /ext/data gives a paired device: the wall view, all of it made up
const WALL = {
  role: 'wall',
  updatedAt: AT,
  tzOffsetHours: 7,
  tasks24: [Array(24).fill(1), Array(24).fill(2), Array(24).fill(0)],
  branches: [
    { id: 'hcm', name: 'Head office', lat: 10.78, lon: 106.7, isHq: true },
    { id: 'dn', name: 'Da Nang', lat: 16.05, lon: 108.2, isHq: false },
  ],
  people: [
    { name: 'An', branch: 'hcm', status: 'working', usdToday: 1.86, usd7d: 10.31, waitingSince: null, models: { 'claude-fable-5-2': 4, 'claude-haiku-5-5': 1 }, quota: { windows: [{ kind: 'five_hour', pct: 22 }, { kind: 'seven_day', pct: 31 }] } },
    { name: 'Nga', branch: 'dn', status: 'waiting', usdToday: 10.64, usd7d: 29.69, waitingSince: AT - 27 * 60_000, models: { 'claude-opus-5-5': 2 }, quota: { windows: [{ kind: 'five_hour', pct: 96.4 }] } },
    { name: 'Device 3fa9c1', branch: '', status: 'offline', usdToday: 0, usd7d: 0, waitingSince: null, models: {}, quota: null },
  ],
}

test('the board reads as plain lines: the team, each office, each person', () => {
  const text = summarizeBoard(WALL, AT)
  expect(text).toContain('AI Worker board at 2026-11-14 14:05 (UTC+7). Amounts are US dollars at API prices.')
  expect(text).toContain('Team: 3 people, 1 working, 1 waiting for an answer, 0 idle, 1 offline. Cost today 12.50, last 7 days 40.00.')
  expect(text).toContain('Tasks handed to helper assistants in the last 24 hours: Gemini 24, ChatGPT 48, Gemma 0.')
  expect(text).toContain('- Head office | 1 | 1 | 0 | 1.86 | 10.31')
  expect(text).toContain('- Da Nang | 1 | 0 | 1 | 10.64 | 29.69')
  expect(text).toContain('- An | Head office | working | - | 1.86 | 10.31 | 22 | 31 | Fable 5.2')
  expect(text).toContain('- Nga | Da Nang | waiting for an answer | 27 | 10.64 | 29.69 | 96 | - | Opus 5.5')
  // a person at no named office is still listed, with nothing made up
  expect(text).toContain('- Device 3fa9c1 | no office (mobile or not assigned) | offline | - | 0.00 | 0.00 | - | - | -')
})

test('an empty or broken board answer does not throw', () => {
  expect(summarizeBoard({}, AT)).toContain('Team: 0 people')
  expect(summarizeBoard({ people: [{}], branches: 'x' } as never, AT)).toContain('- ? | no office (mobile or not assigned) | offline')
})

test('the plugin names itself to the server, and model ids read as names', () => {
  expect(boardUserAgent('0.31.6', 'Mac')).toBe('AI-Worker-Plugin/0.31.6 (Mac)')
  expect(boardUserAgent(undefined, 'Windows')).toBe('AI-Worker-Plugin/0 (Windows)')
  expect(modelLabel('claude-sonnet-5-5')).toBe('Sonnet 5.5')
  expect(modelLabel('gemma4:26b')).toBe('gemma4:26b')
})

type Call = { path: string; method: string; auth: string; agent: string }
type Server = { approved: boolean; revoked: boolean; status?: number; calls: Call[]; tools: string[] }

const PAIRED = { 'board-pairing': { token: 'tv_secret', name: 'Claude of Hoa' } }

/** A manager's computer whose company server speaks the pairing paths. `kept` is what the plugin's store holds at the start; `status` makes every board path answer with that status. */
function boardServer(on: On, kept: Record<string, unknown> = {}, withServer = true): Server {
  const server: Server = { approved: false, revoked: false, calls: [], tools: [] }
  mock.clock(on)
  mock.store(on, kept)
  mock.env(on, { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('command.run', () => ({ text: 'not the plugin' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.list', () => ({ value: [] }) as never)
  on('fs.read', (_, e) => {
    if (e.path.endsWith('/.claude-plugin/plugin.json')) return { value: '{"version":"9.9.8"}' }
    if (withServer && e.path.endsWith('/web/company.json')) return { value: '{"sharing":{"enabled":true,"webhook":"https://board.example","ingestKey":"k"}}' }
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('process.run', (_, e) => ({ value: { exitCode: e.argv[0] === 'uname' ? 0 : 1, stdout: e.argv[0] === 'uname' ? 'Darwin\n' : '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('tool.register', (_, e) => {
    server.tools.push((e as unknown as { name: string }).name)
    return { value: { tool: (e as unknown as { name: string }).name } }
  })
  on('http.fetch', (_, e) => {
    const path = e.url.replace('https://board.example', '')
    const headers = (e.init?.headers ?? {}) as Record<string, string>
    const auth = headers.Authorization ?? ''
    const reply = (status: number, body: unknown = {}) => ({ value: { ok: status >= 200 && status < 300, status, headers: {}, text: JSON.stringify(body) } })
    if (!path.startsWith('/ext/')) return reply(404)
    server.calls.push({ path, method: e.init?.method ?? 'GET', auth, agent: headers['User-Agent'] ?? '' })
    if (server.status) return reply(server.status, { error: 'x' })
    if (path === '/ext/request-code') return reply(200, { code: '12345678', key: 'pending-key', secondsLeft: 600 })
    if (path === '/ext/poll') return reply(200, auth !== 'Bearer pending-key' ? { status: 'expired' } : server.approved ? { status: 'done', name: 'Claude of Hoa', token: 'tv_secret' } : { status: 'pending' })
    if (auth !== 'Bearer tv_secret' || server.revoked) return reply(401, { error: 'Not paired' })
    if (path === '/ext/unpair') {
      server.revoked = true
      return reply(200, { ok: true })
    }
    return reply(200, path === '/ext/data' ? WALL : { updatedAt: AT, people: [] })
  })
  return server
}

const run = async ($: Engine, command = 'ai-worker:board', args = '') =>
  ((await $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 80 } })) as { text: string }).text
const ask = async ($: Engine) => (await $.tool.call({ tool: 'mcp__ai-worker__office_board' })) as unknown as { result: string; isError: boolean }

test('/ai-worker:board asks for a code, waits for an admin, then Claude can read the board', async ($, on) => {
  const server = boardServer(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  // not paired: no extra tool on this computer, and the tool itself says how to pair
  expect(server.tools).not.toContain('office_board')
  expect((await ask($)).result).toContain('/ai-worker:board')

  const first = await run($)
  expect(first).toContain('Pairing code: 1234-5678')
  expect(first).toContain('https://board.example/admin')
  expect(first).toContain('"TV screens"')
  expect(server.calls[0]).toEqual({ path: '/ext/request-code', method: 'POST', auth: '', agent: 'AI-Worker-Plugin/9.9.8 (Mac)' })

  // typed again before an admin approved: the same code, no new request
  const second = await run($, 'board')
  expect(second).toContain('Not approved yet.')
  expect(second).toContain('1234-5678')
  expect(server.calls.filter(c => c.path === '/ext/request-code').length).toBe(1)
  expect(server.tools).not.toContain('office_board')

  server.approved = true
  const third = await run($)
  expect(third).toContain('paired with the board as "Claude of Hoa"')
  expect(server.tools).toContain('office_board')

  const answer = await ask($)
  expect(answer.isError).toBe(false)
  expect(answer.result).toContain('- Nga | Da Nang | waiting for an answer |')
  expect(server.calls.at(-1)).toEqual({ path: '/ext/data', method: 'GET', auth: 'Bearer tv_secret', agent: 'AI-Worker-Plugin/9.9.8 (Mac)' })
  // the pending key is spent: from here on only the board key is sent
  expect(await run($)).toContain('paired with the board')
  expect(server.calls.at(-1)).toEqual({ path: '/ext/state', method: 'GET', auth: 'Bearer tv_secret', agent: 'AI-Worker-Plugin/9.9.8 (Mac)' })
})

test('a paired computer registers the tool when a session starts, and says where it stands', async ($, on) => {
  const server = boardServer(on, PAIRED)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(server.tools).toContain('office_board')
  expect(await run($)).toContain('paired with the board as "Claude of Hoa"')
  expect(server.calls.at(-1)?.path).toBe('/ext/state')
})

test('a key revoked by an admin stops working: the tool says so, and the command starts a new pairing', async ($, on) => {
  const server = boardServer(on, PAIRED)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  server.revoked = true
  const answer = await ask($)
  expect(answer.isError).toBe(true)
  expect(answer.result).toContain('revoked or has expired')
  // the dead key is forgotten: the command goes straight to a new code, without trying the old key again
  const before = server.calls.length
  expect(await run($)).toContain('Pairing code: 1234-5678')
  expect(server.calls.slice(before).map(c => c.path)).toEqual(['/ext/request-code'])
})

test('/ai-worker:board unpair gives the key back to the server and forgets it here', async ($, on) => {
  const server = boardServer(on, PAIRED)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(await run($, 'ai-worker:board', 'unpair')).toContain('no longer paired')
  expect(server.calls.at(-1)).toEqual({ path: '/ext/unpair', method: 'POST', auth: 'Bearer tv_secret', agent: 'AI-Worker-Plugin/9.9.8 (Mac)' })
  const after = await ask($)
  expect(after.isError).toBe(true)
  expect(after.result).toContain('not paired')
})

test('away from the office the board refuses: the command and the tool say why and keep the pairing', async ($, on) => {
  const server = boardServer(on, PAIRED)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  server.status = 403
  expect(await run($)).toContain('only from the office network')
  const answer = await ask($)
  expect(answer.isError).toBe(true)
  expect(answer.result).toContain('only from the office network')
  // back at the office the same key works again: a refused network does not cost the pairing
  server.status = undefined
  expect((await ask($)).isError).toBe(false)
})

test('permission settings that deny the tool are obeyed before anything is read', async ($, on) => {
  const server = boardServer(on, PAIRED)
  on('tool.check', () => ({ decision: 'deny' }) as never)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const before = server.calls.length
  const answer = await ask($)
  expect(answer.isError).toBe(true)
  expect(answer.result).toContain('permission settings')
  expect(server.calls.length).toBe(before)
})

test('a computer with no company server has no board to pair with', async ($, on) => {
  const server = boardServer(on, {}, false)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(await run($)).toContain('no company server')
  expect(server.calls.length).toBe(0)
})
