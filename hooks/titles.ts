// The chat's title, renewed as the talk moves on: what this session knows about it, and when a fresh one is due. Asking the model for
// it stays in register.tsx; everything here is pure, on one state object.
// Tiêu đề cuộc trò chuyện, làm mới khi cuộc nói chuyện đi tiếp: những gì phiên này biết về nó, và khi nào tới lúc làm tiêu đề mới.
// Việc nhờ mô hình đặt tiêu đề ở lại register.tsx; mọi thứ ở đây là thuần, trên một đối tượng trạng thái.

/** A first fresh title after a few prompts, then one every ten. */
/** Tiêu đề mới đầu tiên sau vài lời nhắc, rồi cứ mười lời nhắc một lần. */
export const RETITLE_FIRST = 4
export const RETITLE_EVERY = 10

/**
 * `session`: the chat's title as the app shows it, '' until an event brings one. `recent`: the person's recent prompts (clipped), the
 * source for a fresh title, and `count` how many there were. `auto`: the last title this plugin set; `pending`: a new one waiting for the
 * next prompt to apply it. `off`: the person renamed the chat themselves, so their title is never overwritten.
 */
/** `session`: tiêu đề cuộc trò chuyện như app hiển thị, '' cho tới khi một sự kiện mang tới. `recent`: các lời nhắc gần đây của người dùng (đã cắt ngắn), nguồn cho tiêu đề mới, và `count` là số lời nhắc. `auto`: tiêu đề cuối cùng plugin này đặt; `pending`: tiêu đề mới đang chờ lời nhắc kế tiếp để áp dụng. `off`: người dùng đã tự đổi tên, nên tiêu đề của họ không bao giờ bị ghi đè. */
export type Titles = { session: string; recent: string[]; count: number; auto: string; pending: string; off: boolean }

export function newTitles(): Titles {
  return { session: '', recent: [], count: 0, auto: '', pending: '', off: false }
}

/** Whether to ask for a fresh title now. */
/** Có nên xin một tiêu đề mới lúc này không. */
export function titleDue(t: Titles): boolean {
  if (t.off || !t.recent.length) return false
  return t.count === RETITLE_FIRST || (t.count > RETITLE_FIRST && (t.count - RETITLE_FIRST) % RETITLE_EVERY === 0)
}

/** The model's answer as a title: its first line, without quotes, marks or a full stop, at most 60 characters. */
/** Câu trả lời của mô hình thành tiêu đề: dòng đầu, bỏ ngoặc kép, dấu và dấu chấm cuối, tối đa 60 ký tự. */
export function cleanTitle(answer: string): string {
  return answer.split('\n')[0]!.replace(/^["'“”\s#*-]+|["'“”\s.]+$/g, '').slice(0, 60)
}

/** A title an event brought, on one line and at most 80 characters; '' for anything else. */
/** Tiêu đề một sự kiện mang tới, trên một dòng và tối đa 80 ký tự; '' cho mọi thứ khác. */
export function chatTitle(raw: unknown): string {
  return typeof raw === 'string' ? raw.replace(/\s+/g, ' ').trim().slice(0, 80) : ''
}

/** A title shown other than the one this plugin set means the person renamed the chat. */
/** Tiêu đề đang hiện khác với tiêu đề plugin này đặt nghĩa là người dùng đã đổi tên cuộc trò chuyện. */
export function noteRename(t: Titles, shown: unknown) {
  if (t.auto && typeof shown === 'string' && shown && shown !== t.auto) t.off = true
}

/** Keeps a prompt the person wrote (not a slash command) for the next title: the last six, each clipped. */
/** Giữ một lời nhắc người dùng viết (không phải lệnh gạch chéo) cho tiêu đề sau: sáu lời nhắc gần nhất, mỗi lời cắt ngắn. */
export function notePrompt(t: Titles, prompt: unknown) {
  if (typeof prompt === 'string' && prompt.trim() && !prompt.trim().startsWith('/')) {
    t.recent = [...t.recent, prompt.replace(/\s+/g, ' ').trim().slice(0, 240)].slice(-6)
    t.count++
  }
}

/** The title waiting to be applied, taken once; undefined when there is none or the person renamed the chat. */
/** Tiêu đề đang chờ áp dụng, lấy một lần; undefined khi không có hoặc người dùng đã đổi tên. */
export function nextTitle(t: Titles): string | undefined {
  if (t.off || !t.pending) return undefined
  const title = t.pending
  t.pending = ''
  t.auto = title
  return title
}
