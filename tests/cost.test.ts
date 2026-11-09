import { expect, test } from 'claude-code/testing'
import { LEDGER_HOURS, addSpend, costDelta, formatUsd, repairInflatedHours, mergeLongSpend, LONG_HOURS } from '../hooks/edits'
import { contextAdvice, contextFill, contextWarning } from '../hooks/edits'
import { clockLabel, dayLabel } from '../hooks/office'

const ONE = { usd: 0.5, input: 10, output: 20, cacheRead: 30, cacheWrite: 40 }

test('spend adds up by hour and old hours drop off', () => {
  let l = addSpend(undefined, 1000, ONE)
  l = addSpend(l, 1000, ONE)
  expect(l['1000']).toEqual({ usd: 1, input: 20, output: 40, cacheRead: 60, cacheWrite: 80 })
  l = addSpend(l, 1000 + LEDGER_HOURS, ONE)
  expect(Object.keys(l)).toEqual([String(1000 + LEDGER_HOURS)])
})

test('a turn costs what the session total grew by', () => {
  expect(costDelta(undefined, 0.25)).toBe(0.25)
  expect(costDelta(0.25, 0.75)).toBe(0.5)
  // the session started over (a resume): the new total is all new
  // phiên bắt đầu lại (một lần mở lại): tổng mới hoàn toàn là mới
  expect(costDelta(2, 0.5)).toBe(0.5)
})

test('a reopened session does not count its old total again', () => {
  expect(costDelta(undefined, 188)).toBe(0)
  expect(costDelta(188, 188.5)).toBe(0.5)
})

test('an hour holding a whole session total is repriced, ordinary hours stay', () => {
  const hour = (usd: number) => ({ usd, input: 0, output: 40_000, cacheRead: 12_000_000, cacheWrite: 0 })
  const fixed = repairInflatedHours({ 1: hour(5), 2: hour(6), 3: hour(188), 4: hour(5.5) })
  expect(fixed[1]!.usd).toBe(5)
  expect(fixed[4]!.usd).toBe(5.5)
  expect(Math.round(fixed[3]!.usd)).toBe(6)
  expect(fixed[3]!.output).toBe(40_000)
  // too few hours to know what is usual: left alone
  // quá ít giờ để biết thế nào là bình thường: để nguyên
  const few = { 1: hour(5), 2: hour(188) }
  expect(repairInflatedHours(few)).toEqual(few)
})

test('the long history keeps old hours, follows the ledger and drops past its limit', () => {
  const ledger = { 1000: { usd: 2, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }
  const long = mergeLongSpend({ 900: 1, 1000: 9, [1000 - LONG_HOURS]: 5 }, ledger, 1000)
  expect(long).toEqual({ 900: 1, 1000: 2 })
})

test('dollars read the English way', () => {
  expect(formatUsd(0.4213)).toBe('$0.42')
  expect(formatUsd(0.0042)).toBe('$0.004')
  expect(formatUsd(12)).toBe('$12.00')
})

test('context fill reads like the status line, and says when to switch', () => {
  expect(contextFill({ window: 200_000 })).toBeUndefined()
  expect(contextFill({ window: 200_000, tokens: 91_000, percent: 45.5 })).toEqual({ percent: 46, tokens: 91_000, window: 200_000 })
  expect([contextAdvice(40), contextAdvice(65), contextAdvice(85)]).toEqual(['', 'getting full', 'start a new session'])
})

test('a context warning shows once per level and again after a compact', () => {
  expect(contextWarning(40, 0)).toEqual({ level: 0 })
  expect(contextWarning(62, 0).text).toContain('getting full')
  expect(contextWarning(70, 60).text).toBeUndefined()
  expect(contextWarning(85, 60).text).toContain('almost full')
  expect(contextWarning(90, 80).text).toBeUndefined()
  expect(contextWarning(85, 60, true).text).toContain('/handoff')
  expect(contextWarning(62, 0, true).text).toContain('/handoff')
  expect(contextWarning(85, 60).text).not.toContain('/handoff')
  // compacted back to 20%: the level resets, the next climb warns again
  // nén xuống còn 20%: mức được đặt lại, lần tăng kế tiếp sẽ cảnh báo lại
  expect(contextWarning(20, 80)).toEqual({ level: 0 })
})

test('job times: clock plus a day heading', () => {
  const now = new Date(2026, 9, 30, 9, 0).getTime()
  expect(clockLabel(new Date(2026, 9, 29, 8, 5).getTime())).toBe('08:05')
  expect(dayLabel(new Date(2026, 9, 30, 8, 5).getTime(), now)).toBe('Today')
  expect(dayLabel(new Date(2026, 9, 29, 23, 59).getTime(), now)).toBe('Yesterday')
  expect(dayLabel(new Date(2026, 9, 28, 14, 24).getTime(), now)).toBe('10/28/2026')
  expect(dayLabel(new Date(2025, 9, 29, 14, 24).getTime(), new Date(2026, 9, 30).getTime())).toBe('10/29/2025')
})
