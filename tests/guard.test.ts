import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { dangerQuestion, destructiveCommand, shellWords } from '../hooks/guard'

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

test('the question says in plain words what is about to be lost', () => {
  expect(dangerQuestion({ kind: 'delete-folder', target: 'src' })).toContain('delete a whole folder and everything in it: src')
  expect(dangerQuestion({ kind: 'delete-folder', target: '' })).toContain('delete whole folders')
  expect(dangerQuestion({ kind: 'reset-hard', target: '' })).toContain('not saved in git yet')
  expect(dangerQuestion({ kind: 'force-push', target: 'origin main' })).toContain('shared git server')
  expect(dangerQuestion({ kind: 'clean', target: '' })).toContain('git does not track')
})

type Setup = { verdict: 'allow' | 'ask' | 'deny'; answer?: string; config?: string }

/** A computer where a shell command is about to run. `verdict` is what the engine itself decided; `answer` is what the person clicks. */
function computer(on: On, s: Setup) {
  const seen = { asked: [] as string[], ran: [] as string[] }
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
  // as the real engine answers: a check that carries the event's own fields beside the tool's input reads as "ask"
  on('tool.check', (_, e) => {
    const input = (e as unknown as { input?: Record<string, unknown> }).input ?? {}
    return { decision: 'tool' in input || 'tool_use_id' in input ? 'ask' : s.verdict } as never
  })
  on('tool.call', (_, e) => {
    const call = e as unknown as { tool: string; command?: string; questions?: { question: string }[] }
    if (call.tool === 'AskUserQuestion') {
      const question = call.questions![0]!.question
      seen.asked.push(question)
      if (s.answer === undefined) throw new Error('dismissed')
      return { result: { questions: call.questions, answers: { [question]: s.answer } } } as never
    }
    seen.ran.push(call.command ?? call.tool)
    return { result: 'ran' } as never
  })
  return seen
}

const bash = async ($: Engine, command: string) => (await $.tool.call({ tool: 'Bash', command } as never)) as unknown as { deny?: string; result?: string }

test('a folder delete that nothing would ask about is put to the person, and runs on a yes', async ($, on) => {
  const seen = computer(on, { verdict: 'allow', answer: 'Let it run' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await bash($, 'rm -rf src')
  expect(seen.asked.length).toBe(1)
  expect(seen.asked[0]).toContain('delete a whole folder and everything in it: src')
  expect(r.deny).toBe(undefined)
  expect(seen.ran).toEqual(['rm -rf src'])
})

test('on a no the command does not run, and Claude is told not to find another way', async ($, on) => {
  const seen = computer(on, { verdict: 'allow', answer: 'Do not run' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await bash($, 'git reset --hard')
  expect(seen.asked.length).toBe(1)
  expect(r.deny).toContain('did not allow this command')
  expect(r.deny).toContain('do not reach the same result another way')
  expect(seen.ran).toEqual([])
})

test('with nobody to answer, the command does not run', async ($, on) => {
  const seen = computer(on, { verdict: 'allow' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect((await bash($, 'git push --force')).deny).toContain('did not allow this command')
  expect(seen.ran).toEqual([])
})

test('when the engine is going to ask by itself, the plugin adds no second question', async ($, on) => {
  const seen = computer(on, { verdict: 'ask', answer: 'Do not run' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await bash($, 'rm -rf src')
  // what happens next is the engine's own question, not the plugin's
  expect(seen.asked).toEqual([])
})

test('an ordinary command, and a delete that loses nothing, run without a question', async ($, on) => {
  const seen = computer(on, { verdict: 'allow', answer: 'Do not run' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await bash($, 'ls -la')
  await bash($, 'rm -rf node_modules dist')
  expect(seen.asked).toEqual([])
  expect(seen.ran).toEqual(['ls -la', 'rm -rf node_modules dist'])
})

test('config.js can turn the question off for someone who writes code all day', async ($, on) => {
  const seen = computer(on, { verdict: 'allow', answer: 'Do not run', config: 'window.__aiWorkerConfig = { "askBeforeDestructive": false };' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await bash($, 'rm -rf src')
  expect(seen.asked).toEqual([])
  expect(seen.ran).toEqual(['rm -rf src'])
})
