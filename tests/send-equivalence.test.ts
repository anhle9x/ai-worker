import { expect, test } from 'claude-code/testing'
import type { Answer } from '../hooks/io'
import { send, type SendMem, type SendResult } from '../hooks/send'
import { afterAnswer, packetFor, type SendState } from '../hooks/sendv2'
import {
  backoff, buildMachineSummary, deviceKeyIn, FALLBACK_SPREAD_MS, paceFrom, PACE_MIN_MS, receiverOutcome, refusalAfter, routeFrom, routeRested,
  routeTarget, summarySignature, WEBHOOK_BACKOFF_FIRST_MS, WEBHOOK_BACKOFF_MAX_MS, webhookDown, type IngestRoute, type MachineSummary,
} from '../hooks/team'

// TEMPORARY, until the release after hooks/send.ts: the block shareOnce ran before the cut, copied word for word from register.tsx of
// 0.50.27 (37a155f, lines 818 to 927), against send() on the same seeded runs: the same reads and writes of the store, the same requests,
// the same outcome. Delete this file after that release.
// TẠM THỜI, tới bản phát hành sau hooks/send.ts: khối shareOnce chạy trước khi tách, chép nguyên văn từ register.tsx của 0.50.27
// (37a155f, dòng 818 tới 927), so với send() trên cùng các lượt chạy có hạt giống: cùng các lần đọc ghi kho, cùng các yêu cầu, cùng kết
// quả. Xoá file này sau bản phát hành đó.

const SHARE_EVERY_MS = 5 * 60_000
const SHARED_KEY = 'sharedLast'
const DEVICE_KEY = 'deviceKey'
const REFUSED_KEY = 'shareRefused'
const PACE_KEY = 'sharePace'
const ROUTE_KEY = 'ingestRoute'
const WEBHOOK_DOWN_KEY = 'webhookDown'
const SEND_KEY = 'sendState'

type Init = { method: string; headers: Record<string, string>; body?: string }
type Fake = {
  store: { get(k: string): Promise<unknown>; set(k: string, v: unknown): Promise<void>; delete(k: string): Promise<void> }
  http: { fetch(url: string, init: Init): Promise<Answer> }
  fs: { write(path: string, text: string): Promise<void> }
}
type Share = { webhook: string; ingestKey: string; ingestHosts: string[] }

