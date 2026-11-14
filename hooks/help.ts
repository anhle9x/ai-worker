// What /ai-worker:help prints: everything this plugin gives on this computer, read from the computer itself.
// Những gì /ai-worker:help in ra: mọi thứ plugin này mang lại trên máy này, đọc từ chính máy đó.
import { tx } from './lang'

/** `byNameOnly`: the skill's own file says Claude must not start it by itself, so it runs only when the person types its name. */
/** `byNameOnly`: file của chính skill ghi rằng Claude không được tự khởi động nó, nên nó chỉ chạy khi người dùng gõ tên. */
export type SkillLine = { name: string; about: string; byNameOnly?: boolean }

export type HelpInfo = {
  title: string
  version?: string
  skills: SkillLine[]
  /** The helpers found on this computer; undefined before the first look. */
  workers?: { gemma?: string; chatgpt?: string; gemini?: string }
  /** An ai-workers MCP server hands out the work to ChatGPT and Gemini instead of the plugin. */
  viaMcp: boolean
  sharing: boolean
}

const ABOUT_MAX = 80

/** The skills anyone may use day to day; the plugin's other skills are for people who write code or run systems. */
/** Các skill ai cũng dùng được hằng ngày; các skill còn lại của plugin dành cho người viết code hoặc vận hành hệ thống. */
const EVERYDAY = ['handoff', 'meeting-notes', 'lesson-generator', 'make-skill']

/** The skills the plugin ships, each in a few plain words; another skill is told by the first sentence of its own description. */
/** Các skill plugin mang theo, mỗi cái vài chữ dễ hiểu; skill khác thì dùng câu đầu tiên trong mô tả của chính nó. */
function plainAbout(name: string): string | undefined {
  if (name === 'handoff') return tx('write a handoff note so a new session can carry on')
  if (name === 'meeting-notes') return tx('turn rough meeting notes into tidy minutes')
  if (name === 'lesson-generator') return tx('build a small course with lessons, flashcards and quizzes')
  if (name === 'make-skill') return tx("turn a document or your team's procedure into a new skill, as a draft you review first")
  if (name === 'write-spec') return tx('write a specification: goal, scope, roles, numbered requirements')
  if (name === 'draw-flow') return tx('draw how a system really works, as diagrams')
  if (name === 'interview-me') return tx('ask you one question at a time until the real need is clear')
  if (name === 'grilling') return tx('question your plan hard to find its weak points')
  if (name === 'tdd') return tx('build a feature or fix a bug by writing the test first')
  if (name === 'diagnosing-bugs') return tx('track down a hard bug or a slowdown, step by step')
  if (name === 'codebase-design') return tx('design modules with a small, clear interface')
  if (name === 'domain-modeling') return tx("agree on the project's terms and record decisions")
  if (name === 'improve-codebase-architecture') return tx("find where the code's structure can be made better")
  if (name === 'qa-test') return tx('test one web flow and write a bug report')
  if (name === 'qa-site') return tx('test a whole website, flow by flow, into one report')
  if (name === 'browser-testing-with-devtools') return tx('test a page in Chrome: screen, console, network')
  if (name === 'security-audit') return tx('review code for security problems')
  if (name === 'ui-ux-pro-max') return tx('guidance for designing and reviewing interfaces')
  return undefined
}

/** A skill's name and the first sentence of its description, from its SKILL.md; undefined for a file with no front matter. */
/** Tên một skill và câu đầu tiên trong mô tả của nó, đọc từ SKILL.md; undefined với file không có phần đầu. */
export function skillLine(text: string, folder: string): SkillLine | undefined {
  if (!text.startsWith('---')) return undefined
  const end = text.indexOf('\n---', 3)
  if (end < 0) return undefined
  const head = text.slice(3, end)
  const field = (key: string) => {
    const value = new RegExp(`^${key}:[ \\t]*(.*)$`, 'm').exec(head)?.[1]?.trim() ?? ''
    return /^(".*"|'.*')$/.test(value) ? value.slice(1, -1) : value
  }
  const sentence = (field('description').split(/(?<=\.)\s/)[0] ?? '').replace(/\.$/, '')
  const about = sentence.length > ABOUT_MAX ? `${sentence.slice(0, ABOUT_MAX).replace(/\s+\S*$/, '')}…` : sentence
  return { name: field('name') || folder, about, ...(field('disable-model-invocation') === 'true' ? { byNameOnly: true } : {}) }
}

/**
 * The whole answer of /ai-worker:help, written for someone who has never opened the plugin's folder: short lines,
 * one thing per line, as a list (the app draws "- " as a bullet, a terminal shows it as it is).
 */
/** Toàn bộ câu trả lời của /ai-worker:help, viết cho người chưa từng mở thư mục của plugin: dòng ngắn, mỗi dòng một ý, dạng danh sách (app vẽ "- " thành chấm đầu dòng, terminal hiện nguyên như vậy). */
export function buildHelp(i: HelpInfo): string {
  const has = (found: string | undefined, extra = '') => (found ? tx('ready') + extra : tx('not installed'))
  const skill = (s: SkillLine) => `- /ai-worker:${s.name} — ${plainAbout(s.name) ?? s.about}${s.byNameOnly ? ` (${tx('runs only when you type its name')})` : ''}`
  const everyday = i.skills.filter(s => EVERYDAY.includes(s.name))
  const technical = i.skills.filter(s => !EVERYDAY.includes(s.name))
  const lines = [
    i.version ? `${i.title} ${i.version}` : i.title,
    '',
    tx('Commands you can type:'),
    `- /office — ${tx('open the office page in your browser')}`,
    `- /office-pane — ${tx('open the office next to the chat')}`,
    `- /update — ${tx('install the newest version')}`,
    `- /ai-worker:board — ${tx('for managers: pair with the company board, then ask Claude about the team in your own words')}`,
    `- /ai-worker:voice — ${tx('speak instead of typing, in Vietnamese too: opens the dictation settings of this computer and shows the steps')}`,
    `- /ai-worker:help — ${tx('show this list')}`,
    '',
    tx('Skills. You do not need to remember the names: say what you need in your own words and Claude picks the right one.'),
    '',
    tx('For everyday work:'),
    ...(everyday.length ? everyday.map(skill) : [`- ${tx('none')}`]),
  ]
  if (technical.length) {
    lines.push(
      '',
      tx('For people who write code or run systems:'),
      ...technical.map(skill),
      `- planner — ${tx('an assistant that plans a big decision; Claude asks you before calling it')}`,
    )
  }
  lines.push('', tx('Helper assistants (Claude gives them side jobs by itself, you do not call them):'))
  if (!i.workers) lines.push(`- ${tx('not checked yet: send any message first, then run this again')}`)
  else {
    lines.push(`- Gemma, ${tx('runs on this computer')}: ${has(i.workers.gemma)}`)
    if (i.viaMcp) lines.push(`- ChatGPT, Gemini: ${tx('set up separately on this computer (ai-workers)')}`)
    else {
      lines.push(`- ChatGPT: ${has(i.workers.chatgpt)}`)
      lines.push(`- Gemini: ${has(i.workers.gemini, `, ${tx('can also make images')}`)}`)
    }
  }
  lines.push('', i.sharing ? tx('Usage numbers go to the company server. Chat content is never sent.') : tx('Nothing is sent to a company server.'))
  return lines.join('\n')
}
