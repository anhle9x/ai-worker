import { expect, test } from 'claude-code/testing'
import { LAST_COST_KEY, LEDGER_KEY, LONG_KEY, lastCost, logSpend, readLedger, rememberCost, repairLedgerOnce, REPAIRED_KEY } from '../hooks/ledger'

// hooks/ledger.ts with a store in memory and the page's files kept in a map.
// hooks/ledger.ts với kho trong bộ nhớ và các file của trang giữ trong một bảng.

const HOUR = 500_000

function machine(kept: Record<string, unknown> = {}) {
  const data: Record<string, unknown> = structuredClone(kept)
  const page: Record<string, string> = {}
  const store = {
    get: async (k: string) => structuredClone(data[k]),
    set: async (k: string, v: unknown) => {
      data[k] = structuredClone(v)
    },
    delete: async (k: string) => {
      delete data[k]
    },
  }
  return { data, page, store, io: { store, writePage: async (name: string, text: string) => void (page[name] = text) } }
}

test('the store keys of the ledger keep their names', () => {
  expect([LEDGER_KEY, LAST_COST_KEY, REPAIRED_KEY, LONG_KEY]).toEqual(['ledger', 'sessionCost', 'ledgerRepaired1', 'longLedger'])
})

test('a turn adds to its hour, and the page gets the ledger and the long history', async () => {
  const m = machine()
  await logSpend(m.io, HOUR * 3_600_000 + 5, { input: 10, output: 2, cacheRead: 0, cacheWrite: 1, turns: 1 }, 0.5)
  await logSpend(m.io, HOUR * 3_600_000 + 60_000, undefined, 0.25)
  expect(await readLedger(m.store)).toEqual({ [HOUR]: { usd: 0.75, input: 10, output: 2, cacheRead: 0, cacheWrite: 1 } })
  expect(m.page['cost.js']).toBe(`window.__aiWorkerCost = ${JSON.stringify(m.data.ledger)};\n`)
  expect(m.data.longLedger).toEqual({ [HOUR]: 0.75 })
  expect(m.page['cost-long.js']).toBe(`window.__aiWorkerCostLong = {"${HOUR}":0.75};\n`)
})

test('a page that cannot be written leaves the ledger kept', async () => {
  const m = machine()
  await logSpend({ store: m.store, writePage: async () => Promise.reject(new Error('disk full')) }, HOUR * 3_600_000, undefined, 1)
  expect(m.data.ledger).toEqual({ [HOUR]: { usd: 1, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } })
})

test('the last cost is kept per session, newest last, at most 50', async () => {
  const m = machine()
  const id = (s: string) => async () => s
  expect(await lastCost(m.store, id('a'))).toBeUndefined()
  for (let i = 0; i < 55; i++) await rememberCost(m.store, id(`s${i}`), i)
  await rememberCost(m.store, id('s10'), 99)
  const all = m.data.sessionCost as Record<string, number>
  expect(Object.keys(all).length).toBe(50)
  expect(Object.keys(all).at(-1)).toBe('s10')
  expect(await lastCost(m.store, id('s10'))).toBe(99)
  expect(await lastCost(m.store, id('s0'))).toBeUndefined()
})

test('the repair runs once per machine', async () => {
  const ledger = { [HOUR]: { usd: 1, input: 1, output: 0, cacheRead: 0, cacheWrite: 0 } }
  const m = machine({ ledger })
  await repairLedgerOnce(m.io)
  expect(m.data.ledgerRepaired1).toBe(true)
  expect(m.page['cost.js']).toBeDefined()
  delete m.page['cost.js']
  await repairLedgerOnce(m.io)
  expect(m.page['cost.js']).toBeUndefined()
})
