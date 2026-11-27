import { expect, test } from 'claude-code/testing'
import type { Answer } from '../hooks/io'
import { DEVICE_KEY, PACE_KEY, REFUSED_KEY, ROUTE_KEY, SEND_KEY, send, SHARED_KEY, WEBHOOK_DOWN_KEY, type SendMem, type SendResult, type SendTarget } from '../hooks/send'
import { buildMachineSummary, PACE_MIN_MS } from '../hooks/team'

// hooks/send.ts without the engine: a store in memory that logs each step, a server that answers from a script, a fixed random.
// hooks/send.ts không cần engine: kho trong bộ nhớ ghi lại từng bước, máy chủ trả lời theo kịch bản, số ngẫu nhiên cố định.

const NOW = 1_800_000_000_000
const WEBHOOK = 'https://board.example.com'
const RECEIVER = 'https://ingest.example.com'
const RECEIVER2 = 'https://ingest2.example.com'
const OWN = 'awd1.a.b.c.d.e.f.g'
const NEW_OWN = 'awd1.h.i.j.k.l.m.n'
const WEB: SendTarget = { kind: 'web', webhook: WEBHOOK, ingestKey: 'k', ingestHosts: [] }

type Call = { url: string; method: string; auth: string; body?: Record<string, unknown> }

/** A computer: its store, the calls it made, and one send at a time against `reply`. */
/** Một máy: kho của nó, các lệnh gọi nó đã gửi, và từng lần gửi theo `reply`. */
function computer(kept: Record<string, unknown> = {}) {
  const data: Record<string, unknown> = structuredClone(kept)
  const log: string[] = []
  const calls: Call[] = []
  const mem: SendMem = { gapMs: PACE_MIN_MS }
  let reply: (c: Call) => Answer | undefined = () => ok({ ok: true })
  const store = {
    async get(k: string) {
      log.push(`get ${k}`)
      return structuredClone(data[k])
    },
    async set(k: string, v: unknown) {
      log.push(`set ${k}`)
      data[k] = structuredClone(v)
    },
    async delete(k: string) {
      log.push(`delete ${k}`)
      delete data[k]
    },
  }
  const fetch = async (url: string, init: { method: string; headers: Record<string, string>; body?: string }) => {
    const c: Call = { url, method: init.method, auth: init.headers.Authorization ?? '', body: init.body ? JSON.parse(init.body) : undefined }
    calls.push(c)
    const r = reply(c)
    if (!r) throw new Error('no answer')
    return r
  }
  let n = 0
  return {
    data, log, calls, mem,
    answer(f: (c: Call) => Answer | undefined) {
      reply = f
    },
    /** One send at `at`; each send carries new numbers unless `same`. */
    /** Một lần gửi lúc `at`; mỗi lần mang số liệu mới trừ khi `same`. */
    send(at: number, target: SendTarget = WEB, same = false): Promise<SendResult> {
      if (!same) n++
      return send({ store, fetch, random: () => 0.5 }, target, mem, summaryOf(`An ${n}`, at), at)
    },
  }
}

const summaryOf = (name: string, at: number) => buildMachineSummary([], undefined, at, { device: 'device-a', name, account: 'an@example.com' })
const ok = (body: unknown): Answer => ({ ok: true, status: 200, headers: {}, text: JSON.stringify(body) })
const status = (s: number, headers: Record<string, string> = {}): Answer => ({ ok: false, status: s, headers, text: '{}' })

test('the seven keys of the store keep their names: computers in the pilot must not lose their key or route', () => {
  expect([SHARED_KEY, DEVICE_KEY, REFUSED_KEY, PACE_KEY, ROUTE_KEY, WEBHOOK_DOWN_KEY, SEND_KEY]).toEqual(['sharedLast', 'deviceKey', 'shareRefused', 'sharePace', 'ingestRoute', 'webhookDown', 'sendState'])
})

