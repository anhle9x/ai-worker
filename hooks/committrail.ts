// A commit message a reader can trust a month later: what kind of change it is, and for a fix the proven cause and for a fix,
// feature, speed or security change the command that was run and what it showed. Checked after Claude commits, when the
// computer's config.js turns it on ("commitTrail": true); Claude is reminded to amend the message, the commit is never held
// back. The rules come from commit-trail in kennetvn/nextcore-skills (MIT), without its demand for an issue number. Pure.
// Một lời commit người đọc tin được sau một tháng: thay đổi thuộc loại gì, với commit sửa lỗi thì nguyên nhân đã chứng minh,
// với sửa lỗi, tính năng, tốc độ hay bảo mật thì lệnh đã chạy và kết quả của nó. Được kiểm sau khi Claude commit, khi config.js
// của máy bật nó ("commitTrail": true); Claude được nhắc sửa lời commit, commit không bao giờ bị giữ lại. Các luật lấy từ
// commit-trail trong kennetvn/nextcore-skills (MIT), bỏ yêu cầu ghi số issue. Mã thuần.
import { tx } from './lang'

const TYPES = ['feat', 'fix', 'perf', 'refactor', 'docs', 'chore', 'test', 'ci', 'build', 'style', 'security', 'release', 'revert']
// the kinds of change that must show what was measured
// các loại thay đổi phải cho thấy đã đo được gì
const FULL = new Set(['fix', 'feat', 'perf', 'security'])

/** The value of a `Name:` line of the body, with the indented or bulleted lines that follow it; null when there is none. */
/** Giá trị của một dòng `Name:` trong thân, kèm các dòng thụt vào hay gạch đầu dòng theo sau; null khi không có. */
function field(lines: string[], name: string): string | null {
  const start = new RegExp(`^${name}\\s*:`, 'i')
  const i = lines.findIndex(l => start.test(l))
  if (i < 0) return null
  const out = [lines[i]!.replace(new RegExp(`^${name}\\s*:\\s*`, 'i'), '')]
  for (const l of lines.slice(i + 1)) {
    if (!l.trim() || /^[A-Z][\w·\- ]{1,30}:\s/.test(l) || !/^(\s+|- )/.test(l)) break
    out.push(l.trim())
  }
  return out.join(' ').trim()
}

/** What the message lacks, each as one short line for Claude; none for a good message, a merge, a revert or a fixup. */
/** Lời commit còn thiếu gì, mỗi thứ một dòng ngắn cho Claude; không có gì với lời commit tốt, merge, revert hay fixup. */
export function trailProblems(message: string): string[] {
  const lines = message.replace(/\r/g, '').split('\n').filter(l => !l.startsWith('#'))
  const subject = (lines[0] ?? '').trim()
  if (!subject || /^(Merge |fixup! |squash! |amend! |Revert ")/.test(subject)) return []
  const problems: string[] = []
  const m = /^([a-z]+)(\([^)]*\))?!?: \S/.exec(subject)
  const type = m?.[1]
  if (!m || !TYPES.includes(type!)) problems.push(tx('the subject is not "type(scope): summary" with a type from: {types}', { types: TYPES.join(' ') }))
  if (subject.length > 72) problems.push(tx('the subject has {n} characters, keep it at most 72', { n: subject.length }))
  if (subject.endsWith('.')) problems.push(tx('the subject ends with a period'))
  if (!type || !FULL.has(type)) return problems
  const body = lines.slice(1)
  if (type === 'fix') {
    const cause = field(body, 'Root cause')
    if (!cause || cause.length < 8 || /^(unknown|n\/?a|-|tbd)\.?$/i.test(cause)) {
      problems.push(tx('a fix needs a "Root cause:" line with the proven cause (file:line), or "unknown — hypothesis: …"'))
    }
  }
  const measured = field(body, 'Measured')
  if (measured === null) problems.push(tx('a {type} commit needs a "Measured:" line with the command that was run, in backticks, and its real result', { type }))
  else if (/^not run\b/i.test(measured)) {
    if (measured.length < 16) problems.push(tx('"Measured: not run" needs the reason, as in "not run — needs the production mailbox"'))
  } else if (!/`[^`]+`/.test(measured) && !/\d/.test(measured)) {
    problems.push(tx('"Measured: {what}" cannot be checked: give the command in backticks and its number', { what: measured.slice(0, 40) }))
  }
  return problems
}

/** What Claude reads after its commit when the message lacks something. */
/** Điều Claude đọc sau khi commit khi lời commit còn thiếu gì đó. */
export function trailNote(problems: string[]): string {
  return tx('ai-worker (commitTrail): the commit just made has a message that lacks: {list}. Amend the message with git commit --amend (only if it is not pushed yet), keeping what it says and adding what is missing; never invent a result you did not see. The shape: "fix(scope): summary", then lines "Root cause: …" (a fix), "Measured: `command` → result" (fix, feat, perf, security).', { list: problems.join('; ') })
}
