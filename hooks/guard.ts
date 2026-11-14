// A safety net for the few shell commands that destroy work and cannot be undone: deleting a whole folder,
// throwing away unsaved changes, overwriting the shared git server, deleting untracked files.
// When a rule or the permission mode already lets such a command through, the plugin asks the person in plain
// words first. It reads the command as text, so it catches the common forms, not every way to delete something.
// Lưới an toàn cho vài lệnh shell phá huỷ công việc và không hoàn tác được: xoá cả thư mục,
// bỏ các thay đổi chưa lưu, ghi đè máy chủ git dùng chung, xoá file chưa được theo dõi.
// Khi một quy tắc hay chế độ quyền đã cho lệnh như vậy đi qua, plugin hỏi người dùng bằng lời thường trước.
// Nó đọc lệnh dưới dạng chữ, nên bắt được các dạng phổ biến, không phải mọi cách xoá.
import { tx } from './lang'

export type Danger = { kind: 'delete-folder' | 'reset-hard' | 'force-push' | 'clean'; target: string }

// folders a build makes again, and the system's temporary folders: deleting them loses nothing
// các thư mục mà một lần build sẽ tạo lại, và thư mục tạm của hệ thống: xoá chúng không mất gì
const SAFE_NAMES = new Set(['node_modules', 'dist', 'build', 'out', '.next', '.cache', '.turbo', '__pycache__', '.pytest_cache', 'coverage'])
const SAFE_ROOTS = /^(\/private)?\/tmp\/.|^\/var\/folders\/./
const PREFIXES = new Set(['sudo', 'command', 'time', 'nohup', 'exec', 'env', 'xargs'])
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash'])
const WINDOWS_DELETERS = new Set(['remove-item', 'ri', 'del', 'erase', 'rd', 'rmdir'])

/** A command line cut into its commands (at `;`, `&&`, `||`, `|`, a new line), each cut into words; quotes keep a word whole. */
/** Một dòng lệnh cắt thành từng lệnh (ở `;`, `&&`, `||`, `|`, xuống dòng), mỗi lệnh cắt thành từng từ; dấu nháy giữ nguyên một từ. */
export function shellWords(command: string): string[][] {
  const lines: string[][] = [[]]
  let word = ''
  let has = false
  let quote = ''
  const flush = () => {
    if (has) lines[lines.length - 1]!.push(word)
    word = ''
    has = false
  }
  for (let i = 0; i < command.length; i++) {
    const c = command[i]!
    if (quote) {
      if (c === quote) quote = ''
      else word += c
      continue
    }
    if (c === '"' || c === "'") {
      quote = c
      has = true
    } else if (c === ';' || c === '\n' || c === '|' || (c === '&' && command[i + 1] === '&')) {
      flush()
      lines.push([])
      if (command[i + 1] === c) i++
    } else if (/\s/.test(c)) {
      flush()
    } else {
      word += c
      has = true
    }
  }
  flush()
  return lines.filter(l => l.length)
}

const base = (word: string) => word.split(/[\\/]/).pop() ?? word