test('1. the shared key sends v1; the answer gives a key of its own and a route, and the next send goes v2 to the receiver with that key', async () => {
  const c = computer()
  c.answer(() => ok({ ok: true, deviceKey: OWN, accepts: [1, 2], ingestUrls: [RECEIVER], ingestTtlMs: 3_600_000 }))
  expect(await c.send(NOW)).toEqual({ kind: 'sent', to: 'webhook', full: true, needFull: false })
  expect(c.calls).toMatchObject([{ url: `${WEBHOOK}/ingest`, method: 'POST', auth: 'Bearer k', body: { v: 1, seq: NOW } }])
  expect(c.data.deviceKey).toBe(OWN)
  expect(c.data.ingestRoute).toEqual({ urls: [RECEIVER], until: NOW + 3_600_000 })
  expect(c.data.sendState).toMatchObject({ v2: true, seq: NOW, fullAfter: NOW + 3_600_000 + 450_000 })
  expect(c.data.sharedLast).toMatchObject({ at: NOW })
  // the order of the reads and writes, as the versions before hooks/send.ts made them
  // thứ tự đọc và ghi, như các bản trước hooks/send.ts
  expect(c.log).toEqual([
    'get sharedLast', 'get shareRefused', 'get sharePace', 'get deviceKey', 'get sendState', 'set sendState',
    'get webhookDown', 'set sharePace', 'set sendState', 'set deviceKey', 'set ingestRoute', 'set sharedLast',
  ])

  c.answer(() => ok({ ok: true, accepts: [1, 2] }))
  expect(await c.send(NOW + 600_000)).toMatchObject({ kind: 'sent', to: 'receiver' })
  expect(c.calls[1]).toMatchObject({ url: `${RECEIVER}/ingest`, auth: `Bearer ${OWN}`, body: { v: 2 } })
})

for (const broken of [0, 500, 401, 404]) {
  test(`2. a receiver that answers ${broken || 'nothing'} puts the send off, rests, and takes the sends again once it answers`, async () => {
    const c = computer({ deviceKey: OWN, ingestRoute: { urls: [RECEIVER], until: NOW + 600_000 } })
    c.answer(x => (x.url.startsWith(RECEIVER) ? (broken ? status(broken) : undefined) : ok({ ok: true })))
    expect(await c.send(NOW)).toEqual({ kind: 'putOff' })
    expect(c.calls.map(x => x.url)).toEqual([`${RECEIVER}/ingest`])
    expect(c.data.ingestRoute).toEqual({ urls: [RECEIVER], until: NOW + 600_000, rest: { until: NOW + 60_000, wait: 60_000 } })
    expect((c.data.sharePace as { until: number }).until).toBe(NOW + 15_000)
    expect((c.data.sharePace as { until: number }).until).toBeLessThanOrEqual(NOW + 30_000)
    expect(c.data.sharedLast).toBeUndefined()
    // the key of its own is not dropped for what the receiver said
    // khoá riêng không bị bỏ vì điều bộ nhận nói
    expect(c.data.deviceKey).toBe(OWN)

    // before the wait: nothing; after it, the webhook takes the send while the route rests
    // trước khi hết chờ: không gửi; sau đó, webhook nhận lần gửi trong lúc tuyến nghỉ
    expect(await c.send(NOW + 10_000)).toEqual({ kind: 'notDue', why: 'busy' })
    expect(await c.send(NOW + 20_000)).toMatchObject({ kind: 'sent', to: 'webhook' })
    expect(c.calls.at(-1)!.url).toBe(`${WEBHOOK}/ingest`)
    expect((c.data.ingestRoute as { rest?: unknown }).rest).toBeDefined()

    // the rest is over and the receiver takes it: the rest is dropped
    // hết nghỉ và bộ nhận nhận được: bỏ thời gian nghỉ
    c.answer(() => ok({ ok: true }))
    expect(await c.send(NOW + 70_000)).toMatchObject({ kind: 'sent', to: 'receiver' })
    expect(c.data.ingestRoute).toEqual({ urls: [RECEIVER], until: NOW + 600_000 })
  })
}

test('3. a busy receiver (503 with Retry-After) is waited for: the send fails, the route holds, nothing rests and nothing goes to the webhook', async () => {
  const c = computer({ deviceKey: OWN, ingestRoute: { urls: [RECEIVER], until: NOW + 600_000 } })
  c.answer(() => status(503, { 'retry-after': '30' }))
  expect(await c.send(NOW)).toEqual({ kind: 'failed', status: 503 })
  expect(c.calls.map(x => x.url)).toEqual([`${RECEIVER}/ingest`])
  expect(c.data.ingestRoute).toEqual({ urls: [RECEIVER], until: NOW + 600_000 })
  expect(c.data.sharePace).toEqual({ until: NOW + 30_000 })
  expect(c.data.webhookDown).toBeUndefined()
  expect(await c.send(NOW + 29_000)).toEqual({ kind: 'notDue', why: 'busy' })
})

