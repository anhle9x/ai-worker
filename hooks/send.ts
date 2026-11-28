// One send of this computer's numbers: to the Go receiver or the webhook with the right key, or to the common folder, and what the
// answers ask of the next sends. The keys of the store and the shapes of their values are those of the versions before this file:
// a computer must keep its own key and its route across the update.
// Một lần gửi số liệu của máy này: tới bộ nhận Go hay webhook với đúng khoá, hoặc vào thư mục chung, và những gì câu trả lời dặn
// cho các lần gửi sau. Các khoá của kho và hình dạng giá trị của chúng giữ như các bản trước file này: máy phải giữ được khoá riêng
// và tuyến của nó qua lần cập nhật.
import type { Fetch, Store } from './io'
import { gemmaServerIn } from './workers'
import { afterAnswer, packetFor, type SendState } from './sendv2'
import {
  backoff, deviceKeyIn, FALLBACK_SPREAD_MS, paceFrom, receiverOutcome, refusalAfter, routeFrom, routeRested, routeTarget, summarySignature,
  WEBHOOK_BACKOFF_FIRST_MS, WEBHOOK_BACKOFF_MAX_MS, webhookDown, type IngestRoute, type MachineSummary,
} from './team'

/** The last send that reached the server or the folder, kept in the plugin's store so every session on this computer sees it: three open sessions do not send the same change three times. */
/** Lần gửi gần nhất đã tới máy chủ hay thư mục, giữ trong kho của plugin để mọi phiên trên máy này cùng thấy: ba phiên đang mở không gửi cùng một thay đổi ba lần. */
export const SHARED_KEY = 'sharedLast'
/** The key of its own the server gave this computer (awd1.…), kept in the plugin's store, never in config.js where the office page reads. */
/** Khoá riêng máy chủ cấp cho máy này (awd1.…), giữ trong kho của plugin, không bao giờ trong config.js nơi trang văn phòng đọc được. */
export const DEVICE_KEY = 'deviceKey'
/** The Gemma server the company dashboard announced (workers.ts, gemmaServerIn); an address set on this computer beats it. */
/** Máy chủ Gemma do bảng tổng của công ty báo (workers.ts, gemmaServerIn); địa chỉ đặt trên máy này thắng nó. */
export const GEMMA_BOARD_KEY = 'gemmaFromBoard'
/** After the server refuses a send (401 or 403), no send before `until` (refusalAfter). */
/** Sau khi máy chủ từ chối một lần gửi (401 hay 403), không gửi trước `until` (refusalAfter). */
export const REFUSED_KEY = 'shareRefused'
/** What the server's answers ask of the next sends: the gap between them and, after "busy", no send before `until` (paceFrom). */
/** Các câu trả lời của máy chủ dặn gì cho các lần gửi sau: khoảng cách giữa chúng và, sau "bận", không gửi trước `until` (paceFrom). */
export const PACE_KEY = 'sharePace'
/** Where this computer sends while the server says so: the Go receiver's addresses and until when (docs/RECEIVER.md, section 4). */
/** Máy này gửi tới đâu trong lúc máy chủ còn dặn: các địa chỉ của bộ nhận Go và tới khi nào (docs/RECEIVER.vi.md, mục 4). */
export const ROUTE_KEY = 'ingestRoute'
/** How long the sends wait after the webhook itself did not answer, doubling each time (team.ts, backoff). */
/** Các lần gửi chờ bao lâu sau khi chính webhook không trả lời, gấp đôi mỗi lần (team.ts, backoff). */
export const WEBHOOK_DOWN_KEY = 'webhookDown'
/** Whether the server reads v: 2 and which hours it holds (hooks/sendv2.ts). */
/** Máy chủ có đọc v: 2 không và nó đang giữ những giờ nào (hooks/sendv2.ts). */
export const SEND_KEY = 'sendState'

/** A send changes the board this often at least, even when nothing changed. */
/** Một lần gửi làm mới bảng ít nhất mỗi chừng này, kể cả khi không có gì đổi. */
export const SHARE_EVERY_MS = 5 * 60_000

