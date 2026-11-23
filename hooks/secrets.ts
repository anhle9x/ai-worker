// Secrets in text that is about to leave this computer for ChatGPT or Gemini: keys, tokens, private keys, passwords in
// connection strings and in .env lines. A text that holds one is not sent, whatever the permission mode: Claude is told
// what was found and where, without the value, so it can take it out and send again. Pure: no sockets, no files.
// The patterns are the shapes of real credentials, kept narrow so ordinary code and words pass; the providers' own
// documentation examples (an AWS key that ends in EXAMPLE, and the like) pass too.
// Bí mật trong chữ sắp rời máy này sang ChatGPT hay Gemini: khoá, token, khoá riêng, mật khẩu trong chuỗi kết nối và
// trong dòng .env. Chữ có một thứ như vậy thì không được gửi, ở mọi chế độ quyền: Claude được báo đã thấy gì và ở đâu,
// không kèm giá trị, để bỏ nó đi rồi gửi lại. Mã thuần: không socket, không file.
// Các mẫu là hình dạng của thông tin đăng nhập thật, giữ hẹp để code và chữ bình thường đi qua; các ví dụ trong
// tài liệu của chính nhà cung cấp (khoá AWS kết thúc bằng EXAMPLE, và tương tự) cũng đi qua.
import { tx } from './lang'

export type Secret = { kind: string; line: number; hint: string }