test('4. a webhook that does not answer, or answers 5xx, backs off from 5 seconds doubling to 5 minutes; a send that goes through clears it', async () => {
  const c = computer()
  let at = NOW
  const waits: number[] = []
  for (let i = 0; i < 8; i++) {
    c.answer(() => (i % 2 ? status(500) : undefined))
    expect(await c.send(at)).toEqual({ kind: 'failed', status: i % 2 ? 500 : 0 })
    const down = c.data.webhookDown as { until: number; wait: number }
    waits.push(down.wait)
    expect(down.until).toBe(at + down.wait)
    expect((c.data.sharePace as { until: number }).until).toBe(down.until)
    at = down.until
  }
  expect(waits).toEqual([5_000, 10_000, 20_000, 40_000, 80_000, 160_000, 300_000, 300_000])
  c.answer(() => ok({ ok: true }))
  expect(await c.send(at)).toMatchObject({ kind: 'sent', to: 'webhook' })
  expect(c.data.webhookDown).toBeUndefined()
})

test('5. a refused key of its own is dropped, the refusals wait longer each time, and a send that goes through clears them', async () => {
  const c = computer({ deviceKey: OWN })
  c.answer(() => status(401))
  expect(await c.send(NOW)).toEqual({ kind: 'failed', status: 401 })
  expect(c.data.deviceKey).toBeUndefined()
  expect(c.data.shareRefused).toEqual({ until: NOW + 30_000, wait: 30_000 })
  expect(await c.send(NOW + 10_000)).toEqual({ kind: 'notDue', why: 'refused' })
  // the shared key now, refused too: the wait doubles
  // giờ là khoá chung, cũng bị từ chối: thời gian chờ gấp đôi
  expect(await c.send(NOW + 30_000)).toEqual({ kind: 'failed', status: 401 })
  expect(c.calls.at(-1)!.auth).toBe('Bearer k')
  expect(c.data.shareRefused).toEqual({ until: NOW + 90_000, wait: 60_000 })
  c.answer(() => ok({ ok: true, deviceKey: NEW_OWN }))
  expect(await c.send(NOW + 90_000)).toMatchObject({ kind: 'sent' })
  expect(c.data.shareRefused).toBeUndefined()
  expect(c.data.deviceKey).toBe(NEW_OWN)

  // 403 refuses the send but keeps the key
  // 403 từ chối lần gửi nhưng giữ khoá
  const d = computer({ deviceKey: OWN })
  d.answer(() => status(403))
  expect(await d.send(NOW)).toEqual({ kind: 'failed', status: 403 })
  expect(d.data.deviceKey).toBe(OWN)
  expect(d.data.shareRefused).toEqual({ until: NOW + 30_000, wait: 30_000 })
})

test('6. a route that ran out is asked again: a good answer is kept, no answer or a host not allowed sends to the webhook, and an empty list drops it', async () => {
  const expired = { urls: [RECEIVER], until: NOW - 1 }
  const asked = (answer: Answer | undefined, v2: boolean) => {
    const c = computer({ deviceKey: OWN, ingestRoute: expired, ...(v2 ? { sendState: { v2: true, seq: 1 } } : {}) })
    c.answer(x => (x.url.includes('/ingest/route') ? answer : ok({ ok: true })))
    return c
  }

  const good = asked(ok({ ingestUrls: [RECEIVER2], ingestTtlMs: 600_000 }), true)
  expect(await good.send(NOW)).toMatchObject({ kind: 'sent', to: 'receiver' })
  expect(good.calls.map(x => [x.method, x.url, x.auth])).toEqual([
    ['GET', `${WEBHOOK}/ingest/route?v=2`, `Bearer ${OWN}`],
    ['POST', `${RECEIVER2}/ingest`, `Bearer ${OWN}`],
  ])
  expect(good.data.ingestRoute).toEqual({ urls: [RECEIVER2], until: NOW + 600_000 })

  const v1 = asked(ok({ ingestUrls: [RECEIVER2] }), false)
  await v1.send(NOW)
  expect(v1.calls[0]!.url).toBe(`${WEBHOOK}/ingest/route`)

  for (const bad of [undefined, status(500), ok({ ingestUrls: ['https://ingest.example.net'] })]) {
    const c = asked(bad, true)
    expect(await c.send(NOW)).toMatchObject({ kind: 'sent', to: 'webhook' })
    expect(c.calls.at(-1)!.url).toBe(`${WEBHOOK}/ingest`)
    expect(c.data.ingestRoute).toBeUndefined()
  }

  // the webhook says send here again (an empty list): the route is dropped
  // webhook bảo gửi lại về đây (danh sách rỗng): bỏ tuyến
  const back = computer({ deviceKey: OWN, ingestRoute: { urls: [RECEIVER], until: NOW + 600_000 } })
  back.answer(() => ok({ ok: true, ingestUrls: [] }))
  await back.send(NOW)
  expect(back.data.ingestRoute).toBeUndefined()
})

