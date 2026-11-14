// The handoff notes earlier sessions left on this computer, told to Claude when a session starts.
// The handoff skill writes a note so the next session can carry on; without this list a new session does not know
// any note exists, and the person has to explain where to look. Only names and dates are given, never a note's text.
// Các ghi chú bàn giao mà những phiên trước để lại trên máy này, báo cho Claude khi một phiên bắt đầu.
// Skill handoff ghi một ghi chú để phiên sau làm tiếp; thiếu danh sách này thì phiên mới không biết
// có ghi chú nào, và người dùng phải giải thích chỗ tìm. Chỉ đưa tên và ngày, không bao giờ đưa nội dung ghi chú.
import { tx } from './lang'

export type HandoffNote = { name: string; at: number }

export const HANDOFF_MAX = 5

// A note's name from its file name, or undefined when it is not a note the skill would write: the skill names tasks in
// plain lower-case words with hyphens, so a file name carrying anything else is not put in front of the model.
// Tên ghi chú lấy từ tên file, hoặc undefined khi đó không phải ghi chú mà skill sẽ viết: skill đặt tên việc bằng
// chữ thường không dấu nối bằng gạch ngang, nên tên file mang thứ gì khác thì không được đưa ra trước mô hình.
export function noteName(fileName: string): string | undefined {
  const m = /^([a-z0-9][a-z0-9._-]{0,59})\.md$/.exec(fileName)
  return m ? m[1] : undefined
}

/** The newest few notes, newest first. */
/** Vài ghi chú mới nhất, mới nhất đứng đầu. */
export function newestNotes(all: HandoffNote[]): HandoffNote[] {
  return [...all].sort((a, b) => b.at - a.at || a.name.localeCompare(b.name)).slice(0, HANDOFF_MAX)
}

const day = (at: number) => {
  const d = new Date(at)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`
}

/** What the session is told about the notes, or undefined when there is none: a computer with no note adds nothing. */
/** Điều phiên được báo về các ghi chú, hoặc undefined khi không có ghi chú nào: máy không có ghi chú thì không thêm gì. */
export function handoffSection(notes: HandoffNote[], folder: string): string | undefined {
  if (!notes.length) return undefined
  return [
    tx('# Handoff notes on this computer'),
    tx('Earlier sessions left these notes, newest first: {list}.', { list: notes.map(n => `${n.name} (${day(n.at)})`).join(', ') }),
    tx('Each is the file <name>.md in {folder}.', { folder }),
    tx('When the user asks to continue one of these tasks, read its note before anything else. When they say to continue without saying which task, ask which one and name these. Do not read a note for any other reason, and do not bring this list up by yourself.'),
  ].join('\n')
}
