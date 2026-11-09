// The menu bar window: reads the wall view from /data every 30 seconds and draws one tab at a time.
// Khung thanh menu: đọc phần màn hình treo tường từ /data mỗi 30 giây và vẽ từng thẻ một.
;(function () {
  'use strict'
  var body = document.body
  // inside the macOS app the page is see-through, so the app's blurred background shows
  // trong app macOS trang trong suốt, để lộ nền mờ của app
  if (/AIWorkerApp\//.test(navigator.userAgent)) document.documentElement.classList.add('app')
  var words = JSON.parse(body.getAttribute('data-words') || '{}')
  var lang = body.getAttribute('data-lang') || 'en'
  var rate = Number(body.getAttribute('data-rate')) || 0
  var t = function (w, n) { return (words[w] || w).replace('{n}', n).replace('{time}', n) }
  var $ = function (id) { return document.getElementById(id) }
  var KINDS = { five_hour: '5-hour', seven_day: '7-day', seven_day_opus: '7-day Opus', seven_day_sonnet: '7-day Sonnet', spend_limit: 'spending' }
  var tab = 'waiting'
  var data = null
  var settings = { notify: true, notifyMinutes: 10 }
  // A page that hosts this window elsewhere (the manager browser extension) defines window.MiniApi first: data, state, save, unpair, setLang, openLink, each returning a promise.
  // Without it the window talks to its own server with its cookie, as the menu bar windows do.
  // Trang đặt khung này ở nơi khác (tiện ích trình duyệt của quản lý) định nghĩa window.MiniApi trước: data, state, save, unpair, setLang, openLink, mỗi hàm trả về promise.
  // Không có thì khung nói với chính máy chủ của nó bằng cookie, như các khung thanh menu.
  var api = window.MiniApi || null
  function json(r) {
    if (!r.ok) throw new Error(String(r.status))
    return r.json()
  }
  var server = api || {
    data: function () { return fetch('/data', { credentials: 'same-origin', cache: 'no-store' }).then(json) },
    state: function () { return fetch('/mini/state', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null }) },
    save: function (next) {
      return fetch('/mini/settings', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) })
        .then(function (r) { return r.ok })
    },
    unpair: function () { return fetch('/mini/unpair', { method: 'POST', credentials: 'same-origin' }) }
  }

  function money(usd) {
    if (lang !== 'vi') return '$' + usd.toFixed(2)
    return Math.round(usd * rate).toLocaleString('vi-VN') + ' \u0111'
  }
  function minutesSince(ms) { return ms ? Math.max(0, Math.floor((Date.now() - ms) / 60000)) : 0 }
  function row(cls, name, val, extra) {
    var li = document.createElement('li')
    if (cls) li.className = cls
    var dot = document.createElement('span'); dot.className = 'dot'; li.appendChild(dot)
    var n = document.createElement('span'); n.className = 'name'; n.textContent = name; li.appendChild(n)
    if (extra) li.appendChild(extra)
    var v = document.createElement('span'); v.className = 'val'; v.textContent = val; li.appendChild(v)
    return li
  }
  function empty(text) { var li = document.createElement('li'); li.className = 'empty'; li.textContent = text; return li }
  function bar(pct) {
    var b = document.createElement('span'); b.className = 'bar'
    var i = document.createElement('i'); i.style.width = Math.min(100, pct) + '%'; if (pct >= 80) i.className = 'hi'
    b.appendChild(i); return b
  }

  // the highlight under the selected tab: placed on that tab, slides to the new one on a switch
  // ô nền dưới thẻ đang chọn: đặt đúng chỗ thẻ đó, đổi thẻ thì trượt sang
  function placeHighlight() {
    var nav = document.querySelector('nav'), on = document.querySelector('nav button[aria-selected=true]')
    if (!nav || !on) return
    var o = nav.querySelector('.o-chon')
    if (!o) { o = document.createElement('span'); o.className = 'o-chon'; nav.insertBefore(o, nav.firstChild); nav.classList.add('co-o') }
    o.style.width = on.offsetWidth + 'px'
    o.style.height = on.offsetHeight + 'px'
    o.style.transform = 'translate(' + on.offsetLeft + 'px,' + on.offsetTop + 'px)'
  }
  // switching tabs: the highlight slides, and the title and content fade quickly (on a click only, not on the automatic refresh)
  // đổi thẻ: ô nền trượt, tiêu đề và nội dung đổi mờ nhanh (chỉ khi bấm, không khi tự làm mới)
  function animate() {
    placeHighlight()
    ;['title', 'list', 'settings'].forEach(function (id) {
      var el = $(id)
      el.classList.remove('chuyen-the')
      void el.offsetWidth
      el.classList.add('chuyen-the')
    })
  }

  function draw() {
    var titles = { waiting: 'Waiting', working: 'Working', quota: 'Quota', cost: 'Cost today', settings: 'Settings' }
    $('title').textContent = t(titles[tab])
    document.querySelectorAll('nav button').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-tab') === tab)) })
    var list = $('list')
    list.textContent = ''
    $('settings').hidden = tab !== 'settings'
    list.hidden = tab === 'settings'
    if (!data || tab === 'settings') return
    var people = (data.people || []).filter(function (p) { return p.status !== 'offline' })
    var waiting = people.filter(function (p) { return p.waiting })
    var badge = $('badge')
    badge.hidden = !waiting.length
    badge.textContent = String(waiting.length)
    if (tab === 'waiting') {
      waiting.sort(function (a, b) { return (a.waitingSince || 0) - (b.waitingSince || 0) })
      waiting.forEach(function (p) {
        var m = minutesSince(p.waitingSince)
        list.appendChild(row(m >= settings.notifyMinutes ? 'long' : '', p.name, m ? t('{n} min', m) : t('just now')))
      })
      if (!waiting.length) list.appendChild(empty(t('Nobody is waiting')))
    } else if (tab === 'working') {
      var working = people.filter(function (p) { return p.working && !p.waiting })
      working.forEach(function (p) {
        var model = Object.keys(p.models || {})[0] || ''
        var m = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?/.exec(model)
        list.appendChild(row('work', p.name, m ? m[1].charAt(0).toUpperCase() + m[1].slice(1) + ' ' + m[2] + (m[3] ? '.' + m[3] : '') : model))
      })
      if (!working.length) list.appendChild(empty(t('Nobody is working')))
    } else if (tab === 'quota') {
      var seen = 0
      ;(data.people || []).forEach(function (p) {
        // every window the account reports: a plan without a 5-hour limit simply has no five_hour window
        // mọi khung tài khoản báo về: gói không giới hạn 5 giờ thì không có khung five_hour
        var w = ((p.quota || {}).windows || []).filter(function (x) { return typeof x.pct === 'number' })
        if (!w.length) return
        seen++
        var worst = w.reduce(function (a, b) { return b.pct > a.pct ? b : a })
        list.appendChild(row(worst.pct >= 80 ? 'long' : '', p.name, Math.round(worst.pct) + '% ' + (KINDS[worst.kind] ? t(KINDS[worst.kind]) : worst.kind), bar(worst.pct)))
      })
      if (!seen) list.appendChild(empty(t('No quota reading yet')))
    } else {
      var total = 0
      ;(data.people || []).slice().sort(function (a, b) { return (b.usdToday || 0) - (a.usdToday || 0) }).forEach(function (p) {
        total += p.usdToday || 0
        if (p.usdToday) list.appendChild(row('', p.name, money(p.usdToday)))
      })
      list.insertBefore(row('work', t('Whole team'), money(total)), list.firstChild)
    }
  }

  function load() {
    Promise.resolve().then(server.data).then(function (d) {
      data = d
      var now = new Date()
      $('updated').textContent = t('Updated {time}', ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2))
      $('updated').className = ''
      draw()
    }).catch(function () {
      data = null
      $('updated').textContent = t('Cannot reach the server')
      $('updated').className = 'err'
      draw()
    })
  }

  function loadSettings() {
    Promise.resolve().then(server.state).then(function (s) {
      if (!s) return
      settings = { notify: s.notify, notifyMinutes: s.notifyMinutes }
      $('notify').checked = !!s.notify
      $('minutes').value = String(s.notifyMinutes)
      redrawPickers.forEach(function (f) { f() })
      draw()
    })
  }

  function saveSettings() {
    var next = { notify: $('notify').checked, notifyMinutes: Number($('minutes').value) }
    Promise.resolve(next).then(server.save).catch(function () { return false }).then(function (ok) {
      $('saved').textContent = ok ? t('Saved') : t('Could not save')
      $('saved').className = ok ? '' : 'err'
      if (ok) { settings = next; draw() }
    })
  }

  document.querySelectorAll('nav button').forEach(function (b) {
    b.addEventListener('click', function () { tab = b.getAttribute('data-tab'); draw(); animate() })
  })
  placeHighlight()
  addEventListener('resize', placeHighlight)
  $('notify').addEventListener('change', saveSettings)
  $('minutes').addEventListener('change', saveSettings)
  // the macOS app answers through window.appState; the page talks to it through webkit.messageHandlers.app
  // app macOS trả lời qua window.appState; trang nói với app qua webkit.messageHandlers.app
  var toApp = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.app
  window.appState = function (s) { if (s && typeof s.login === 'boolean') $('login').checked = s.login }
  if (toApp) toApp.postMessage({ action: 'hello' })
  // the Windows window (WebView2) and the Ubuntu window take short text messages: lang:en|vi, hello, login:on|off.
  // They answer hello through window.appState, like the macOS app, and show the start-at-login row (class host-login).
  // khung Windows (WebView2) và khung Ubuntu nhận tin ngắn: lang:en|vi, hello, login:on|off.
  // Chúng trả lời hello qua window.appState, như app macOS, và hiện dòng tự chạy khi đăng nhập (lớp host-login).
  function toHost(message) {
    if (window.chrome && window.chrome.webview) window.chrome.webview.postMessage(message)
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.host) window.webkit.messageHandlers.host.postMessage(message)
  }
  function tellHost(code) { toHost('lang:' + code) }
  $('login').addEventListener('change', function () {
    if (toApp) toApp.postMessage({ action: 'login', on: $('login').checked })
    toHost('login:' + ($('login').checked ? 'on' : 'off'))
  })
  toHost('hello')
  tellHost(lang === 'vi' ? 'vi' : 'en')
  // the page language is the board's own lang cookie; the macOS app is told too, for its menu and notifications
  // ngôn ngữ trang là cookie lang của bảng; app macOS cũng được báo, cho menu và thông báo của nó
  $('lang').value = lang === 'vi' ? 'vi' : 'en'
  $('lang').addEventListener('change', function () {
    var code = $('lang').value === 'vi' ? 'vi' : 'en'
    // the extension keeps the choice itself and draws the window again in that language
    // tiện ích tự giữ lựa chọn và vẽ lại khung theo ngôn ngữ đó
    if (api) { api.setLang(code); return }
    document.cookie = 'lang=' + code + '; path=/; max-age=31536000; SameSite=Lax'
    if (toApp) toApp.postMessage({ action: 'lang', value: code })
    tellHost(code)
    window.location.reload()
  })
  // A question drawn in the window itself instead of the browser's own dialog (which says "localhost says" and gets cut off):
  // a card that slides up from the bottom, Cancel and the action; Escape or a click outside the card cancels.
  // Câu hỏi vẽ ngay trong khung thay cho hộp mặc định của trình duyệt (ghi "localhost says" và bị cắt):
  // tấm thẻ trượt lên từ đáy, nút Huỷ và nút thao tác; Escape hoặc bấm ra ngoài thẻ là huỷ.
  function ask(text, action, danger, yes) {
    var veil = document.createElement('div'); veil.className = 'hoi'
    var card = document.createElement('div'); card.className = 'hoi-the'; card.setAttribute('role', 'alertdialog')
    var p = document.createElement('p'); p.textContent = text
    var row = document.createElement('div'); row.className = 'hoi-nut'
    var no = document.createElement('button'); no.type = 'button'; no.className = 'btn'; no.textContent = t('Cancel')
    var ok = document.createElement('button'); ok.type = 'button'; ok.className = 'btn' + (danger ? ' danger' : ''); ok.textContent = action
    row.appendChild(no); row.appendChild(ok); card.appendChild(p); card.appendChild(row); veil.appendChild(card)
    function close() { veil.remove(); document.removeEventListener('keydown', key, true) }
    function key(e) { if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close() } }
    no.addEventListener('click', close)
    ok.addEventListener('click', function () { close(); yes() })
    veil.addEventListener('click', function (e) { if (e.target === veil) close() })
    document.addEventListener('keydown', key, true)
    document.body.appendChild(veil)
    no.focus()
  }
  $('uninstall').addEventListener('click', function () {
    if (toApp) {
      ask(t('Remove the app from this Mac? This computer is unpaired and the app goes to the Trash.'), t('Remove the app'), true, function () { toApp.postMessage({ action: 'uninstall' }) })
      return
    }
    // the Windows and Ubuntu windows: unpair on the server first, then the window removes the app from this computer
    // khung Windows và Ubuntu: bỏ ghép trên máy chủ trước, rồi khung gỡ app khỏi máy này
    ask(t('Remove the app from this computer? This computer is unpaired and the app is removed.'), t('Remove the app'), true, function () {
      Promise.resolve().then(server.unpair).catch(function () {}).then(function () { toHost('uninstall') })
    })
  })
  // quit the app (before installing a new copy over it): no question, opening it again brings it back as it was
  // thoát app (trước khi cài bản mới đè lên): không hỏi, mở lại là như cũ
  $('quit').addEventListener('click', function () {
    if (toApp) toApp.postMessage({ action: 'quit' })
    else toHost('quit')
  })
  $('unpair').addEventListener('click', function () {
    ask(t('Unpair this computer? You will need a new code from an admin.'), t('Unpair this computer'), false, function () {
      Promise.resolve().then(server.unpair).then(function () { window.location.reload() })
    })
  })
  // drop-downs drawn in the window's own style: a rounded list on the glass, a tick on the chosen line; the real select still holds the value
  // ô xổ xuống vẽ theo kiểu của khung: danh sách bo góc, nền kính, dấu tích ở dòng đang chọn; ô gốc vẫn giữ giá trị
  var redrawPickers = []
  function nicePicker(sel) {
    var box = document.createElement('div'); box.className = 'chon'
    var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'chon-nut'; btn.setAttribute('aria-haspopup', 'listbox')
    var ds = document.createElement('ul'); ds.className = 'chon-ds'; ds.setAttribute('role', 'listbox'); ds.hidden = true
    function label() { var o = sel.options[sel.selectedIndex]; btn.textContent = o ? o.textContent : '' }
    function pick(i) {
      close()
      if (sel.selectedIndex !== i) { sel.selectedIndex = i; label(); sel.dispatchEvent(new Event('change')) }
      btn.focus()
    }
    function open() {
      ds.textContent = ''
      Array.prototype.forEach.call(sel.options, function (o, i) {
        var li = document.createElement('li'); li.setAttribute('role', 'option'); li.textContent = o.textContent
        li.setAttribute('aria-selected', String(i === sel.selectedIndex))
        li.addEventListener('click', function (e) { e.stopPropagation(); pick(i) })
        ds.appendChild(li)
      })
      ds.hidden = false; box.classList.add('mo')
      // near the bottom of the window the list opens upward, so it is not cut off
      // gần đáy khung thì mở lên trên, để danh sách không bị cắt
      var r = btn.getBoundingClientRect()
      ds.classList.toggle('len', window.innerHeight - r.bottom < ds.offsetHeight + 8 && r.top > ds.offsetHeight + 8)
    }
    function close() { ds.hidden = true; box.classList.remove('mo') }
    btn.addEventListener('click', function (e) { e.stopPropagation(); if (ds.hidden) open(); else close() })
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        var i = Math.max(0, Math.min(sel.options.length - 1, sel.selectedIndex + (e.key === 'ArrowDown' ? 1 : -1)))
        if (i !== sel.selectedIndex) { sel.selectedIndex = i; label(); sel.dispatchEvent(new Event('change')) }
      } else if (e.key === 'Escape' && !ds.hidden) { e.stopPropagation(); close() }
    })
    document.addEventListener('click', close)
    sel.parentNode.insertBefore(box, sel)
    box.appendChild(btn); box.appendChild(ds); box.appendChild(sel)
    sel.hidden = true
    // a row with a drop-down: text on the left (wrapping within its own part when long), the drop-down and its unit together on the right
    // dòng có ô chọn: chữ bên trái (dài thì xuống dòng trong phần của nó), ô chọn và đơn vị đứng chung bên phải
    var row = box.closest('.row')
    if (row && row.querySelector('input[type=checkbox]')) {
      // with a check box in front: the drop-down and its unit stay together; they sit on the text's line when it fits,
      // otherwise they move down together, lined up under the text
      // có ô đánh dấu phía trước: ô chọn và đơn vị đi liền nhau; đủ chỗ thì nằm cùng dòng với chữ,
      // không đủ thì cùng xuống dòng, thụt vào thẳng hàng dưới chữ
      var group = document.createElement('span'); group.className = 'cum'
      row.insertBefore(group, box)
      group.appendChild(box)
      while (group.nextSibling) group.appendChild(group.nextSibling)
      row.classList.add('co-o-danh-dau')
      var text = row.querySelector('label')
      var align = function () { group.classList.remove('xuong'); if (group.offsetTop > text.offsetTop + 4) group.classList.add('xuong') }
      new ResizeObserver(align).observe(row); align()
    } else if (row) row.classList.add('co-chon')
    label()
    redrawPickers.push(label)
  }
  document.querySelectorAll('.row select').forEach(nicePicker)
  // inside the extension a link such as /board points at the extension itself, so the host opens it on the board
  // trong tiện ích, liên kết như /board trỏ vào chính tiện ích, nên bên chứa mở nó trên bảng
  if (api && api.openLink) {
    document.querySelectorAll('.mini a[href]').forEach(function (a) {
      a.addEventListener('click', function (e) { e.preventDefault(); api.openLink(a.getAttribute('href')) })
    })
  }
  draw()
  load()
  loadSettings()
  setInterval(load, 30000)
})()
