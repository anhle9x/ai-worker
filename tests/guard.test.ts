import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { dangerNote, dangerQuestion, destructiveCommand, shellWords } from '../hooks/guard'

type Engine = Parameters<TestBody>[0]

test('a command line is cut into commands and words, and quotes keep a word whole', () => {
  expect(shellWords('cd app && rm -rf "my files"; echo done | cat')).toEqual([['cd', 'app'], ['rm', '-rf', 'my files'], ['echo', 'done'], ['cat']])
  expect(shellWords("git commit -m 'rm -rf /; done'")).toEqual([['git', 'commit', '-m', 'rm -rf /; done']])
})

test('deleting a whole folder is caught in its common forms', () => {
  for (const command of [
    'rm -rf src',
    'rm -fr ./src/',
    'rm -r -f src',
    'rm --recursive --force src',
    'sudo rm -rf /Users/an/Documents',
    'cd project && rm -rf .',
    'rm -rf "$HOME/work"',
    'rm -rf ~/work',
    'rm -rf dist ../other',
    'rm -rf',
    'bash -c "rm -rf src"',
    'find . -name old -exec rm -rf {} +',
    'Remove-Item -Recurse -Force C:\\Users\\an\\work',
    'rd /s /q C:\\work',
    'rmdir /S work',
  ]) {
    expect([command, destructiveCommand(command)?.kind]).toEqual([command, 'delete-folder'])
  }
  expect(destructiveCommand('rm -rf dist ../other')).toEqual({ kind: 'delete-folder', target: '../other' })
})

test('what a build makes again, a temporary folder and a plain file are left alone', () => {
  for (const command of [
    'rm -rf node_modules',
    'rm -rf ./web/dist build/',
    'rm -rf /tmp/claude-test/out',
    'rm -rf /private/tmp/x/y',
    'rm -rf app/__pycache__ .pytest_cache',
    'rm notes.txt',
    'rm -f a.log b.log',
    'rmdir empty-folder',
    'git rm -r --cached vendor',
    "git commit -m 'rm -rf everything'",
    'echo "rm -rf /"',
    'ls -R src',
  ]) {
    expect([command, destructiveCommand(command)]).toEqual([command, undefined])
  }
})

test('the three git commands that lose work are caught, their careful forms are not', () => {
  expect(destructiveCommand('git reset --hard HEAD~2')?.kind).toBe('reset-hard')
  expect(destructiveCommand('git -C ../app reset --hard')?.kind).toBe('reset-hard')
  expect(destructiveCommand('git push --force origin main')).toEqual({ kind: 'force-push', target: 'origin main' })
  expect(destructiveCommand('git push -f')?.kind).toBe('force-push')
  expect(destructiveCommand('git push origin +main')?.kind).toBe('force-push')
  expect(destructiveCommand('git add . && git clean -fd')?.kind).toBe('clean')
  expect(destructiveCommand('git clean -xdf')?.kind).toBe('clean')
  for (const command of ['git reset --soft HEAD~1', 'git reset HEAD file.ts', 'git push origin main', 'git push --force-with-lease', 'git clean -n', 'git clean -fdn', 'git status']) {
    expect([command, destructiveCommand(command)]).toEqual([command, undefined])
  }
})

test('the permission dialog says in plain words what is about to be lost', () => {
  expect(dangerQuestion({ kind: 'delete-folder', target: 'src' })).toBe('This deletes a whole folder and everything in it: src. It cannot be brought back. Allow it only if that is what you want.')
  expect(dangerQuestion({ kind: 'delete-folder', target: '' })).toContain('deletes whole folders')
  expect(dangerQuestion({ kind: 'reset-hard', target: '' })).toContain('not saved in git yet')
  expect(dangerQuestion({ kind: 'force-push', target: 'origin main' })).toContain('shared git server')
  expect(dangerQuestion({ kind: 'clean', target: '' })).toContain('git does not track')
})

test('the note for the permission box puts the warning first and keeps what Claude wrote', () => {
  expect(dangerNote({ kind: 'clean', target: '' }, 'Tidy the working tree')).toBe(
    'This deletes every file in this project that git does not track (git clean). They cannot be brought back. Allow it only if that is what you want. Claude wrote: Tidy the working tree',
  )
  expect(dangerNote({ kind: 'reset-hard', target: '' }, undefined)).toBe(dangerQuestion({ kind: 'reset-hard', target: '' }))
  expect(dangerNote({ kind: 'reset-hard', target: '' }, '   ')).toBe(dangerQuestion({ kind: 'reset-hard', target: '' }))
})

