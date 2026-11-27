// This computer's cost ledger: dollars and tokens by hour in the plugin's store, the long history behind the page's longer ranges,
// and the files the page reads (cost.js, cost-long.js). The store and the writing of the page's files are handed in (hooks/io.ts).
// Sổ chi phí của máy này: đô la và token theo giờ trong kho của plugin, lịch sử dài đứng sau các khoảng dài của trang, và các file
// trang đọc (cost.js, cost-long.js). Kho và việc ghi file của trang được đưa vào (hooks/io.ts).
import type { Ledger, Usage } from '../types'
import { addSpend, mergeLongSpend, repairInflatedHours } from './edits'
import type { Store } from './io'

export const LEDGER_KEY = 'ledger'
/** Each session's last known dollar total, kept across app restarts (the session state does not always come back). */
/** Tổng chi phí biết lần cuối của mỗi phiên, giữ qua các lần khởi động lại app (trạng thái phiên không phải lúc nào cũng quay lại). */
export const LAST_COST_KEY = 'sessionCost'
export const REPAIRED_KEY = 'ledgerRepaired1'
export const LONG_KEY = 'longLedger'

/** The store, and a way to write one file of the page in its folder. */
/** Kho, và cách ghi một file của trang vào thư mục của nó. */
export type LedgerIo = { store: Store; writePage(name: string, text: string): Promise<void> }

/** The hourly ledger as kept; a store that cannot be read throws. */
/** Sổ theo giờ như đang giữ; kho không đọc được thì ném lỗi. */
export async function readLedger(store: Store): Promise<Ledger | undefined> {
  return (await store.get(LEDGER_KEY)) as Ledger | undefined
}

export async function writeLedger(io: LedgerIo, ledger: Ledger | undefined) {
  await io.writePage('cost.js', `window.__aiWorkerCost = ${JSON.stringify(ledger ?? {})};\n`)
}

/** The long history behind the page's "1 month" to "1 year" ranges: dollars by hour, on this machine only. */
/** Lịch sử dài đứng sau mục "1 tháng" tới "1 năm" của trang: chi phí theo giờ, chỉ trên máy này. */
export async function writeLongSpend(io: LedgerIo, ledger: Ledger, hour: number) {
  try {
    const long = mergeLongSpend((await io.store.get(LONG_KEY)) as Record<string, number> | undefined, ledger, hour)
    await io.store.set(LONG_KEY, long)
    await io.writePage('cost-long.js', `window.__aiWorkerCostLong = ${JSON.stringify(long)};\n`)
  } catch {
    // the page falls back to the hourly ledger
    // trang quay về dùng sổ theo giờ
  }
}

/** The dollar total last known for session `id()`. */
/** Tổng đô la biết lần cuối của phiên `id()`. */
export async function lastCost(store: Store, id: () => Promise<string>): Promise<number | undefined> {
  try {
    const all = (await store.get(LAST_COST_KEY)) as Record<string, number> | undefined
    return all?.[await id()]
  } catch {
    return undefined
  }
}

export async function rememberCost(store: Store, id: () => Promise<string>, usd: number) {
  try {
    const all = ((await store.get(LAST_COST_KEY)) as Record<string, number> | undefined) ?? {}
    const key = await id()
    // newest last, so the oldest sessions fall off
    // mới nhất để cuối, nên các phiên cũ nhất rơi ra
    delete all[key]
    all[key] = usd
    await store.set(LAST_COST_KEY, Object.fromEntries(Object.entries(all).slice(-50)))
  } catch {
    // the guard in costDelta still holds
    // lớp bảo vệ trong costDelta vẫn còn đó
  }
}

/** Once per machine: takes out what resumed sessions had already added to the ledger before costDelta stopped it. */
/** Một lần cho mỗi máy: gỡ ra phần mà các phiên được mở lại đã thêm vào sổ trước khi costDelta chặn lại. */
export async function repairLedgerOnce(io: LedgerIo) {
  try {
    if (await io.store.get(REPAIRED_KEY)) return
    const ledger = await readLedger(io.store)
    if (ledger) {
      const fixed = repairInflatedHours(ledger)
      await io.store.set(LEDGER_KEY, fixed)
      await writeLedger(io, fixed)
    }
    await io.store.set(REPAIRED_KEY, true)
  } catch {
    // tried again next start
    // thử lại ở lần khởi động sau
  }
}

/** Adds a turn's tokens and dollars to the machine's hourly ledger and writes the page's files. */
/** Cộng token và đô la của một lượt vào sổ theo giờ của máy và ghi các file của trang. */
export async function logSpend(io: LedgerIo, now: number, turn: Usage | undefined, usd: number) {
  try {
    const hour = Math.floor(now / 3_600_000)
    const ledger = addSpend(await readLedger(io.store), hour, {
      usd,
      input: turn?.input ?? 0,
      output: turn?.output ?? 0,
      cacheRead: turn?.cacheRead ?? 0,
      cacheWrite: turn?.cacheWrite ?? 0,
    })
    await io.store.set(LEDGER_KEY, ledger)
    await writeLedger(io, ledger)
    await writeLongSpend(io, ledger, hour)
  } catch {
    // the totals are optional
    // các tổng là tuỳ chọn
  }
}
