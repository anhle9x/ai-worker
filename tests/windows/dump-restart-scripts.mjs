// Writes the Windows scripts that close and reopen the Claude app after /update (hooks/update.ts) to files, so
// tests/windows/test-restart.ps1 can run them with Windows PowerShell 5.
// Ghi các script Windows đóng rồi mở lại app Claude sau /update (hooks/update.ts) ra file, để
// tests/windows/test-restart.ps1 chạy chúng bằng Windows PowerShell 5.
// Run: node --experimental-strip-types tests/windows/dump-restart-scripts.mjs <folder>
// Chạy: node --experimental-strip-types tests/windows/dump-restart-scripts.mjs <thư mục>
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

const out = process.argv[2]
if (!out) throw new Error('usage: dump-restart-scripts.mjs <folder>')
const m = await import('../../hooks/update.ts')
for (const name of ['WINDOWS_FIND_SCRIPT', 'WINDOWS_HELPER', 'WINDOWS_RESTART_SCRIPT', 'WINDOWS_CLAUDE_SCRIPT']) {
  writeFileSync(join(out, `${name}.ps1`), m[name])
}
