// The few ways out of a hook module that are not pure: the plugin's store and the network. register.tsx hands them in from `$`;
// tests hand in fakes. A module that takes these instead of `$` can be tested without the engine.
// Vài lối ra không thuần của một module hook: kho của plugin và mạng. register.tsx đưa chúng vào từ `$`;
// test đưa vào bản giả. Module nhận chúng thay cho `$` thì test được mà không cần engine.

/** The plugin's store, shared by every session on this computer. */
/** Kho của plugin, dùng chung cho mọi phiên trên máy này. */
export type Store = { get(k: string): Promise<unknown>; set(k: string, v: unknown): Promise<void>; delete(k: string): Promise<void> }

/** An answer over the network; `headers` with lower-case names. */
/** Một câu trả lời qua mạng; `headers` với tên viết thường. */
export type Answer = { ok: boolean; status: number; headers?: Record<string, string>; text: string }

/** One request; it rejects when no answer came at all. */
/** Một yêu cầu; nó báo lỗi khi không có câu trả lời nào. */
export type Fetch = (url: string, init: { method: string; headers: Record<string, string>; body?: string }) => Promise<Answer>
