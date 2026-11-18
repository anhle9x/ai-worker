// A safety net for the few shell commands that destroy work and cannot be undone: deleting a whole folder,
// throwing away unsaved changes, overwriting the shared git server, deleting untracked files.
// Such a command is put to a person in plain words, whatever the permission mode: an automatic approval does not
// answer for them. It reads the command as text, so it catches the common forms, not every way to delete something.
// Lưới an toàn cho vài lệnh shell phá huỷ công việc và không hoàn tác được: xoá cả thư mục,
// bỏ các thay đổi chưa lưu, ghi đè máy chủ git dùng chung, xoá file chưa được theo dõi.
// Lệnh như vậy được đưa cho một người trả lời bằng lời thường, ở mọi chế độ quyền: bước tự duyệt không trả lời thay họ.
// Nó đọc lệnh dưới dạng chữ, nên bắt được các dạng phổ biến, không phải mọi cách xoá.
import { tx } from './lang'

// and a few that put the whole computer at risk: a script downloaded and run at once, macOS's check on downloaded apps
// turned off, a disk written to or erased, a file opened to every user and program
// và vài lệnh đặt cả máy vào rủi ro: một script tải về rồi chạy ngay, tắt bước kiểm app tải về của macOS,
// ghi thẳng ra hay xoá một ổ đĩa, mở một file cho mọi người dùng và chương trình
export type Danger = { kind: 'delete-folder' | 'reset-hard' | 'force-push' | 'clean' | 'pipe-to-shell' | 'quarantine-off' | 'disk-write' | 'open-permissions'; target: string }

