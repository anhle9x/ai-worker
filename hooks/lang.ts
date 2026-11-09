// Display language of the plugin: English is the source text, lang.vi.ts holds the Vietnamese.
// Ngôn ngữ hiển thị của plugin: tiếng Anh là bản gốc, lang.vi.ts giữ bản tiếng Việt.
import { VI } from './lang.vi'

export type Lang = 'en' | 'vi'

export function pickLang(saved?: unknown, env: Record<string, string | undefined> = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}): Lang {
  const chosen = env.AI_WORKER_LANG || saved
  if (chosen === 'en' || chosen === 'vi') return chosen
  return /^vi(?![a-z])/i.test(env.LC_ALL || env.LC_MESSAGES || env.LANG || '') ? 'vi' : 'en'
}

let current: Lang = pickLang()

// register.tsx calls this once it has read language from user.json.
// register.tsx gọi hàm này sau khi đọc language trong user.json.
export function setLang(saved: unknown): void {
  current = pickLang(saved)
}

export function getLang(): Lang {
  return current
}

// tx('{n} sessions', { n: 2 }): text missing from the dictionary falls back to English.
// tx('{n} sessions', { n: 2 }): chữ chưa có trong từ điển thì hiện tiếng Anh.
export function tx(text: string, params?: Record<string, string | number>): string {
  const found = current === 'vi' && Object.hasOwn(VI, text) ? VI[text]! : text
  return params ? found.replace(/\{(\w+)\}/g, (all, name) => (name in params ? String(params[name]) : all)) : found
}

// The page cannot read user.json, so the plugin writes the language chosen on purpose into language.js. Empty follows the browser.
// Trang không đọc được user.json, nên plugin ghi ngôn ngữ đã chủ động chọn vào language.js. Để trống thì theo trình duyệt.
export function pageLanguageScript(chosen: unknown): string {
  const lang = chosen === 'en' || chosen === 'vi' ? chosen : ''
  return `window.__aiWorkerLang = ${JSON.stringify(lang)};\n`
}