/** The old block, as it was; `paceGapMs` is the session's variable it read and wrote. */
/** Khối cũ, y nguyên; `paceGapMs` là biến của phiên mà nó đọc và ghi. */
async function reference($: Fake, share: Share, folder: string, device: string, summary: MachineSummary, now: number, mem: SendMem): Promise<void> {
  const viaWeb = share.webhook !== ''
  const dir = ''
  const noteShare = async (_$: Fake, _dir: string, _now: number) => undefined
  let paceGapMs = mem.gapMs
  try {
    const sig = summarySignature(summary)
    const last = ((await $.store.get(SHARED_KEY).catch(() => undefined)) ?? {}) as { sig?: string; at?: number }
    const refused = ((await $.store.get(REFUSED_KEY).catch(() => undefined)) ?? {}) as { until?: number; wait?: number }
    const pace = ((await $.store.get(PACE_KEY).catch(() => undefined)) ?? {}) as { gapMs?: number; until?: number }
    if (typeof pace.gapMs === 'number') paceGapMs = pace.gapMs
    // a busy server said when to come back: nothing before then, not even the beat that sends when nothing changed
    // máy chủ bận đã nói khi nào quay lại: không gửi gì trước lúc đó, kể cả nhịp gửi khi không có gì đổi
    // and never two sends closer than the gap it asked, the beat's included
    // và không bao giờ hai lần gửi sát hơn khoảng cách nó dặn, kể cả lần gửi của nhịp tim
    const busy = viaWeb && (now < (pace.until ?? 0) || now - (last.at ?? 0) < paceGapMs)
    if ((sig !== last.sig || now - (last.at ?? 0) > SHARE_EVERY_MS) && !(viaWeb && now < (refused.until ?? 0)) && !busy) {
      if (viaWeb) {
        // this computer's own key once the server has given it one, else the key of the install package
        // khoá riêng của máy này khi máy chủ đã cấp, nếu không thì khoá của gói cài
        const own = await $.store.get(DEVICE_KEY).catch(() => undefined)
        const key = typeof own === 'string' && own.startsWith('awd1.') ? own : share.ingestKey
        // v: 1 until the server says it reads v: 2, then only the hours that changed, and the whole book once an hour
        // v: 1 cho tới khi máy chủ nói nó đọc v: 2, sau đó chỉ các giờ đã đổi, và cả sổ mỗi giờ một lần
        const sendState = (await $.store.get(SEND_KEY).catch(() => undefined)) as SendState | undefined
        const packet = packetFor(summary, sendState, now)
        // the number is kept before the send: a send whose answer is lost may still have been written, and the next one must be above it
        // số được giữ trước khi gửi: lần gửi mất câu trả lời vẫn có thể đã được ghi, và lần sau phải có số cao hơn
        await $.store.set(SEND_KEY, { ...sendState, seq: packet.seq }).catch(() => undefined)
        const body = JSON.stringify(packet.body)
        const post = (base: string) => $.http.fetch(`${base}/ingest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
          body,
        })
        // the Go receiver takes only a computer's own key: the shared key of the package always goes to the webhook
        // bộ nhận Go chỉ nhận khoá riêng của máy: khoá chung của gói luôn đi tới webhook
        const ownKey = key !== share.ingestKey
        let route = ownKey ? ((await $.store.get(ROUTE_KEY).catch(() => undefined)) as IngestRoute | undefined) : undefined
        if (route && !(route.until > now)) {
          // the address ran out: ask the webhook where to send now, which writes nothing; no answer sends to the webhook
          // địa chỉ đã hết hạn: hỏi webhook giờ gửi tới đâu, việc này không ghi gì; không trả lời thì gửi tới webhook
          const asked = await $.http.fetch(`${share.webhook}/ingest/route${sendState?.v2 ? '?v=2' : ''}`, { method: 'GET', headers: { Authorization: `Bearer ${key}` } }).catch(() => undefined)
          route = (asked?.ok ? routeFrom(asked.text, share.webhook, share.ingestHosts, now) : null) ?? undefined
          if (route) await $.store.set(ROUTE_KEY, route)
          else await $.store.delete(ROUTE_KEY).catch(() => undefined)
        }
        const target = route ? routeTarget(route, now) : undefined
        // the webhook; no answer at all counts as status 0, as a 5xx without Retry-After does: the sends after it back off
        // webhook; không trả lời gì được tính là mã 0, như 5xx không có Retry-After: các lần gửi sau đó lùi lại
        const toWebhook = async () => {
          const got = (await post(share.webhook).catch(() => undefined)) ?? { ok: false, status: 0, headers: {}, text: '' }
          const down = (await $.store.get(WEBHOOK_DOWN_KEY).catch(() => undefined)) as { wait?: number } | undefined
          if (webhookDown(got)) {
            const b = backoff(down, now, WEBHOOK_BACKOFF_FIRST_MS, WEBHOOK_BACKOFF_MAX_MS, 0.5)
            await $.store.set(WEBHOOK_DOWN_KEY, b).catch(() => undefined)
            await $.store.set(PACE_KEY, { gapMs: pace.gapMs, until: b.until }).catch(() => undefined)
          } else if (down) {
            await $.store.delete(WEBHOOK_DOWN_KEY).catch(() => undefined)
          }
          return got
        }
        let r: Awaited<ReturnType<typeof post>> | undefined
        if (target && route) {
          const got = await post(target).catch(() => undefined)
          if (receiverOutcome(got) === 'fallback') {
            // the receiver could not take it (down, unreachable, its key check, a missing path): the webhook takes the sends for a
            // while, longer each time, and this one goes there after a wait under 30 seconds at random, so a whole office that lost
            // the receiver together reaches the webhook spread out
            // bộ nhận không nhận được (đã dừng, không tới được, kiểm khoá ở đó, thiếu đường): webhook nhận các lần gửi trong một lúc,
            // lâu dần mỗi lần, và lần này đi tới đó sau một khoảng chờ ngẫu nhiên dưới 30 giây, để cả văn phòng cùng mất bộ nhận tới
            // webhook rải ra
            route = routeRested(route, now)
            await $.store.set(ROUTE_KEY, route)
            await $.store.set(PACE_KEY, { gapMs: pace.gapMs, until: now + Math.round(Math.random() * FALLBACK_SPREAD_MS) }).catch(() => undefined)
          } else {
            r = got!
            if (route.rest) await $.store.set(ROUTE_KEY, { urls: route.urls, until: route.until })
          }
        } else {
          r = await toWebhook()
        }
        // put off to the webhook: nothing was sent, the next beat after the wait sends it
        // hoãn sang webhook: chưa gửi gì, nhịp sau khi hết chờ sẽ gửi
        if (!r) return
        // its own key refused (too old, or the server was set up again): drop it, so the next send asks for a new one
        // khoá riêng bị từ chối (quá cũ, hoặc máy chủ được cài lại): bỏ nó, để lần gửi sau xin khoá mới
        if (r.status === 401 && key !== share.ingestKey) await $.store.delete(DEVICE_KEY).catch(() => undefined)
        // a refusal does not pass by itself: wait longer each time instead of asking again every second
        // lần từ chối không tự hết: chờ lâu dần thay vì hỏi lại mỗi giây
        if (r.status === 401 || r.status === 403) {
          await $.store.set(REFUSED_KEY, refusalAfter(refused, now))
        }
        // the gap the server asks, or when to come back after "busy", for every session of this computer
        // khoảng cách máy chủ dặn, hoặc lúc quay lại sau "bận", cho mọi phiên trên máy này
        const asked = paceFrom(r, now)
        if (asked.gapMs !== undefined || asked.until !== undefined) {
          if (asked.gapMs !== undefined) paceGapMs = asked.gapMs
          await $.store.set(PACE_KEY, { gapMs: asked.gapMs ?? pace.gapMs, until: asked.until }).catch(() => undefined)
        }
        if (!r.ok) throw new Error(`webhook ${r.status}`)
        await $.store.set(SEND_KEY, afterAnswer(sendState, r.text, packet, now)).catch(() => undefined)
        if (refused.wait) await $.store.delete(REFUSED_KEY).catch(() => undefined)
        const given = deviceKeyIn(r.text)
        if (given) await $.store.set(DEVICE_KEY, given)
        // the webhook says where to send from now on: the Go receiver, or here again (an empty list); nothing said keeps what is held
        // webhook dặn từ giờ gửi tới đâu: bộ nhận Go, hoặc lại về đây (danh sách rỗng); không dặn gì thì giữ cái đang có
        const next = ownKey || given ? routeFrom(r.text, share.webhook, share.ingestHosts, now) : undefined
        if (next) await $.store.set(ROUTE_KEY, route?.rest && route.urls.join() === next.urls.join() ? { ...next, rest: route.rest } : next)
        else if (next === null) await $.store.delete(ROUTE_KEY).catch(() => undefined)
      } else {
        await $.fs.write(`${folder}/${device}.json`, JSON.stringify(summary))
      }
      await $.store.set(SHARED_KEY, { sig, at: now })
      if (viaWeb) await noteShare($, dir, now)
    }
  } finally {
    mem.gapMs = paceGapMs
  }
}

/** A small seeded random (mulberry32): the same seed gives the same run. */
/** Bộ ngẫu nhiên nhỏ có hạt giống (mulberry32): cùng hạt giống cho cùng lượt chạy. */
function seeded(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const NOW = 1_800_000_000_000
const WEBHOOK = 'https://board.example.com'
const RECEIVER = 'https://ingest.example.com'
const OWN = 'awd1.a.b.c.d.e.f.g'
const NEW_OWN = 'awd1.h.i.j.k.l.m.n'
const SHARE: Share = { webhook: WEBHOOK, ingestKey: 'k', ingestHosts: [] }

const pick = <T>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)]!

/** What the store holds at the start of a run, near what computers in the pilot hold. */
/** Kho có gì lúc bắt đầu một lượt chạy, gần với những gì các máy thí điểm đang giữ. */
function startStore(r: () => number): Record<string, unknown> {
  const kept: Record<string, unknown> = {}
  const maybe = (k: string, xs: unknown[]) => {
    const v = pick(r, [undefined, ...xs])
    if (v !== undefined) kept[k] = v
  }
  maybe(DEVICE_KEY, [OWN, 'old-key', 'awd1.short'])
  maybe(ROUTE_KEY, [
    { urls: [RECEIVER], until: NOW + 600_000 },
    { urls: [RECEIVER], until: NOW - 1 },
    { urls: [RECEIVER], until: NOW + 600_000, rest: { until: NOW + 30_000, wait: 60_000 } },
    { urls: [RECEIVER], until: NOW + 600_000, rest: { until: NOW - 1, wait: 120_000 } },
  ])
  maybe(PACE_KEY, [{ gapMs: 5_000 }, { until: NOW + 20_000 }, { gapMs: 2_000, until: NOW - 1 }])
  maybe(REFUSED_KEY, [{ until: NOW + 10_000, wait: 30_000 }, { until: NOW - 1, wait: 60_000 }, { until: NOW - 1 }])
  maybe(WEBHOOK_DOWN_KEY, [{ until: NOW - 1, wait: 5_000 }, { until: NOW + 3_000, wait: 20_000 }])
  maybe(SEND_KEY, [{ seq: NOW + 50 }, { v2: true, seq: 7 }, { v2: true, seq: 7, acked: { ledger: {}, tasks: {}, blocks: {} }, fullAfter: NOW + 1, boot: 'b1' }])
  maybe(SHARED_KEY, [{ sig: 'other', at: NOW - 1_000 }, { sig: 'other', at: NOW - 400_000 }])
  return kept
}

/** One answer the server or the receiver may give. */
/** Một câu trả lời máy chủ hay bộ nhận có thể đưa. */
function anAnswer(r: () => number): Answer | undefined {
  const s = pick(r, [200, 200, 200, 200, 0, 401, 403, 404, 429, 500, 503])
  if (s === 0) return undefined
  const headers: Record<string, string> = r() < 0.5 ? { 'retry-after': pick(r, ['30', '0', 'x', '900']) } : {}
  if (s !== 200) return { ok: false, status: s, headers, text: pick(r, ['', '{}', '{"error":"x"}']) }
  const body: Record<string, unknown> = { ok: true }
  if (r() < 0.3) body.deviceKey = pick(r, [NEW_OWN, 'nope'])
  if (r() < 0.5) body.accepts = pick(r, [[1, 2], [1]])
  if (r() < 0.4) body.ingestUrls = pick(r, [[RECEIVER], [], ['https://ingest.example.net'], [RECEIVER, 'https://ingest2.example.com']])
  if (r() < 0.3) body.ingestTtlMs = pick(r, [1, 600_000, 99_999_999_999])
  if (r() < 0.3) body.minGapMs = pick(r, [10, 10_000, 999_999])
  if (r() < 0.2) body.needFull = true
  if (r() < 0.2) body.boot = pick(r, ['b1', 'b2'])
  return { ok: true, status: 200, headers, text: r() < 0.05 ? 'not json' : JSON.stringify(body) }
}

type World = { kept: Record<string, unknown>; log: string[] }

/** A fake engine over `w`; `faults` decides which store calls and writes throw, `answers` what each request gets. */
/** Engine giả trên `w`; `faults` quyết định lệnh kho và lệnh ghi nào ném lỗi, `answers` mỗi yêu cầu nhận gì. */
function fake(w: World, faults: () => number, answers: () => number): Fake {
  const fail = (what: string) => {
    if (faults() < 0.04) {
      w.log.push(`${what} THROWS`)
      throw new Error(`store ${what}`)
    }
  }
  return {
    store: {
      async get(k) {
        w.log.push(`get ${k}`)
        fail('get')
        return structuredClone(w.kept[k])
      },
      async set(k, v) {
        w.log.push(`set ${k} ${JSON.stringify(v)}`)
        fail('set')
        w.kept[k] = structuredClone(v)
      },
      async delete(k) {
        w.log.push(`delete ${k}`)
        fail('delete')
        delete w.kept[k]
      },
    },
    http: {
      async fetch(url, init) {
        w.log.push(`fetch ${init.method} ${url} ${init.headers.Authorization} ${init.body ?? ''}`)
        const a = anAnswer(answers)
        if (!a) throw new Error('no answer')
        return a
      },
    },
    fs: {
      async write(path, text) {
        w.log.push(`write ${path} ${text}`)
        fail('write')
      },
    },
  }
}

function outcome(w: World, from: number, err: unknown): string {
  if (err !== undefined) {
    const m = /^webhook (\d+)$/.exec(String((err as Error).message))
    return m ? `failed ${m[1]}` : `throws ${(err as Error).message}`
  }
  const step = w.log.slice(from)
  if (step.some(l => l.startsWith('set sharedLast') && !l.endsWith('THROWS'))) return 'sent'
  return step.some(l => l.startsWith('fetch POST')) ? 'putOff' : 'notDue'
}

// Math.random cannot be replaced in the test sandbox, Math itself can: a Math whose random is seeded, the rest the real one
// Math.random không thay được trong sandbox của test, còn chính Math thì được: một Math có random theo hạt giống, phần còn lại là Math thật
const realMath = Math
const g = globalThis as unknown as { Math: Math }
const seedMath = (seed: number) => {
  g.Math = Object.create(realMath, { random: { value: seeded(seed) } }) as Math
}

function named(r: SendResult): string {
  return r.kind === 'failed' ? `failed ${r.status}` : r.kind
}

test('send() reads, writes, asks and ends exactly as the block of shareOnce it replaced, on 500 seeded runs', async () => {
  let steps = 0
  try {
    for (let run = 1; run <= 500; run++) {
      const plan = seeded(run)
      const start = startStore(plan)
      const viaFolder = run % 10 === 0
      const old: World = { kept: structuredClone(start), log: [] }
      const now: World = { kept: structuredClone(start), log: [] }
      const oldMem: SendMem = { gapMs: PACE_MIN_MS }
      const newMem: SendMem = { gapMs: PACE_MIN_MS }
      let at = NOW
      for (let step = 0; step < 6; step++) {
        at += pick(plan, [0, 1_000, 2_000, 2_500, 15_000, 31_000, 61_000, 300_000, 301_000, 3_700_000, -60_000])
        const summary = buildMachineSummary([], undefined, at, { device: 'device-a', name: pick(plan, ['An', 'An', 'Binh']), account: 'an@example.com' })
        const seed = Math.floor(plan() * 2 ** 31)
        const oldFrom = old.log.length
        const newFrom = now.log.length
        // the same faults, answers and random numbers for both, drawn in the order each asks for them
        // cùng lỗi, câu trả lời và số ngẫu nhiên cho cả hai, rút theo thứ tự mỗi bên cần
        let oldErr: unknown
        seedMath(seed + 3)
        try {
          await reference(fake(old, seeded(seed + 1), seeded(seed + 2)), viaFolder ? { webhook: '', ingestKey: '', ingestHosts: [] } : SHARE, viaFolder ? '/nas' : '', 'device-a', summary, at, oldMem)
        } catch (e) {
          oldErr = e
        }
        let newName: string
        const $ = fake(now, seeded(seed + 1), seeded(seed + 2))
        seedMath(seed + 3)
        try {
          const target = viaFolder ? { kind: 'folder' as const, write: (json: string) => $.fs.write('/nas/device-a.json', json) } : { kind: 'web' as const, ...SHARE }
          newName = named(await send({ store: $.store, fetch: (u, i) => $.http.fetch(u, i), random: () => Math.random() }, target, newMem, summary, at))
        } catch (e) {
          newName = `throws ${(e as Error).message}`
        }
        g.Math = realMath
        const where = `run ${run}, step ${step}`
        expect([where, now.log.slice(newFrom)]).toEqual([where, old.log.slice(oldFrom)])
        expect([where, newName]).toEqual([where, outcome(old, oldFrom, oldErr)])
        expect([where, newMem.gapMs]).toEqual([where, oldMem.gapMs])
        expect([where, now.kept]).toEqual([where, old.kept])
        steps++
      }
    }
  } finally {
    g.Math = realMath
  }
  expect(steps).toBe(3_000)
})