const PATTERNS: [string, RegExp][] = [
  ['private key', /-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----/g],
  ['AWS access key', /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g],
  ['AWS secret key', /aws_secret_access_key["']?\s*[:=]\s*["']?[A-Za-z0-9/+=]{40}\b/gi],
  ['GitHub token', /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b/g],
  ['GitLab token', /\bglpat-[A-Za-z0-9_-]{20,}\b/g],
  ['Slack token', /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g],
  ['Anthropic API key', /\bsk-ant-[A-Za-z0-9_-]{20,}\b/g],
  ['OpenAI API key', /\bsk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b/g],
  ['Google API key', /\bAIza[0-9A-Za-z_-]{35}\b/g],
  ['Stripe key', /\b[rs]k_live_[0-9A-Za-z]{20,}\b/g],
  ['Telegram bot token', /\b\d{8,10}:AA[A-Za-z0-9_-]{30,40}\b/g],
  ['JSON web token', /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g],
  ['password in a connection string', /\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqps?|mssql|sqlserver):\/\/[^\s:/@]+:[^\s@/]{3,}@/gi],
  // a .env-style setting anywhere in a line: an upper-case name that says password, secret, token or key, then = (or : and a
  // quote, as in JSON and YAML), and a value that is not a placeholder, nor a read of the environment such as os.getenv(...)
  // một thiết lập kiểu .env ở bất cứ đâu trong dòng: tên viết hoa nói mật khẩu, bí mật, token hay khoá, rồi = (hoặc : và dấu
  // ngoặc kép, như trong JSON và YAML), và giá trị không phải chỗ trống để điền, cũng không phải lời đọc biến môi trường như os.getenv(...)
  ['password or key in a .env line', /(?<![A-Za-z0-9_])[A-Z][A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|_KEY|APIKEY)[A-Z0-9_]*(?:[ \t]*=[ \t]*["']?|["']?[ \t]*:[ \t]*["'])(?![<$%{]|x{4}|\*{4}|changeme|your[_-]|process\.env|import\.meta|os\.environ)(?=([^\s"'#()]{8,}))\1(?!\()/g],
]

// the providers' own published examples, and values that only stand for a secret
// các ví dụ do chính nhà cung cấp công bố, và giá trị chỉ đứng thay cho một bí mật
const EXAMPLE = /EXAMPLE|example|placeholder|dummy|redacted|REDACTED|\.\.\.|xxxxxxxx|XXXXXXXX/

// a constant declared in code whose value is a name made of words (camelCase or kebab-case, at most two digits at the
// end), as in const PACE_KEY = 'sharePace': the name of a stored setting, not a secret; a .env, JSON or YAML line has no
// declaration word, so it is still read in full
// một hằng khai báo trong code có giá trị là một cái tên ghép từ các chữ (camelCase hay kebab-case, tối đa hai chữ số ở
// cuối), như const PACE_KEY = 'sharePace': tên một ô lưu thiết lập, không phải bí mật; dòng .env, JSON hay YAML không có
// từ khai báo, nên vẫn được đọc đầy đủ
const DECLARED = /(?:^|[\s(;{])(?:const|let|var|val|final|static|readonly)\s+(?:[A-Za-z_][\w<>,[\]]*\s+)?$/
const WORDS_NAME = /^[a-z]+(?:[A-Z][a-z]+|-[a-z]+)+\d{0,2}$/
function isNameConstant(text: string, at: number, value: string | undefined): boolean {
  if (!value || !WORDS_NAME.test(value)) return false
  const lineStart = text.lastIndexOf('\n', at - 1) + 1
  return DECLARED.test(text.slice(lineStart, at))
}

/** Each secret found in the text: its kind, the line it is on (from 1), and a hint with no more than its first four characters. */
/** Mỗi bí mật tìm thấy trong chữ: loại của nó, dòng chứa nó (đếm từ 1), và một gợi ý không quá bốn ký tự đầu. */
export function findSecrets(text: string): Secret[] {
  const out: Secret[] = []
  if (typeof text !== 'string' || !text) return out
  for (const [kind, re] of PATTERNS) {
    re.lastIndex = 0
    for (let m = re.exec(text); m; m = re.exec(text)) {
      const value = m[0]
      if (!EXAMPLE.test(value) && !(kind.endsWith('.env line') && isNameConstant(text, m.index, m[1]))) {
        const line = text.slice(0, m.index).split('\n').length
        // a .env line shows its name, which says what kind of secret it is, and never its value
        // một dòng .env hiện tên của nó, tên nói loại bí mật, và không bao giờ hiện giá trị
        const name = /^([A-Z][A-Z0-9_]*)/.exec(value)?.[1]
        const hint = kind.endsWith('.env line') && name ? `${name}=…` : `${value.trim().slice(0, 4)}…`
        if (!out.some(s => s.line === line && s.kind === kind)) out.push({ kind, line, hint })
      }
      if (re.lastIndex === m.index) re.lastIndex++
    }
  }
  return out.sort((a, b) => a.line - b.line)
}

/** The kind of a secret in the person's language. */
/** Loại của một bí mật, bằng ngôn ngữ của người dùng. */
export function secretLabel(kind: string): string {
  switch (kind) {
    case 'private key': return tx('private key')
    case 'AWS access key': return tx('AWS access key')
    case 'AWS secret key': return tx('AWS secret key')
    case 'GitHub token': return tx('GitHub token')
    case 'GitLab token': return tx('GitLab token')
    case 'Slack token': return tx('Slack token')
    case 'Anthropic API key': return tx('Anthropic API key')
    case 'OpenAI API key': return tx('OpenAI API key')
    case 'Google API key': return tx('Google API key')
    case 'Stripe key': return tx('Stripe key')
    case 'Telegram bot token': return tx('Telegram bot token')
    case 'JSON web token': return tx('JSON web token')
    case 'password in a connection string': return tx('password in a connection string')
    case 'password or key in a .env line': return tx('password or key in a .env line')
    default: return kind
  }
}

/** Why text for a helper outside this computer is not sent: what was found and on which line, never the value itself. */
/** Lý do chữ gửi cho một trợ lý ngoài máy này không được gửi: đã thấy gì, ở dòng nào, không bao giờ kèm giá trị. */
export function secretRefusal(found: Secret[], worker: string): string {
  const list = found.slice(0, 8).map(s => tx('{kind} on line {line} ({hint})', { kind: secretLabel(s.kind), line: s.line, hint: s.hint }))
  const more = found.length > 8 ? ` ${tx('and {n} more', { n: found.length - 8 })}` : ''
  return tx('Not sent to {worker}: the text holds what looks like a secret: {list}{more}. Take it out, or put a placeholder such as <API_KEY> in its place, and send again. Nothing left this computer.', { worker, list: list.join('; '), more })
}