export type SendIo = { store: Store; fetch: Fetch; random?: () => number }

/** Where this send goes: the server (its webhook, the key of the package, the receiver hosts it allows), or the common folder. */
/** Lần gửi này đi đâu: máy chủ (webhook của nó, khoá của gói, các máy chủ bộ nhận được phép), hoặc thư mục chung. */
export type SendTarget =
  | { kind: 'web'; webhook: string; ingestKey: string; ingestHosts: string[] }
  | { kind: 'folder'; write(json: string): Promise<void> }

/** What the session keeps between sends: the gap of the last answer, for the timer of the next send. */
/** Những gì phiên giữ giữa các lần gửi: khoảng cách của câu trả lời gần nhất, cho bộ hẹn giờ của lần gửi sau. */
export type SendMem = { gapMs: number }

/**
 * `sent`: it reached the receiver, the webhook or the folder. `notDue`: nothing to send yet (the same numbers, a refusal still running,
 * or the server asked to wait). `putOff`: the receiver failed and this send waits for the webhook. `failed`: the server answered `status`
 * (0: no answer).
 */
/** `sent`: đã tới bộ nhận, webhook hay thư mục. `notDue`: chưa có gì để gửi (cùng số liệu, lần từ chối chưa hết, hoặc máy chủ dặn chờ). `putOff`: bộ nhận hỏng và lần gửi này chờ sang webhook. `failed`: máy chủ trả `status` (0: không trả lời). */
export type SendResult =
  | { kind: 'sent'; to: 'receiver' | 'webhook' | 'folder'; full: boolean; needFull: boolean }
  | { kind: 'notDue'; why: 'same' | 'refused' | 'busy' }
  | { kind: 'putOff' }
  | { kind: 'failed'; status: number }

/**
 * Sends `summary` if it is due. Writes the store in the same order as the versions before; a write of the store that fails throws, except
 * those whose loss only costs a send again.
 */