// folders a build makes again, and the system's temporary folders: deleting them loses nothing
// các thư mục mà một lần build sẽ tạo lại, và thư mục tạm của hệ thống: xoá chúng không mất gì
const SAFE_NAMES = new Set(['node_modules', 'dist', 'build', 'out', '.next', '.cache', '.turbo', '__pycache__', '.pytest_cache', 'coverage'])
const SAFE_ROOTS = /^(\/private)?\/tmp\/.|^\/var\/folders\/./
const PREFIXES = new Set(['sudo', 'command', 'time', 'nohup', 'exec', 'env', 'xargs'])
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash'])
const WINDOWS_DELETERS = new Set(['remove-item', 'ri', 'del', 'erase', 'rd', 'rmdir'])
const DISK_ERASERS = new Set(['erasedisk', 'erasevolume', 'zerodisk', 'randomdisk', 'secureerase', 'partitiondisk', 'reformat'])
// a download handed straight to a program that runs it: curl … | sh, wget -O- … | python, iwr … | iex
// một bản tải về được đưa thẳng cho chương trình chạy nó: curl … | sh, wget -O- … | python, iwr … | iex
const PIPE_TO_SHELL = /\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^;&\n|]*\|\s*(?:sudo\s+(?:-\S+\s+)*)?(?:sh|bash|zsh|dash|ksh|python3?|perl|ruby|node|iex|invoke-expression)\b/i
const RUN_DOWNLOAD = /\b(?:iex|invoke-expression)\b[^\n;]*\(\s*(?:iwr|irm|invoke-webrequest|invoke-restmethod|\(?\s*new-object\s+net\.webclient)/i
const FETCHED = /^\s*(?:\$\(|`|<\()\s*(?:curl|wget)\b/
const URL_IN = /https?:\/\/[^\s'"|;)]+/

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
    // bash -c "$(curl …)" and bash <(curl …): a downloaded script run as it arrives
    // bash -c "$(curl …)" và bash <(curl …): một script tải về được chạy ngay khi tới
    const fetched = rest.find(w => FETCHED.test(w))
    if (fetched) return { kind: 'pipe-to-shell', target: URL_IN.exec(rest.join(' '))?.[0] ?? '' }
    const c = rest.indexOf('-c')
    return c >= 0 && rest[c + 1] ? destructiveCommand(rest[c + 1]!) : undefined
  }
  if (program === 'xattr') {
    // removing com.apple.quarantine, or clearing every attribute (-c), lets a downloaded app skip macOS's check
    // gỡ com.apple.quarantine, hoặc xoá mọi thuộc tính (-c), cho app tải về bỏ qua bước kiểm của macOS
    const flags = rest.filter(w => /^-[A-Za-z]+$/.test(w)).join('')
    const targets = rest.filter(w => !w.startsWith('-') && w !== 'com.apple.quarantine')
    if ((flags.includes('d') && rest.includes('com.apple.quarantine')) || flags.includes('c')) return { kind: 'quarantine-off', target: targets.join(' ') }
    return undefined
  }
  if (program === 'spctl') return rest.some(w => /^--(master|global)-disable$/.test(w)) ? { kind: 'quarantine-off', target: 'Gatekeeper' } : undefined
  if (program === 'dd') {
    const out = rest.find(w => /^of=\/dev\//.test(w))
    return out ? { kind: 'disk-write', target: out.slice(3) } : undefined
  }
  if (/^mkfs(\.|$)/.test(program)) return { kind: 'disk-write', target: rest.filter(w => !w.startsWith('-')).pop() ?? '' }
  if (program === 'diskutil') return DISK_ERASERS.has((rest[0] ?? '').toLowerCase()) ? { kind: 'disk-write', target: rest.slice(1).join(' ') } : undefined
  if (program === 'chmod') {
    // 777 or 666, or write for "others" or "all": every user and program on the computer may change the file
    // 777 hay 666, hoặc quyền ghi cho "others" hay "all": mọi người dùng và chương trình trên máy đổi được file
    const open = rest.find(w => /^0?[0-7]?[67][67][67]$/.test(w) && /[2367]$/.test(w) || /^[ugo]*[ao][ugo]*[+=][rwxXst]*w/.test(w))
    return open ? { kind: 'open-permissions', target: rest.filter(w => !w.startsWith('-') && w !== open).join(' ') } : undefined
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
  // a pipe joins two commands, so it is read on the line itself, with what is inside quotes left out (a commit message
  // that mentions curl | sh runs nothing); bash -c "…" is read again below, on its own
  // ống nối hai lệnh, nên được đọc trên chính dòng lệnh, bỏ qua phần trong dấu nháy (lời commit nhắc tới curl | sh
  // thì không chạy gì); bash -c "…" được đọc lại riêng ở dưới
  const bare = command.replace(/'[^']*'|"[^"]*"/g, '""')
  if (PIPE_TO_SHELL.test(bare) || RUN_DOWNLOAD.test(bare)) return { kind: 'pipe-to-shell', target: URL_IN.exec(command)?.[0] ?? '' }
  for (const words of shellWords(command)) {
    const found = inOne(words)
    if (found) return found
  }
  return undefined
}

// The note a destructive command carries into the permission box. The app's box shows the command's own description,
// the line Claude wrote for it, and not the reason a hook gives: so the warning takes that line's place, and what
// Claude wrote follows it.
// Lời ghi chú mà một lệnh phá huỷ mang vào hộp xin phép. Hộp của app hiện phần mô tả của chính lệnh,
// dòng Claude viết cho nó, chứ không hiện lý do mà một hook đưa ra: nên câu cảnh báo thế chỗ dòng đó,
// và điều Claude viết đi theo sau.
export function dangerNote(d: Danger, written: unknown): string {
  const note = typeof written === 'string' ? written.trim() : ''
  return note ? `${dangerQuestion(d)} ${tx('Claude wrote: {note}', { note })}` : dangerQuestion(d)
}

/** What the permission dialog tells the person, in plain words: what is about to happen and that it cannot be undone. */
/** Điều hộp xin phép nói với người dùng, bằng lời thường: điều gì sắp xảy ra và rằng nó không hoàn tác được. */
export function dangerQuestion(d: Danger): string {
  const only = tx('Allow it only if that is what you want.')
  switch (d.kind) {
    case 'delete-folder':
      return d.target
        ? `${tx('This deletes a whole folder and everything in it: {target}. It cannot be brought back.', { target: d.target })} ${only}`
        : `${tx('This deletes whole folders and everything in them. They cannot be brought back.')} ${only}`
    case 'reset-hard':
      return `${tx('This throws away every change in this project that is not saved in git yet (git reset --hard). They cannot be brought back.')} ${only}`
    case 'force-push':
      return `${tx('This overwrites what is on the shared git server with what is on this computer (git push --force). Work that others put there can be lost.')} ${only}`
    case 'clean':
      return `${tx('This deletes every file in this project that git does not track (git clean). They cannot be brought back.')} ${only}`
    case 'pipe-to-shell':
      return `${d.target ? tx('This downloads a script and runs it at once, without anyone reading it first: {target}. A changed script can do anything this computer allows.', { target: d.target }) : tx('This downloads a script and runs it at once, without anyone reading it first. A changed script can do anything this computer allows.')} ${only}`
    case 'quarantine-off':
      return `${d.target ? tx('This turns off macOS\'s check on a downloaded app (Gatekeeper), so it runs without Apple\'s warning: {target}.', { target: d.target }) : tx('This turns off macOS\'s check on downloaded apps (Gatekeeper), so they run without Apple\'s warning.')} ${only}`
    case 'disk-write':
      return `${tx('This writes straight to a disk or erases it: {target}. Everything on it can be lost.', { target: d.target || '?' })} ${only}`
    case 'open-permissions':
      return `${d.target ? tx('This lets every user and program on this computer change {target}.', { target: d.target }) : tx('This lets every user and program on this computer change these files.')} ${only}`
  }
}
