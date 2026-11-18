import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { commitIn, commitQuestion, diffCommand, secretsInDiff } from '../hooks/commitscan'

type Engine = Parameters<TestBody>[0]

// key-shaped values put together here, so this file holds none a scanner would flag
// giá trị có hình dạng khoá ghép ở đây, để file này không chứa giá trị nào bị máy quét bắt
const GITHUB = 'gh' + 'p_' + 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8'
const PASS = 'DB_PASS' + 'WORD'

test('the git commit in a command line, its folder and whether it takes every changed file', () => {
  expect(commitIn('git commit -m "fix"')).toEqual({ dir: '', all: false })
  expect(commitIn('git add . && git commit -am "fix"')).toEqual({ dir: '', all: true })
  expect(commitIn('cd ~/work/app && git commit --all -m x')).toEqual({ dir: '~/work/app', all: true })
  expect(commitIn('git -C server commit -m "-a is in the message"')).toEqual({ dir: 'server', all: false })
  expect(commitIn('git commit --amend --no-edit')).toEqual({ dir: '', all: false })
  expect(commitIn('git status && git log -1')).toBeUndefined()
  expect(commitIn('echo "git commit"')).toBeUndefined()
  expect(diffCommand({ dir: '', all: false })).toContain('--cached')
  expect(diffCommand({ dir: '', all: true })).toContain('HEAD')
})

test('only the lines a commit adds are read, with the file and the line in the new file', () => {
  const diff = [
    'diff --git a/config/.env b/config/.env',
    '--- a/config/.env',
    '+++ b/config/.env',
    '@@ -3,0 +4,2 @@',
    '+PORT=8080',
    `+${PASS}=s3cretValue99`,
    'diff --git a/app.py b/app.py',
    '--- a/app.py',
    '+++ b/app.py',
    '@@ -10 +10 @@',
    `-token = "${GITHUB}"`,
    '+token = os.getenv("GITHUB_TOKEN")',
    'diff --git a/old.txt b/old.txt',
    '--- a/old.txt',
    '+++ /dev/null',
    '@@ -1 +0,0 @@',
    `-${GITHUB}`,
  ].join('\n')
  const found = secretsInDiff(diff)
  expect(found.map(s => [s.file, s.line, s.kind])).toEqual([['config/.env', 5, 'password or key in a .env line']])
  const asked = commitQuestion(found)
  expect(asked).toContain('config/.env line 5')
  expect(asked).toContain('stays in the history')
  expect(asked).not.toContain('s3cretValue99')
})

/** A session whose `git diff` prints `diff`: returns the verdict for `command` and the argv git was run with. */
async function checkCommit($: Engine, on: On, command: string, diff: string) {
  mock.clock(on)
  mock.store(on)
  mock.env(on, { HOME: '/Users/an' })
  const ran: { argv: readonly string[]; cwd?: string }[] = []
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('process.run', (_, e) => {
    ran.push({ argv: e.argv, cwd: e.init?.cwd })
    return { value: { exitCode: 0, stdout: e.argv[0] === 'git' ? diff : '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.check', () => ({ decision: 'allow' as const }))
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const verdict = await $.tool.check({ tool: 'Bash', input: { command } })
  return { verdict, git: ran.filter(r => r.argv[0] === 'git') }
}

test('a commit that adds a secret is put to the person, even where the rules allow it', async ($, on) => {
  const diff = ['+++ b/.env', '@@ -0,0 +1 @@', `+API_TOKEN=${GITHUB}`].join('\n')
  const { verdict, git } = await checkCommit($, on, 'cd ~/app && git commit -m "add config"', diff)
  expect(verdict.decision).toBe('ask')
  expect(String((verdict as { reason?: string }).reason)).toContain('.env line 1')
  expect(git[0]!.argv).toContain('--cached')
  expect(git[0]!.cwd).toBe('/Users/an/app')
})

test('a commit with nothing secret goes on as the rules say', async ($, on) => {
  const { verdict } = await checkCommit($, on, 'git commit -m "docs"', ['+++ b/README.md', '@@ -1 +1 @@', '+Read me first.'].join('\n'))
  expect(verdict.decision).toBe('allow')
})
