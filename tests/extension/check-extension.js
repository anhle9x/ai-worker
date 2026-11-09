// Tests the manager extension's logic (extensions/manager/core.js) against a real local webhook with made-up people. Run: node tests/extension/check-extension.js
// The browser APIs are replaced by small fakes; the popup and the real badge still need a look in Chrome.
// Thử logic của tiện ích cho quản lý (extensions/manager/core.js) với webhook thật chạy trên máy, người giả. Chạy: node tests/extension/check-extension.js
// API trình duyệt được thay bằng bản giả nhỏ; cửa sổ nhỏ và biểu tượng thật vẫn cần xem trong Chrome.
const { spawn } = require('node:child_process')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const assert = require('node:assert/strict')
const readline = require('node:readline')

const here = __dirname
const extDir = join(here, '..', '..', 'extensions', 'manager')
const core = require(join(extDir, 'core.js'))
const messages = { en: JSON.parse(readFileSync(join(extDir, '_locales/en/messages.json'), 'utf8')), vi: JSON.parse(readFileSync(join(extDir, '_locales/vi/messages.json'), 'utf8')) }

let passed = 0
function check (name, fn) {
  fn()
  passed++
  console.log('ok   ' + name)
}

// --- pure parts ---
// --- phần thuần ---
check('both languages have the same keys and placeholders', () => {
  assert.deepEqual(Object.keys(messages.vi).sort(), Object.keys(messages.en).sort())
  for (const k of Object.keys(messages.en)) assert.deepEqual(Object.keys(messages.vi[k].placeholders || {}), Object.keys(messages.en[k].placeholders || {}), k)
})
// The popup runs copies of the menu bar window's files; after changing server/static/mini.js or mini.css, copy them again:
// cp server/static/mini.js server/static/mini.css extensions/manager/mini/ (the logos come from server/menubar/icons/generic-*.png).
// Cửa sổ nhỏ chạy bản chép các file của khung thanh menu; sửa server/static/mini.js hay mini.css thì chép lại:
// cp server/static/mini.js server/static/mini.css extensions/manager/mini/ (logo lấy từ server/menubar/icons/generic-*.png).
check('bundled menu bar window files equal the server copies', () => {
  const root = join(here, '..', '..')
  const pairs = [['server/static/mini.js', 'mini/mini.js'], ['server/static/mini.css', 'mini/mini.css'],
    ['server/menubar/icons/generic-black.png', 'mini/logo-black.png'], ['server/menubar/icons/generic-white.png', 'mini/logo-white.png']]
  for (const [from, to] of pairs) assert.ok(readFileSync(join(root, from)).equals(readFileSync(join(extDir, to))), to + ' differs from ' + from)
  // mini.css looks for the logo at /mini/logo-*.png, which inside the extension is this folder
  // mini.css tìm logo ở /mini/logo-*.png, trong tiện ích chính là thư mục này
  assert.match(readFileSync(join(extDir, 'mini/mini.css'), 'utf8'), /url\("\/mini\/logo-black\.png"\)/)
})
check('the extension asks for no site up front, only the board when pairing', () => {
  const manifest = JSON.parse(readFileSync(join(extDir, 'manifest.json'), 'utf8'))
  assert.equal(manifest.host_permissions, undefined)
  // offscreen: a hidden page that only watches the light or dark mode for the toolbar icon
  // offscreen: trang ẩn chỉ theo dõi chế độ sáng hay tối cho biểu tượng thanh công cụ
  assert.deepEqual(manifest.permissions.sort(), ['alarms', 'notifications', 'offscreen', 'storage'])
})
check('toolbar icon: a dark and a light G, both sizes, and the hidden page that picks one', () => {
  const manifest = JSON.parse(readFileSync(join(extDir, 'manifest.json'), 'utf8'))
  assert.deepEqual(Object.values(manifest.action.default_icon), ['icons/toolbar-dark-16.png', 'icons/toolbar-dark-32.png'])
  for (const tone of ['dark', 'light']) for (const n of [16, 32]) assert.ok(readFileSync(join(extDir, `icons/toolbar-${tone}-${n}.png`)).length > 100)
  assert.match(readFileSync(join(extDir, 'offscreen.js'), 'utf8'), /prefers-color-scheme: dark/)
})
check('board address keeps only the origin', () => {
  assert.equal(core.normalizeBoardUrl('board.company.com/board?x=1'), 'https://board.company.com')
  assert.equal(core.normalizeBoardUrl('http://127.0.0.1:8080/admin'), 'http://127.0.0.1:8080')
  for (const bad of ['', 'javascript:alert(1)', 'file:///etc/passwd', 'ftp://x', 'https://user:pw@host']) assert.equal(core.normalizeBoardUrl(bad), '', bad)
  assert.equal(core.originPattern('http://127.0.0.1:8080'), 'http://127.0.0.1/*')
  // plain http only to this very computer: elsewhere the key would travel readable on the network
  // http thường chỉ tới chính máy này: nơi khác thì khoá đi trên mạng ai cũng đọc được
  assert.equal(core.normalizeBoardUrl('http://localhost:3000/x'), 'http://localhost:3000')
  for (const bad of ['http://10.0.0.5:8080', 'http://board.company.com', 'http://localhost.evil.example.com', 'http://127.0.0.1.evil.example.com']) {
    assert.equal(core.normalizeBoardUrl(bad), '', bad)
    assert.equal(core.addressProblem(bad), 'httpNotAllowed', bad)
  }
  assert.equal(core.addressProblem('javascript:alert(1)'), 'invalidAddress')
  const manifest = JSON.parse(readFileSync(join(extDir, 'manifest.json'), 'utf8'))
  assert.deepEqual(manifest.optional_host_permissions, ['https://*/*', 'http://localhost/*', 'http://127.0.0.1/*'])
  assert.equal(core.boardPath('/board'), '/board')
  for (const bad of ['//evil.example.com/x', '/\\evil', 'https://evil.example.com', 'javascript:alert(1)', '/a b', null]) assert.equal(core.boardPath(bad), '/board', String(bad))
})
check('the board page copied into the popup keeps only an allowlist of tags and attributes', () => {
  for (const tag of ['script', 'style', 'link', 'iframe', 'img', 'video', 'object', 'embed', 'form', 'base', 'meta', 'animate', 'set', 'use', 'foreignObject', 'image', 'math', 'template'])
    assert.equal(core.keepTag(tag), false, tag)
  for (const [name, value] of [['style', 'background:url(//evil.example.com/x)'], ['srcset', '//evil.example.com/a.png 1x'], ['poster', '//evil.example.com/p.png'],
    ['ping', 'https://evil.example.com'], ['background', '//evil.example.com/b.png'], ['formaction', 'https://evil.example.com'], ['onclick', 'alert(1)'],
    ['onload', 'x'], ['src', '/x.png'], ['xlink:href', '/x'], ['attributeName', 'href'], ['to', 'javascript:alert(1)'], ['values', 'javascript:alert(1)'],
    ['href', 'javascript:alert(1)'], ['href', '//evil.example.com/x'], ['href', '/\\evil.example.com'], ['href', 'https://evil.example.com'], ['target', '_blank'], ['action', '/x']])
    assert.equal(core.keepAttribute(name, value), false, name + '=' + value)
  for (const [name, value] of [['class', 'btn'], ['aria-selected', 'true'], ['data-tab', 'quota'], ['viewBox', '0 0 24 24'], ['stroke-linecap', 'round'], ['href', '/board'], ['d', 'M12 7v5']])
    assert.equal(core.keepAttribute(name, value), true, name)
})
check('badge: number, nothing at zero, grey when unreachable or not paired', () => {
  assert.equal(core.badgeFor({ status: 'ok', people: [{ waiting: true }, { waiting: false }] }).text, '1')
  assert.equal(core.badgeFor({ status: 'ok', people: [{ waiting: false }] }).text, '')
  assert.deepEqual([core.badgeFor({ status: 'unreachable' }).text, core.badgeFor({ status: 'unreachable' }).color], ['?', '#8a8a8a'])
  assert.equal(core.badgeFor({ status: 'unpaired' }).text, '!')
})
check('messages fill their placeholders', () => {
  assert.equal(core.formatMessage(messages.en, 'notifyMessage', ['Ann', '12']), 'Ann has been waiting for 12 minutes.')
  assert.equal(core.formatMessage(messages.vi, 'hoursMinutes', ['1', '5']), '1 giờ 5 phút') // i18n-allow
})
check('the language chosen in the popup wins over the browser language', () => {
  assert.deepEqual([core.pickLang('vi', 'en-US'), core.pickLang('en', 'vi'), core.pickLang('', 'vi-VN'), core.pickLang('xx', 'fr')], ['vi', 'en', 'vi', 'en'])
})

