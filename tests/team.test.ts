import { expect, test } from 'claude-code/testing'
import { hasSigningKeys, parseHash, parseSignatureResult, parseManifest, shouldOfferUpdate } from '../hooks/update'
import { OPEN_MS, buildMachineSummary, hardwareMark, parseHardwareId, sha256Hex, isLanIp, mergeShare, mergeTeam, parseLanIp, parseSessionFile, readShareConfig, summarySignature, SHARE_WARN_MS, shareProblem, shareWarning, signedInEmail, answerModel, toQuota, quotaWarning } from '../hooks/team'

const H = 3_600_000
const NOW = 500_000 * H

test('sharing stays off unless IT turns it on, and ~ means home', () => {
  expect(readShareConfig(undefined, '/Users/an').enabled).toBe(false)
  const c = readShareConfig({ enabled: true, name: ' An ', account: 'An@Example.com', folders: '~/Drive/AI/', viewBoard: 'yes' }, '/Users/an')
  expect(c).toEqual({ enabled: true, name: 'An', account: 'an@example.com', folders: ['/Users/an/Drive/AI'], viewBoard: false, webhook: '', ingestKey: '', viewCode: '' })
  const nas = readShareConfig({ folders: ['/Volumes/AI/office/', 'Z:\\office', 'Y:\\', '\\\\nas\\AI', '//nas/AI', ''] }, '/Users/an')
  expect(nas.folders).toEqual(['/Volumes/AI/office', 'Z:\\office', 'Y:\\'])
})

test('only the type of a running subagent leaves the machine, never its task', () => {
  const who = { device: 'device-1', name: 'An', account: 'an@example.com' }
  const open = { jobs: [], now: NOW, seenAt: NOW }
  const m = buildMachineSummary(
    [
      { ...open, subagents: [{ name: 'general-purpose', description: 'Review customer A contract' }, { name: 'Explore', description: 'x' }] },
      { ...open, subagents: [{ name: 'general-purpose', description: 'y' }, { name: 'odd <name>', description: 'z' }] },
      { ...open, seenAt: NOW - OPEN_MS - 1, subagents: [{ name: 'lap-ke-hoach', description: 'session already closed' }] },
    ],
    undefined, NOW, who,
  )
  expect(m.subagents).toEqual({ 'general-purpose': 2, Explore: 1 })
  expect(JSON.stringify(m)).not.toContain('contract')
  expect(buildMachineSummary([open], undefined, NOW, who).subagents).toBeUndefined()
})

test('a session file reads back', () => {
  const raw = 'window.__aiWorkerIn && window.__aiWorkerIn("abc", {"jobs":[],"now":1,"seenAt":5});\n'
  expect(parseSessionFile(raw)?.seenAt).toBe(5)
  expect(parseSessionFile('garbage')).toBeUndefined()
})

test('a machine shares counts only, never titles, prompts or files', () => {
  const sessions = [
    { jobs: [{ key: 'k', worker: 'gemini' as const, kind: 'Web research', startedAt: NOW - 10 }], now: NOW, seenAt: NOW - 1000, claudeBusySince: NOW - 5,
      edits: [{ key: 'e', path: '/customers/contract.docx', tool: 'Edit', at: NOW, added: 1, removed: 0, lines: ['+secret'] }],
      activity: [{ at: NOW, kind: 'you' as const, text: 'Quote for customer John Smith' }] },
    { jobs: [], now: NOW, seenAt: NOW - OPEN_MS - 1, asking: true },
  ]
  const m = buildMachineSummary(sessions, { [NOW / H]: { usd: 1, input: 1, output: 1, cacheRead: 0, cacheWrite: 0 } }, NOW, { device: 'device-1', name: 'An', account: 'an@example.com' })
  expect(m.openSessions).toBe(1)
  expect(m.working).toBe(1)
  expect(m.waiting).toBe(0)
  expect(m.tasks[String(Math.floor((NOW - 10) / H))]).toEqual({ gemini: 1, chatgpt: 0, gemma: 0 })
  const text = JSON.stringify(m)
  for (const leak of ['contract.docx', 'John', 'secret', 'Web research']) expect(text.includes(leak)).toBe(false)
  expect(summarySignature({ ...m, updatedAt: 1 })).toBe(summarySignature(m))
})

