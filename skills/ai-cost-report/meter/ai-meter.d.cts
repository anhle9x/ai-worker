// Types for ai-meter.cjs, so a TypeScript project gets checking and completion. Copy it next to ai-meter.cjs (TypeScript looks for this name).
// Kiểu cho ai-meter.cjs, để dự án TypeScript được kiểm và gợi ý. Chép file này cạnh ai-meter.cjs (TypeScript tìm đúng tên này).
//
//   import { Meter } from './ai-meter.cjs'
//   const meter = new Meter({ file: 'ai-meter.jsonl' })
//   const answer = await meter.turn(async (t) => { const r = await client.messages.create(...); t.record(r); return r })

/** Token counts of one call. input is billed at the normal price, without cache reads and writes. */
/** Số token của một lần gọi. input là đầu vào tính giá thường, không gồm đọc và ghi cache. */
export interface Counts {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  cacheWriteLong: number
}

export interface RecordOptions {
  /** A short lowercase name such as "deepseek"; needed when the answer does not tell. */
  /** Tên ngắn chữ thường như "deepseek"; cần khi câu trả lời không cho biết. */
  provider?: string
  model?: string
  /** This call repeats one that failed. */
  /** Lần gọi này lặp lại một lần đã lỗi. */
  retry?: boolean
}

export interface CountNumbers {
  /** Leave input or output out when the answer carried no token counts: the call is then "not measured", never zero. */
  /** Bỏ trống input hay output khi câu trả lời không kèm số token: lần gọi đó là "không đo được", không bao giờ là 0. */
  input?: number | null
  output?: number | null
  cacheRead?: number
  cacheWrite?: number
  cacheWriteLong?: number
  retry?: boolean
}

export type Outcome = 'ok' | 'error' | 'timeout'

export interface MeterOptions {
  /** Default "ai-meter.jsonl"; AI_METER_FILE wins. */
  /** Mặc định "ai-meter.jsonl"; AI_METER_FILE được ưu tiên. */
  file?: string
  /** Default "prod"; AI_METER_ENV wins. */
  /** Mặc định "prod"; AI_METER_ENV được ưu tiên. */
  env?: 'prod' | 'test'
  /** Write each line at once instead of in the background. */
  /** Ghi từng dòng ngay thay vì ở nền. */
  sync?: boolean
  /** https://<board domain>/projects/ingest; AI_METER_URL wins. */
  sendUrl?: string
  /** The prj_… key made on the board's Admin page; AI_METER_KEY wins. Only on the project's server. */
  /** Khoá prj_… tạo trên trang Quản trị của bảng; AI_METER_KEY được ưu tiên. Chỉ đặt trên máy chủ của dự án. */
  sendKey?: string
}

/** One user turn: every LLM call made to answer it. */
/** Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. */
export class Turn {
  outcome: Outcome
  /** Counts one LLM call from the provider's answer (or its usage). */
  /** Đếm một lần gọi LLM từ câu trả lời (hay usage) của hãng. */
  record(response: unknown, opts?: RecordOptions): void
  /** Counts one LLM call from numbers read by hand, for any provider. */
  /** Đếm một lần gọi LLM từ số tự đọc, cho hãng bất kỳ. */
  count(provider: string, model: string, numbers?: CountNumbers): void
  /** Counts one LLM call that failed. Pass no error text. */
  /** Đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi. */
  fail(provider: string, model: string, opts?: { retry?: boolean }): void
  /** Marks the first streamed piece of the answer. */
  /** Đánh dấu mẩu đầu tiên của câu trả lời khi streaming. */
  firstToken(): void
  /** Writes the line; meter.turn(fn) calls it for you. */
  /** Ghi dòng; meter.turn(fn) tự gọi. */
  end(outcome?: Outcome): void
}

export class Meter {
  readonly file: string
  readonly env: 'prod' | 'test'
  readonly off: boolean
  constructor(opts?: MeterOptions)
  /** A turn to end yourself with end(). */
  /** Một lượt tự kết thúc bằng end(). */
  start(): Turn
  /** Runs fn(turn), writes the line when it ends, and returns or rethrows what fn did. */
  /** Chạy fn(turn), ghi dòng khi xong, và trả về hay ném lại đúng điều fn làm. */
  turn<T>(fn: (t: Turn) => T | Promise<T>): Promise<T>
  /** The background sender, when sendUrl and sendKey are set; flush() sends what is waiting now. */
  /** Phần gửi ở nền, khi có sendUrl và sendKey; flush() gửi ngay những gì đang chờ. */
  readonly sender: { flush(): Promise<void> } | null
}

/** Reads the provider, the model and the counts of an answer; counts is null when it carries no usage. */
/** Đọc hãng, model và số đếm của một câu trả lời; counts là null khi không có usage. */
export function readUsage(response: unknown, provider?: string): { provider?: string; model?: string; counts: Counts | null }

export const VERSION: number
