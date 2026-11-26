import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { trailNote, trailProblems } from '../hooks/committrail'

test('a good message has nothing to fix, and a light change needs only its subject', () => {
  expect(trailProblems('fix(board): the arrow stands inside the box\n\nRoot cause: the default arrow of the select, ops.css:324\nMeasured: `node tests/check-map-layout.js` → 21 checks passed')).toEqual([])
  expect(trailProblems('docs(readme): say how to turn the check on')).toEqual([])
  expect(trailProblems('feat(server): count the hours left out\n\nMeasured: not run — needs the company server')).toEqual([])
})

test('a fix without its cause or what was measured is named, one line each', () => {
  const got = trailProblems('fix(server): pages are faster\n\nMeasured: tested, works')
  expect(got.length).toBe(2)
  expect(got[0]).toContain('Root cause')
  expect(got[1]).toContain('cannot be checked')
  expect(trailProblems('perf(server): pages are faster').join(' ')).toContain('"Measured:"')
  expect(trailProblems('fix(server): x\n\nRoot cause: unknown\nMeasured: `make test` → ok').join(' ')).toContain('Root cause')
})

test('the subject keeps the shape, the length and no period', () => {
  expect(trailProblems('server: a page picks only the ids it needs')[0]).toContain('type(scope): summary')
  expect(trailProblems('docs: ' + 'a'.repeat(80)).join(' ')).toContain('at most 72')
  const period = trailProblems('docs: say it.')
  expect(period.length).toBe(1)
  expect(period[0]).toContain('period')
})

test('merges, reverts, fixups and an empty message are left alone', () => {
  for (const m of ['Merge branch \'order-plan\'', 'Revert "fix: x"', 'fixup! fix: x', '', '# only a comment']) expect(trailProblems(m)).toEqual([])
})

test('a field goes on over indented and bulleted lines, and stops at the next field', () => {
  expect(trailProblems('fix(x): y\n\nRoot cause:\n  the lock was taken\n  after the page\nMeasured: `go test` → ok 1.2s')).toEqual([])
  expect(trailProblems('fix(x): y\n\nRoot cause: short\nFix: the lock\nMeasured: 3 runs').join(' ')).toContain('Root cause')
})

test('the note for Claude lists what is missing and says not to invent a result', () => {
  const note = trailNote(['a', 'b'])
  expect(note).toContain('a; b')
  expect(note).toContain('--amend')
  expect(note).toContain('never invent')
})

type Engine = Parameters<TestBody>[0]

/** A computer whose git has HEAD `before` until the shell runs, then `after`, with `message` as its last commit; config.js as given.
 *  Returns what Claude read after a command. */
async function commitOn($: Engine, on: On, s: { config?: string; before: string; after: string; message: string }, command: string) {
  let ran = false
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
    if (s.config && e.path.endsWith('/config.js') && !e.path.includes('claude-plugins')) return { value: s.config }
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('http.fetch', () => ({ value: { ok: false, status: 0, headers: {}, text: '' } }))
  on('process.run', (_, e) => {
    const argv = (e as unknown as { argv: string[] }).argv.join(' ')
    const out = argv.includes('rev-parse') ? (ran ? s.after : s.before) + '\n' : argv.includes('log -1') ? s.message : ''
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.check', () => ({ decision: 'allow' as const }))
  on('tool.call', () => {
    ran = true
    return { result: 'ran' } as never
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const got = (await $.tool.call({ tool: 'Bash', command } as never)) as { result?: unknown; context?: readonly string[] }
  return got.context ?? []
}

const ON = 'window.__aiWorkerConfig = { "commitTrail": true };'

test('with commitTrail on, a new commit whose message lacks its cause and measure reminds Claude to amend it', async ($, on) => {
  const notes = await commitOn($, on, { config: ON, before: 'a1', after: 'b2', message: 'fix(server): pages are faster\n' }, 'git commit -m "fix(server): pages are faster"')
  expect(notes.length).toBe(1)
  expect(notes[0]).toContain('Root cause')
  expect(notes[0]).toContain('--amend')
})

test('nothing is said when config.js does not turn the check on', async ($, on) => {
  expect(await commitOn($, on, { before: 'a1', after: 'b2', message: 'fix: x\n' }, 'git commit -m "fix: x"')).toEqual([])
})

test('a commit that failed leaves HEAD where it was, and Claude is told nothing', async ($, on) => {
  expect(await commitOn($, on, { config: ON, before: 'a1', after: 'a1', message: 'fix: x\n' }, 'git commit -m "fix: x"')).toEqual([])
})

test('a new commit with a good message is left alone', async ($, on) => {
  const good = 'fix(board): arrow inside\n\nRoot cause: the default select arrow, ops.css:324\nMeasured: `node tests/x.js` → 21 passed\n'
  expect(await commitOn($, on, { config: ON, before: 'a1', after: 'b2', message: good }, 'git commit -F msg.txt')).toEqual([])
})

test('a shell command that is not a commit is not looked at', async ($, on) => {
  expect(await commitOn($, on, { config: ON, before: 'a1', after: 'b2', message: 'nope\n' }, 'git status')).toEqual([])
})
