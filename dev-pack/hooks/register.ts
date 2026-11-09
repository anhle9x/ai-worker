import type { EngineInterface, Register } from 'claude-code'

import { setLang, tx } from './lang'

const rules = () => [
  tx('# Rules for technical work'),
  tx('- After changing the interface, open the real page and check both the desktop and the phone size before saying it is done. If you cannot check, say clearly that you have not.'),
  tx('- When the user says "split sessions": make a plan first, then evaluate. Only split when there are at least 2 large parts that can be done independently without touching the same file; otherwise give the reason in one sentence and work in the current session. If you split, show the assignment table and then create the sessions right away: mechanical parts use Sonnet, read-only parts use Haiku, design and checking stay in the main session. When done, check each session result before reporting. Commit only when the user says so. When the user says "split anyway", split the parts that can be separated and say clearly which parts cannot be.'),
  tx('- Call the `planner` assistant only after the user has agreed, because it uses a lot of quota; use it for big decisions that are hard to undo.'),
].join('\n')

/** The language in use: AI_WORKER_LANG, then the one saved by the ai-worker plugin (user.json), then the system's (the sandbox has no process.env). */
/** Ngôn ngữ đang dùng: AI_WORKER_LANG, rồi ngôn ngữ plugin ai-worker đã lưu (user.json), rồi của hệ thống (sandbox không có process.env). */
async function languageOf($: EngineInterface): Promise<unknown> {
  const forced = await $.env.get('AI_WORKER_LANG')
  if (forced) return forced
  try {
    const home = (await $.env.get('HOME')) ?? (await $.env.get('USERPROFILE')) ?? ''
    const saved = (JSON.parse(await $.fs.read(`${home}/.local/share/ai-worker/user.json`)) as { language?: unknown }).language
    if (saved === 'en' || saved === 'vi') return saved
  } catch {
    // no saved choice: the system decides
    // chưa lưu lựa chọn nào: để hệ thống quyết định
  }
  const locale = (await $.env.get('LC_ALL')) || (await $.env.get('LC_MESSAGES')) || (await $.env.get('LANG')) || ''
  return /^vi(?![a-z])/i.test(locale) ? 'vi' : undefined
}

export const register: Register = on => {
  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    setLang(await languageOf($))
    return { ...r, sections: [...r.sections, { id: 'ai-worker-dev:rules', text: rules(), scope: 'session' as const }] }
  })
}