test('one account on two machines is one row; an old file counts as offline', () => {
  const base = { v: 1, name: 'An', account: 'an@example.com', openSessions: 1, working: 1, waiting: 0, tasks: {} }
  const rows = mergeTeam([
    { ...base, device: 'device-1', updatedAt: NOW, ledger: { 1: { usd: 1, input: 10, output: 0, cacheRead: 0, cacheWrite: 0 } } },
    { ...base, device: 'device-2', updatedAt: NOW - 60 * 60_000, ledger: { 1: { usd: 2, input: 5, output: 0, cacheRead: 0, cacheWrite: 0 } } },
    { ...base, name: 'Binh', account: 'binh@example.com', device: 'device-3', updatedAt: NOW, ledger: {} },
    { hello: 'not ours' },
  ], NOW, 12 * 60_000)
  expect(rows.map(r => r.name)).toEqual(['An', 'Binh'])
  expect(rows[0]!.deviceCount).toBe(2)
  expect(rows[0]!.openSessions).toBe(1)
  expect(rows[0]!.ledger['1']!.usd).toBe(3)
})

test('the webhook adds each machine IP; a nameless machine shows its IP', () => {
  const base = { v: 1, name: 'An', account: 'an@example.com', openSessions: 0, working: 0, waiting: 0, ledger: {}, tasks: {} }
  const rows = mergeTeam([
    { ...base, device: 'device-1', updatedAt: NOW, ip: '192.168.1.20' },
    { ...base, device: 'device-2', updatedAt: NOW, ip: '192.168.1.31' },
    { ...base, name: '', account: '', device: 'device-3', updatedAt: NOW, ip: '192.168.1.45' },
  ], NOW, 12 * 60_000)
  expect(rows.map(r => [r.name, r.ip])).toEqual([['192.168.1.45', ['192.168.1.45']], ['An', ['192.168.1.20', '192.168.1.31']]])
})

test('one account shared by several people keeps a row per person', () => {
  const base = { v: 1, account: 'chung@example.com', openSessions: 0, working: 0, waiting: 0, ledger: {}, tasks: {} }
  const rows = mergeTeam([
    { ...base, name: 'An', device: 'device-1', updatedAt: NOW },
    { ...base, name: 'Binh', device: 'device-2', updatedAt: NOW },
    { ...base, name: 'an', device: 'device-3', updatedAt: NOW },
  ], NOW, 12 * 60_000)
  expect(rows.map(r => [r.name, r.account, r.deviceCount])).toEqual([['An', 'chung@example.com', 2], ['Binh', 'chung@example.com', 1]])
})

test('company settings ship in the package; the machine and the person fill in the rest', () => {
  const shipped = { enabled: true, name: '', account: '', folders: ['/Volumes/AI/office', 'Z:\\office'], viewBoard: false }
  const mine = { enabled: true, name: '', account: '', folders: '', viewBoard: false }
  const c = readShareConfig(mergeShare(shipped, mine, { name: 'Binh', account: 'Binh@Example.com' }), '/Users/b')
  expect(c).toEqual({ enabled: true, name: 'Binh', account: 'binh@example.com', folders: ['/Volumes/AI/office', 'Z:\\office'], viewBoard: false, webhook: '', ingestKey: '', viewCode: '' })
  // the machine's own config wins, and the manager turns xemTong on there
  // config của chính máy thắng, và người quản lý bật xemTong ở đó
  expect(readShareConfig(mergeShare(shipped, { viewBoard: true, folders: '~/thu' }, {}), '/Users/b').folders).toEqual(['/Users/b/thu'])
  // IT can switch one machine off
  // phòng IT có thể tắt một máy
  expect(readShareConfig(mergeShare(shipped, { enabled: false }, {}), '/Users/b').enabled).toBe(false)
  // a general package shares nothing
  // một gói chung thì không chia sẻ gì
  expect(readShareConfig(mergeShare({ enabled: false, folders: '' }, undefined, { name: 'An' }), '/Users/b').enabled).toBe(false)
})

test('a webhook address is kept only when it is one', () => {
  const ok = readShareConfig({ webhook: ' http://192.168.1.10:8787/ ', ingestKey: 'g', viewCode: 'x' }, '/h')
  expect([ok.webhook, ok.ingestKey, ok.viewCode]).toEqual(['http://192.168.1.10:8787', 'g', 'x'])
  expect(readShareConfig({ webhook: 'ftp://x' }, '/h').webhook).toBe('')
  expect(readShareConfig({ webhook: '192.168.1.10' }, '/h').webhook).toBe('')
})

