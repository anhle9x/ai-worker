import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { LINUX_DETACH, LINUX_FIND_SCRIPT, LINUX_RESTART_SCRIPT, WINDOWS_FIND_SCRIPT, WINDOWS_HELPER, WINDOWS_RESTART_SCRIPT } from '../hooks/update'

type Engine = Parameters<TestBody>[0]

/** A session at 62% of its context: returns the warnings toasted. `shipsHandoff` says whether the plugin folder holds the skill. */
async function warnAt62($: Engine, on: On, shipsHandoff: boolean): Promise<string[]> {
  mock.clock(on)
  mock.store(on)
  mock.env(on, { HOME: '/Users/an' })
  const toasts: string[] = []
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  on('fs.read', (_, e) => {
    // only the plugin's own folder has the skill: nothing is in ~/.claude/skills
    if (shipsHandoff && e.path.endsWith('/skills/handoff/SKILL.md') && !e.path.startsWith('/Users/an/')) return { value: '---\nname: handoff\n---\n' }
    throw new Error('no such file')
  })
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.session.measure({ context: { tokens: 620_000, window: 1_000_000, percent: 62 }, rateLimits: [], changed: ['context'] })
  return toasts
}

test('the context warning points to /handoff, the skill the plugin ships', async ($, on) => {
  const toasts = await warnAt62($, on, true)
  expect(toasts.length).toBe(1)
  expect(toasts[0]).toContain('62%')
  expect(toasts[0]).toContain('/handoff')
})

test('without the skill the context warning does not name /handoff', async ($, on) => {
  const toasts = await warnAt62($, on, false)
  expect(toasts.length).toBe(1)
  expect(toasts[0]).not.toContain('/handoff')
})

const HASH = 'ab'.repeat(32)
const PS = [
  '    1     0 /sbin/launchd',
  '  414     1 /Applications/Claude.app/Contents/MacOS/Claude',
  '  563   414 /Users/an/Library/Application Support/Claude/claude-code/2.1.321/abc/claude.app/Contents/MacOS/claude',
  '  564   563 /bin/sh',
].join('\n')

/** `found` is what the Linux or Windows find script prints: nothing outside the Claude desktop app. */
type Machine = { system: 'Darwin' | 'Linux' | 'Windows'; surface: 'desktop' | 'terminal'; bundle?: string; found?: string; answer: string | undefined }
type Ran = { argv: string[]; env: Record<string, string> }

