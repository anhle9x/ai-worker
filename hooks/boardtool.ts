// Pairing a manager's computer with the company board and reading it (/ai-worker:board and the office_board tool), through the store and
// the network handed in (hooks/io.ts). register.tsx keeps what needs the engine itself: the permission check and registering the tool.
// Ghép máy của quản lý với bảng công ty và đọc bảng (/ai-worker:board và công cụ office_board), qua kho và mạng được đưa vào
// (hooks/io.ts). register.tsx giữ những gì cần chính engine: kiểm quyền và đăng ký công cụ.
import { BOARD_CODE_MS, BOARD_KEY, boardUnreachable, pairedText, pairingSteps, summarizeBoard, type BoardPairing } from './board'
import type { Fetch, Store } from './io'
import { tx } from './lang'

/**
 * What the board needs from the computer: the store, the network, the company server (`webhook`, '' when none), how the plugin names
 * itself to it, the clock, and a way to put the board tool in this session's list.
 */
/** Bảng cần gì từ máy: kho, mạng, máy chủ công ty (`webhook`, '' khi không có), cách plugin tự xưng tên với nó, đồng hồ, và cách đưa công cụ đọc bảng vào danh sách của phiên này. */
export type BoardIo = {
  store: Store
  fetch: Fetch
  webhook: string
  userAgent(): Promise<string>
  now(): Promise<number>
  registerTool(): Promise<void>
}

/** One request to the board with a key in the Authorization header. A network error reads as status 0, so the caller has one shape to handle. */
/** Một yêu cầu tới bảng kèm khoá trong header Authorization. Lỗi mạng đọc thành trạng thái 0, để nơi gọi chỉ phải xử lý một dạng. */
export async function boardFetch(io: BoardIo, path: string, key: string | undefined, method: 'GET' | 'POST' = 'GET') {
  const agent = await io.userAgent()
  try {
    const r = await io.fetch(`${io.webhook}${path}`, {
      method,
      headers: { 'User-Agent': agent, ...(key ? { Authorization: `Bearer ${key}` } : {}) },
      ...(method === 'POST' ? { body: '' } : {}),
    })
    return { ok: r.ok, status: r.status, text: r.text }
  } catch {
    return { ok: false, status: 0, text: '' }
  }
}

export async function readPairing(store: Store): Promise<BoardPairing> {
  const kept = await store.get(BOARD_KEY).catch(() => undefined)
  return kept && typeof kept === 'object' ? (kept as BoardPairing) : {}
}

/** /ai-worker:board: shows where the pairing stands and moves it one step: ask for a code, collect the key once an admin approved, or unpair. */
/** /ai-worker:board: cho biết việc ghép đang ở đâu và đi tiếp một bước: xin mã, nhận khoá khi quản trị đã duyệt, hoặc bỏ ghép. */
export async function runBoard(io: BoardIo, args: string): Promise<{ text: string }> {
  if (!io.webhook) return { text: tx('This computer has no company server set up, so there is no board to read.') }
  const now = await io.now()
  let pairing = await readPairing(io.store)
  if (/^(unpair|off)$/i.test(args.trim())) {
    if (pairing.token) await boardFetch(io, '/ext/unpair', pairing.token, 'POST')
    await io.store.set(BOARD_KEY, {})
    return { text: tx('This computer is no longer paired with the board. Claude here can no longer read it.') }
  }
  let note = ''
  if (pairing.token) {
    const r = await boardFetch(io, '/ext/state', pairing.token)
    if (r.ok) {
      await io.registerTool()
      return { text: pairedText(pairing.name || '') }
    }
    if (r.status !== 401) return { text: boardUnreachable(r.status) }
    note = `${tx('The earlier pairing was revoked or has expired.')}\n\n`
    pairing = {}
  }
  if (pairing.pending && now - pairing.pending.at < BOARD_CODE_MS) {
    const r = await boardFetch(io, '/ext/poll', pairing.pending.key, 'POST')
    if (!r.ok) return { text: boardUnreachable(r.status) }
    let answer: { status?: unknown; name?: unknown; token?: unknown } = {}
    try {
      answer = JSON.parse(r.text)
    } catch {
      // treated as an expired code below
      // bên dưới coi như mã đã hết hạn
    }
    if (answer.status === 'done' && typeof answer.token === 'string') {
      const name = typeof answer.name === 'string' ? answer.name : ''
      await io.store.set(BOARD_KEY, { token: answer.token, name })
      await io.registerTool()
      return { text: pairedText(name) }
    }
    if (answer.status === 'pending') return { text: `${tx('Not approved yet.')}\n\n${pairingSteps(pairing.pending.code, io.webhook)}` }
    note = `${tx('The earlier code has expired.')}\n\n`
  }
  const r = await boardFetch(io, '/ext/request-code', undefined, 'POST')
  if (!r.ok) return { text: boardUnreachable(r.status) }
  let fresh: { code?: unknown; key?: unknown } = {}
  try {
    fresh = JSON.parse(r.text)
  } catch {
    // an answer that is not the server's: reported below
    // câu trả lời không phải của máy chủ: báo ở dưới
  }
  if (typeof fresh.code !== 'string' || typeof fresh.key !== 'string' || !/^\d{8}$/.test(fresh.code)) return { text: tx('The board sent an answer that could not be read.') }
  await io.store.set(BOARD_KEY, { pending: { key: fresh.key, code: fresh.code, at: now } })
  return { text: note + pairingSteps(fresh.code, io.webhook) }
}

/** The board tool once the permission check let it through: the wall view as plain lines, read from the company server into this conversation. */
/** Công cụ đọc bảng sau khi kiểm quyền cho qua: phần treo tường thành các dòng chữ, đọc từ máy chủ công ty vào cuộc trò chuyện này. */
export async function readBoard(io: BoardIo): Promise<{ text: string; isError: boolean }> {
  const answer = (text: string, isError = false) => ({ text, isError })
  const pairing = await readPairing(io.store)
  if (!io.webhook || !pairing.token) return answer(tx('This computer is not paired with the board. Tell the user to type /ai-worker:board to pair it.'), true)
  const r = await boardFetch(io, '/ext/data', pairing.token)
  if (r.status === 401) {
    await io.store.set(BOARD_KEY, {}).catch(() => undefined)
    return answer(tx('The pairing with the board was revoked or has expired. Tell the user to type /ai-worker:board to pair again.'), true)
  }
  if (!r.ok) return answer(boardUnreachable(r.status), true)
  try {
    return answer(summarizeBoard(JSON.parse(r.text), await io.now()))
  } catch {
    return answer(tx('The board sent an answer that could not be read.'), true)
  }
}
