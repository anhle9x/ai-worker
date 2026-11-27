import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'

type Engine = Parameters<TestBody>[0]

// End to end through the engine: the send that session.start makes, with the store keys and answers a real computer meets.
// Written on the code before hooks/send.ts was cut out of shareOnce, and kept byte for byte after it: the cut must not change a send.
// Đầu-cuối qua engine: lần gửi mà session.start tạo ra, với các khoá kho và câu trả lời mà một máy thật gặp.
// Viết trên mã trước khi hooks/send.ts được tách khỏi shareOnce, và giữ nguyên từng byte sau đó: việc tách không được đổi một lần gửi nào.

// a clock far from 0: at 0 every send is too close to the last one (never sent, at 0) and waits
// đồng hồ xa mốc 0: ở mốc 0 mọi lần gửi đều quá sát lần trước (chưa gửi, ở 0) nên phải chờ
const NOW = 1_800_000_000_000
const WEBHOOK = 'https://board.example.com'
const RECEIVER = 'https://ingest.example.com'
// a key-shaped value put together here, so this file holds none the commit check flags (as in tests/commitscan.test.ts)
// giá trị có hình dạng khoá ghép ở đây, để file này không chứa giá trị nào bị bước kiểm commit bắt (như trong tests/commitscan.test.ts)
const OWN_KEY = 'awd1' + '.a.b.c.d.e.f.g'

type Sent = { url: string; method: string; auth: string; body?: Record<string, unknown> }
type Reply = { ok: boolean; status: number; headers: Record<string, string>; text: string }
type Seen = { sent: Sent[]; shareState: string[]; kept: Record<string, unknown> }