/** A computer with a signed update waiting on its server: returns what the plugin ran and asked. */
function updateWaiting(on: On, machine: Machine) {
  mock.clock(on)
  mock.store(on)
  mock.env(on, machine.system === 'Windows' ? { USERPROFILE: 'C:\\Users\\an', OS: 'Windows_NT' } : { HOME: '/Users/an' })
  const seen = { ran: [] as Ran[], asked: [] as string[] }
  on('command.register', () => ({ value: { command: 'office' } }))
  on('command.run', () => ({ text: 'not the plugin' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.surfaces', () => ({ value: [machine.surface] }))
  on('fs.exists', (_, e) => ({ value: !e.path.endsWith('/.git') && !e.path.endsWith('company.json') }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.read', (_, e) => {
    if (e.path.endsWith('.new/.claude-plugin/plugin.json')) return { value: '{"version":"9.9.9"}' }
    if (e.path.endsWith('/.claude-plugin/plugin.json')) return { value: '{"version":"9.9.8"}' }
    if (e.path.endsWith('/web/company.json')) return { value: '{"sharing":{"enabled":true,"webhook":"https://server.example","ingestKey":"k"}}' }
    if (e.path.endsWith('/keys/allowed_signers')) return { value: 'ai-worker ssh-ed25519 AAAA' }
    // the page's own files, copied next to the session files when a session starts
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('http.fetch', (_, e) => ({
    value: {
      ok: true,
      status: 200,
      headers: {},
      text: e.url.endsWith('latest.json') ? JSON.stringify({ version: '9.9.9', name: 'ai-worker-9.9.9.zip', sha256: HASH, date: 100 }) : 'signature',
    },
  }))
  on('process.run', (_, e) => {
    const env = { ...(e.init?.env ?? {}) }
    seen.ran.push({ argv: [...e.argv], env })
    const out = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    const exe = e.argv[0]
    if (exe === 'uname') return out(`${machine.system}\n`)
    if (exe === 'shasum') return out(`${HASH}  x.zip\n`)
    if (exe === '/bin/sh') return out(e.argv[2] === LINUX_FIND_SCRIPT ? (machine.found ?? '') : '564\n')
    if (exe === 'ps') return out(PS)
    if (exe === '/usr/bin/plutil') return out(`${machine.bundle ?? 'com.anthropic.claudefordesktop'}\n`)
    if (exe === 'powershell' && env.AIW_SCRIPT === WINDOWS_FIND_SCRIPT) return out(machine.found ?? '')
    return out('')
  })
  // $.ui.ask is a call of the AskUserQuestion tool; a question closed without an answer rejects
  on('tool.call', (_, e) => {
    const questions = (e as unknown as { questions: { question: string }[] }).questions
    const question = questions[0]!.question
    seen.asked.push(question)
    if (machine.answer === undefined) throw new Error('dismissed')
    return { result: { questions, answers: { [question]: machine.answer } } } as never
  })
  return seen
}

async function runUpdate($: Engine, on: On, machine: Machine, command = 'update') {
  const seen = updateWaiting(on, machine)
  await $.session.start({ cwd: '/', surface: machine.surface, isInteractive: true })
  const { text } = (await $.command.run({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 80 } })) as { text: string }
  return { text, asked: seen.asked, helper: seen.ran.find(r => r.argv[0] === '/usr/bin/perl' || r.argv[2] === LINUX_DETACH || r.env.AIW_SCRIPT === WINDOWS_RESTART_SCRIPT) }
}

const BY_HAND = 'Quit the Claude app completely'

test('/update in the Claude app on a Mac asks, and on a yes closes and reopens that app', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Darwin', surface: 'desktop', answer: 'Reopen now' })
  expect(r.asked).toEqual(['Version 9.9.9 is installed. Close the Claude app and open it again now? Sessions that are still working will stop.'])
  // the helper gets the app launchd started (not the nearer claude.app of the CLI) and nothing else to act on
  expect(r.helper?.argv.slice(-2)).toEqual(['414', '/Applications/Claude.app'])
  expect(r.text).toContain('closes and opens again')
})

test('/update leaves the app alone when the person says later', async ($, on) => {
  const later = await runUpdate($, on, { system: 'Darwin', surface: 'desktop', answer: 'Later' })
  expect(later.asked.length).toBe(1)
  expect(later.helper).toBeUndefined()
  expect(later.text).toContain(BY_HAND)
})

test('/update leaves the app alone when the question is closed without an answer', async ($, on) => {
  const closed = await runUpdate($, on, { system: 'Darwin', surface: 'desktop', answer: undefined })
  expect(closed.asked.length).toBe(1)
  expect(closed.helper).toBeUndefined()
  expect(closed.text).toContain(BY_HAND)
})

test('/update never offers to reopen in a terminal', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Darwin', surface: 'terminal', answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})

test('/update in the Claude app on Linux asks, and on a yes closes that app and runs its own command again', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Linux', surface: 'desktop', found: '226\t/opt/Claude/claude-desktop\t/usr/bin/claude-desktop', answer: 'Reopen now' })
  expect(r.asked.length).toBe(1)
  expect(r.helper?.argv).toEqual(['/bin/sh', '-c', LINUX_DETACH, LINUX_RESTART_SCRIPT, '226', '/usr/bin/claude-desktop'])
  expect(r.text).toContain('closes and opens again')
})

test('/update never offers to reopen on Linux when no ancestor belongs to the claude-desktop package', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Linux', surface: 'desktop', answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})

test('/update never offers to reopen on Linux in a terminal', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Linux', surface: 'terminal', found: '226\t/opt/Claude/claude-desktop\t/usr/bin/claude-desktop', answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})

test('/update never offers to reopen an app that is not the Claude app', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Darwin', surface: 'desktop', bundle: 'com.apple.Terminal', answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})

const WIN_APP = 'C:\\Users\\an\\AppData\\Local\\AnthropicClaude\\app-5.1.0\\claude.exe'
const WIN_STUB = 'C:\\Users\\an\\AppData\\Local\\AnthropicClaude\\claude.exe'

test('/update in the Claude app on Windows asks, and on a yes hands the app and its launcher to the helper as variables', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Windows', surface: 'desktop', found: `5516\t${WIN_APP}\t${WIN_STUB}`, answer: 'Reopen now' })
  expect(r.asked.length).toBe(1)
  // the command line names a variable and nothing else: no path or script is ever part of it
  expect(r.helper?.argv).toEqual(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', 'Invoke-Expression $env:AIW_SCRIPT'])
  expect(r.helper?.env).toEqual({ AIW_SCRIPT: WINDOWS_RESTART_SCRIPT, AIW_HELPER: WINDOWS_HELPER, AIW_PID: '5516', AIW_LAUNCHER: WIN_STUB })
  expect(r.text).toContain('closes and opens again')
})

test('/update never offers to reopen on Windows when no ancestor is the signed Claude app', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Windows', surface: 'desktop', answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})

test('/update never offers to reopen on Windows in a terminal', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Windows', surface: 'terminal', found: `5516\t${WIN_APP}\t${WIN_STUB}`, answer: 'Reopen now' })
  expect(r.asked).toEqual([])
  expect(r.helper).toBeUndefined()
  expect(r.text).toContain(BY_HAND)
})


test('/ai-worker:update, the name the app lists before a session starts, is the same command as /update', async ($, on) => {
  const r = await runUpdate($, on, { system: 'Darwin', surface: 'desktop', answer: 'Later' }, 'ai-worker:update')
  expect(r.asked.length).toBe(1)
  expect(r.text).toContain(BY_HAND)
  expect(r.text).toContain('9.9.9')
})

test('/ai-worker:help answers from the plugin folder, without the model', async ($, on) => {
  mock.clock(on)
  mock.store(on)
  mock.env(on, { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('command.run', () => ({ text: 'not the plugin' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.list', (_, e) => ({ value: String(e.path).endsWith('/skills') ? [{ name: 'handoff', kind: 'dir', size: 0 }, { name: 'SOURCES.md', kind: 'file', size: 10 }] : [] }) as never)
  on('fs.read', (_, e) => {
    if (e.path.endsWith('/skills/handoff/SKILL.md')) return { value: '---\nname: handoff\ndescription: Write the handoff note. Use it late.\n---\n' }
    if (e.path.endsWith('/.claude-plugin/plugin.json')) return { value: '{"version":"9.9.8"}' }
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('http.fetch', () => ({ value: { ok: false, status: 0, headers: {}, text: '' } }))
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const { text } = (await $.command.run({ command: 'ai-worker:help', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 80 } })) as { text: string }
  expect(text).toContain('9.9.8')
  expect(text).toContain('- /ai-worker:handoff — write a handoff note so a new session can carry on')
  expect(text).not.toContain('SOURCES')
  expect(text).not.toContain('Dev pack')
})