type Setup = { verdict: 'allow' | 'ask' | 'deny'; config?: string }

/** A computer where a shell command is about to run. `verdict` is what the engine itself decided, before any plugin. */
function computer(on: On, s: Setup, onCheck?: (input: Record<string, unknown>) => void) {
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
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('tool.check', (_, e) => {
    onCheck?.(((e as unknown as { input?: Record<string, unknown> }).input ?? {}) as Record<string, unknown>)
    return { decision: s.verdict, ...(s.verdict === 'allow' ? { rule: 'Bash(rm:*)' } : {}) } as never
  })
}

const check = async ($: Engine, command: string, tool = 'Bash') =>
  (await $.tool.check({ tool, input: { command } } as never)) as unknown as { decision: string; reason?: string; rule?: string }

test('a folder delete that a rule or the mode would let through is put to a person instead, in plain words', async ($, on) => {
  computer(on, { verdict: 'allow' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const v = await check($, 'rm -rf src')
  expect(v.decision).toBe('ask')
  expect(v.reason).toContain('This deletes a whole folder and everything in it: src.')
  // the rule that allowed it is not carried along: the ask is the plugin's own
  expect(v.rule).toBe(undefined)
  expect((await check($, 'git reset --hard')).decision).toBe('ask')
  expect((await check($, 'git push --force')).decision).toBe('ask')
  expect((await check($, 'git clean -fd')).decision).toBe('ask')
  expect((await check($, 'Remove-Item -Recurse -Force work', 'PowerShell')).decision).toBe('ask')
})

test('where the engine would ask anyway, the question becomes the plain-words one, so no automatic approval answers it', async ($, on) => {
  computer(on, { verdict: 'ask' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const v = await check($, 'rm -rf src')
  expect(v.decision).toBe('ask')
  expect(v.reason).toContain('It cannot be brought back.')
})

test('a command the settings deny stays denied', async ($, on) => {
  computer(on, { verdict: 'deny' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect((await check($, 'rm -rf src')).decision).toBe('deny')
})

test('an ordinary command, a delete that loses nothing and another tool keep the verdict they had', async ($, on) => {
  computer(on, { verdict: 'allow' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  for (const command of ['ls -la', 'rm -rf node_modules dist', 'rm notes.txt', 'git push origin main']) {
    expect([command, (await check($, command)).decision]).toEqual([command, 'allow'])
  }
  // a tool that is not a shell is not read as a command
  expect((await check($, 'rm -rf src', 'Read')).decision).toBe('allow')
})

test('config.js can turn the question off for someone who writes code all day', async ($, on) => {
  computer(on, { verdict: 'allow', config: 'window.__aiWorkerConfig = { "askBeforeDestructive": false };' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect((await check($, 'rm -rf src')).decision).toBe('allow')
})

/** The same computer: returns each shell call as the engine's own permission step saw it, which is what the permission box shows. */
function shown(on: On, config?: string) {
  const seen: { command?: unknown; description?: unknown }[] = []
  computer(on, { verdict: 'ask', ...(config ? { config } : {}) }, input => seen.push({ command: input.command, description: input.description }))
  on('tool.call', () => ({ result: 'ran' }) as never)
  return seen
}

const call = ($: Engine, command: string, description: string) => $.tool.call({ tool: 'Bash', command, description } as never).catch(() => undefined)

test('a destructive command reaches the permission box with the warning as its description', async ($, on) => {
  const seen = shown(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await call($, 'rm -rf src', 'Clean up')
  await call($, 'ls -la', 'List files')
  await call($, 'rm -rf node_modules', 'Reinstall')
  expect(seen).toEqual([
    { command: 'rm -rf src', description: 'This deletes a whole folder and everything in it: src. It cannot be brought back. Allow it only if that is what you want. Claude wrote: Clean up' },
    // an ordinary command, and a delete that loses nothing, keep what Claude wrote
    { command: 'ls -la', description: 'List files' },
    { command: 'rm -rf node_modules', description: 'Reinstall' },
  ])
})

test('with the question turned off in config.js, the description is left as Claude wrote it', async ($, on) => {
  const seen = shown(on, 'window.__aiWorkerConfig = { "askBeforeDestructive": false };')
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await call($, 'rm -rf src', 'Clean up')
  expect(seen).toEqual([{ command: 'rm -rf src', description: 'Clean up' }])
})