test('7. the gates: the same numbers wait 5 minutes, the gap the server asks is kept, a lost answer still raises the next number, and the folder', async () => {
  const c = computer()
  expect(await c.send(NOW)).toMatchObject({ kind: 'sent' })
  expect(await c.send(NOW + 60_000, WEB, true)).toEqual({ kind: 'notDue', why: 'same' })
  expect(await c.send(NOW + 300_001, WEB, true)).toMatchObject({ kind: 'sent' })

  // the gap the server asks goes to the session's memory and to the store
  // khoảng cách máy chủ dặn vào bộ nhớ của phiên và vào kho
  c.answer(() => ok({ ok: true, minGapMs: 10_000 }))
  await c.send(NOW + 400_000)
  expect(c.mem.gapMs).toBe(10_000)
  expect(c.data.sharePace).toEqual({ gapMs: 10_000 })
  expect(await c.send(NOW + 405_000)).toEqual({ kind: 'notDue', why: 'busy' })
  expect(await c.send(NOW + 411_000)).toMatchObject({ kind: 'sent' })
  // another session reads the gap from the store
  // một phiên khác đọc khoảng cách từ kho
  c.mem.gapMs = PACE_MIN_MS
  expect(await c.send(NOW + 415_000)).toEqual({ kind: 'notDue', why: 'busy' })
  expect(c.mem.gapMs).toBe(10_000)

  // the number is kept before the send: after a lost answer and a clock gone back, the next send is still above it
  // số được giữ trước khi gửi: sau một câu trả lời bị mất và đồng hồ lùi, lần gửi sau vẫn cao hơn
  const lost = computer()
  lost.answer(() => undefined)
  await lost.send(NOW)
  expect((lost.data.sendState as { seq: number }).seq).toBe(NOW)
  delete lost.data.sharePace
  delete lost.data.webhookDown
  lost.answer(() => ok({ ok: true }))
  await lost.send(NOW - 60_000)
  expect(lost.calls.at(-1)!.body!.seq).toBe(NOW + 1)

  // the folder: neither a refusal nor a busy server holds it back, and no network
  // thư mục: không lần từ chối hay máy chủ bận nào giữ nó lại, và không dùng mạng
  const written: string[] = []
  const f = computer({ shareRefused: { until: NOW + 60_000, wait: 30_000 }, sharePace: { until: NOW + 60_000 } })
  expect(await f.send(NOW, { kind: 'folder', write: async j => void written.push(j) })).toEqual({ kind: 'sent', to: 'folder', full: true, needFull: false })
  expect(written.length).toBe(1)
  expect(JSON.parse(written[0]!)).toMatchObject({ v: 1, device: 'device-a', name: 'An 1' })
  expect(f.calls).toEqual([])
  expect(f.data.sharedLast).toMatchObject({ at: NOW })
})

test('a write of the store that must not be lost throws; one whose loss only costs a send again does not', async () => {
  const c = computer({ deviceKey: OWN, ingestRoute: { urls: [RECEIVER], until: NOW - 1 } })
  c.answer(x => (x.url.includes('/ingest/route') ? ok({ ingestUrls: [RECEIVER] }) : ok({ ok: true })))
  const failing = new Set(['ingestRoute', 'sendState'])
  const store = {
    get: async (k: string) => structuredClone(c.data[k]),
    set: async (k: string, v: unknown) => {
      if (failing.has(k)) throw new Error('disk full')
      c.data[k] = v
    },
    delete: async (k: string) => void delete c.data[k],
  }
  const fetch = async () => ok({ ingestUrls: [RECEIVER] })
  await expect(send({ store, fetch, random: () => 0.5 }, WEB, c.mem, summaryOf('An', NOW), NOW)).rejects.toThrow('disk full')
  failing.delete('ingestRoute')
  expect(await send({ store, fetch, random: () => 0.5 }, WEB, c.mem, summaryOf('An', NOW), NOW)).toMatchObject({ kind: 'sent' })
})