/** Whether deleting this path loses nothing: a build folder by name, or something under the system's temporary folder. */
/** Xoá đường dẫn này có không mất gì hay không: một thư mục build theo tên, hoặc thứ nằm trong thư mục tạm của hệ thống. */
function isSafeTarget(target: string): boolean {
  const path = target.replace(/[\\/]\*$/, '').replace(/[\\/]+$/, '')
  if (!path || /(^|[\\/])\.\.([\\/]|$)/.test(path) || /[$~*?`]/.test(path)) return false
  return SAFE_ROOTS.test(path) || SAFE_NAMES.has(base(path))
}

function inGit(words: string[]): Danger | undefined {
  // skip git's own options before the subcommand: -C <path>, -c <name=value>, --git-dir=...
  // bỏ qua các tuỳ chọn của chính git đứng trước lệnh con: -C <path>, -c <name=value>, --git-dir=...
  let i = 0
  while (i < words.length && words[i]!.startsWith('-')) i += words[i] === '-C' || words[i] === '-c' ? 2 : 1
  const rest = words.slice(i + 1)
  const short = (letter: string) => rest.some(w => /^-[A-Za-z]+$/.test(w) && w.includes(letter))
  switch (words[i]) {
    case 'reset':
      return rest.includes('--hard') ? { kind: 'reset-hard', target: '' } : undefined
    case 'push':
      // --force-with-lease refuses when someone else pushed in between: it is the careful form
      // --force-with-lease từ chối khi có người khác vừa đẩy lên: đó là dạng cẩn thận
      return rest.includes('--force') || short('f') || rest.some(w => /^\+[^+]/.test(w)) ? { kind: 'force-push', target: rest.filter(w => !w.startsWith('-')).join(' ') } : undefined
    case 'clean':
      return (rest.includes('--force') || short('f')) && !rest.includes('--dry-run') && !short('n') ? { kind: 'clean', target: '' } : undefined
    default:
      return undefined
  }
}

function inOne(words: string[]): Danger | undefined {
  let i = 0
  while (i < words.length && (PREFIXES.has(words[i]!) || /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i]!))) i++
  const program = base(words[i] ?? '').toLowerCase()
  const rest = words.slice(i + 1)
  if (program === 'git') return inGit(rest)
  // sh -c "…": the command to look at is the quoted one
  // sh -c "…": lệnh cần xem là lệnh nằm trong dấu nháy
  if (SHELLS.has(program)) {
    const c = rest.indexOf('-c')
    return c >= 0 && rest[c + 1] ? destructiveCommand(rest[c + 1]!) : undefined
  }
  // find … -exec rm -rf {} +, and the like: the deleting program sits further along
  // find … -exec rm -rf {} +, và tương tự: chương trình xoá nằm ở phía sau
  const at = program === 'rm' ? i : words.findIndex((w, n) => n > i && base(w) === 'rm' && /^-exec/.test(words[n - 1] ?? ''))
  if (at >= 0) {
    const after = words.slice(at + 1)
    const flags = after.filter(w => w.startsWith('-'))
    if (!flags.some(w => w === '--recursive' || /^-[A-Za-z]*[rR]/.test(w))) return undefined
    const targets = after.filter(w => !w.startsWith('-') && w !== '+' && w !== ';')
    const unsafe = targets.find(t => !isSafeTarget(t))
    return unsafe !== undefined || !targets.length ? { kind: 'delete-folder', target: unsafe ?? '' } : undefined
  }
  if (WINDOWS_DELETERS.has(program)) {
    // rmdir alone only removes an empty folder; -Recurse or /s takes everything inside
    // rmdir một mình chỉ xoá thư mục rỗng; -Recurse hoặc /s lấy đi mọi thứ bên trong
    if (!rest.some(w => /^-r/i.test(w) || /^\/s$/i.test(w))) return undefined
    const targets = rest.filter(w => !/^[-/][A-Za-z]+$/.test(w))
    const unsafe = targets.find(t => !isSafeTarget(t))
    return unsafe !== undefined || !targets.length ? { kind: 'delete-folder', target: unsafe ?? '' } : undefined
  }
  return undefined
}

/** The first thing in a command line that destroys work, or undefined when there is none. */
/** Thứ đầu tiên trong một dòng lệnh phá huỷ công việc, hoặc undefined khi không có. */
export function destructiveCommand(command: string): Danger | undefined {
  for (const words of shellWords(command)) {
    const found = inOne(words)
    if (found) return found
  }
  return undefined
}

/** The question put to the person, in plain words: what is about to happen and that it cannot be undone. */
/** Câu hỏi đưa cho người dùng, bằng lời thường: điều gì sắp xảy ra và rằng nó không hoàn tác được. */
export function dangerQuestion(d: Danger): string {
  switch (d.kind) {
    case 'delete-folder':
      return d.target
        ? tx('Claude is about to delete a whole folder and everything in it: {target}. It cannot be brought back. Let it run?', { target: d.target })
        : tx('Claude is about to delete whole folders and everything in them. They cannot be brought back. Let it run?')
    case 'reset-hard':
      return tx('Claude is about to throw away every change in this project that is not saved in git yet (git reset --hard). They cannot be brought back. Let it run?')
    case 'force-push':
      return tx('Claude is about to overwrite what is on the shared git server with what is on this computer (git push --force). Work that others put there can be lost. Let it run?')
    case 'clean':
      return tx('Claude is about to delete every file in this project that git does not track (git clean). They cannot be brought back. Let it run?')
  }
}

/** What Claude is told when the person said no, or nobody was there to ask. */
/** Điều Claude được báo khi người dùng nói không, hoặc không có ai để hỏi. */
export function dangerRefusal(): string {
  return tx('The person did not allow this command: it destroys work that cannot be brought back. Do not run it, and do not reach the same result another way. Tell them what you wanted to do and why, then wait for their answer.')
}
