// The small window: shows what the service worker stored, and sends it the manager's clicks. All words come from _locales.
// Cửa sổ nhỏ: hiện những gì service worker đã lưu, và chuyển cho nó các lần bấm của quản lý. Mọi chữ lấy từ _locales.
/* global chrome, ManagerCore */
;(function () {
  'use strict'
  // words in the language chosen in the Settings tab (see words()), else the browser's through chrome.i18n
  // chữ theo ngôn ngữ chọn ở thẻ Cài đặt (xem words()), không có thì theo trình duyệt qua chrome.i18n
  let messages = null
  let lang = ManagerCore.pickLang('', chrome.i18n.getUILanguage())
  const t = (key, subs) => messages && messages[key] ? ManagerCore.formatMessage(messages, key, subs) : chrome.i18n.getMessage(key, subs)
  const $ = id => document.getElementById(id)
  const send = msg => chrome.runtime.sendMessage(msg)
  let current = null
  let miniShown = false
  const LANG_KEY = ManagerCore.LANG_KEY

  async function words () {
    const x = await chrome.storage.local.get(LANG_KEY)
    lang = ManagerCore.pickLang(x[LANG_KEY], chrome.i18n.getUILanguage())
    try {
      messages = await (await fetch(chrome.runtime.getURL('_locales/' + lang + '/messages.json'))).json()
    } catch (e) {
      messages = null
    }
    document.documentElement.lang = lang
    for (const el of document.querySelectorAll('[data-msg]')) el.textContent = t(el.dataset.msg)
    for (const m of ManagerCore.NOTIFY_CHOICES) {
      const c = document.createElement('option')
      c.value = String(m)
      c.textContent = t('minutesChoice', String(m))
      $('notify-minutes').append(c)
    }
  }

  const clock = ms => new Date(ms).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })

  function waited (since, now) {
    const m = ManagerCore.minutesWaited(since, now)
    if (m < 1) return t('justNow')
    return m < 60 ? t('minutesShort', String(m)) : t('hoursMinutes', [String(Math.floor(m / 60)), String(m % 60)])
  }

  function item (name, right) {
    const li = document.createElement('li')
    const a = document.createElement('span')
    a.className = 'name'
    a.textContent = name
    li.append(a)
    if (right) {
      const b = document.createElement('span')
      b.className = 'time'
      b.textContent = right
      li.append(b)
    }
    return li
  }

  function empty (text) {
    const li = document.createElement('li')
    li.className = 'empty'
    li.textContent = text
    return li
  }

  function render (s) {
    current = s
    if (miniShown) return
    $('classic').hidden = false
    const now = Date.now()
    const view = s.status === 'ok' ? 'ok' : s.status === 'pairing' ? 'pairing' : s.status === 'unreachable' ? 'unreachable' : 'unpaired'
    for (const name of ['unpaired', 'pairing', 'unreachable', 'ok']) $('view-' + name).hidden = name !== view
    $('paired-as').textContent = s.token && s.pairedName ? t('pairedAs', s.pairedName) : ''
    $('open-board').hidden = !s.boardUrl
    $('forget').hidden = !(s.token || s.pendingKey)
    $('notify').checked = s.settings.notify
    $('notify-minutes').value = String(s.settings.notifyMinutes)
    if (view === 'unpaired') {
      const reasons = { revoked: 'revoked', codeExpired: 'codeExpired' }
      $('unpaired-reason').textContent = t(reasons[s.reason] || 'notPaired')
      if (!$('board-url').value && s.boardUrl) $('board-url').value = s.boardUrl
    } else if (view === 'pairing') {
      $('code').textContent = s.code ? s.code.slice(0, 4) + '-' + s.code.slice(4) : ''
      $('code-left').textContent = s.codeExpiresAt ? t('codeValidUntil', clock(s.codeExpiresAt)) : ''
      $('pairing-trouble').textContent = s.reason === 'pairingUnreachable' ? t('pairingUnreachable') : ''
    } else if (view === 'unreachable') {
      $('unreachable-text').textContent = t(s.reason === 'permission' ? 'needPermission' : 'unreachable')
      $('last-ok').textContent = s.lastCheckAt ? t('lastTried', clock(s.lastCheckAt)) : ''
      $('allow-access').hidden = s.reason !== 'permission'
    } else {
      const people = s.people || []
      const waiting = people.filter(p => p.waiting).sort((a, b) => ((s.seen[a.name] || {}).since || now) - ((s.seen[b.name] || {}).since || now))
      const working = people.filter(p => p.working && !p.waiting)
      $('summary').textContent = t('summary', [String(waiting.length), String(working.length)])
      $('waiting-list').replaceChildren(...(waiting.length ? waiting.map(p => item(p.name, waited((s.seen[p.name] || {}).since || now, now))) : [empty(t('nobodyWaiting'))]))
      $('working-list').replaceChildren(...(working.length ? working.map(p => item(p.name)) : [empty(t('nobodyWorking'))]))
      $('updated').textContent = s.lastOkAt ? t('updatedAt', clock(s.lastOkAt)) : ''
    }
  }

  async function refresh () {
    const r = await send({ type: 'refresh' })
    if (r && r.ok) render(r.result)
  }

  // The language of the small window: the one chosen in its Settings tab, else the browser's.
  // Ngôn ngữ của cửa sổ nhỏ: ngôn ngữ đã chọn ở thẻ Cài đặt, không có thì theo trình duyệt.
  async function chosenLang () {
    const x = await chrome.storage.local.get(LANG_KEY)
    return ManagerCore.pickLang(x[LANG_KEY], chrome.i18n.getUILanguage())
  }

  // The board's page is only copied as layout and words: an allowlist (ManagerCore.keepTag, keepAttribute) keeps the tags and attributes
  // the menu bar window uses; any other element goes with everything inside it, any other attribute is dropped.
  // Trang của bảng chỉ được chép làm bố cục và chữ: danh sách cho phép (ManagerCore.keepTag, keepAttribute) giữ các thẻ và thuộc tính
  // khung thanh menu dùng; phần tử khác bị bỏ cùng mọi thứ bên trong, thuộc tính khác bị xoá.
  function clean (root) {
    for (const el of [...root.querySelectorAll('*')]) {
      if (el.isConnected && !ManagerCore.keepTag(el.localName)) el.remove()
    }
    for (const el of [root, ...root.querySelectorAll('*')]) {
      for (const a of [...el.attributes]) {
        if (!ManagerCore.keepAttribute(a.name, a.value)) el.removeAttribute(a.name)
      }
    }
  }

  function addStyle (href) {
    return new Promise(resolve => {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = href
      link.onload = link.onerror = resolve
      document.head.append(link)
    })
  }

  // Paired: the popup becomes the menu bar window. Its page comes from the board (/ext/mini), its script and style are the copies in mini/,
  // and window.MiniApi sends what the script asks for to the service worker. Any failure keeps the simple view.
  // Đã ghép: cửa sổ nhỏ thành khung thanh menu. Trang lấy từ bảng (/ext/mini), script và style là bản chép trong mini/,
  // còn window.MiniApi chuyển những gì script hỏi sang service worker. Hỏng chỗ nào thì giữ giao diện đơn giản.
  async function showMini () {
    const r = await send({ type: 'miniPage', lang: await chosenLang() })
    const page = r && r.ok && r.result
    if (page && page.status === 401) return false
    if (!page || !page.html) return false
    const doc = new DOMParser().parseFromString(page.html, 'text/html')
    const main = doc.querySelector('main.mini')
    if (!main || !doc.body.hasAttribute('data-words')) return false
    clean(main)
    for (const name of ['data-words', 'data-lang', 'data-rate']) {
      const v = doc.body.getAttribute(name)
      if (v !== null) document.body.setAttribute(name, v)
    }
    document.documentElement.lang = doc.body.getAttribute('data-lang') === 'vi' ? 'vi' : 'en'
    document.title = doc.title
    $('popup-css').remove()
    await Promise.all([addStyle('mini/mini.css'), addStyle('popup-mini.css')])
    miniShown = true
    $('classic').replaceWith(document.adoptNode(main))
    followHeight(main)
    const result = async msg => {
      const x = await send(msg)
      if (!x || !x.ok) throw new Error('no answer')
      return x.result
    }
    window.MiniApi = {
      data: async () => {
        const x = await result({ type: 'wallData' })
        if (x.status === 401) location.reload()
        if (!x.data) throw new Error(String(x.status))
        return x.data
      },
      state: async () => (await result({ type: 'state' })).settings,
      save: async next => {
        const saved = (await result({ type: 'saveSettings', settings: next })).settings
        return saved.notify === next.notify && saved.notifyMinutes === next.notifyMinutes
      },
      // the same as "Unpair this browser" before; mini.js reloads the popup afterwards, which shows the pairing form
      // giống "Bỏ ghép trình duyệt này" trước đây; sau đó mini.js tải lại cửa sổ nhỏ, cửa sổ hiện ô ghép
      unpair: () => result({ type: 'forget' }),
      setLang: async code => {
        await chrome.storage.local.set({ [LANG_KEY]: code === 'vi' ? 'vi' : 'en' })
        location.reload()
      },
      // the tab is opened here and awaited: a message sent just before the popup closes can be lost
      // mở thẻ ngay tại đây và chờ xong: tin nhắn gửi ngay trước khi cửa sổ nhỏ đóng có thể bị mất
      openLink: async href => {
        const s = await result({ type: 'state' })
        if (s.boardUrl) await chrome.tabs.create({ url: s.boardUrl + ManagerCore.boardPath(href) })
        window.close()
      }
    }
    const script = document.createElement('script')
    script.src = 'mini/mini.js'
    document.body.append(script)
    return true
  }

  // Chrome sizes the popup to the page, so a new tab would make it jump; the body's height glides to the window's height instead.
  // While it glides, what sticks out is hidden; afterwards it shows again, so an open drop-down is not cut.
  // Chrome đặt cỡ cửa sổ nhỏ theo trang, nên đổi thẻ sẽ làm nó nhảy cỡ; thay vào đó chiều cao của body trượt dần tới chiều cao của khung.
  // Trong lúc trượt, phần thò ra bị ẩn; trượt xong thì hiện lại, để ô xổ xuống đang mở không bị cắt.
  function followHeight (main) {
    const body = document.body
    let shown = 0
    new ResizeObserver(() => {
      const h = main.offsetHeight
      if (!h || h === shown) return
      // the first height is set at once; later ones glide (none when the system asks for less motion: the CSS has no transition then)
      // chiều cao đầu tiên đặt ngay; các lần sau trượt dần (hệ thống xin giảm chuyển động thì CSS không có chuyển tiếp)
      body.classList.toggle('gian', shown > 0 && !matchMedia('(prefers-reduced-motion: reduce)').matches)
      shown = h
      body.style.height = h + 'px'
    }).observe(main)
    body.addEventListener('transitionend', e => {
      if (e.target === body && e.propertyName === 'height') body.classList.remove('gian')
    })
  }

  async function start () {
    // the popup sees the mode too; this fixes the toolbar icon even if the hidden page could not start
    // cửa sổ nhỏ cũng thấy chế độ; nhờ vậy biểu tượng đúng màu kể cả khi trang ẩn không mở được
    send({ type: 'theme', dark: matchMedia('(prefers-color-scheme: dark)').matches }).catch(() => {})
    await words()
    // a pairing that started after the access prompt closed this popup, or the error it ran into
    // việc ghép đã bắt đầu sau khi hộp hỏi quyền đóng cửa sổ này, hoặc lỗi nó gặp
    const pending = await send({ type: 'pairPending' })
    const pendingError = pending && pending.ok && pending.result && pending.result.error
    const r = await send({ type: 'refresh' })
    if (!r || !r.ok) return
    if (pendingError) {
      render(r.result)
      $('pair-error').textContent = t(pendingError)
      return
    }
    if (r.result.status === 'ok' && await showMini().catch(() => false)) return
    render(r.result.status === 'ok' ? (await send({ type: 'state' })).result : r.result)
  }

  // The browser asks the manager for this one address only; the request must come straight from the click.
  // Trình duyệt hỏi quản lý cho đúng một địa chỉ này; lời xin phải đi thẳng từ lần bấm.
  function requestAccess (origin) {
    return chrome.permissions.request({ origins: [ManagerCore.originPattern(origin)] })
  }

  $('pair-form').addEventListener('submit', async e => {
    e.preventDefault()
    $('pair-error').textContent = ''
    const origin = ManagerCore.normalizeBoardUrl($('board-url').value)
    if (!origin) {
      $('pair-error').textContent = t(ManagerCore.addressProblem($('board-url').value))
      return
    }
    // noted before asking: Chrome may close this popup during the prompt, and the hidden page then starts the pairing
    // ghi lại trước khi hỏi: Chrome có thể đóng cửa sổ này trong lúc hỏi, khi đó trang ẩn bắt đầu ghép
    await chrome.storage.session.set({ pendingPairing: { origin, at: Date.now() } })
    let granted = false
    try {
      granted = await requestAccess(origin)
    } catch (err) {
      granted = false
    }
    if (!granted) {
      await chrome.storage.session.remove('pendingPairing')
      $('pair-error').textContent = t('permissionDenied')
      return
    }
    const r = await send({ type: 'pairPending' })
    if (r && r.ok && r.result && r.result.error) $('pair-error').textContent = t(r.result.error)
    else refresh()
  })

  $('allow-access').addEventListener('click', async () => {
    if (current && current.boardUrl && await requestAccess(current.boardUrl)) refresh()
  })
  $('cancel-pairing').addEventListener('click', async () => {
    const r = await send({ type: 'forget' })
    if (r && r.ok) render(r.result)
  })
  $('forget').addEventListener('click', async () => {
    if (!confirm(t('forgetConfirm'))) return
    const r = await send({ type: 'forget' })
    if (r && r.ok) render(r.result)
  })
  $('open-board').addEventListener('click', () => {
    send({ type: 'openBoard' })
    window.close()
  })
  const saveSettings = async () => {
    const r = await send({ type: 'saveSettings', settings: { notify: $('notify').checked, notifyMinutes: Number($('notify-minutes').value) } })
    if (r && r.ok) render(r.result)
  }
  $('notify').addEventListener('change', saveSettings)
  $('notify-minutes').addEventListener('change', saveSettings)

  // While a code is shown, ask every 5 seconds so the approval shows quickly; otherwise only redraw the times.
  // Khi đang hiện mã thì hỏi mỗi 5 giây để thấy duyệt nhanh; còn lại chỉ vẽ lại thời gian.
  setInterval(() => {
    if (miniShown) return
    if (current && current.status === 'pairing') refresh()
    else if (current) render(current)
  }, 5000)
  start()
})()