test('the office address reads from Linux, macOS and Windows output', () => {
  expect(parseLanIp('1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.25 uid 1000\n    cache\n')).toBe('192.168.1.25')
  expect(parseLanIp('192.168.100.37\n')).toBe('192.168.100.37')
  const win = [
    'IPv4 Route Table',
    'Network Destination        Netmask          Gateway       Interface  Metric',
    '          0.0.0.0          0.0.0.0      192.168.1.1     192.168.1.40     50',
    '          0.0.0.0          0.0.0.0       10.8.0.1        10.8.0.6      25',
  ].join('\r\n')
  expect(parseLanIp(win)).toBe('10.8.0.6')
  expect(parseLanIp('')).toBeUndefined()
  expect(parseLanIp('127.0.0.1')).toBeUndefined()
  expect([isLanIp('192.168.1.300'), isLanIp('169.254.2.2'), isLanIp('<b>x</b>')]).toEqual([false, false, false])
})

test('the board shows each machine its own office address', () => {
  const base = { v: 1, name: 'An', account: 'an@example.com', openSessions: 0, working: 0, waiting: 0, ledger: {}, tasks: {}, ip: '203.0.113.10' }
  const rows = mergeTeam([
    { ...base, device: 'device-1', updatedAt: NOW, lanIp: '192.168.100.37' },
    { ...base, device: 'device-2', updatedAt: NOW, lanIp: 'not an ip' },
    { ...base, name: '', account: '', device: 'device-3', updatedAt: NOW, lanIp: '192.168.100.50' },
  ], NOW, 12 * 60_000)
  expect(rows.map(r => [r.name, r.lanIp, r.ip])).toEqual([
    ['192.168.100.50', ['192.168.100.50'], ['203.0.113.10']],
    ['An', ['192.168.100.37'], ['203.0.113.10']],
  ])
  const m = buildMachineSummary([], undefined, NOW, { device: 'device-1', name: 'An', account: '', lanIp: '192.168.100.37' })
  expect(m.lanIp).toBe('192.168.100.37')
  expect('ipLan' in buildMachineSummary([], undefined, NOW, { device: 'device-1', name: 'An', account: '' })).toBe(false)
})

test('a failed send turns into a warning only after it lasts', () => {
  expect(shareProblem(new Error('webhook 401'))).toContain('refused the key')
  expect(shareProblem(new Error('webhook 502'))).toContain('error 502')
  expect(shareProblem(new Error('timed out'))).toBe('Could not reach the team board server.')
  const fail = { since: 0, error: 'Could not reach the team board server.' }
  expect(shareWarning(undefined, SHARE_WARN_MS * 3)).toBe(undefined)
  expect(shareWarning(fail, SHARE_WARN_MS - 1)).toBe(undefined)
  expect(shareWarning(fail, 15 * 60_000)).toContain('for 15 min')
  expect(shareWarning(fail, 3 * 3_600_000)).toContain('for 3 hours')
})

test('the signed-in email comes from Claude settings, and a typed one that differs is kept apart', () => {
  expect(signedInEmail('{"oauthAccount":{"emailAddress":" Lan@Example.com "}}')).toBe('lan@example.com')
  expect(signedInEmail('{"numStartups":3}')).toBe('')
  expect(signedInEmail('{"oauthAccount":{"emailAddress":"khong-phai-email"}}')).toBe('')
  expect(signedInEmail('not json')).toBe('')
  const m = buildMachineSummary([], {}, 0, { device: 'device-1', name: 'Lan', account: 'lan@example.com', enteredAccount: 'lan@example.org' })
  expect(m.account).toBe('lan@example.com')
  expect(m.enteredAccount).toBe('lan@example.org')
  expect('taiKhoanNhap' in buildMachineSummary([], {}, 0, { device: 'device-1', name: 'Lan', account: 'lan@example.com' })).toBe(false)
  const [row] = mergeTeam([{ ...m, ip: '1.2.3.4' }], 0, 60_000)
  expect(row!.enteredAccount).toEqual(['lan@example.org'])
})

test('jobs under way are counted per helper, stale ones dropped', () => {
  const now = 10 * 3_600_000
  const s = {
    seenAt: now, now, jobs: [
      { key: 'a', worker: 'gemma', kind: 'x', startedAt: now - 60_000 },
      { key: 'b', worker: 'chatgpt', kind: 'x', startedAt: now - 60_000, endedAt: now - 1000, ok: true },
      { key: 'c', worker: 'gemini', kind: 'x', startedAt: now - 3_600_000 },
    ],
  }
  const m = buildMachineSummary([s as never], {}, now, { device: 'device-1', name: 'A', account: 'a@x.com' })
  expect(m.delegating).toEqual({ gemini: 0, chatgpt: 0, gemma: 1 })
})

