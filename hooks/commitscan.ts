// A commit that would put a key, a token or a password into git: once in git, it stays in the history and goes wherever
// the repository is pushed, even after a later commit takes it out. Before Claude runs `git commit`, the lines the commit
// adds are read for secrets; a commit that holds one is put to the person first. Pure: the caller runs git.
// Một commit sẽ đưa khoá, token hay mật khẩu vào git: đã vào git thì nó ở lại trong lịch sử và đi theo repo tới mọi nơi
// repo được đẩy lên, kể cả khi commit sau bỏ nó đi. Trước khi Claude chạy `git commit`, các dòng commit thêm vào được đọc
// để tìm bí mật; commit có bí mật thì được đưa người dùng xem trước. Mã thuần: bên gọi tự chạy git.
import { shellWords } from './guard'
import { tx } from './lang'
import { findSecrets, secretLabel } from './secrets'

export type CommitRun = { dir: string; all: boolean }
export type CommitSecret = { file: string; line: number; kind: string; hint: string }

/** The `git commit` in a command line: the folder it runs in (from `cd` or `git -C`, relative to the session's), and whether it takes every changed tracked file (`-a`). */
/** Lệnh `git commit` trong một dòng lệnh: thư mục nó chạy (từ `cd` hay `git -C`, so với thư mục của phiên), và nó có lấy mọi file đã theo dõi bị đổi không (`-a`). */
export function commitIn(command: string): CommitRun | undefined {
  let dir = ''
  for (const words of shellWords(command)) {
    if (words[0] === 'cd' && words[1]) {
      dir = join(dir, words[1])
      continue
    }
    if (words[0] !== 'git') continue
    let i = 1
    let here = dir
    // git's own options before the subcommand
    // các tuỳ chọn của chính git đứng trước lệnh con
    while (i < words.length && words[i]!.startsWith('-')) {
      const w = words[i]!
      if (w === '-C' && words[i + 1]) {
        here = join(here, words[i + 1]!)
        i += 2
      } else if (w === '-c') i += 2
      else i++
    }
    if (words[i] !== 'commit') continue
    const rest = words.slice(i + 1)
    // -m takes the next word as the message, so "-a" in a message is not the flag
    // -m lấy từ kế tiếp làm lời commit, nên "-a" trong lời commit không phải là cờ
    let all = false
    for (let j = 0; j < rest.length; j++) {
      const w = rest[j]!
      if (w === '--') break
      if (w === '-m' || w === '-F' || w === '-C' || w === '-c' || w === '--message' || w === '--file' || w === '--author' || w === '--date') {
        j++
        continue
      }
      if (w === '--all' || /^-[a-zA-Z]*a[a-zA-Z]*$/.test(w)) all = true
    }
    return { dir: here, all }
  }
  return undefined
}

function join(base: string, next: string): string {
  if (next.startsWith('/') || next.startsWith('~') || /^[A-Za-z]:[\\/]/.test(next)) return next
  return base ? `${base.replace(/[\\/]+$/, '')}/${next}` : next
}

/** The git command that prints what the commit will add: what is staged, or with `-a` every change to a tracked file. */
/** Lệnh git in ra những gì commit sẽ thêm: phần đã stage, hoặc với `-a` mọi thay đổi ở file đã theo dõi. */
export function diffCommand(run: CommitRun): string[] {
  return ['git', 'diff', run.all ? 'HEAD' : '--cached', '--no-color', '--no-ext-diff', '--unified=0']
}

/** The secrets on the lines a diff adds, with the file and the line number in the new file; never the value. */
/** Các bí mật trên những dòng một diff thêm vào, kèm file và số dòng trong file mới; không bao giờ kèm giá trị. */
export function secretsInDiff(diff: string): CommitSecret[] {
  const out: CommitSecret[] = []
  let file = ''
  let line = 0
  for (const raw of diff.split('\n')) {
    if (raw.startsWith('+++ ')) {
      const path = raw.slice(4).trim()
      file = path === '/dev/null' ? '' : path.replace(/^b\//, '')
      continue
    }
    const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw)
    if (hunk) {
      line = Number(hunk[1])
      continue
    }
    if (raw.startsWith('+') && file) {
      for (const s of findSecrets(raw.slice(1))) if (out.length < 50) out.push({ file, line, kind: s.kind, hint: s.hint })
      line++
    }
  }
  return out
}

/** What the person is asked: which files hold what, and that git keeps it in the history for good. */
/** Điều người dùng được hỏi: file nào chứa gì, và git giữ nó trong lịch sử mãi mãi. */
export function commitQuestion(found: CommitSecret[]): string {
  const list = found.slice(0, 6).map(s => tx('{kind} in {file} line {line} ({hint})', { kind: secretLabel(s.kind), file: s.file, line: s.line, hint: s.hint }))
  const more = found.length > 6 ? ` ${tx('and {n} more', { n: found.length - 6 })}` : ''
  return tx('This commit puts what looks like a secret into git: {list}{more}. Once committed it stays in the history and goes wherever the repository is pushed, even if a later commit takes it out. Commit anyway?', { list: list.join('; '), more })
}
