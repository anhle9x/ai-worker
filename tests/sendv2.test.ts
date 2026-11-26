import { expect, test } from 'claude-code/testing'
import { FULL_EVERY_MS, FULL_SPREAD_MS, RESEND_HOURS, afterAnswer, hourMarks, packetFor, type Packet, type SendState, type V2Packet } from '../hooks/sendv2'
import type { MachineSummary } from '../hooks/team'

const H = 3_600_000
const NOW = 500_000 * H
const HOUR = String(NOW / H)

function summary(ledger: Record<string, { usd: number }>, tasks: Record<string, { gemini: number; chatgpt: number; gemma: number }> = {}): MachineSummary {
  return { v: 1, device: 'device-a', name: 'An', account: 'an@example.com', updatedAt: NOW, openSessions: 1, working: 0, waiting: 0, ledger, tasks } as MachineSummary
}

const OK = (boot = 'b1', more: Record<string, unknown> = {}) => JSON.stringify({ ok: true, accepts: [1, 2], needFull: false, boot, ...more })
const hoursOf = (p: Packet) => (p.body as V2Packet).hours

test('v: 1 until the server says it reads v: 2, then only what changed', () => {
  const m = summary({ [HOUR]: { usd: 1 }, '499999': { usd: 2 } })
  const first = packetFor(m, undefined, NOW)
  expect(first.body.v).toBe(1)
  expect(first.full).toBe(true)
  const state = afterAnswer(undefined, OK(), first, NOW, () => 0)
  expect(state.v2).toBe(true)
  expect(state.fullAfter).toBe(NOW + FULL_EVERY_MS)
  // nothing changed: a v: 2 send with no hours, the state still in full
  // không đổi gì: gói v: 2 không có giờ nào, trạng thái vẫn đủ
  const same = packetFor(m, state, NOW + 2000)
  expect(same.body.v).toBe(2)
  expect(same.full).toBe(false)
  expect(hoursOf(same)).toEqual({ ledger: {}, tasks: {}, blocks: {} })
  expect((same.body as V2Packet).name).toBe('An')
  expect('ledger' in same.body).toBe(false)
  // one hour changed, one left the computer's 8 days: the first sent whole, the second as an empty table
  // một giờ đổi, một giờ ra khỏi 8 ngày của máy: giờ đầu gửi trọn, giờ sau là bảng rỗng
  const changed = packetFor(summary({ [HOUR]: { usd: 1.5 } }), state, NOW + 4000)
  expect(hoursOf(changed).ledger).toEqual({ [HOUR]: { usd: 1.5 }, '499999': {} })
})

test('an older server, which answers only ok, keeps getting v: 1', () => {
  const m = summary({ [HOUR]: { usd: 1 } })
  const p = packetFor(m, { v2: true, acked: hourMarks(m), fullAfter: NOW + H }, NOW)
  expect(afterAnswer({ v2: true }, '{"ok": true}', p, NOW)).toEqual({ seq: NOW })
  expect(afterAnswer({ v2: true }, 'not json', p, NOW)).toEqual({ seq: NOW })
  expect(packetFor(m, {}, NOW).body.v).toBe(1)
})

test('needFull, a missing book of marks, and the hour due each send the whole book', () => {
  const m = summary({ [HOUR]: { usd: 1 }, '499999': { usd: 2 } }, { [HOUR]: { gemini: 1, chatgpt: 0, gemma: 0 } })
  const state = afterAnswer(undefined, OK(), packetFor(m, undefined, NOW), NOW, () => 0.5)
  expect(state.fullAfter).toBe(NOW + FULL_EVERY_MS + FULL_SPREAD_MS / 2)
  const asked = afterAnswer(state, OK('b1', { needFull: true }), packetFor(m, state, NOW + 2000), NOW + 2000)
  expect(asked).toEqual({ v2: true, boot: 'b1', needFull: true, seq: NOW + 2000 })
  for (const s of [asked, { v2: true }, { ...state, fullAfter: NOW + 1000 }] as SendState[]) {
    const p = packetFor(m, s, NOW + 2000)
    expect(p.full).toBe(true)
    expect((p.body as V2Packet).full).toBe(true)
    expect(hoursOf(p).ledger).toEqual(m.ledger)
    expect(hoursOf(p).tasks).toEqual(m.tasks)
  }
})

test('another start of the server sends the last two days again, not the older hours', () => {
  const old = String(NOW / H - RESEND_HOURS - 1)
  const recent = String(NOW / H - 2)
  const m = summary({ [HOUR]: { usd: 1 }, [recent]: { usd: 2 }, [old]: { usd: 3 } })
  const state = afterAnswer(undefined, OK('b1'), packetFor(m, undefined, NOW), NOW)
  const quiet = packetFor(m, state, NOW + 2000)
  const restarted = afterAnswer(state, OK('b2'), quiet, NOW + 2000)
  expect(restarted.fullAfter).toBe(state.fullAfter)
  expect(Object.keys(hoursOf(packetFor(m, restarted, NOW + 4000)).ledger).sort()).toEqual([HOUR, recent].sort())
  // the same start again: nothing to send
  // vẫn lần khởi động đó: không có gì để gửi
  expect(hoursOf(packetFor(m, afterAnswer(restarted, OK('b2'), quiet, NOW + 4000), NOW + 6000)).ledger).toEqual({})
})

