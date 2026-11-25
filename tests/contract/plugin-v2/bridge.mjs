// The plugin's own code for format v: 2 (hooks/sendv2.ts, buildMachineSummary in hooks/team.ts), run by Node so that a test in Python can
// send what it makes to the real server: one JSON command a line on stdin, one JSON answer a line on stdout (server/test_plugin_v2.py).
// Chính mã của plugin cho định dạng v: 2, chạy bằng Node để một test Python gửi những gì nó dựng tới máy chủ thật: mỗi dòng stdin một lệnh
// JSON, mỗi dòng stdout một câu trả lời JSON (server/test_plugin_v2.py).
import { register } from 'node:module'
import { createInterface } from 'node:readline'

// the hooks import their files without an extension, as the plugin engine does: find the .ts file
// các hook nhập file không kèm phần đuôi, như engine của plugin: tìm file .ts
register('data:text/javascript,' + encodeURIComponent(`
export async function resolve(spec, ctx, next) {
  try { return await next(spec, ctx) } catch (err) {
    if (spec.startsWith('.') && !/\\.[cm]?[jt]sx?$/.test(spec)) return next(spec + '.ts', ctx)
    throw err
  }
}`))

const { packetFor, afterAnswer } = await import('../../../hooks/sendv2.ts')
const { buildMachineSummary } = await import('../../../hooks/team.ts')

for await (const line of createInterface({ input: process.stdin })) {
  const c = JSON.parse(line)
  let out
  if (c.op === 'packet') out = packetFor(buildMachineSummary([], c.ledger, c.now, c.who), c.state, c.now)
  else if (c.op === 'after') out = afterAnswer(c.state, c.answer, c.sent, c.now, () => c.random ?? 0.5)
  else out = { error: 'unknown op' }
  process.stdout.write(JSON.stringify(out ?? null) + '\n')
}