async function main () {
  // --- against a local server ---
  // --- với máy chủ trên máy ---
  // EXTENSION_TEST_PORT picks a fixed port; without it the system picks a free one
  // EXTENSION_TEST_PORT chọn một cổng cố định; không có thì hệ thống chọn cổng trống
  const py = spawn('python3', [join(here, 'fake_server.py'), ...(process.env.EXTENSION_TEST_PORT ? [process.env.EXTENSION_TEST_PORT] : [])], { stdio: ['pipe', 'pipe', 'inherit'] })
  const lines = readline.createInterface({ input: py.stdout })
  const waiters = []
  lines.on('line', line => waiters.shift()(line))
  const nextLine = () => new Promise(resolve => waiters.push(resolve))
  const server = cmd => {
    const p = nextLine()
    py.stdin.write(cmd + '\n')
    return p
  }

  try {
    const port = Number((await nextLine()).split(' ').pop())
    const board = `http://127.0.0.1:${port}`
    const store = {}
    const badges = []
    const notes = []
    const requests = []
    let clock = Date.now()
    let offline = false
    let allowed = true
    const manager = core.createManager({
      storage: {
        get: async keys => Object.fromEntries(keys.filter(k => k in store).map(k => [k, JSON.parse(JSON.stringify(store[k]))])),
        set: async obj => Object.assign(store, JSON.parse(JSON.stringify(obj))),
        remove: async keys => { for (const k of keys) delete store[k] }
      },
      fetch: async (url, options) => {
        requests.push({ url, options })
        if (offline) throw new TypeError('Failed to fetch')
        return fetch(url, options)
      },
      hasPermission: async origin => allowed && origin === board,
      ui: {
        t: (key, subs) => core.formatMessage(messages.en, key, subs),
        setBadge: async b => badges.push(b),
        notify: async (id, title, message) => notes.push({ id, title, message })
      },
      now: () => clock
    })
    const lastBadge = () => badges[badges.length - 1]
    // Time passes one alarm at a time, as in the browser; a longer silence would restart the wait counts on purpose.
    // Thời gian trôi từng nhịp báo thức như trong trình duyệt; im lâu hơn thì cố ý đếm lại các lần chờ.
    const minutes = async n => {
      let last
      for (let i = 0; i < n; i++) {
        clock += 60000
        last = await manager.tick()
      }
      return last
    }

    let s = await manager.tick()
    check('first start: not paired, grey "!"', () => assert.deepEqual([s.status, lastBadge().text], ['unpaired', '!']))

    assert.deepEqual(await manager.startPairing('javascript:alert(1)'), { error: 'invalidAddress' })
    check('invalid address refused before any request', () => assert.equal(requests.length, 0))

    const pairing = await manager.startPairing(board + '/board')
    s = await manager.load()
    check('pairing code shown, only the pending key kept', () => {
      assert.match(pairing.code, /^\d{8}$/)
      assert.equal(s.status, 'pairing')
      assert.equal(s.boardUrl, board)
      assert.ok(s.pendingKey && !s.token)
    })
    s = await manager.tick()
    check('waits while the admin has not approved', () => assert.equal(s.status, 'pairing'))

    assert.equal(await server('approve'), 'approved extension')
    s = await manager.tick()
    check('approved: paired, people by short name, badge counts waiting', () => {
      assert.equal(s.status, 'ok')
      assert.equal(s.pairedName, 'Test laptop')
      assert.ok(s.token.startsWith('tv_'))
      assert.equal(s.pendingKey, undefined)
      assert.deepEqual(s.people.map(p => p.name).sort(), ['Ann', 'Ben', 'Cat'])
      assert.equal(lastBadge().text, '2')
      assert.equal(lastBadge().title, 'AI Worker: 2 waiting')
    })
    check('stores no email, internal IP, cost or cookie', () => {
      const all = JSON.stringify(store)
      for (const leak of ['@example.com', '10.0.0.', 'usd', 'cookie', 'session=']) assert.ok(!all.toLowerCase().includes(leak), leak)
      assert.deepEqual(Object.keys(s.people[0]).sort(), ['name', 'waiting', 'working'])
    })
    check('every request omits cookies and sends the key only in Authorization', () => {
      for (const r of requests) {
        assert.equal(r.options.credentials, 'omit')
        assert.ok(!('Cookie' in r.options.headers))
      }
    })

    await minutes(9)
    check('no notification before the wait time (10 minutes)', () => assert.equal(notes.length, 0))
    await minutes(2)
    check('one notification per waiting person past the wait time', () => {
      assert.deepEqual(notes.map(n => n.message).sort(), ['Ann has been waiting for 10 minutes.', 'Ben has been waiting for 10 minutes.'])
    })
    await minutes(2)
    check('no repeat notification during the same wait', () => assert.equal(notes.length, 2))

    await server('stop Ann')
    clock += 60000
    s = await manager.tick()
    check('a person who stops waiting is dropped', () => assert.deepEqual(Object.keys(s.seen), ['Ben']))
    await server('wait Ann')
    clock += 60000
    s = await manager.tick()
    const annSince = s.seen.Ann.since
    check('a new wait counts from when the extension first saw it', () => assert.equal(annSince, clock))
    await minutes(11)
    check('a new wait gets its own notification', () => assert.equal(notes.filter(n => n.message.startsWith('Ann')).length, 2))

    await manager.saveSettings({ notify: false, notifyMinutes: 5 })
    await server('stop Ben')
    await manager.tick()
    await server('wait Ben')
    clock += 60000
    await manager.tick()
    s = await minutes(30)
    check('notifications off: none sent; settings are kept and checked', () => {
      assert.equal(notes.filter(n => n.message.startsWith('Ben')).length, 1)
      assert.deepEqual(s.settings, { notify: false, notifyMinutes: 5 })
    })
    s = await manager.saveSettings({ notify: 'yes', notifyMinutes: 7 })
    check('bad settings fall back to the defaults', () => assert.deepEqual(s.settings, { notify: true, notifyMinutes: 10 }))

    offline = true
    clock += 60000
    s = await manager.tick()
    check('server unreachable: grey "?", old numbers dropped', () => {
      assert.equal(s.status, 'unreachable')
      assert.deepEqual([lastBadge().text, lastBadge().color], ['?', '#8a8a8a'])
      assert.deepEqual(s.people, [])
      assert.equal(core.waitingCount(s), 0)
    })
    offline = false
    allowed = false
    s = await manager.tick()
    check('access to the board taken away in the browser: says so', () => assert.deepEqual([s.status, s.reason], ['unreachable', 'permission']))
    allowed = true
    clock += 60000
    s = await manager.tick()
    check('server back: numbers again', () => assert.deepEqual([s.status, lastBadge().text], ['ok', '2']))

    const page = await manager.miniPage('vi')
    const pageEn = await manager.miniPage('xx')
    check('popup page: the menu bar window in the chosen language, "this browser"', () => {
      assert.equal(page.status, 200)
      assert.match(page.html, /<main class="mini">/)
      assert.match(page.html, /data-lang="vi"/)
      assert.match(pageEn.html, /data-lang="en"/)
      assert.match(pageEn.html, /Unpair this browser/)
    })
    check('the real /ext/mini page keeps every tag and its five tabs after cleaning', () => {
      const main = pageEn.html.slice(pageEn.html.indexOf('<main'), pageEn.html.indexOf('</main>'))
      const tags = [...main.matchAll(/<([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^\s=>/]+(?:="[^"]*")?)*)\s*\/?>/g)]
      const dropped = new Set()
      for (const [, tag, attrs] of tags) {
        assert.ok(core.keepTag(tag), 'tag ' + tag + ' would be removed')
        for (const [, name, value] of attrs.matchAll(/([^\s=]+)(?:="([^"]*)")?/g)) if (!core.keepAttribute(name, value || '')) dropped.add(name)
      }
      // only the link's target and rel go; the popup opens links itself through MiniApi.openLink
      // chỉ target và rel của đường dẫn bị bỏ; cửa sổ nhỏ tự mở đường dẫn qua MiniApi.openLink
      assert.deepEqual([...dropped].sort(), ['rel', 'target'])
      const tabs = tags.filter(([, tag, attrs]) => tag === 'button' && /data-tab="/.test(attrs)).map(([, , attrs]) => attrs.match(/data-tab="([^"]*)"/)[1])
      assert.deepEqual(tabs, ['waiting', 'working', 'quota', 'cost', 'settings'])
      assert.equal(tags.filter(([, tag]) => tag === 'svg').length, 5)
    })
    const wall = await manager.wallData()
    check('popup data: the wall view, with no email or internal IP', () => {
      assert.equal(wall.status, 200)
      assert.deepEqual(wall.data.people.map(p => p.name).sort(), ['Ann', 'Ben', 'Cat'])
      const all = JSON.stringify(wall.data)
      for (const leak of ['@example.com', '10.0.0.', 'lanIp']) assert.ok(!all.includes(leak), leak)
    })
    check('popup requests omit cookies too', () => {
      for (const r of requests) assert.equal(r.options.credentials, 'omit')
    })

    assert.equal(await server('revoke'), 'revoked 1')
    clock += 60000
    s = await manager.tick()
    check('revoked in /admin: the next poll shows not paired and forgets the key', () => {
      assert.deepEqual([s.status, s.reason, lastBadge().text], ['unpaired', 'revoked', '!'])
      assert.equal(s.token, undefined)
      assert.deepEqual(s.seen, {})
    })
    const audit = (await server('audit')).split(' ')
    check('audit log: code asked, joined, revoked, revoked key used, all marked extension', () => {
      for (const a of ['tv-request-code:extension', 'tv-joined:extension', 'tv-revoke:extension', 'tv-revoked-key-used:extension']) assert.ok(audit.includes(a), a)
    })
    const before = requests.length
    await manager.tick()
    check('after revoking it stops using the old key', () => assert.ok(requests.slice(before).every(r => !r.url.endsWith('/ext/state'))))

    // Unpairing from the popup revokes the key on the board, and so does pairing again over an old key.
    // Bỏ ghép trong cửa sổ nhỏ thu hồi khoá trên bảng, và ghép lại đè lên khoá cũ cũng vậy.
    const pairAgain = async () => {
      await manager.startPairing(board)
      assert.equal(await server('approve'), 'approved extension')
      const x = await manager.tick()
      assert.equal(x.status, 'ok')
      return x.token
    }
    const stateWith = async key => (await fetch(board + '/ext/state', { headers: { Authorization: 'Bearer ' + key } })).status
    const firstKey = await pairAgain()
    const secondKey = await pairAgain()
    const keyStatus = [await stateWith(firstKey), await stateWith(secondKey)]
    check('pairing again revokes the key it replaces on the board', () => {
      assert.notEqual(firstKey, secondKey)
      assert.deepEqual(keyStatus, [401, 200])
    })
    const sent = requests.length
    s = await manager.forget()
    const unpairCall = requests.slice(sent).find(r => r.url === board + '/ext/unpair')
    check('unpair this browser: the board is told first, with the key only in Authorization', () => {
      assert.ok(unpairCall)
      assert.equal(unpairCall.options.method, 'POST')
      assert.equal(unpairCall.options.headers.Authorization, 'Bearer ' + secondKey)
      assert.equal(unpairCall.options.credentials, 'omit')
      assert.deepEqual([s.status, s.token], ['unpaired', undefined])
    })
    const afterUnpair = await stateWith(secondKey)
    check('after unpairing, the old key no longer works on the board', () => assert.equal(afterUnpair, 401))
    const unpairAudit = (await server('audit')).split(' ')
    check('audit log: the extension unpaired itself, marked extension', () => assert.ok(unpairAudit.includes('tv-unpaired-itself:extension')))
    const thirdKey = await pairAgain()
    offline = true
    s = await manager.forget()
    offline = false
    check('unpair with the board out of reach still forgets the key here', () => assert.deepEqual([s.status, s.token], ['unpaired', undefined]))
    assert.equal(await server('revoke'), 'revoked 1')
    assert.equal(await stateWith(thirdKey), 401)

    console.log(`\n${passed} checks passed`)
  } finally {
    py.kill()
  }
}

main().catch(e => {
  console.error(e)
  process.exit(1)
})