test('each send is numbered above the last one, even when the clock goes back', () => {
  const m = summary({ [HOUR]: { usd: 1 } })
  const first = packetFor(m, undefined, NOW)
  expect([first.seq, first.body.seq]).toEqual([NOW, NOW])
  const state = afterAnswer(undefined, OK(), first, NOW)
  expect(state.seq).toBe(NOW)
  // the clock went back two minutes: the number still goes up
  // đồng hồ lùi hai phút: số vẫn tăng
  const back = packetFor(m, state, NOW - 120_000)
  expect([back.seq, back.body.seq]).toEqual([NOW + 1, NOW + 1])
  expect(packetFor(m, { ...state, seq: back.seq }, NOW - 100_000).seq).toBe(NOW + 2)
  // needFull and an older server keep the number; an answer never takes it back below the one held (another session sent since)
  // needFull và máy chủ cũ vẫn giữ số; một câu trả lời không bao giờ kéo số xuống dưới số đang giữ (phiên khác đã gửi sau đó)
  expect(afterAnswer(state, OK('b1', { needFull: true }), back, NOW).seq).toBe(NOW + 1)
  expect(afterAnswer(state, '{"ok": true}', back, NOW).seq).toBe(NOW + 1)
  expect(afterAnswer({ ...state, seq: NOW + 5 }, OK(), back, NOW).seq).toBe(NOW + 5)
})

// The server as docs/DATA-MODEL.md says (merge_hours, replace_hours in server/board/devices.py): a v: 1 or full book replaces, a send of
// changed hours puts each hour over the kept one and an empty hour removes it. Sends may be lost on the way or their answer lost.
// Máy chủ như docs/DATA-MODEL.vi.md mô tả (merge_hours, replace_hours trong server/board/devices.py): gói v: 1 hay cả sổ thì thay,
// gói các giờ đã đổi thì đặt từng giờ lên giờ đang giữ và giờ rỗng thì xoá. Gói có thể mất trên đường hoặc mất câu trả lời.
function serverTakes(kept: Record<string, unknown> | undefined, body: MachineSummary | V2Packet): Record<string, unknown> | 'needFull' {
  const nonEmpty = (b: Record<string, unknown>) => Object.fromEntries(Object.entries(b).filter(([, t]) => t && Object.keys(t as object).length))
  if (body.v === 1) return nonEmpty(body.ledger)
  if (body.full) return nonEmpty(body.hours.ledger)
  if (!kept) return 'needFull'
  const out = { ...kept }
  for (const [h, t] of Object.entries(body.hours.ledger)) {
    if (t && Object.keys(t as object).length) out[h] = t
    else delete out[h]
  }
  return out
}

test('whatever is lost on the way, the server ends with the money the computer holds', () => {
  let seed = 7
  const random = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  for (let run = 0; run < 40; run++) {
    const ledger: Record<string, { usd: number }> = {}
    let kept: Record<string, unknown> | undefined
    let state: SendState | undefined
    let boot = 'b0'
    let now = NOW
    for (let step = 0; step < 300; step++) {
      now += 2000 + Math.floor(random() * 60_000)
      const hour = String(Math.floor(now / H))
      ledger[hour] = { usd: Math.round(((ledger[hour]?.usd ?? 0) + random()) * 1e6) / 1e6 }
      // hours older than 8 days leave the computer
      // giờ cũ hơn 8 ngày rời khỏi máy
      for (const h of Object.keys(ledger)) if (Number(h) <= Math.floor(now / H) - 192) delete ledger[h]
      // now and then the server starts again and loses what it took in its last seconds
      // thỉnh thoảng máy chủ khởi động lại và mất những gì nhận trong mấy giây cuối
      if (random() < 0.03 && kept) {
        boot = 'b' + step
        const last = Object.keys(kept).sort((a, b) => Number(a) - Number(b)).pop()!
        kept = { ...kept, [last]: { usd: 0.000001 } }
      }
      if (random() < 0.01) kept = undefined
      const p = packetFor(summary({ ...ledger }), state, now)
      const fate = random()
      if (fate < 0.1) continue
      const took = serverTakes(kept, p.body)
      if (took !== 'needFull') kept = took
      if (fate < 0.2) continue
      state = afterAnswer(state, JSON.stringify({ ok: true, accepts: [1, 2], needFull: took === 'needFull', boot }), p, now, random)
    }
    // two quiet sends after the noise: the server must hold exactly what the computer holds
    // hai lần gửi yên ổn sau khi hết nhiễu: máy chủ phải giữ đúng những gì máy đang giữ
    for (let i = 0; i < 2; i++) {
      now += 2000
      const p = packetFor(summary({ ...ledger }), state, now)
      const took = serverTakes(kept, p.body)
      if (took !== 'needFull') kept = took
      state = afterAnswer(state, JSON.stringify({ ok: true, accepts: [1, 2], needFull: took === 'needFull', boot }), p, now, random)
    }
    expect(kept).toEqual(ledger)
  }
})