/** Gửi `summary` nếu tới hạn. Ghi kho theo đúng thứ tự như các bản trước; một lần ghi kho bị lỗi thì ném ra, trừ các lần mà mất đi chỉ tốn thêm một lần gửi. */
export async function send(io: SendIo, target: SendTarget, mem: SendMem, summary: MachineSummary, now: number): Promise<SendResult> {
  const { store } = io
  const random = io.random ?? Math.random
  const viaWeb = target.kind === 'web'
  const sig = summarySignature(summary)
  const last = ((await store.get(SHARED_KEY).catch(() => undefined)) ?? {}) as { sig?: string; at?: number }
  const refused = ((await store.get(REFUSED_KEY).catch(() => undefined)) ?? {}) as { until?: number; wait?: number }
  const pace = ((await store.get(PACE_KEY).catch(() => undefined)) ?? {}) as { gapMs?: number; until?: number }
  if (typeof pace.gapMs === 'number') mem.gapMs = pace.gapMs
  // a busy server said when to come back: nothing before then, not even the beat that sends when nothing changed
  // máy chủ bận đã nói khi nào quay lại: không gửi gì trước lúc đó, kể cả nhịp gửi khi không có gì đổi
  // and never two sends closer than the gap it asked, the beat's included
  // và không bao giờ hai lần gửi sát hơn khoảng cách nó dặn, kể cả lần gửi của nhịp tim
  const busy = viaWeb && (now < (pace.until ?? 0) || now - (last.at ?? 0) < mem.gapMs)
  if (!(sig !== last.sig || now - (last.at ?? 0) > SHARE_EVERY_MS)) return { kind: 'notDue', why: 'same' }
  if (viaWeb && now < (refused.until ?? 0)) return { kind: 'notDue', why: 'refused' }
  if (busy) return { kind: 'notDue', why: 'busy' }
  if (target.kind === 'folder') {
    await target.write(JSON.stringify(summary))
    await store.set(SHARED_KEY, { sig, at: now })
    return { kind: 'sent', to: 'folder', full: true, needFull: false }
  }
  const { webhook, ingestKey, ingestHosts } = target
  // this computer's own key once the server has given it one, else the key of the install package
  // khoá riêng của máy này khi máy chủ đã cấp, nếu không thì khoá của gói cài
  const own = await store.get(DEVICE_KEY).catch(() => undefined)
  const key = typeof own === 'string' && own.startsWith('awd1.') ? own : ingestKey
  // v: 1 until the server says it reads v: 2, then only the hours that changed, and the whole book once an hour
  // v: 1 cho tới khi máy chủ nói nó đọc v: 2, sau đó chỉ các giờ đã đổi, và cả sổ mỗi giờ một lần
  const sendState = (await store.get(SEND_KEY).catch(() => undefined)) as SendState | undefined
  const packet = packetFor(summary, sendState, now)
  // the number is kept before the send: a send whose answer is lost may still have been written, and the next one must be above it
  // số được giữ trước khi gửi: lần gửi mất câu trả lời vẫn có thể đã được ghi, và lần sau phải có số cao hơn
  await store.set(SEND_KEY, { ...sendState, seq: packet.seq }).catch(() => undefined)
  const body = JSON.stringify(packet.body)
  const post = (base: string) => io.fetch(`${base}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body,
  })
  // the Go receiver takes only a computer's own key: the shared key of the package always goes to the webhook
  // bộ nhận Go chỉ nhận khoá riêng của máy: khoá chung của gói luôn đi tới webhook
  const ownKey = key !== ingestKey
  let route = ownKey ? ((await store.get(ROUTE_KEY).catch(() => undefined)) as IngestRoute | undefined) : undefined
  if (route && !(route.until > now)) {
    // the address ran out: ask the webhook where to send now, which writes nothing; no answer sends to the webhook
    // địa chỉ đã hết hạn: hỏi webhook giờ gửi tới đâu, việc này không ghi gì; không trả lời thì gửi tới webhook
    const asked = await io.fetch(`${webhook}/ingest/route${sendState?.v2 ? '?v=2' : ''}`, { method: 'GET', headers: { Authorization: `Bearer ${key}` } }).catch(() => undefined)
    route = (asked?.ok ? routeFrom(asked.text, webhook, ingestHosts, now, random) : null) ?? undefined
    if (asked?.ok) await keepGemmaServer(store, asked.text)
    if (route) await store.set(ROUTE_KEY, route)
    else await store.delete(ROUTE_KEY).catch(() => undefined)
  }
  const to = route ? routeTarget(route, now) : undefined
  // the webhook; no answer at all counts as status 0, as a 5xx without Retry-After does: the sends after it back off
  // webhook; không trả lời gì được tính là mã 0, như 5xx không có Retry-After: các lần gửi sau đó lùi lại
  const toWebhook = async () => {
    const got = (await post(webhook).catch(() => undefined)) ?? { ok: false, status: 0, headers: {}, text: '' }
    const down = (await store.get(WEBHOOK_DOWN_KEY).catch(() => undefined)) as { wait?: number } | undefined
    if (webhookDown(got)) {
      const b = backoff(down, now, WEBHOOK_BACKOFF_FIRST_MS, WEBHOOK_BACKOFF_MAX_MS, 0.5, random)
      await store.set(WEBHOOK_DOWN_KEY, b).catch(() => undefined)
      await store.set(PACE_KEY, { gapMs: pace.gapMs, until: b.until }).catch(() => undefined)
    } else if (down) {
      await store.delete(WEBHOOK_DOWN_KEY).catch(() => undefined)
    }
    return got
  }
  let r: Awaited<ReturnType<typeof post>> | undefined
  if (to && route) {
    const got = await post(to).catch(() => undefined)
    if (receiverOutcome(got) === 'fallback') {
      // the receiver could not take it (down, unreachable, its key check, a missing path): the webhook takes the sends for a
      // while, longer each time, and this one goes there after a wait under 30 seconds at random, so a whole office that lost
      // the receiver together reaches the webhook spread out
      // bộ nhận không nhận được (đã dừng, không tới được, kiểm khoá ở đó, thiếu đường): webhook nhận các lần gửi trong một lúc,
      // lâu dần mỗi lần, và lần này đi tới đó sau một khoảng chờ ngẫu nhiên dưới 30 giây, để cả văn phòng cùng mất bộ nhận tới
      // webhook rải ra
      route = routeRested(route, now, random)
      await store.set(ROUTE_KEY, route)
      await store.set(PACE_KEY, { gapMs: pace.gapMs, until: now + Math.round(random() * FALLBACK_SPREAD_MS) }).catch(() => undefined)
    } else {
      r = got!
      if (route.rest) await store.set(ROUTE_KEY, { urls: route.urls, until: route.until })
    }
  } else {
    r = await toWebhook()
  }
  // put off to the webhook: nothing was sent, the next beat after the wait sends it
  // hoãn sang webhook: chưa gửi gì, nhịp sau khi hết chờ sẽ gửi
  if (!r) return { kind: 'putOff' }
  // its own key refused (too old, or the server was set up again): drop it, so the next send asks for a new one
  // khoá riêng bị từ chối (quá cũ, hoặc máy chủ được cài lại): bỏ nó, để lần gửi sau xin khoá mới
  if (r.status === 401 && key !== ingestKey) await store.delete(DEVICE_KEY).catch(() => undefined)
  // a refusal does not pass by itself: wait longer each time instead of asking again every second
  // lần từ chối không tự hết: chờ lâu dần thay vì hỏi lại mỗi giây
  if (r.status === 401 || r.status === 403) {
    await store.set(REFUSED_KEY, refusalAfter(refused, now))
  }
  // the gap the server asks, or when to come back after "busy", for every session of this computer
  // khoảng cách máy chủ dặn, hoặc lúc quay lại sau "bận", cho mọi phiên trên máy này
  const asked = paceFrom(r, now)
  if (asked.gapMs !== undefined || asked.until !== undefined) {
    if (asked.gapMs !== undefined) mem.gapMs = asked.gapMs
    await store.set(PACE_KEY, { gapMs: asked.gapMs ?? pace.gapMs, until: asked.until }).catch(() => undefined)
  }
  if (!r.ok) return { kind: 'failed', status: r.status }
  const after = afterAnswer(sendState, r.text, packet, now, random)
  await store.set(SEND_KEY, after).catch(() => undefined)
  if (refused.wait) await store.delete(REFUSED_KEY).catch(() => undefined)
  const given = deviceKeyIn(r.text)
  if (given) await store.set(DEVICE_KEY, given)
  await keepGemmaServer(store, r.text)
  // the webhook says where to send from now on: the Go receiver, or here again (an empty list); nothing said keeps what is held
  // webhook dặn từ giờ gửi tới đâu: bộ nhận Go, hoặc lại về đây (danh sách rỗng); không dặn gì thì giữ cái đang có
  const next = ownKey || given ? routeFrom(r.text, webhook, ingestHosts, now, random) : undefined
  if (next) await store.set(ROUTE_KEY, route?.rest && route.urls.join() === next.urls.join() ? { ...next, rest: route.rest } : next)
  else if (next === null) await store.delete(ROUTE_KEY).catch(() => undefined)
  await store.set(SHARED_KEY, { sig, at: now })
  return { kind: 'sent', to: to && route ? 'receiver' : 'webhook', full: packet.full, needFull: !!after.needFull }
}

/** Keeps the Gemma server an answer announced, drops it when the answer says null, and keeps what is held when it says nothing. */
/** Giữ máy chủ Gemma mà câu trả lời đã báo, bỏ nó khi câu trả lời ghi null, và giữ cái đang có khi không nói gì. */
async function keepGemmaServer(store: Store, answer: string) {
  const g = gemmaServerIn(answer)
  if (g) await store.set(GEMMA_BOARD_KEY, g).catch(() => undefined)
  else if (g === null) await store.delete(GEMMA_BOARD_KEY).catch(() => undefined)
}
