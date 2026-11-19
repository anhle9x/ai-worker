// The record of each piece of work Claude hands to ChatGPT, Gemini or Gemma, for the server's audit log: which helper,
// which tool, how long the text was, what was stopped and what the check of the answer found, and a fingerprint of the
// prompt. Never the prompt or the answer. The fingerprint is salted with a value kept on this computer, so the server
// cannot guess a short prompt by trying likely texts; someone holding the prompt can check it on this computer.
// Pure: no sockets, no files.
// Biên bản của mỗi việc Claude giao cho ChatGPT, Gemini hay Gemma, cho nhật ký của máy chủ: trợ lý nào, công cụ nào, chữ
// dài bao nhiêu, đã chặn gì và bước kiểm câu trả lời thấy gì, kèm dấu vân tay của đề bài. Không bao giờ có đề bài hay câu
// trả lời. Dấu vân tay có muối giữ trên máy này, nên máy chủ không đoán được một đề bài ngắn bằng cách thử các câu hay gặp;
// người đang có đề bài thì kiểm được trên máy này. Mã thuần: không socket, không file.
import type { Delegation, DelegationOutcome, DelegationTool, TeamState } from '../types'
import { sha256Hex } from './team'

export const MAX_DELEGATIONS = 100
/** Records this old are no longer sent: the server has had many beats to take them. */
/** Biên bản cũ cỡ này thì thôi gửi: máy chủ đã có nhiều nhịp để nhận. */
export const DELEGATION_SEND_MS = 48 * 3_600_000
export const DELEGATION_TOOLS: readonly DelegationTool[] = ['ask_chatgpt', 'ask_gemini', 'ask_local', 'generate_image']

export function delegationTool(name: string | undefined): DelegationTool | undefined {
  return DELEGATION_TOOLS.find(t => t === name)
}

/** The helper a tool hands work to. */
/** Trợ lý mà một công cụ giao việc cho. */
export function delegationWorker(tool: DelegationTool): Delegation['worker'] {
  return tool === 'ask_chatgpt' ? 'chatgpt' : tool === 'ask_local' ? 'gemma' : 'gemini'
}

/** The prompt's fingerprint: SHA-256 of the salt and the text, the first 32 hex. */
/** Dấu vân tay của đề bài: SHA-256 của muối và chữ, 32 ký tự hex đầu. */
export function promptHash(salt: string, prompt: string): string {
  return sha256Hex(`ai-worker-delegation|${salt}|${prompt}`).slice(0, 32)
}

/** A new salt: 32 hex from whatever randomness the engine has. */
/** Muối mới: 32 ký tự hex từ nguồn ngẫu nhiên mà engine có. */
export function newSalt(random: () => number = Math.random): string {
  const bytes = new Uint8Array(16)
  const c = (globalThis as { crypto?: { getRandomValues?: (a: Uint8Array) => Uint8Array } }).crypto
  if (c?.getRandomValues) c.getRandomValues(bytes)
  else for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(random() * 256)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

/** The record's id from the tool call's own id, so the same work sent twice is taken once by the server. */
/** Mã của biên bản từ mã của chính lệnh gọi công cụ, để cùng một việc gửi hai lần thì máy chủ chỉ nhận một. */
export function delegationId(callId: string): string {
  return sha256Hex(`ai-worker-delegation-id|${callId}`).slice(0, 24)
}

export function makeDelegation(p: {
  callId: string
  at: number
  tool: DelegationTool
  via: Delegation['via']
  promptChars: number
  promptHash: string
  outcome: DelegationOutcome
  answerChars?: number
  check?: Delegation['check']
  found?: string[]
}): Delegation {
  return {
    id: delegationId(p.callId),
    at: p.at,
    worker: delegationWorker(p.tool),
    tool: p.tool,
    via: p.via,
    promptChars: p.promptChars,
    answerChars: p.answerChars ?? 0,
    promptHash: p.promptHash,
    outcome: p.outcome,
    ...(p.check?.length ? { check: p.check } : {}),
    ...(p.found?.length ? { found: [...new Set(p.found)].slice(0, 8) } : {}),
  }
}

export function addDelegation(s: TeamState, h: Delegation): TeamState {
  const list = (s.delegations ?? []).filter(x => x.id !== h.id)
  return { ...s, delegations: [...list, h].slice(-MAX_DELEGATIONS) }
}

/** The records every open session holds, newest last, those of the last two days, once each. */
/** Biên bản mà mọi phiên đang giữ, mới nhất sau cùng, của hai ngày gần nhất, mỗi cái một lần. */
export function recentDelegations(sessions: readonly Pick<TeamState, 'delegations'>[], now: number): Delegation[] {
  const seen = new Map<string, Delegation>()
  for (const s of sessions) for (const h of s.delegations ?? []) if (now - h.at < DELEGATION_SEND_MS && h.at <= now + 60_000) seen.set(h.id, h)
  return [...seen.values()].sort((a, b) => a.at - b.at).slice(-MAX_DELEGATIONS)
}