/** A staff computer whose package sends to WEBHOOK; `answer` replies to each POST /ingest (undefined: no answer at all). */
/** Một máy nhân viên có gói gửi tới WEBHOOK; `answer` trả lời mỗi POST /ingest (undefined: không trả lời gì). */
function staffComputer(on: On, kept: Record<string, unknown>, answer: (url: string) => Reply | undefined): Seen {
  const seen: Seen = { sent: [], shareState: [], kept }
  mock.clock(on, { now: NOW })
  // the store by hand, not mock.store: the test reads what the plugin wrote
  // kho tự dựng, không dùng mock.store: test đọc lại những gì plugin đã ghi
  on('store.get', (_, e) => ({ value: structuredClone(kept[(e as unknown as { key: string }).key]) }) as never)
  on('store.set', (_, e) => {
    const { key, value } = e as unknown as { key: string; value: unknown }
    kept[key] = structuredClone(value)
    return { value: undefined } as never
  })
  on('store.delete', (_, e) => {
    delete kept[(e as unknown as { key: string }).key]
    return { value: undefined } as never
  })
  mock.env(on, { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.surfaces', () => ({ value: ['desktop'] }))
  on('tool.list', () => ({ value: [] }) as never)
  on('fs.exists', (_, e) => ({ value: !e.path.endsWith('/.git') && !e.path.endsWith('company.json') }))
  on('fs.list', () => ({ value: [] }) as never)
  on('fs.write', (_, e) => {
    if (e.path.endsWith('/share-state.js')) seen.shareState.push(String(e.text))
    return { value: undefined }
  })
  on('fs.read', (_, e) => {
    if (e.path.endsWith('/.claude-plugin/plugin.json')) return { value: '{"version":"9.9.8"}' }
    if (e.path.endsWith('/web/company.json')) return { value: JSON.stringify({ sharing: { enabled: true, name: 'An', webhook: WEBHOOK, ingestKey: 'k' } }) }
    if (e.path.includes('/web/')) return { value: '' }
    throw new Error('no such file')
  })
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('http.fetch', (_, e) => {
    const headers = (e.init?.headers ?? {}) as Record<string, string>
    if (!e.url.endsWith('/ingest')) return { value: { ok: false, status: 404, headers: {}, text: '' } }
    const body = e.init?.body ? (JSON.parse(String(e.init.body)) as Record<string, unknown>) : undefined
    seen.sent.push({ url: e.url, method: e.init?.method ?? 'GET', auth: headers.Authorization ?? '', body })
    const r = answer(e.url)
    if (!r) throw new Error('no answer')
    return { value: r }
  })
  return seen
}

/** Starts a session and waits for its first send to settle (the send runs after session.start returns). */
/** Mở một phiên và chờ lần gửi đầu tiên xong (lần gửi chạy sau khi session.start trả về). */
async function startAndSettle($: Engine, seen: Seen) {
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const settled = () => (seen.sent.length && seen.kept.sharedLast) || seen.shareState.length || (seen.kept.ingestRoute as { rest?: unknown } | undefined)?.rest
  for (let i = 0; i < 60 && !settled(); i++) await new Promise(r => setTimeout(r, 50))
  // a little more, for the writes that follow the answer
  // thêm một chút, cho các lần ghi sau câu trả lời
  await new Promise(r => setTimeout(r, 200))
}

const ok = (body: unknown): Reply => ({ ok: true, status: 200, headers: {}, text: JSON.stringify(body) })

test('the first send uses the shared key of the package and keeps the key of its own the server gives', async ($, on) => {
  const seen = staffComputer(on, {}, () => ok({ ok: true, deviceKey: OWN_KEY, accepts: [1, 2] }))
  await startAndSettle($, seen)
  expect(seen.sent.length).toBe(1)
  expect(seen.sent[0]).toMatchObject({ url: `${WEBHOOK}/ingest`, method: 'POST', auth: 'Bearer k' })
  expect(seen.sent[0]!.body).toMatchObject({ v: 1, name: 'An' })
  // the seven keys of the store keep their names and shapes: a computer in the pilot must not lose its key or route
  // bảy khoá của kho giữ nguyên tên và hình dạng: máy đang thí điểm không được mất khoá hay tuyến
  expect(seen.kept.deviceKey).toBe(OWN_KEY)
  expect(seen.kept.sharedLast).toMatchObject({ at: NOW })
  expect(typeof (seen.kept.sharedLast as { sig: unknown }).sig).toBe('string')
  expect(seen.kept.sendState).toMatchObject({ v2: true })
  expect(seen.kept.shareRefused).toBeUndefined()
  expect(seen.kept.webhookDown).toBeUndefined()
  expect(seen.kept.ingestRoute).toBeUndefined()
  expect(seen.shareState).toEqual(['window.__aiWorkerShare = null;\n'])
})

test('a computer with its own key and a route held sends to the receiver, not the webhook', async ($, on) => {
  const seen = staffComputer(on, { deviceKey: OWN_KEY, ingestRoute: { urls: [RECEIVER], until: NOW + 600_000 } }, () => ok({ ok: true }))
  await startAndSettle($, seen)
  expect(seen.sent.map(s => [s.url, s.auth])).toEqual([[`${RECEIVER}/ingest`, `Bearer ${OWN_KEY}`]])
  expect(seen.kept.ingestRoute).toEqual({ urls: [RECEIVER], until: NOW + 600_000 })
  expect(seen.kept.deviceKey).toBe(OWN_KEY)
  expect(seen.kept.sharedLast).toMatchObject({ at: NOW })
})

test('a webhook that does not answer backs the sends off and leaves a warning for the page', async ($, on) => {
  const seen = staffComputer(on, {}, () => undefined)
  await startAndSettle($, seen)
  expect(seen.sent.length).toBe(1)
  const down = seen.kept.webhookDown as { until: number; wait: number }
  expect(down.wait).toBe(5_000)
  // 5 seconds, spread by up to half either way
  // 5 giây, lệch tới một nửa mỗi phía
  expect(down.until).toBeGreaterThanOrEqual(NOW + 2_500)
  expect(down.until).toBeLessThanOrEqual(NOW + 7_500)
  expect(seen.kept.sharePace).toMatchObject({ until: down.until })
  // nothing reached the server: the last send is not moved
  // không có gì tới máy chủ: lần gửi gần nhất không bị dời
  expect(seen.kept.sharedLast).toBeUndefined()
  expect(seen.kept.deviceKey).toBeUndefined()
  const state = seen.shareState.at(-1)!
  expect(state.startsWith('window.__aiWorkerShare = {')).toBe(true)
  const data = JSON.parse(state.slice(state.indexOf('{'), state.lastIndexOf('}') + 1)) as { since: number; error: string }
  expect(data.since).toBe(NOW)
  expect(data.error).toBe('The team board server reported error 0.')
})

test('a receiver that fails puts the send off: nothing goes to the webhook this time, and the route rests', async ($, on) => {
  const seen = staffComputer(on, { deviceKey: OWN_KEY, ingestRoute: { urls: [RECEIVER], until: NOW + 600_000 } }, url =>
    url.startsWith(RECEIVER) ? { ok: false, status: 500, headers: {}, text: '' } : ok({ ok: true }))
  await startAndSettle($, seen)
  expect(seen.sent.map(s => s.url)).toEqual([`${RECEIVER}/ingest`])
  const route = seen.kept.ingestRoute as { urls: string[]; until: number; rest: { until: number; wait: number } }
  expect(route.urls).toEqual([RECEIVER])
  expect(route.until).toBe(NOW + 600_000)
  expect(route.rest.wait).toBe(60_000)
  // this send goes to the webhook after a wait under 30 seconds at random
  // lần gửi này đi tới webhook sau một khoảng chờ ngẫu nhiên dưới 30 giây
  const pace = seen.kept.sharePace as { until: number }
  expect(pace.until).toBeGreaterThanOrEqual(NOW)
  expect(pace.until).toBeLessThanOrEqual(NOW + 30_000)
  expect(seen.kept.sharedLast).toBeUndefined()
  expect(seen.kept.webhookDown).toBeUndefined()
  // nothing was sent, so nothing failed: no warning for the page
  // chưa gửi gì nên chưa có gì lỗi: không có cảnh báo cho trang
  expect(seen.shareState).toEqual([])
})