test('open sessions are counted per Claude model, and installed helpers ride along', () => {
  const now = 10 * 3_600_000
  const s = (model?: string) => ({ seenAt: now, now, jobs: [], ...(model ? { model } : {}) })
  const m = buildMachineSummary([s('claude-opus-5-5'), s('claude-opus-5-5'), s('claude-fable-5-1'), s()] as never, {}, now,
    { device: 'device-1', name: 'A', account: 'a@x.com', assistants: { gemma: 'gemma4:e4b', chatgpt: true, gemini: false } })
  expect(m.models).toEqual({ 'claude-opus-5-5': 2, 'claude-fable-5-1': 1 })
  expect(m.assistants).toEqual({ gemma: 'gemma4:e4b', chatgpt: true, gemini: false })
})

test('the answering model is read from the last line of a helper answer', () => {
  expect(answerModel('Review result...\n\n(model: gpt-6.1-sol)')).toBe('gpt-6.1-sol')
  expect(answerModel('hello\n\n(model: Gemini 3.8 Flash (High))')).toBe('Gemini 3.8 Flash (High)')
  expect(answerModel('an answer with no model line')).toBe(undefined)
})

test('rate-limit windows: kept clean, and the newest reading goes up with the machine', () => {
  const h = toQuota([{ kind: 'five_hour', percentUsed: 23.46, resetsAt: '2026-10-30T15:00:00Z' }, { kind: 'seven_day', percentUsed: 41 }, { kind: 'BAD KIND', percentUsed: 5 }], 1000)
  expect(h).toEqual({ readAt: 1000, windows: [{ kind: 'five_hour', pct: 23.5, resetsAt: Date.parse('2026-10-30T15:00:00Z') }, { kind: 'seven_day', pct: 41 }] })
  expect(toQuota([], 1000)).toBe(undefined)
  const now = Date.parse('2026-10-30T12:00:00Z')
  const base = { jobs: [], now, seenAt: now }
  const old = { readAt: now - 3_600_000, windows: [{ kind: 'five_hour', pct: 10 }] }
  const newer = { readAt: now - 60_000, windows: [{ kind: 'five_hour', pct: 30 }] }
  const who = { device: 'm', name: 'A', account: 'a@x' }
  expect(buildMachineSummary([{ ...base, quota: old }, { ...base, quota: newer }], {}, now, who).quota).toEqual(newer)
  const stale = { readAt: now - 8 * 24 * 3_600_000, windows: [{ kind: 'five_hour', pct: 99 }] }
  expect(buildMachineSummary([{ ...base, quota: stale }], {}, now, who).quota).toBe(undefined)
})

test('rate-limit warning: 80% suggests Sonnet, 95% says it stops, a reset window or Sonnet drops the advice', () => {
  const now = Date.parse('2026-11-01T12:00:00Z')
  const quota = (pct: number, resetsAt = now + 3_600_000) => ({ readAt: now, windows: [{ kind: 'five_hour', pct: 10, resetsAt }, { kind: 'seven_day', pct, resetsAt: resetsAt + 86_400_000 }] })
  expect(quotaWarning(quota(79), now)).toBeUndefined()
  const a = quotaWarning(quota(82), now, 'claude-opus-5-5')!
  expect(a.level).toBe(80)
  expect(a.text).toContain('82% of its 7-day quota')
  expect(a.text).toContain('/model sonnet')
  expect(quotaWarning(quota(82), now, 'claude-sonnet-5-5')!.text).not.toContain('/model')
  const b = quotaWarning(quota(96), now)!
  expect(b.level).toBe(95)
  expect(b.key).not.toBe(a.key)
  // the window already reset: nothing to warn about
  // cửa sổ đã được đặt lại: không có gì để cảnh báo
  expect(quotaWarning(quota(99, now - 90_000_000), now)).toBeUndefined()
  // a reading older than seven days says nothing
  // số đọc cũ hơn bảy ngày không nói lên điều gì
  expect(quotaWarning({ ...quota(99), readAt: now - 8 * 86_400_000 }, now)).toBeUndefined()
})

