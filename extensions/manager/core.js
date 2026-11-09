// Logic of the manager extension with no browser API inside: storage, network, badge and notifications are handed in, so Node can test it against a local server.
// Logic của tiện ích cho quản lý, không dùng API trình duyệt: lưu trữ, mạng, biểu tượng và thông báo được truyền vào, để Node thử được với máy chủ trên máy.
;(function (root) {
  'use strict'

  const POLL_MINUTES = 1
  const NOTIFY_CHOICES = [5, 10, 15, 30, 60]
  const DEFAULT_SETTINGS = { notify: true, notifyMinutes: 10 }
  const REQUEST_TIMEOUT_MS = 10000
  // After a gap this long without an answer, nobody knows whether a wait went on or started again: counting restarts.
  // Mất liên lạc lâu hơn ngần này thì không biết một lần chờ còn tiếp hay đã bắt đầu lại: đếm lại từ đầu.
  const GAP_RESETS_WAITS_MS = 5 * 60 * 1000
  const BADGE_WAITING = '#c0392b'
  const BADGE_GREY = '#8a8a8a'
  const STATE_KEYS = ['boardUrl', 'token', 'pendingKey', 'code', 'codeExpiresAt', 'pairedName', 'status', 'reason', 'people', 'seen', 'lastOkAt', 'lastCheckAt', 'settings']

  // Plain http only to this very computer, for testing: the key would otherwise travel readable on the network.
  // The manifest's optional host permissions list the same two hosts.
  // http thường chỉ tới chính máy này, để thử: không thì khoá đi trên mạng ai cũng đọc được.
  // Quyền truy cập tuỳ chọn trong manifest liệt kê đúng hai máy này.
  const LOCAL_HOSTS = ['localhost', '127.0.0.1']

  function parseBoardUrl (text) {
    let s = String(text || '').trim()
    if (!s) return null
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = 'https://' + s
    try {
      return new URL(s)
    } catch (e) {
      return null
    }
  }

  // The board address as an origin only (scheme, host, port); anything else is refused. No scheme means https.
  // Địa chỉ bảng chỉ giữ phần gốc (giao thức, máy, cổng); kiểu khác thì từ chối. Không ghi giao thức thì coi là https.
  function normalizeBoardUrl (text) {
    const u = parseBoardUrl(text)
    if (!u || (u.protocol !== 'https:' && u.protocol !== 'http:') || !u.hostname || u.username || u.password) return ''
    if (u.protocol === 'http:' && !LOCAL_HOSTS.includes(u.hostname)) return ''
    return u.origin
  }

  // The message key that says why an address was refused: plain http to another computer gets its own words.
  // Khoá câu nói vì sao địa chỉ bị từ chối: http thường tới máy khác có câu riêng.
  function addressProblem (text) {
    const u = parseBoardUrl(text)
    return u && u.protocol === 'http:' && u.hostname && !LOCAL_HOSTS.includes(u.hostname) ? 'httpNotAllowed' : 'invalidAddress'
  }

  // What the popup keeps of the board's page (/ext/mini): only the tags and attributes that page uses, so nothing from the board can run,
  // load or send anything. svg keeps only its drawing shapes; href only a path on the board.
  // Những gì cửa sổ nhỏ giữ lại từ trang của bảng (/ext/mini): chỉ các thẻ và thuộc tính trang đó dùng, để không gì từ bảng chạy được,
  // tải được hay gửi được gì. svg chỉ giữ các hình vẽ; href chỉ là một đường dẫn trên bảng.
  const KEPT_TAGS = ['main', 'header', 'footer', 'nav', 'section', 'div', 'span', 'b', 'strong', 'small', 'p', 'h1', 'h2', 'h3', 'ul', 'ol', 'li',
    'button', 'label', 'input', 'select', 'option', 'a', 'svg', 'g', 'path', 'circle', 'rect']
  const KEPT_ATTRIBUTES = ['class', 'id', 'role', 'hidden', 'type', 'value', 'for', 'title', 'viewbox', 'width', 'height', 'fill', 'stroke', 'd',
    'cx', 'cy', 'r', 'x', 'y', 'rx', 'points', 'xmlns']
  function keepTag (tag) {
    return KEPT_TAGS.includes(String(tag || '').toLowerCase())
  }
  function keepAttribute (name, value) {
    const n = String(name || '').toLowerCase()
    if (n === 'href') return /^\/(?![\/\\])/.test(String(value || ''))
    return KEPT_ATTRIBUTES.includes(n) || /^(aria|data)-[a-z0-9-]+$/.test(n) || /^stroke-[a-z-]+$/.test(n)
  }

  // The one site the browser is asked for: a match pattern has no port, so it covers every port of that host.
  // Trang duy nhất xin trình duyệt cho phép: mẫu khớp không có cổng, nên gồm mọi cổng của máy đó.
  function originPattern (origin) {
    const u = new URL(origin)
    return u.protocol + '//' + u.hostname + '/*'
  }

  // A link the small window may open: a path on the board only (such as /board); anything else becomes /board.
  // Liên kết cửa sổ nhỏ được mở: chỉ một đường dẫn trên bảng (như /board); kiểu khác thành /board.
  function boardPath (path) {
    return typeof path === 'string' && /^\/(?![\/\\])[A-Za-z0-9/_.?=&-]*$/.test(path) ? path : '/board'
  }

  // The language of the extension's words: the one chosen in the popup's Settings tab (stored under LANG_KEY), else the browser's.
  // Ngôn ngữ chữ của tiện ích: ngôn ngữ đã chọn ở thẻ Cài đặt của cửa sổ nhỏ (lưu dưới LANG_KEY), không có thì theo trình duyệt.
  const LANG_KEY = 'uiLang'
  function pickLang (stored, browserLang) {
    if (stored === 'vi' || stored === 'en') return stored
    return String(browserLang || '').toLowerCase().startsWith('vi') ? 'vi' : 'en'
  }

  function cleanSettings (x) {
    const notifyMinutes = NOTIFY_CHOICES.includes(x && x.notifyMinutes) ? x.notifyMinutes : DEFAULT_SETTINGS.notifyMinutes
    return { notify: x && typeof x.notify === 'boolean' ? x.notify : DEFAULT_SETTINGS.notify, notifyMinutes }
  }

  // Keep only what the popup shows; the server already sends no more than the wall view.
  // Chỉ giữ những gì cửa sổ nhỏ hiện; máy chủ vốn không gửi quá phần treo tường.
  function cleanPeople (list) {
    if (!Array.isArray(list)) return []
    return list.filter(p => p && typeof p.name === 'string').slice(0, 300)
      .map(p => ({ name: p.name.slice(0, 60), waiting: p.waiting === true, working: p.working === true }))
  }

  // When each waiting person was first seen waiting; someone who stopped waiting is dropped, so the next wait is a new one.
  // Lúc lần đầu thấy mỗi người đang chờ; ai thôi chờ thì bỏ, để lần chờ sau là một lần mới.
  function trackWaits (seen, people, now) {
    const out = {}
    for (const p of people) {
      if (!p.waiting) continue
      const old = seen && seen[p.name]
      out[p.name] = old && typeof old.since === 'number' ? { since: old.since, notified: old.notified === true } : { since: now, notified: false }
    }
    return out
  }

  // Names that passed the wait time and have not been notified in this wait yet.
  // Tên đã quá thời gian chờ mà chưa được báo trong lần chờ này.
  function dueNotifications (seen, settings, now) {
    if (!settings.notify) return []
    const limit = settings.notifyMinutes * 60000
    return Object.keys(seen).filter(name => !seen[name].notified && now - seen[name].since >= limit).sort()
  }

  function waitingCount (state) {
    return state.status === 'ok' ? (state.people || []).filter(p => p.waiting).length : 0
  }

  // Badge: the number waiting, nothing when nobody waits; grey "?" when the server cannot be reached; grey "!" when not paired.
  // Biểu tượng: số người chờ, không ai chờ thì trống; "?" xám khi không tới được máy chủ; "!" xám khi chưa ghép.
  function badgeFor (state) {
    if (state.status === 'ok') {
      const n = waitingCount(state)
      return { text: n ? (n > 99 ? '99+' : String(n)) : '', color: BADGE_WAITING, title: 'badgeOk', n }
    }
    if (state.status === 'unreachable') return { text: '?', color: BADGE_GREY, title: 'badgeUnreachable', n: 0 }
    return { text: '!', color: BADGE_GREY, title: 'badgeNotPaired', n: 0 }
  }

  function minutesWaited (since, now) {
    return Math.max(0, Math.floor((now - since) / 60000))
  }

  // Fill $1, $2... in a message of _locales. chrome.i18n only knows the browser's language, so the language chosen in the popup goes through here.
  // Điền $1, $2... vào một câu trong _locales. chrome.i18n chỉ biết ngôn ngữ của trình duyệt, nên ngôn ngữ chọn trong cửa sổ nhỏ đi qua hàm này.
  function formatMessage (messages, key, subs) {
    const entry = messages[key]
    if (!entry) return ''
    const list = subs === undefined ? [] : [].concat(subs).map(String)
    let text = entry.message
    for (const [name, ph] of Object.entries(entry.placeholders || {})) {
      const value = ph.content.replace(/\$(\d)/g, (_, i) => list[Number(i) - 1] || '')
      text = text.split('$' + name.toUpperCase() + '$').join(value).split('$' + name + '$').join(value)
    }
    return text
  }

  // deps: storage {get(keys), set(obj), remove(keys)}, fetch, hasPermission(origin), ui {setBadge, notify, t}, now().
  // deps: lưu trữ {get, set, remove}, fetch, hasPermission(địa chỉ gốc), giao diện {setBadge, notify, t}, now().
  function createManager (deps) {
    const now = deps.now || (() => Date.now())

    async function load () {
      const s = await deps.storage.get(STATE_KEYS)
      s.settings = cleanSettings(s.settings)
      s.seen = s.seen || {}
      s.status = s.status || 'unpaired'
      return s
    }

    async function save (patch) {
      await deps.storage.set(patch)
      const s = await load()
      await showBadge(s)
      return s
    }

    async function showBadge (s) {
      const b = badgeFor(s)
      await deps.ui.setBadge({ text: b.text, color: b.color, title: deps.ui.t(b.title, String(b.n)) })
    }

    // No cookie is sent or kept (credentials omit): the only key is the one the server gave on approval, in the Authorization header.
    // Không gửi và không giữ cookie (credentials omit): khoá duy nhất là khoá máy chủ cấp khi duyệt, trong header Authorization.
    async function call (origin, method, path, key, asText) {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      try {
        const headers = key ? { Authorization: 'Bearer ' + key } : {}
        const r = await deps.fetch(origin + path, { method, headers, credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal })
        let body = null
        try {
          body = asText ? await r.text() : await r.json()
        } catch (e) {
          body = null
        }
        return { status: r.status, body }
      } catch (e) {
        return { status: 0, body: null }
      } finally {
        clearTimeout(timer)
      }
    }

    // Tell the board this browser's key is no longer used, so it stops working there too. Best effort: a network error changes nothing here.
    // Báo bảng là khoá của trình duyệt này thôi dùng, để nó cũng hết dùng được ở đó. Cố hết sức: lỗi mạng không đổi gì ở đây.
    async function unpairOnServer (s) {
      if (s.token && s.boardUrl) await call(s.boardUrl, 'POST', '/ext/unpair', s.token)
    }

    // Ask for a pairing code. The caller has already been granted access to this address.
    // Xin mã ghép. Bên gọi đã được trình duyệt cho truy cập địa chỉ này.
    async function startPairing (boardUrl) {
      const origin = normalizeBoardUrl(boardUrl)
      if (!origin) return { error: addressProblem(boardUrl) }
      const s = await load()
      const r = await call(origin, 'POST', '/ext/request-code', s.boardUrl === origin ? s.pendingKey : '')
      if (r.status === 429) return { error: 'tooManyWaiting' }
      if (r.status !== 200 || !r.body || !/^\d{8}$/.test(r.body.code || '') || !r.body.key) return { error: 'cannotReach' }
      // a key from an earlier pairing is replaced: revoke it on its board first
      // khoá của lần ghép trước bị thay: thu hồi nó trên bảng của nó trước
      await unpairOnServer(s)
      await deps.storage.remove(['token', 'people', 'pairedName', 'lastOkAt'])
      await save({ boardUrl: origin, pendingKey: r.body.key, code: r.body.code, codeExpiresAt: now() + (r.body.secondsLeft || 600) * 1000,
        status: 'pairing', reason: '', seen: {}, lastCheckAt: now() })
      return { code: r.body.code }
    }

    async function pollPairing (s) {
      const r = await call(s.boardUrl, 'POST', '/ext/poll', s.pendingKey)
      if (r.status !== 200 || !r.body) return save({ lastCheckAt: now(), reason: 'pairingUnreachable' })
      if (r.body.status === 'done' && typeof r.body.token === 'string') {
        await deps.storage.remove(['pendingKey', 'code', 'codeExpiresAt'])
        await save({ token: r.body.token, pairedName: String(r.body.name || '').slice(0, 40), status: 'ok', reason: '', people: [] })
        return checkBoard(await load())
      }
      if (r.body.status === 'pending') return save({ lastCheckAt: now(), reason: '' })
      await deps.storage.remove(['pendingKey', 'code', 'codeExpiresAt'])
      return save({ status: 'unpaired', reason: 'codeExpired', lastCheckAt: now() })
    }

    async function checkBoard (s) {
      const t = now()
      if (!(await deps.hasPermission(s.boardUrl))) {
        return save({ status: 'unreachable', reason: 'permission', people: [], lastCheckAt: t })
      }
      const r = await call(s.boardUrl, 'GET', '/ext/state', s.token)
      if (r.status === 401) {
        // revoked in /admin (or expired): forget the key and ask to pair again
        // bị thu hồi trong /admin (hoặc hết hạn): quên khoá và đòi ghép lại
        await deps.storage.remove(['token', 'people', 'pairedName'])
        return save({ status: 'unpaired', reason: 'revoked', seen: {}, lastCheckAt: t })
      }
      if (r.status !== 200 || !r.body || !Array.isArray(r.body.people)) {
        // old numbers are dropped, never shown as current; the wait start times are kept for a short break
        // số cũ bị bỏ, không bao giờ hiện như số hiện tại; lúc bắt đầu chờ được giữ nếu mất liên lạc ngắn
        return save({ status: 'unreachable', reason: r.status === 0 ? 'network' : 'server', people: [], lastCheckAt: t })
      }
      const people = cleanPeople(r.body.people)
      const previous = s.lastOkAt && t - s.lastOkAt <= GAP_RESETS_WAITS_MS ? s.seen : {}
      const seen = trackWaits(previous, people, t)
      const due = dueNotifications(seen, s.settings, t)
      for (const name of due) {
        seen[name].notified = true
        await deps.ui.notify('wait:' + name + ':' + seen[name].since, deps.ui.t('notifyTitle'),
          deps.ui.t('notifyMessage', [name, String(minutesWaited(seen[name].since, t))]))
      }
      return save({ status: 'ok', reason: '', people, seen, lastOkAt: t, lastCheckAt: t })
    }

    // One beat, every minute from the alarm and whenever the popup opens.
    // Một nhịp, mỗi phút theo báo thức và mỗi lần mở cửa sổ nhỏ.
    async function tick () {
      const s = await load()
      if (s.token && s.boardUrl) return checkBoard(s)
      if (s.pendingKey && s.boardUrl) {
        if (s.codeExpiresAt && now() > s.codeExpiresAt) {
          await deps.storage.remove(['pendingKey', 'code', 'codeExpiresAt'])
          return save({ status: 'unpaired', reason: 'codeExpired' })
        }
        return pollPairing(s)
      }
      return save({ status: 'unpaired' })
    }

    // The menu bar window's page and the wall view for the popup, asked with the key like /ext/state; a revoked key forgets the pairing at once.
    // Trang khung thanh menu và phần treo tường cho cửa sổ nhỏ, hỏi bằng khoá như /ext/state; khoá bị thu hồi thì quên lần ghép ngay.
    async function askPaired (path, asText) {
      const s = await load()
      if (!s.token || !s.boardUrl) return { status: 401, body: null }
      if (!(await deps.hasPermission(s.boardUrl))) return { status: 0, body: null }
      const r = await call(s.boardUrl, 'GET', path, s.token, asText)
      if (r.status === 401) {
        await deps.storage.remove(['token', 'people', 'pairedName'])
        await save({ status: 'unpaired', reason: 'revoked', seen: {}, lastCheckAt: now() })
      }
      return r
    }

    async function miniPage (lang) {
      const r = await askPaired('/ext/mini?lang=' + (lang === 'vi' ? 'vi' : 'en'), true)
      return { status: r.status, html: r.status === 200 && typeof r.body === 'string' ? r.body : '' }
    }

    async function wallData () {
      const r = await askPaired('/ext/data', false)
      return { status: r.status, data: r.status === 200 && r.body && Array.isArray(r.body.people) ? r.body : null }
    }

    async function saveSettings (x) {
      return save({ settings: cleanSettings(x) })
    }

    // Unpair: the key is revoked on the board (best effort), then forgotten here. If the board could not be reached,
    // the row stays in /admin, where an admin can still revoke it.
    // Bỏ ghép: khoá bị thu hồi trên bảng (cố hết sức), rồi bị quên ở đây. Nếu không tới được bảng,
    // dòng vẫn còn trong /admin, nơi quản trị vẫn thu hồi được.
    async function forget () {
      await unpairOnServer(await load())
      await deps.storage.remove(['token', 'pendingKey', 'code', 'codeExpiresAt', 'people', 'pairedName', 'lastOkAt'])
      return save({ status: 'unpaired', reason: '', seen: {} })
    }

    return { load, tick, startPairing, saveSettings, forget, showBadge, miniPage, wallData }
  }

  const api = { POLL_MINUTES, NOTIFY_CHOICES, DEFAULT_SETTINGS, LANG_KEY, pickLang, normalizeBoardUrl, addressProblem, keepTag, keepAttribute, originPattern, boardPath, cleanSettings, cleanPeople, trackWaits, dueNotifications, waitingCount, badgeFor, minutesWaited, formatMessage, createManager }
  root.ManagerCore = api
  if (typeof module !== 'undefined' && module.exports) module.exports = api
})(typeof self !== 'undefined' ? self : globalThis)