test('the plugin version rides along with the machine summary', () => {
  const m = buildMachineSummary([], undefined, 1, { device: 'device-a', name: 'An', account: 'a@x', pluginVersion: '0.18.0' })
  expect(m.pluginVersion).toBe('0.18.0')
  expect(buildMachineSummary([], undefined, 1, { device: 'device-a', name: 'An', account: 'a@x' }).pluginVersion).toBeUndefined()
})

const HASH = 'ab'.repeat(32)
test('a manifest is read strictly, and an old signed one cannot be replayed', () => {
  const m = { version: '1.2.0', name: 'ai-worker-1.2.0.zip', sha256: HASH, date: 100 }
  expect(parseManifest(JSON.stringify(m))).toEqual(m)
  expect(parseManifest('{}')).toBeUndefined()
  expect(parseManifest('khong phai json')).toBeUndefined()
  // the file name is fixed by the version: a manifest cannot point anywhere else
  // tên file được cố định theo phiên bản: manifest không thể trỏ tới nơi nào khác
  expect(parseManifest(JSON.stringify({ ...m, name: '../../x.zip' }))).toBeUndefined()
  expect(parseManifest(JSON.stringify({ ...m, sha256: 'x' }))).toBeUndefined()
  expect(shouldOfferUpdate(m, '1.1.0', 50)).toBe(true)
  expect(shouldOfferUpdate(m, '1.2.0', 50)).toBe(false)
  // IT rolling back
  // phòng IT quay lui
  expect(shouldOfferUpdate(m, '1.3.0', 50)).toBe(true)
  // replayed
  // bị phát lại
  expect(shouldOfferUpdate(m, '1.1.0', 101)).toBe(false)
})

test('a bad signature is not the same as a machine too old to check one', () => {
  expect(parseSignatureResult({ exitCode: 0, stdout: 'Good' })).toBe('valid')
  expect(parseSignatureResult({ exitCode: 255, stdout: '', stderr: 'Could not verify signature.' })).toBe('invalid')
  expect(parseSignatureResult({ exitCode: 1, stdout: '', stderr: 'unknown option -- Y' })).toBe('unsupported')
})

test('the hash is read from each tool', () => {
  expect(parseHash(`${HASH}  /a/b.zip`)).toBe(HASH)
  expect(parseHash(`SHA256 hash of x:\r\n${HASH.toUpperCase()}\r\nCertUtil: done`)).toBe(HASH)
  expect(parseHash(`SHA256 hash of x:\n${'ab '.repeat(32)}\n`)).toBe(HASH)
  expect(parseHash('khong co')).toBeUndefined()
})

test('a signers file of comments alone holds no key', () => {
  expect(hasSigningKeys('')).toBe(false)
  expect(hasSigningKeys('# chua co khoa\n\n')).toBe(false)
  expect(hasSigningKeys('# khoa\nai-worker ssh-ed25519 AAAA\n')).toBe(true)
})

test('sha256Hex matches the standard test vectors', () => {
  expect(sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
  expect(sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  expect(sha256Hex('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq')).toBe('248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1')
  expect(sha256Hex('na\u00efve caf\u00e9 \u2713')).toBe('23888e71341419cd61548274abb7629c5551f55080d2135bc65841c1edc7b528')
})

test('parseHardwareId reads macOS, Windows and Linux output, and the mark hides the id', () => {
  const mac = '+-o J516sAP  <class IOPlatformExpertDevice>\n    "IOPlatformUUID" = "1A2B3C4D-0000-1111-2222-333344445555"\n'
  expect(parseHardwareId(mac)).toBe('1a2b3c4d-0000-1111-2222-333344445555')
  const win = '\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n    MachineGuid    REG_SZ    9f8e7d6c-1111-2222-3333-444455556666\r\n'
  expect(parseHardwareId(win)).toBe('9f8e7d6c-1111-2222-3333-444455556666')
  expect(parseHardwareId('0123456789abcdef0123456789abcdef\n')).toBe('0123456789abcdef0123456789abcdef')
  expect(parseHardwareId('00000000-0000-0000-0000-000000000000')).toBeUndefined()
  expect(parseHardwareId('error')).toBeUndefined()
  const m = hardwareMark('1a2b3c4d-0000-1111-2222-333344445555')
  expect(m).toMatch(/^[0-9a-f]{32}$/)
  expect(m).not.toContain('1a2b3c4d')
  const s = buildMachineSummary([], undefined, 1, { device: 'device-a', name: 'A', account: 'a@b', hardwareMark: m })
  expect(s.hardwareMark).toBe(m)
})
