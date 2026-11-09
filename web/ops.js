// Operations dashboard for the whole team (main page of the webhook): a diagram of person cards -> Claude -> Gemini/ChatGPT/Gemma
// with moving light dots, an activity list, a 24-hour heat map, key numbers, an event stream and an hourly chart.
// Everything is drawn from /data (numbers sent up by the machines, no chat content or file names).
// window.OpsBoard.create(root, { viewerName }) -> { update(data) }
// opts.local: used by the single-machine page (web/index.html), where each "person" is a session: button, cardLines(p), help
// Bảng điều khiển vận hành cả team (trang chính của webhook): sơ đồ thẻ nút người -> Claude -> Gemini/ChatGPT/Gemma
// có hạt sáng chạy, danh sách hoạt động, bản đồ nhiệt 24 giờ, chỉ số, luồng sự kiện, biểu đồ theo giờ.
// Toàn bộ vẽ từ /data (số liệu máy gửi lên, không có nội dung chat hay tên file).
// window.OpsBoard.create(gốc, { viewerName }) -> { update(dữ liệu) }
// opts.local: dùng cho trang trên một máy (web/index.html), mỗi "người" là một phiên: button, cardLines(p), help
;(function () {
  'use strict'
  const COLORS = { cyan: '#5ee6f0', purple: '#9b7bff', green: '#3df5a7', yellow: '#ffc24b', red: '#ff5a7a', muted: '#6f8d99', fg: '#cfe9ef' }
  const STATUS_INFO = {
    working: { name: tx('WORKING'), color: COLORS.green, label: 'b-ok' },
    waiting: { name: tx('WAITING'), color: COLORS.yellow, label: 'b-warn' },
    open: { name: tx('IDLE'), color: COLORS.cyan, label: 'b-info' },
    offline: { name: tx('OFFLINE'), color: '#3c5260', label: 'b-off' },
  }
  const HELPERS = [
    { name: 'GEMINI', color: '#5b8cff' },
    { name: 'CHATGPT', color: '#2fd39b' },
    { name: 'GEMMA', color: '#b07bff' },
  ]
  const STATUS_ORDER = { working: 0, waiting: 1, open: 2, offline: 3 }
  // claude-opus-5-5 -> Opus 5.5; a person's main model is the one with the most sessions
  // claude-opus-5-5 -> Opus 5.5; mô hình chính của một người là mô hình nhiều phiên nhất
  const modelName = id => {
    const m = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?/.exec(id || '')
    return m ? m[1][0].toUpperCase() + m[1].slice(1) + ' ' + m[2] + (m[3] ? '.' + m[3] : '') : id || ''
  }
  // helper assistants that are running: "general-purpose ×2, Explore"
  // trợ lý phụ đang chạy: "general-purpose ×2, Explore"
  const subagentNames = p => (p.subagents || []).map(a => a.name + (a.count > 1 ? ` ×${a.count}` : '')).join(', ')
  const mainModel = p => {
    const list = Object.entries(p.models || {}).sort((a, b) => b[1] - a[1])
    return list.length ? modelName(list[0][0]) : ''
  }
  // Fable costs about 2.5 times more than Opus: give it its own color so it stands out
  // Fable đắt hơn khoảng 2,5 lần Opus: tô màu riêng để dễ thấy
  const modelColor = name => (/^Fable|^Mythos/.test(name) ? COLORS.yellow : /^Opus/.test(name) ? COLORS.cyan : /^Sonnet/.test(name) ? COLORS.green : COLORS.muted)
  // help text for each panel (the "? Help" button toggles it; the ⓘ icon can always be hovered)
  // chú thích từng khung (nút "? Chú thích" bật/tắt; biểu tượng ⓘ luôn rê chuột xem được)
  const QUOTA_TAGS = { five_hour: tx('5H'), seven_day: tx('7D') }
  const HELP = {
    top: [tx('Overall status of the whole team.'),
      tx('NODES 3/5: 3 people have their computer on, out of 5 people.'),
      tx('ALL SYSTEMS NOMINAL: nobody is waiting, everything is normal.'),
      tx('2 AWAITING INPUT: Claude has stopped and is waiting for 2 people to reply.')],
    models: [tx('AI models the whole team is using.'),
      tx('Claude: how many people have a session open with each model. Fable (yellow) is the strongest but costs about 2.5 times more than Opus.'),
      tx('Gemma: size of the model installed on each person\'s computer (26b is the strongest, e4b and e2b are lighter) and how many people have it.'),
      tx('ChatGPT, Gemini: the model that last replied on each person\'s computer (for example gpt-6.1-sol, Gemini 3.8 Flash); "not used" means it is installed but has never been given a task.'),
      tx('"Unknown": the computer runs an old plugin version and has not sent this information.')],
    ops: [tx('List of the whole team: who is doing what.'),
      tx('Green dot: that person\'s Claude is working.'),
      tx('Yellow dot: Claude is waiting for that person to reply.'),
      tx('Light blue dot: Claude is open but idle.'),
      tx('Grey dot: the computer is off or offline.'),
      tx('% number: that person\'s share of what the whole team spent today.'),
      tx('5H / 7D (next to the %): how much of the subscription quota that person\'s Claude account has used in the 5-hour / 7-day window; at 100% they must wait for it to reset. Yellow from 60%, red from 80%. Hover to see the reset time.'),
      tx('Click a name to see details.')],
    graph: [tx('Diagram of who is working with whom.'),
      tx('Left column is each person, the middle box is Claude, the right column is the 3 helper AI assistants (Gemini, ChatGPT, Gemma).'),
      tx('Bright line with a moving dot: working, or asking that assistant for help.'),
      tx('Dashed, faded line: idle.'),
      tx('Click a person\'s box to see that person\'s numbers.'),
      tx('View mode button at the bottom left: Default (flat), 2.5D (tilted back), 3D (drag to rotate the view, scroll to zoom in).'),
      tx('Clock button (replay): drag the time bar to see who was working over the past 24 hours and who asked which assistant; ▶ to play, LIVE to return to now.'),
      tx('Zoom in / out like a map: scroll the mouse (or pinch with 2 fingers on a touchpad), double-click to zoom in, drag to move; the ◎ button in the corner fits everything back in view.'),
      tx('The same row of buttons at the bottom right: full screen, and open the diagram in its own window.')],
    heat: [tx('Who used the most, and at what hour, over the past 24 hours.'),
      tx('Each row is a person, each cell is an hour; the far right is the current hour.'),
      tx('The brighter and more purple a cell, the more was used that hour.'),
      tx('Faded cell: not used that hour.')],
    vitals: [tx('Main numbers for today.'),
      tx('RUNNING: people working / people with their computer on.'),
      tx('WAITING: people Claude is waiting on for a reply.'),
      tx('COST TODAY: total spent by the whole team today (converted at API prices).'),
      tx('TOKENS IN: amount of text sent to Claude to read today (a token is a unit for counting text, M = million).'),
      tx('Small line under each box: recent trend.')],
    tele: [tx('Usage of each kind of AI.'),
      tx('CLAUDE · COST LAST HOUR: money (converted at API prices) the whole team spent on Claude in the last 1 hour; the line below is each hour over the past 24 hours.'),
      tx('GEMINI / CHATGPT / GEMMA · TASKS TODAY: how many tasks Claude gave each assistant today; the line below is tasks per hour.'),
      tx('Zero means nobody asked that assistant today.')],
    events: [tx('Log of what just happened, newest on top.'),
      tx('SUCCESS: someone started working, or an assistant finished a task.'),
      tx('WARNING: Claude is waiting for someone to reply.'),
      tx('HAND-OFF: Claude just asked an AI assistant to do something.'),
      tx('INFO: other information (idle, opened the page...).'),
      tx('Only recorded since you opened this page; reloading starts the log again.')],
    env: [tx('Trends over the past 24 hours.'),
      tx('Light blue line: money the whole team spends each hour.'),
      tx('Purple line: how many people use Claude each hour.'),
      tx('ONLINE: what % of people have their computer on.'),
      tx('RUNNING: of those with their computer on, what % are working.'),
      tx('AI HAND-OFF: of those with their computer on, what % are asking an AI assistant for help.')],
  }
  const p2 = n => String(n).padStart(2, '0')
  const makeSvg = (name, attrs) => {
    const n = document.createElementNS('http://www.w3.org/2000/svg', name)
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v)
    return n
  }
  // simplified outline of Vietnam, only to show where branches are (longitude, latitude), not a surveying map
  // đường viền Việt Nam giản lược, để minh hoạ vị trí chi nhánh (kinh độ, vĩ độ), không dùng làm bản đồ đo đạc
  const compact = n => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'K' : String(Math.round(n)))
  const compactMoney = d => (d >= 1e6 ? (d / 1e6).toFixed(2).replace('.', ',') + 'tr' : d >= 1e3 ? Math.round(d / 1e3) + 'k' : Math.round(d) + '') + ' đ' // i18n-allow
  const money = (usd, rate) => (I18n.lang === 'vi' ? compactMoney(usd * rate) : '$' + usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
  const countPeople = n => (n === 1 ? tx('{n} person', { n }) : tx('{n} people', { n }))
  const countSessions = n => (n === 1 ? tx('{n} session', { n }) : tx('{n} sessions', { n }))
  const hourNow = () => {
    const d = new Date()
    return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
  }
  function o(tag, cls, text) {
    const e = document.createElement(tag)
    if (cls) e.className = cls
    if (text !== undefined) e.textContent = text
    return e
  }
  // size the canvas to the screen's pixel density; returns the scaled context and the CSS size
  // canvas theo mật độ điểm ảnh của màn hình; trả về ngữ cảnh đã co giãn và kích thước CSS
  function fit(c) {
    const r = window.devicePixelRatio || 1
    const w = c.clientWidth
    const h = c.clientHeight
    if (c.width !== Math.round(w * r) || c.height !== Math.round(h * r)) {
      c.width = Math.round(w * r)
      c.height = Math.round(h * r)
    }
    const g = c.getContext('2d')
    g.setTransform(r, 0, 0, r, 0, 0)
    return { g, w, h }
  }
  function roundRect(g, x, y, w, h, r) {
    g.beginPath()
    g.moveTo(x + r, y)
    g.arcTo(x + w, y, x + w, y + h, r)
    g.arcTo(x + w, y + h, x, y + h, r)
    g.arcTo(x, y + h, x, y, r)
    g.arcTo(x, y, x + w, y, r)
    g.closePath()
  }
  function spark(c, data, color, area) {
    const { g, w, h } = fit(c)
    g.clearRect(0, 0, w, h)
    if (!data.length) return
    const max = Math.max(...data, 1e-9)
    const pts = data.map((v, i) => [(i / Math.max(data.length - 1, 1)) * w, h - 2 - (v / max) * (h - 4)])
    g.beginPath()
    pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)))
    g.strokeStyle = color
    g.lineWidth = 1.6
    g.shadowColor = color
    g.shadowBlur = 6
    g.stroke()
    g.shadowBlur = 0
    if (area) {
      g.lineTo(w, h)
      g.lineTo(0, h)
      g.closePath()
      const gr = g.createLinearGradient(0, 0, 0, h)
      gr.addColorStop(0, color + '55')
      gr.addColorStop(1, color + '00')
      g.fillStyle = gr
      g.fill()
    }
  }

  // floating help box: clicking the ⓘ button shows it next to the button, clicking again / outside / Esc hides it
  // ô chú thích nổi: bấm nút ⓘ thì hiện cạnh nút, bấm lại / bấm ra ngoài / Esc thì ẩn
  const pop = o('div', 'o-pop')
  pop.hidden = true
  pop.setAttribute('role', 'tooltip')
  let popButton = null
  function closePopup() {
    pop.hidden = true
    if (popButton) popButton.classList.remove('on')
    popButton = null
  }
  function openPopup(button, key) {
    if (popButton === button) return closePopup()
    closePopup()
    popButton = button
    button.classList.add('on')
    // first line: what this panel is for; the next lines: each number
    // dòng đầu: khung này để làm gì; các dòng sau: từng con số
    const [head, ...y] = HELP[key]
    const ul = o('ul')
    for (const lines of y) ul.append(o('li', '', lines))
    pop.replaceChildren(o('b', '', head), ul)
    pop.hidden = false
    const r = button.getBoundingClientRect()
    const w = Math.min(320, window.innerWidth - 24)
    pop.style.width = w + 'px'
    pop.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + window.scrollX + 'px'
    const bottom = r.bottom + 10
    pop.style.top = bottom + window.scrollY + 'px'
    // if there is not enough room below, show it above the button
    // không đủ chỗ phía dưới thì hiện lên trên nút
    const height = pop.offsetHeight
    if (bottom + height > window.innerHeight - 8) pop.style.top = r.top - height - 10 + window.scrollY + 'px'
  }
  document.addEventListener('click', e => {
    if (popButton && !pop.contains(e.target) && !popButton.contains(e.target)) closePopup()
  })
  document.addEventListener('keydown', e => e.key === 'Escape' && closePopup())
  window.addEventListener('resize', closePopup)
  window.addEventListener('scroll', closePopup, true)
  function helpButton(key) {
    const i = o('button', 'o-i', 'i')
    i.type = 'button'
    i.setAttribute('aria-label', tx('Explain'))
    i.addEventListener('click', e => {
      e.stopPropagation()
      openPopup(i, key)
    })
    return i
  }
  // panel title with an ⓘ button
  // tiêu đề khung kèm nút ⓘ
  function heading(text, key, subtitleText) {
    const h = o('h3', '', text)
    if (subtitleText) h.append(o('small', '', subtitleText))
    h.append(helpButton(key))
    return [h]
  }

  function create(root, opts) {
    opts = opts || {}
    const M = opts.local || null
    if (M && M.help) Object.assign(HELP, M.help)
    root.replaceChildren()
    // ---- panels ----
    // ---- các khung ----
    const top = o('div', 'panel o-top')
    const dots = o('div', 'o-dots')
    dots.append(o('i'), o('i'), o('i'))
    const live = o('span', 'o-pill')
    live.append(o('b'), 'SYSTEM LIVE')
    const title = o('div', 'o-title')
    const brand = o('div')
    brand.append('AI WORKER', o('span', 'o-title-more', ' // AGENT OPERATIONS MATRIX'))
    title.append(brand, o('small', '', 'ORCHESTRATION · TELEMETRY · CONTROL'))
    const right = o('div', 'o-right')
    const nodes = o('span')
    const statusEl = o('span', 'o-pill')
    const clock = o('span', 'o-clock')
    const boardLink = o('a', 'o-btn', tx('Detail board'))
    boardLink.href = '/board'
    const form = o('form')
    form.method = 'post'
    form.action = '/logout'
    form.style.margin = '0'
    form.append(o('button', 'o-btn', tx('Sign out') + (opts.viewerName ? ` (${opts.viewerName})` : '')))
    if (M) {
      right.append(nodes, statusEl, helpButton('top'), clock, I18n.switcher(), ...(M.button || []).map(n => {
        const b = o(n.href ? 'a' : 'button', 'o-btn', n.text)
        if (n.href) {
          b.href = n.href
          b.target = '_blank'
          b.rel = 'noopener'
        } else {
          b.type = 'button'
          b.addEventListener('click', n.onClick)
        }
        return b
      }))
    } else if (new URLSearchParams(location.search).get('frame') === 'wall' || document.body.dataset.role === 'wall') {
      // wall display: no text board. Full screen needs one click; a touch TV has no Esc key, so the button toggles it
      // treo tường: không có bảng chữ. Toàn màn hình cần một lần bấm; TV cảm ứng không có phím Esc nên nút bật tắt được
      const fullscreenButton = o('button', 'o-btn', tx('⛶ Full screen'))
      fullscreenButton.type = 'button'
      fullscreenButton.addEventListener('click', () => {
        (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => {})
      })
      document.addEventListener('fullscreenchange', () => {
        fullscreenButton.textContent = document.fullscreenElement ? tx('⛶ Exit full screen') : tx('⛶ Full screen')
      })
      // a wall account signs out completely; an admin trying it in this tab just goes back to the normal board
      // tài khoản treo tường thì đăng xuất hẳn; quản trị mở thử ở tab này thì chỉ về bảng thường
      const wallOnly = document.body.dataset.role === 'wall'
      const exitButton = o('button', 'o-btn', tx('Exit'))
      exitButton.type = 'button'
      form.hidden = true
      exitButton.addEventListener('click', () => {
        if (!wallOnly) return void (location.href = '/')
        if (confirm(tx('Leave this screen? To come back you must enter an OTP code or have an admin approve it again.'))) form.submit()
      })
      const reloadButton = o('button', 'o-btn', tx('Reload'))
      reloadButton.type = 'button'
      reloadButton.dataset.reload = ''
      reloadButton.addEventListener('click', () => location.reload())
      right.append(nodes, statusEl, clock, I18n.switcher(), fullscreenButton, reloadButton, exitButton, form)
      // the browser only allows full screen after a person acts on this very machine: the first touch or key press is used for that.
      // if it was opened in kiosk mode the window already fills the screen, so no reminder is needed.
      // reloading while in full screen: the new page runs while the window is still full, then the browser leaves full screen, so check again when the window is resized
      // trình duyệt chỉ cho vào toàn màn hình khi có người thao tác trên chính máy này: lần chạm hoặc bấm phím đầu tiên dùng cho việc đó.
      // đã mở bằng chế độ kiosk thì cửa sổ vốn kín màn hình, không cần nhắc.
      // tải lại lúc đang toàn màn hình: trang mới chạy khi cửa sổ còn kín rồi trình duyệt mới thoát ra, nên phải xét lại khi cửa sổ đổi cỡ
      let hinted = false
      const checkKiosk = () => {
        // only used to drop the reminder, not to hide the button: a full-screen Safari window is as tall as the screen even though it still has a toolbar
        // chỉ dùng để bỏ dòng nhắc, không ẩn nút: cửa sổ Safari toàn màn hình cũng cao bằng màn hình dù vẫn còn thanh công cụ
        const kiosk = innerHeight >= screen.height - 2 && !document.fullscreenElement
        if (hinted || kiosk || document.fullscreenElement || !document.fullscreenEnabled) return
        hinted = true
        const hint = o('div', 'o-fullscreen-hint', tx('Touch or press any key for full screen'))
        document.body.append(hint)
        const done = () => {
          hint.remove()
          document.removeEventListener('click', onTouch, true)
          document.removeEventListener('keydown', onKey, true)
        }
        const tokensIn = e => {
          e.preventDefault()
          e.stopPropagation()
          done()
          document.documentElement.requestFullscreen().catch(() => {})
        }
        // the buttons in the top bar still work right away, especially Exit
        // nút trên thanh đầu vẫn bấm được ngay, nhất là nút Thoát
        const onTouch = e => {
          if (!e.target.closest('.o-top button, dialog')) tokensIn(e)
          else done()
        }
        const onKey = e => {
          if (e.key !== 'Escape' && !/^(Tab|Shift|Control|Alt|Meta)$/.test(e.key)) tokensIn(e)
        }
        document.addEventListener('click', onTouch, true)
        document.addEventListener('keydown', onKey, true)
      }
      checkKiosk()
      addEventListener('resize', checkKiosk)
      document.addEventListener('fullscreenchange', checkKiosk)
    } else {
      const wallLink = o('a', 'o-btn', tx('Wall display'))
      wallLink.href = '/?frame=wall'
      wallLink.target = '_blank'
      wallLink.rel = 'noopener'
      const adminButton = o('a', 'o-btn', tx('Admin'))
      adminButton.href = '/admin'
      right.append(nodes, statusEl, helpButton('top'), clock, I18n.switcher(), wallLink, boardLink, ...(document.body.dataset.role === 'admin' ? [adminButton] : []), form)
    }
    top.append(dots, live, title, right)

    const left = o('div', 'panel o-left')
    const list = o('div', 'o-list')
    const lfoot = o('div', 'o-foot')
    const modelList = o('div', 'o-models')
    left.append(...heading('Active operations', 'ops', M ? tx('whole session') : tx('today')), list, lfoot, ...heading(M ? 'Models & quota' : 'Models in use', 'models'), modelList)

    const graph = o('div', 'panel o-graph')
    const gcv = o('canvas')
    const hoverCard = o('div')
    hoverCard.id = 'o-card'
    const mapBox = o('div', 'o-map')
    hoverCard.hidden = true
    const cardCloseButton = o('button', 'o-card-close', '×')
    cardCloseButton.type = 'button'
    cardCloseButton.title = tx('Close (Esc)')
    cardCloseButton.setAttribute('aria-label', tx('Close'))
    cardCloseButton.addEventListener('click', () => (hoverCard.hidden = true))
    // drag the card with the mouse or touch, never outside the frame; the position is kept until the page is reloaded.
    // the ratio is measured directly because the wall display's zoom makes 1 CSS px differ from 1 screen px, and each browser reports sizes differently
    // kéo thẻ bằng chuột hoặc cảm ứng, không ra ngoài khung; vị trí giữ tới khi tải lại trang.
    // tỉ lệ đo trực tiếp vì zoom của màn treo tường làm 1px CSS khác 1px màn hình, và mỗi trình duyệt báo cỡ khác nhau
    const placeCard = (x, y) => {
      const r = hoverCard.getBoundingClientRect()
      const k = graph.getBoundingClientRect()
      hoverCard.style.right = 'auto'
      hoverCard.style.left = hoverCard.style.top = '0'
      const origin = hoverCard.getBoundingClientRect()
      hoverCard.style.left = '100px'
      const ratio = (hoverCard.getBoundingClientRect().left - origin.left) / 100 || 1
      hoverCard.style.left = (Math.max(k.left, Math.min(x, k.right - r.width)) - origin.left) / ratio + 'px'
      hoverCard.style.top = (Math.max(k.top, Math.min(y, k.bottom - r.height)) - origin.top) / ratio + 'px'
    }
    const keepCardInside = () => {
      if (hoverCard.hidden || !hoverCard.style.left) return
      const r = hoverCard.getBoundingClientRect()
      placeCard(r.left, r.top)
    }
    let cardDrag = null
    hoverCard.addEventListener('pointerdown', e => {
      if (e.button || e.target.closest('button')) return
      const r = hoverCard.getBoundingClientRect()
      cardDrag = { id: e.pointerId, x: e.clientX - r.left, y: e.clientY - r.top }
      hoverCard.setPointerCapture(e.pointerId)
      hoverCard.classList.add('dragging')
    })
    hoverCard.addEventListener('pointermove', e => {
      if (cardDrag && e.pointerId === cardDrag.id) placeCard(e.clientX - cardDrag.x, e.clientY - cardDrag.y)
    })
    const dropCard = () => {
      cardDrag = null
      hoverCard.classList.remove('dragging')
    }
    hoverCard.addEventListener('pointerup', dropCard)
    hoverCard.addEventListener('pointercancel', dropCard)
    addEventListener('resize', keepCardInside)
    // map-style zoom: mouse wheel, drag, double-click, or the buttons in the corner
    // phóng to / thu nhỏ kiểu bản đồ: lăn chuột, kéo, nhấp đúp, hoặc các nút ở góc
    const zoomBar = o('div', 'o-zoom')
    const zoomButton = (text, buttonTitle, tasks) => {
      const b = o('button', 'o-btn', text)
      b.type = 'button'
      b.title = buttonTitle
      b.addEventListener('click', tasks)
      zoomBar.append(b)
    }
    // view modes in one menu button: Default (flat), 2.5D (tilted, grid floor), 3D (free rotation); remembered per browser
    // chế độ xem trong một nút menu: Mặc định (phẳng), 2.5D (nghiêng, nền lưới), 3D (xoay tự do); nhớ theo trình duyệt
    const stage = o('div', 'o-stage')
    stage.append(gcv, mapBox)
    const modeBar = o('div', 'o-mode-bar')
    const MODES = [['default', tx('Default')], ['2.5d', '2.5D'], ['3d', '3D'], ...(M ? [] : [['map', tx('Map')]])]
    const wallMode = !M && (new URLSearchParams(location.search).get('frame') === 'wall' || document.body.dataset.role === 'wall')
    // only used to hide buttons; the server itself refuses write actions from anyone who is not an admin
    // chỉ để bớt nút; máy chủ tự từ chối thao tác ghi của người không phải quản trị
    const isAdmin = !M && document.body.dataset.role === 'admin'
    let mode = 'default'
    let tilted = false
    try {
      const saved = localStorage.getItem('ops-mode')
      if (MODES.some(([k]) => k === saved)) mode = saved
    } catch {
      // no localStorage: use the default
      // không có localStorage: dùng mặc định
    }
    const menuButton = o('button', 'o-btn o-menu-button')
    menuButton.type = 'button'
    menuButton.setAttribute('aria-haspopup', 'menu')
    menuButton.title = tx('View mode')
    const menu = o('div', 'o-menu')
    menu.hidden = true
    menu.setAttribute('role', 'menu')
    menu.setAttribute('aria-label', tx('View mode'))
    menu.append(o('div', 'o-menu-title', tx('View mode')))
    const closeMenu = MODES.map(([k, text]) => {
      const b = o('button', 'o-menu-item', text)
      b.type = 'button'
      b.setAttribute('role', 'menuitemradio')
      b.addEventListener('click', () => {
        menu.hidden = true
        setMode(k)
      })
      menu.append(b)
      return [b, k]
    })
    menuButton.addEventListener('click', e => {
      e.stopPropagation()
      menu.hidden = !menu.hidden
    })
    addEventListener('click', e => {
      if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true
    })
    addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        menu.hidden = true
        hoverCard.hidden = true
      }
    })
    modeBar.append(menu, menuButton)
    function setMode(k) {
      mode = k
      tilted = k === '2.5d'
      stage.classList.toggle('tilted', tilted)
      stage.classList.toggle('three-d', k === '3d')
      stage.classList.toggle('map', k === 'map')
      if (k === 'map') drawMap()
      else for (const r of Object.values(mapViews)) r.draw.show(false)
      // stacked-layers icon (like the layer button in Google Maps) + the name of the selected mode
      // biểu tượng lớp xếp chồng (như nút đổi lớp bản đồ của Google Maps) + tên chế độ đang chọn
      menuButton.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z"/></svg>'
      menuButton.append(' ' + (MODES.find(([m]) => m === k) || MODES[0])[1] + ' ▾')
      for (const [b, m] of closeMenu) b.setAttribute('aria-checked', String(m === k))
      try {
        localStorage.setItem('ops-mode', k)
      } catch {
        // the browser blocks storage: nothing to save
        // trình duyệt chặn lưu trữ: không lưu được
      }
      if (k === '3d') enable3d()
      else if (view3d) view3d.show(false)
    }
    // full screen button and open the diagram in its own window, in the same row as the zoom buttons
    // nút toàn màn hình và mở sơ đồ trong cửa sổ riêng, cùng dãy với các nút phóng to / thu nhỏ
    const diagramOnly = new URLSearchParams(location.search).get('frame') === 'diagram'
    if (diagramOnly) {
      document.body.classList.add('o-diagram')
      document.title = tx('AI Worker · Diagram')
    }
    // Material-style icons (like Google Meet): full screen, open a new window
    // biểu tượng kiểu Material (như Google Meet): toàn màn hình, mở cửa sổ mới
    const ICON = {
      replay: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/></svg>',
      full: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>',
      newWindow: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>',
    }
    const actionButton = (text, buttonTitle, tasks) => {
      const b = o('button', 'o-btn')
      b.innerHTML = ICON[text]
      b.type = 'button'
      b.title = buttonTitle
      b.setAttribute('aria-label', buttonTitle)
      b.addEventListener('click', tasks)
      b.dataset.action = ''
      zoomBar.append(b)
    }
    if (!M) actionButton('replay', tx('Replay last 24 hours'), () => (replay.on ? stopReplay() : startReplay()))
    if (document.fullscreenEnabled)
      actionButton('full', tx('Full screen'), () => (document.fullscreenElement ? document.exitFullscreen() : graph.requestFullscreen()).catch(() => {}))
    if (!diagramOnly && !M)
      actionButton('newWindow', tx('Open in new window'), () => {
        const width = Math.min(1400, screen.availWidth - 40)
        const height = Math.min(880, screen.availHeight - 60)
        window.open('/?frame=diagram', 'ai-worker-diagram', `popup,width=${width},height=${height}`)
      })
    const replayBar = o('div', 'o-replay')
    replayBar.hidden = true
    const replayPlay = o('button', 'o-btn', '▶')
    replayPlay.type = 'button'
    replayPlay.title = tx('Play')
    const replaySlider = o('input')
    replaySlider.type = 'range'
    replaySlider.setAttribute('aria-label', tx('Replay time'))
    const replayTime = o('span', 'o-replay-time')
    const replayLive = o('button', 'o-btn', 'LIVE')
    replayLive.type = 'button'
    replayLive.title = tx('Back to now')
    replayBar.append(replayPlay, replaySlider, replayTime, replayLive)
    graph.append(...heading('Neural workflow / live execution graph', 'graph'), stage, hoverCard, replayBar, modeBar, zoomBar)

    const col = o('div', 'o-col o-r')
    const heat = o('div', 'panel o-heat')
    const hcv = o('canvas')
    const hfoot = o('div', 'o-foot')
    hfoot.append(o('span', '', '−24H'), o('span', '', M ? tx('ACTIVITY PER HOUR') : tx('COST PER HOUR')), o('span', '', 'NOW'))
    heat.append(...heading(M ? 'Session load map' : 'Team load map', 'heat', '24h'), hcv, hfoot)
    const vitals = o('div', 'panel o-vitals')
    const tiles = o('div', 'o-tiles')
    const tile = (label, color) => {
      const t = o('div', 'o-tile')
      const s = o('strong')
      s.style.color = color
      const c = o('canvas')
      t.append(o('small', '', label), s, c)
      tiles.append(t)
      return { s, c, color }
    }
    const vRun = tile('RUNNING', COLORS.green)
    const vWait = tile('WAITING', COLORS.yellow)
    const vCost = tile('COST TODAY', COLORS.cyan)
    const vTok = tile('TOKENS IN', COLORS.purple)
    vitals.append(...heading('System vitals', 'vitals'), tiles)
    const ringPanel = o('div', 'panel o-ring')
    const ringRow = o('div', 'o-ring-row')
    ringPanel.append(...heading('Quota & load', 'vitals'), ringRow)
    col.append(heat, ringPanel, vitals)

    const tele = o('div', 'panel o-tele')
    const miniTiles = o('div', 'o-tiles')
    const miniTile = (label, color) => {
      const t = o('div', 'o-tile')
      const s = o('strong')
      s.style.color = color
      const c = o('canvas')
      t.append(o('small', '', label), s, c)
      miniTiles.append(t)
      return { s, c, color }
    }
    const claudeTile = miniTile(wallMode ? tx('CLAUDE · LAST HOUR') : tx('CLAUDE · COST LAST HOUR'), COLORS.cyan)
    const aiTiles = HELPERS.map(a => miniTile(wallMode ? tx('{name} · TASKS', { name: a.name }) : tx('{name} · TASKS TODAY', { name: a.name }), a.color))
    tele.append(...heading('Model telemetry', 'tele', '24h'), miniTiles)

    const evp = o('div', 'panel o-events')
    const ev = o('div', 'o-ev')
    evp.append(...heading('Real-time diagnostics / event stream', 'events'), ev)

    const env = o('div', 'panel o-env')
    const ecv = o('canvas')
    const leg = o('div', 'o-legend')
    const l1 = o('span', '', 'COST / H')
    l1.prepend(Object.assign(o('i'), { style: `background:${COLORS.cyan}` }))
    const l2 = o('span', '', M ? 'ACTIVE SESSIONS' : 'ACTIVE MEMBERS')
    l2.prepend(Object.assign(o('i'), { style: `background:${COLORS.purple}` }))
    leg.append(l1, l2)
    const ebars = o('div')
    ebars.style.marginTop = '8px'
    const ebar = label => {
      const r = o('div', 'o-row')
      r.style.cursor = 'default'
      r.style.padding = '3px 0'
      r.style.borderBottom = '0'
      const n = o('span', 'n', label)
      const p = o('span', 'p')
      const b = o('div', 'bar')
      const i = o('i')
      b.append(i)
      r.append(o('span'), n, p, b)
      ebars.append(r)
      return { p, i }
    }
    const barOnline = ebar('ONLINE')
    const barRunning = ebar('RUNNING')
    const barAi = ebar('AI HAND-OFF')
    env.append(...heading('Performance envelope', 'env', '24h'), ecv, leg, ebars)

    root.append(top, left, graph, col, tele, evp, env)
    document.body.append(pop)

    // ---- state ----
    // ---- trạng thái ----
    let snapshot = null
    let people = []
    let selected = -1
    const events = []
    let previous = null
    const history = { working: [], waiting: [] }
    let rects = []
    // view of the diagram: s = zoom, (x, y) = shift; free = the viewer has zoomed or dragged by hand (no longer auto-fit)
    // khung nhìn của sơ đồ: s = độ phóng, (x, y) = dịch; tuDo = người xem đã tự phóng/kéo (không tự vừa khung nữa)
    const view = { s: 1, x: 0, y: 0, free: false, fit: 1 }
    const zoom = (k, cx, cy) => {
      const s2 = Math.min(3, Math.max(0.25, view.s * k))
      view.x = cx - ((cx - view.x) * s2) / view.s
      view.y = cy - ((cy - view.y) * s2) / view.s
      view.s = s2
      view.free = true
    }
    const center = () => [gcv.clientWidth / 2, gcv.clientHeight / 2]
    // ---- 3D: load three.js and ops3d.js on first use (whoever does not use 3D does not download ~2 MB) ----
    // ---- 3D: tải three.js và ops3d.js khi chọn lần đầu (ai không dùng 3D thì không phải tải ~2 MB) ----
    let view3d = null
    let loading3d = null
    function enable3d() {
      if (view3d) return view3d.show(true)
      if (loading3d) return
      const waiting = o('div', 'o-load3d', tx('Loading 3D…'))
      stage.append(waiting)
      const scriptSrc = (document.querySelector('script[src*="ops.js"]') || {}).src || 'ops.js'
      const loadScript = name => new Promise((ok, reject) => {
        const sc = document.createElement('script')
        sc.src = scriptSrc.replace('ops.js', name)
        sc.onload = ok
        sc.onerror = reject
        document.head.append(sc)
      })
      loading3d = (window.THREE ? Promise.resolve() : loadScript('three.js'))
        .then(() => (window.Ops3D ? 0 : loadScript('ops3d.js')))
        .then(() => {
          view3d = window.Ops3D.create(stage, {
            people: drawPeople, card, HELPERS, STATUS_INFO, mainModel: mainModel, compact,
            selected: i => selectPerson(i), selectedIndex: () => selected,
          })
          view3d.show(mode === '3d')
        })
        .catch(() => {
          waiting.textContent = tx('Could not load 3D (this device or browser does not support WebGL). Choose Default or 2.5D.')
          loading3d = null
          return
        })
        .then(() => waiting.textContent === tx('Loading 3D…') && waiting.remove())
    }
    // ---- replay of the last 24 hours: the server records every time a person's status changes (/history) ----
    // ---- tua lại 24 giờ: máy chủ ghi mỗi lần trạng thái một người đổi (/history) ----
    const replay = { on: false, t: 0, from: 0, to: 0, byPerson: new Map(), timer: null, fetchFn: null }
    function drawPeople() {
      if (!replay.on) return people
      return people.map(p => {
        const list = replay.byPerson.get(p.name + '|' + p.account) || []
        let st = null
        for (const d of list) {
          if (d.at > replay.t) break
          st = d
        }
        return st ? { ...p, status: st.status, delegating: st.delegating } : { ...p, status: 'offline', delegating: [0, 0, 0] }
      })
    }
    // point on the screen -> coordinates in the canvas; when tilted, project back through the CSS 3D transform
    // điểm trên màn hình -> toạ độ trong canvas; khi nghiêng thì chiếu ngược qua phép biến đổi 3D của CSS
    function pointOf(cx, cy) {
      const r = stage.getBoundingClientRect()
      const qx = cx - r.left
      const qy = cy - r.top
      const style = getComputedStyle(gcv)
      if (!tilted || style.transform === 'none') return [qx, qy]
      const [ox, oy] = style.transformOrigin.split(' ').map(parseFloat)
      const inv = new DOMMatrix(style.transform).inverse()
      const a = inv.transformPoint(new DOMPoint(qx - ox, qy - oy, 0, 1))
      const b = inv.transformPoint(new DOMPoint(qx - ox, qy - oy, 1, 1))
      const A = [a.x / a.w, a.y / a.w, a.z / a.w]
      const B = [b.x / b.w, b.y / b.w, b.z / b.w]
      const t = B[2] === A[2] ? 0 : -A[2] / (B[2] - A[2])
      return [A[0] + t * (B[0] - A[0]) + ox, A[1] + t * (B[1] - A[1]) + oy]
    }
    zoomButton('−', tx('Zoom out'), () => (mode === '3d' && view3d ? view3d.zoom(0.8) : zoom(0.8, ...center())))
    zoomButton('+', tx('Zoom in'), () => (mode === '3d' && view3d ? view3d.zoom(1.25) : zoom(1.25, ...center())))
    zoomButton('◎', tx('Fit to view'), () => (mode === '3d' && view3d ? view3d.fit() : (view.free = false)))
    // order in the row: − + ◎ first, then full screen, then new window
    // thứ tự trong dãy: − + ◎ rồi mới tới toàn màn hình, cửa sổ mới
    zoomBar.append(...zoomBar.querySelectorAll('[data-action]'))
    gcv.addEventListener('wheel', e => {
      e.preventDefault()
      zoom(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), ...pointOf(e.clientX, e.clientY))
    }, { passive: false })
    let drag = null
    let justDragged = false
    gcv.addEventListener('pointerdown', e => {
      // phone: swipe scrolls the page, unless already zoomed in
      // điện thoại: vuốt để cuộn trang, trừ khi đã phóng to
      if (e.pointerType === 'touch' && !view.free) return
      const [lx, ly] = pointOf(e.clientX, e.clientY)
      drag = { x: e.clientX, y: e.clientY, lx, ly, vx: view.x, vy: view.y, id: e.pointerId }
      justDragged = false
    })
    addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return
      const dx = e.clientX - drag.x
      const dy = e.clientY - drag.y
      if (!justDragged && Math.hypot(dx, dy) < 4) return
      justDragged = true
      gcv.classList.add('dragging')
      const [lx, ly] = pointOf(e.clientX, e.clientY)
      view.x = drag.vx + lx - drag.lx
      view.y = drag.vy + ly - drag.ly
      view.free = true
    })
    addEventListener('pointerup', () => {
      drag = null
      gcv.classList.remove('dragging')
    })
    gcv.addEventListener('dblclick', e => {
      zoom(1.6, ...pointOf(e.clientX, e.clientY))
    })
    function updateReplay() {
      const d = new Date(replay.t)
      const hh = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
      const last = replay.to - replay.t < 60_000
      replayTime.textContent = last ? tx('NOW') : `${hh} · ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
      replayLive.classList.toggle('on', last)
      replaySlider.value = String(replay.t)
    }
    async function loadHistory() {
      try {
        const r = await fetch('/history', { cache: 'no-store', credentials: 'same-origin' })
        if (!r.ok) throw new Error(String(r.status))
        const d = await r.json()
        const atEnd = replay.to - replay.t < 60_000
        replay.from = d.since
        replay.to = d.now
        replay.byPerson = new Map()
        for (const x of (d.items || []).sort((a, b) => a.at - b.at)) {
          const k = x.name + '|' + (x.account || '')
          if (!replay.byPerson.has(k)) replay.byPerson.set(k, [])
          replay.byPerson.get(k).push(x)
        }
        replaySlider.min = String(replay.from)
        replaySlider.max = String(replay.to)
        replaySlider.step = '60000'
        if (atEnd || !replay.t) replay.t = replay.to
        updateReplay()
      } catch {
        replayTime.textContent = tx('Could not load history')
      }
    }
    function startReplay() {
      replay.on = true
      replayBar.hidden = false
      graph.classList.add('replaying')
      replay.t = 0
      loadHistory()
      replay.fetchFn = setInterval(loadHistory, 60_000)
    }
    function stopReplay() {
      replay.on = false
      replayBar.hidden = true
      graph.classList.remove('replaying')
      clearInterval(replay.fetchFn)
      stopPlayback()
    }
    function stopPlayback() {
      clearInterval(replay.timer)
      replay.timer = null
      replayPlay.textContent = '▶'
      replayPlay.title = tx('Play')
    }
    replaySlider.addEventListener('input', () => {
      stopPlayback()
      replay.t = +replaySlider.value
      updateReplay()
    })
    replayPlay.addEventListener('click', () => {
      if (replay.timer) return stopPlayback()
      if (replay.to - replay.t < 60_000) replay.t = replay.from
      replayPlay.textContent = '❚❚'
      replayPlay.title = tx('Pause')
      // the whole 24 hours play in about 30 seconds
      // cả 24 giờ phát trong khoảng 30 giây
      replay.timer = setInterval(() => {
        replay.t = Math.min(replay.to, replay.t + (replay.to - replay.from) / 300)
        updateReplay()
        if (replay.t >= replay.to) stopPlayback()
      }, 100)
    })
    replayLive.addEventListener('click', () => {
      stopPlayback()
      replay.t = replay.to
      updateReplay()
    })
    let prevCounts = null
    const stars = Array.from({ length: 70 }, () => [Math.random(), Math.random(), Math.random() * 1.4 + 0.4])

    function addEvent(label, text, color) {
      events.unshift({ t: hourNow(), label, text, color })
      if (events.length > 40) events.pop()
    }

    function update(d) {
      snapshot = d
      people = [...(d.people || [])].map((p, i) => ({ ...p, root: i })).sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name, I18n.locale))
      // events: compare the status with the previous time
      // sự kiện: so trạng thái với lần trước
      const current = {}
      for (const p of people) current[p.name + '|' + p.account] = { s: p.status, g: (p.delegating || []).map(v => v > 0) }
      if (!previous) {
        addEvent('b-info', `OPERATIONS MATRIX ONLINE · ${people.length} NODES`, COLORS.cyan)
        for (const p of people) if (p.status !== 'offline') addEvent(STATUS_INFO[p.status].label, `${p.name} · ${STATUS_INFO[p.status].name}`)
      } else {
        for (const p of people) {
          const k = p.name + '|' + p.account
          const a = previous[k]
          const b = current[k]
          if (!a) addEvent('b-info', `${p.name} · NODE JOINED`)
          else {
            if (a.s !== b.s) addEvent(STATUS_INFO[b.s].label, `${p.name} · ${STATUS_INFO[a.s].name} → ${STATUS_INFO[b.s].name}`)
            b.g.forEach((on, i) => {
              if (on && !a.g[i]) addEvent('b-ai', `${p.name} >> ${HELPERS[i].name} · HAND-OFF`)
              if (!on && a.g[i]) addEvent('b-ok', `${HELPERS[i].name} → ${p.name} · TASK COMPLETE`)
            })
          }
        }
      }
      previous = current
      const counts = { working: 0, waiting: 0, open: 0, offline: 0 }
      for (const p of people) counts[p.status]++
      history.working.push(counts.working)
      history.waiting.push(counts.waiting)
      for (const k of ['working', 'waiting']) if (history[k].length > 40) history[k].shift()
      prevCounts = counts
      drawStatic(counts)
      if (mode === 'map') drawMap()
      drawRings(counts)
    }

    // a person's highest quota if it is 95% or more, otherwise 0
    // hạn mức cao nhất của một người nếu từ 95%, không thì 0
    function nearQuotaLimit(p) {
      const height = Math.max(0, ...((p.quota && p.quota.windows) || []).map(c => c.pct))
      return height >= 95 ? Math.round(height) : 0
    }

    // gauge rings on the wall display: people working, and the team's highest quota for each window
    // vòng đo khi treo tường: người đang làm, và hạn mức cao nhất cả team theo từng khung
    function drawRings(counts) {
      const height = kind => Math.max(0, ...people.flatMap(p => ((p.quota && p.quota.windows) || []).filter(c => c.kind === kind).map(c => c.pct)))
      const online = people.length - counts.offline
      const levelColor = p => (p >= 95 ? COLORS.red : p >= 80 ? COLORS.yellow : COLORS.cyan)
      const list = [
        [tx('WORKING'), online ? Math.round((counts.working / online) * 100) : 0, `${counts.working}/${online}`, COLORS.green],
        [tx('HIGHEST 5H'), Math.round(height('five_hour')), '', 0],
        [tx('HIGHEST 7D'), Math.round(height('seven_day')), '', 0],
      ]
      ringRow.replaceChildren(...list.map(([label, pct, text, color]) => {
        const box = o('div')
        const m = color || levelColor(pct), R = 34, C = 2 * Math.PI * R
        const svg = makeSvg('svg', { viewBox: '0 0 84 84' })
        svg.append(
          makeSvg('circle', { cx: 42, cy: 42, r: R, fill: 'none', stroke: 'rgba(255,255,255,.08)', 'stroke-width': 7 }),
          makeSvg('circle', { cx: 42, cy: 42, r: R, fill: 'none', stroke: m, 'stroke-width': 7, 'stroke-linecap': 'round', 'stroke-dasharray': `${(Math.min(100, pct) / 100) * C} ${C}`, transform: 'rotate(-90 42 42)' }),
        )
        const t = makeSvg('text', { x: 42, y: 48, 'text-anchor': 'middle', fill: '#e8fbff', 'font-size': 17, 'font-weight': 700, 'font-family': 'ui-monospace,Menlo,Consolas,monospace' })
        t.textContent = text || `${pct}%`
        svg.append(t)
        box.append(svg, o('small', '', label))
        return box
      }))
    }

    // ---- branch map: machines are grouped by IP, a manager names each location once; no one's position is looked up ----
    // ---- bản đồ chi nhánh: máy tự gom theo IP, quản lý đặt tên mỗi địa điểm một lần; không tra vị trí từng người ----
    let teamOpen = false
    // the three map styles live in their own files and load only when opened; the frame is kept across redraws
    // ba kiểu bản đồ nằm ở file riêng, chỉ tải khi mở; giữ nguyên khung qua các lần vẽ lại
    const mapOverlay = o('div', 'o-bd-overlay')
    const mapViews = {}, loadingMaps = {}
    let newGroups = []
    // full screen for the whole diagram frame so the detail card stays visible; if the browser refuses, just cover the page
    // toàn màn hình cho cả khung sơ đồ để thẻ chi tiết vẫn hiện; trình duyệt không cho thì chỉ phủ kín trang
    const fullButton = o('button', 'zoom')
    fullButton.type = 'button'
    function setFullscreen(on) {
      graph.classList.toggle('bd-full', on)
      const label = on ? tx('Exit full screen (Esc)') : tx('Full screen')
      fullButton.title = label
      fullButton.setAttribute('aria-label', label)
      fullButton.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4"><path d="${on ? 'M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6' : 'M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6'}"/></svg>`
    }
    function exitFullscreen() {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
      setFullscreen(false)
    }
    fullButton.addEventListener('click', () => {
      if (graph.classList.contains('bd-full')) return exitFullscreen()
      graph.requestFullscreen?.()?.catch(() => {})
      setFullscreen(true)
    })
    setFullscreen(false)
    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement) setFullscreen(false)
    })
    addEventListener('keydown', e => {
      if (e.key === 'Escape' && graph.classList.contains('bd-full')) exitFullscreen()
    })
    const MAP_SCRIPTS = { flat: ['map2d.js', 'Map2D'], tilted: ['map25d.js', 'Map25D'], 'three-d': ['map3d.js', 'Map3D'] }
    function loadMapScript(name) {
      const root = (document.querySelector('script[src*="ops.js"]') || {}).src || 'ops.js'
      return new Promise((ok, reject) => {
        const sc = document.createElement('script')
        sc.src = root.replace('ops.js', name)
        sc.onload = ok
        sc.onerror = reject
        document.head.append(sc)
      })
    }
    function enableKind(k) {
      for (const [name, r] of Object.entries(mapViews)) {
        r.cls.hidden = name !== k
        r.draw.show(name === k && mode === 'map')
      }
      if (mapViews[k] || loadingMaps[k]) return
      loadingMaps[k] = true
      const waiting = o('div', 'o-load3d', tx('Loading map…'))
      mapOverlay.append(waiting)
      const [script, name] = MAP_SCRIPTS[k]
      ;(window.MapCommon ? Promise.resolve() : loadMapScript('map-common.js'))
        .then(() => (k === 'flat' || window.THREE ? 0 : loadMapScript('three.js')))
        .then(() => (window[name] ? 0 : loadMapScript(script)))
        .then(() => {
          const cls = o('div', 'bd-layer')
          mapOverlay.append(cls)
          const draw = window[name].create(cls, {
            wall: wallMode, STATUS_INFO, money: usd => money(usd, snapshot.usdRate || 26000),
            selected: id => {
              const n = newGroups.find(x => x.b.id === id)
              if (n) branchCard(n, snapshot.usdRate || 26000)
              const r = mapViews[mapKind]
              if (r) r.draw.flyTo(id)
            },
          })
          mapViews[k] = { cls, draw }
          waiting.remove()
          loadingMaps[k] = false
          drawMap()
        })
        .catch(() => {
          loadingMaps[k] = false
          waiting.remove()
          // if 3D cannot run, go back to 2D, the style that needs no WebGL
          // không chạy được 3D thì về 2D, là kiểu không cần WebGL
          if (k !== 'flat') { mapKind = 'flat'; drawMap() } else mapOverlay.append(o('div', 'o-load3d', tx('Could not load the map.')))
        })
    }
    let mapKind = 'three-d'
    try {
      const saved = localStorage.getItem('ops-map-kind')
      if (MAP_SCRIPTS[saved]) mapKind = saved
    } catch {
      // the browser blocks storage: use the default
      // trình duyệt chặn lưu trữ: dùng mặc định
    }

    // costs from the Team plan CSV file; uploading the file and marking the sales team are done on the admin page
    // chi phí từ file CSV của gói Team; nạp file và đánh dấu đội sale nằm ở trang quản trị
    function teamSection(rate) {
      const t = snapshot.team
      const box = o('div', 'o-bd-team')
      const usd = v => v.net || v.gross
      box.append(o('div', 'o-bd-title', tx('Cost outside the plugin (Team plan)')))
      const sale = t.items.filter(x => x.isSales)
      const period = t.dateFrom || t.dateTo ? `${t.dateFrom || '?'} → ${t.dateTo || '?'}` : tx('no period set')
      box.append(o('div', 'o-bd-row empty', tx('{period} · {people} · {amount}', { period, people: countPeople(t.items.length), amount: money(t.items.reduce((a, x) => a + usd(x.other), 0), rate) })))
      if (sale.length) box.append(o('div', 'o-bd-row empty', tx('Market sales: {people} · {amount}', { people: countPeople(sale.length), amount: money(sale.reduce((a, x) => a + usd(x.other), 0), rate) })))
      const details = document.createElement('details')
      details.open = teamOpen
      details.addEventListener('toggle', () => (teamOpen = details.open))
      const summaryEl = document.createElement('summary')
      summaryEl.textContent = tx('Each person')
      details.append(summaryEl)
      for (const x of t.items) {
        const h = o('div', 'o-bd-people')
        h.append(o('i'), o('span', '', x.email + (x.isSales ? ' · ' + tx('sales') : '') + (x.hasDevice ? '' : ' · ' + tx('plugin not installed'))), o('b', '', money(usd(x.other), rate)))
        details.append(h)
      }
      box.append(details)
      return box
    }

    function drawMap() {
      if (!snapshot) return
      // while a field is being filled in, do not redraw the right column, or the text being typed would be lost
      // đang điền dở thì không vẽ lại cột bên phải, nếu không ô đang gõ sẽ mất
      const typingTarget = document.activeElement
      const branches = snapshot.branches || []
      const groups = branches.map(b => {
        const members = people.filter(p => p.branch === b.id)
        const counts = k => members.filter(p => p.status === k).length
        const online = members.length - counts('offline')
        const critical = members.filter(nearQuotaLimit).length
        return {
          b, members, online, working: counts('working'), waiting: counts('waiting'), critical, usd: members.reduce((s, p) => s + p.usdToday, 0),
          color: critical ? COLORS.red : counts('waiting') ? COLORS.yellow : counts('working') ? COLORS.green : online ? COLORS.cyan : STATUS_INFO.offline.color,
        }
      })
      newGroups = groups
      const rate = snapshot.usdRate || 26000
      enableKind(mapKind)
      if (mapViews[mapKind]) mapViews[mapKind].draw.update(groups)
      if (mapBox.contains(typingTarget) && /^(SELECT|INPUT)$/.test(typingTarget.tagName) && typingTarget.type !== 'checkbox') return
      const mapList = o('div', 'o-bd-list')
      mapList.append(...groups.map(n => {
        const r = o('div', 'o-bd-row')
        const c = o('i')
        c.style.background = n.color
        c.style.boxShadow = `0 0 8px ${n.color}`
        r.append(c, o('span', '', n.b.name), o('span', '', money(n.usd, rate)))
        r.append(o('small', '', tx('{working} working · {waiting} waiting · {online}/{total} online', { working: n.working, waiting: n.waiting, online: n.online, total: n.members.length }) + (n.critical ? ' · ' + tx('⛔ {n} near quota limit', { n: n.critical }) : '')))
        r.addEventListener('click', () => {
          branchCard(n, rate)
          if (mapViews[mapKind]) mapViews[mapKind].draw.flyTo(n.b.id)
        })
        return r
      }))
      const unassigned = people.filter(p => !branches.some(b => b.id === p.branch))
      if (unassigned.length) mapList.append(o('div', 'o-bd-row empty', tx('Mobile / unassigned: {who}', { who: wallMode ? countPeople(unassigned.length) : unassigned.map(p => p.name).join(', ') })))
      // the wall display has no emails; naming is done on the admin page
      // màn hình treo tường không có email; việc đặt tên nằm ở trang quản trị
      if (isAdmin && !wallMode && (snapshot.unnamedGroups || []).length) {
        const a = o('a', 'o-bd-row empty o-bd-notice', tx('{n} unnamed computer groups → Admin', { n: snapshot.unnamedGroups.length }))
        a.href = '/admin'
        mapList.prepend(a)
      }
      if (!wallMode && snapshot.team) mapList.append(teamSection(rate))
      // the three map view styles, matching the three styles of the diagram
      // ba kiểu xem của bản đồ, giống ba kiểu của sơ đồ
      const kindBox = o('div', 'o-bd-kind')
      for (const [k, text] of [['flat', '2D'], ['tilted', '2.5D'], ['three-d', '3D']]) {
        const b = o('button', k === mapKind ? 'on' : '', text)
        b.type = 'button'
        b.setAttribute('aria-pressed', String(k === mapKind))
        b.addEventListener('click', () => {
          mapKind = k
          try {
            localStorage.setItem('ops-map-kind', k)
          } catch {
            // the browser blocks storage: nothing to save
            // trình duyệt chặn lưu trữ: không lưu được
          }
          drawMap()
        })
        kindBox.append(b)
      }
      for (const [text, label, working] of [['−', tx('Zoom map out'), r => r.draw.zoom(0.8)], ['+', tx('Zoom map in'), r => r.draw.zoom(1.25)], ['◎', tx('Show whole map'), r => r.draw.fit()]]) {
        const b = o('button', 'zoom', text)
        b.type = 'button'
        b.title = label
        b.setAttribute('aria-label', label)
        b.addEventListener('click', () => mapViews[mapKind] && working(mapViews[mapKind]))
        kindBox.append(b)
      }
      kindBox.append(fullButton)
      mapBox.replaceChildren(mapOverlay, mapList, kindBox)
      if (!branches.length) mapBox.append(o('div', 'o-bd-empty', isAdmin ? tx('No locations yet. Name the computer groups on the Admin page.') : tx('No locations yet.')))
    }
    function branchCard(n, rate) {
      hoverCard.replaceChildren(cardCloseButton, o('b', '', n.b.name), o('br'))
      for (const p of n.members) hoverCard.append(`${STATUS_INFO[p.status].name.padEnd(12)} ${p.name} · ${money(p.usdToday, rate)}`, o('br'))
      if (!n.members.length) hoverCard.append(tx('Nobody at this branch yet.'))
      hoverCard.hidden = false
      keepCardInside()
    }

    function drawStatic(counts) {
      const rate = snapshot.usdRate || 26000
      const online = people.length - counts.offline
      nodes.replaceChildren('NODES ', o('strong', '', `${online}/${people.length}`))
      statusEl.className = 'o-pill' + (counts.waiting ? ' warn' : '')
      statusEl.replaceChildren(o('b'), counts.waiting ? `${counts.waiting} AWAITING INPUT` : 'ALL SYSTEMS NOMINAL')
      // list
      // danh sách
      const maxUsd = Math.max(...people.map(p => p.usdToday), 1e-9)
      const totalUsd = people.reduce((a, p) => a + p.usdToday, 0)
      list.replaceChildren(
        ...people.map((p, i) => {
          const r = o('div', 'o-row' + (i === selected ? ' selected' : ''))
          const d = o('span', 'd')
          d.style.background = STATUS_INFO[p.status].color
          d.style.boxShadow = p.status === 'offline' ? 'none' : `0 0 8px ${STATUS_INFO[p.status].color}`
          const pct = totalUsd ? Math.round((p.usdToday / totalUsd) * 100) : 0
          const b = o('div', 'bar')
          const fill = o('i')
          fill.style.width = `${Math.max(2, (p.usdToday / maxUsd) * 100)}%`
          b.append(fill)
          const s = o('span', 's', `${STATUS_INFO[p.status].name} · `)
          const model = mainModel(p)
          if (model) {
            const t = o('b', '', model)
            t.style.color = modelColor(model)
            t.style.fontWeight = '600'
            s.append(t, ' · ')
          }
          s.append(money(p.usdToday, rate))
          const subagentText = subagentNames(p)
          const subagentTag = subagentText ? o('span', 's o-subagent', tx('ASSISTANTS · {list}', { list: subagentText })) : null
          // the account's Claude plan quota (5 hours / 7 days), compact on the right
          // hạn mức gói Claude của tài khoản (5 giờ / 7 ngày), gọn ở góc phải
          const h = o('span', 'h')
          for (const c of (p.quota && p.quota.windows) || []) {
            if (!QUOTA_TAGS[c.kind]) continue
            // from 80% add a ⚠ mark (95%: ⛔) so an account close to its quota is visible at a glance
            // từ 80% thêm dấu ⚠ (95%: ⛔) để nhìn lướt cũng thấy tài khoản sắp chạm hạn mức
            const v = o('b', '', `${c.pct >= 95 ? '⛔' : c.pct >= 80 ? '⚠' : ''}${QUOTA_TAGS[c.kind]} ${Math.round(c.pct)}%`)
            v.style.color = c.pct >= 80 ? COLORS.red : c.pct >= 60 ? COLORS.yellow : COLORS.muted
            if (c.resetsAt) v.title = (c.pct >= 80 ? tx('Near quota limit') + ' · ' : '') + tx('resets at {time}', { time: new Date(c.resetsAt).toLocaleString(I18n.locale, { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) })
            h.append(v)
          }
          const pc = o('span', 'p')
          pc.append(h, o('span', '', pct + '%'))
          r.append(d, o('span', 'n', p.name), pc, b, s)
          if (subagentTag) r.append(subagentTag)
          r.addEventListener('click', () => selectPerson(i))
          return r
        }),
      )
      const tasksToday = people.reduce((a, p) => a + p.tasks.reduce((x, y) => x + y, 0), 0)
      // single-machine page: each session's cost covers its whole life, while the "today" figure comes from the machine's hourly ledger (usdTodayTotal)
      // trang một máy: chi phí từng phiên là cả đời phiên, còn số "hôm nay" lấy từ sổ theo giờ của máy (du.usdNayTong)
      const usdToday = snapshot.usdTodayTotal ?? totalUsd
      lfoot.replaceChildren(o('span', '', 'AI TASKS '), o('b', '', String(tasksToday)), o('span', '', M ? tx('TODAY') + ' ' : 'TEAM '), o('b', '', money(usdToday, rate)))
      // models in use: Claude by person with an open session, Gemma by size, ChatGPT / Gemini by machine that has it installed
      // mô hình đang dùng: Claude theo người có phiên mở, Gemma theo cỡ, ChatGPT / Gemini theo máy có cài
      {
        const lines = []
        const claude = {}
        for (const p of people) for (const k of Object.keys(p.models || {})) (claude[modelName(k)] ??= new Set()).add(p.name)
        for (const [name, members] of Object.entries(claude).sort((a, b) => b[1].size - a[1].size)) lines.push(['Claude ' + name, (M ? countSessions(members.size) : countPeople(members.size)), modelColor(name)])
        const gemma = {}
        for (const p of people) for (const g of (p.assistants && p.assistants.gemma) || []) gemma[g] = (gemma[g] || 0) + 1
        for (const [g, n] of Object.entries(gemma)) lines.push(['Gemma ' + g.replace(/^gemma\d*:/, ''), countPeople(n), HELPERS[2].color])
        // ChatGPT / Gemini: by the model that replied; a person who has it installed but never gave it a task shows "not used"
        // ChatGPT / Gemini: theo mô hình đã trả lời; người có cài mà chưa giao việc lần nào thì "chưa dùng"
        const byModel = (name, k, modelsKey, color) => {
          const groups = {}
          let unusedCount = 0
          for (const p of people) {
            if (!(p.assistants && p.assistants[k] > 0)) continue
            const list = p.assistants[modelsKey] || []
            if (!list.length) unusedCount++
            for (const m of list) groups[m] = (groups[m] || 0) + 1
          }
          // "Gemini 3.8 Flash (High)" under the Gemini label: drop the repeated word Gemini
          // "Gemini 3.8 Flash (High)" dưới nhãn Gemini: bỏ chữ Gemini lặp lại
          for (const [m, n] of Object.entries(groups).sort((a, b) => b[1] - a[1])) lines.push([`${name} · ${m.replace(new RegExp('^' + name + '\\s*', 'i'), '')}`, countPeople(n), color])
          if (unusedCount || !Object.keys(groups).length) lines.push([tx('{name} · not used', { name }), countPeople(unusedCount), color])
        }
        if (!M) {
          byModel('ChatGPT', 'chatgpt', 'mhChatgpt', HELPERS[1].color)
          byModel('Gemini', 'gemini', 'mhGemini', HELPERS[0].color)
        }
        // single-machine page: all sessions share one account, so the quota is shown only once, here
        // trang một máy: mọi phiên chung một tài khoản nên hạn mức chỉ hiện một lần, ở đây
        if (M) for (const c of (snapshot.machineQuota && snapshot.machineQuota.windows) || []) {
          if (QUOTA_TAGS[c.kind]) lines.push([c.kind === 'five_hour' ? tx('Quota 5 hours') : tx('Quota 7 days'), `${c.pct >= 95 ? '⛔ ' : c.pct >= 80 ? '⚠ ' : ''}${Math.round(c.pct)}%`, c.pct >= 80 ? COLORS.red : c.pct >= 60 ? COLORS.yellow : COLORS.muted])
        }
        const unknownCount = M ? 0 : people.filter(p => !p.assistants || !p.assistants.known).length
        if (unknownCount) lines.push([tx('Unknown (old plugin)'), countPeople(unknownCount), COLORS.muted])
        modelList.replaceChildren(...lines.map(([name, count, color]) => {
          const r = o('div', 'o-mrow')
          const d = o('i')
          d.style.background = color
          d.style.boxShadow = `0 0 6px ${color}`
          r.append(d, o('span', '', name), o('b', '', count))
          return r
        }))
      }
      // key numbers
      // chỉ số
      vRun.s.textContent = `${p2(counts.working)}/${p2(online)}`
      vWait.s.textContent = p2(counts.waiting)
      vCost.s.textContent = money(usdToday, rate)
      vTok.s.textContent = compact(snapshot.tokensInTotal ?? people.reduce((a, p) => a + p.tokensIn, 0))
      const hourly24 = snapshot.hourlyTotal24 || Array.from({ length: 24 }, (_, i) => people.reduce((a, p) => a + (p.hourly24 ? p.hourly24[i] : 0), 0))
      spark(vRun.c, history.working, COLORS.green, true)
      spark(vWait.c, history.waiting, COLORS.yellow, true)
      spark(vCost.c, hourly24, COLORS.cyan, true)
      spark(vTok.c, hourly24.map((v, i) => v + (i % 3) * 1e-6), COLORS.purple, true)
      // telemetry per model
      // telemetry theo mô hình
      claudeTile.s.textContent = money(hourly24[23], rate)
      spark(claudeTile.c, hourly24, COLORS.cyan, false)
      aiTiles.forEach((t, k) => {
        const s = (snapshot.tasks24 && snapshot.tasks24[k]) || []
        t.s.textContent = String(people.reduce((a, p) => a + p.tasks[k], 0))
        spark(t.c, s, HELPERS[k].color, false)
      })
      // heat map of people x hours
      // bản đồ nhiệt người x giờ
      {
        const { g, w, h } = fit(hcv)
        g.clearRect(0, 0, w, h)
        const rows = people.slice(0, 10)
        const max = Math.max(...rows.flatMap(p => p.hourly24 || [0]), 1e-9)
        const cw = w / 24
        const cellH = h / Math.max(rows.length, 1)
        rows.forEach((p, r) =>
          (p.hourly24 || []).forEach((v, c) => {
            const k = v / max
            g.fillStyle = v <= 0 ? 'rgba(94,214,232,0.06)' : k > 0.66 ? COLORS.purple : k > 0.33 ? '#3fb6c8' : '#1f6f7c'
            g.globalAlpha = v <= 0 ? 1 : 0.45 + k * 0.55
            g.fillRect(c * cw + 1, r * cellH + 1, cw - 2, cellH - 2)
          }),
        )
        g.globalAlpha = 1
      }
      // 24-hour chart: cost (area) and number of active people (line)
      // biểu đồ 24 giờ: chi phí (vùng) và số người hoạt động (đường)
      {
        const { g, w, h } = fit(ecv)
        g.clearRect(0, 0, w, h)
        const activity24 = Array.from({ length: 24 }, (_, i) => people.filter(p => p.hourly24 && p.hourly24[i] > 0).length)
        const draw = (data, color, area) => {
          const max = Math.max(...data, 1e-9)
          const pts = data.map((v, i) => [(i / 23) * w, h - 6 - (v / max) * (h - 18)])
          g.beginPath()
          g.moveTo(pts[0][0], pts[0][1])
          for (let i = 1; i < pts.length; i++) {
            const [x0, y0] = pts[i - 1]
            const [x1, y1] = pts[i]
            g.bezierCurveTo((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, x1, y1)
          }
          g.strokeStyle = color
          g.lineWidth = 2
          g.shadowColor = color
          g.shadowBlur = 8
          g.stroke()
          g.shadowBlur = 0
          if (area) {
            g.lineTo(w, h)
            g.lineTo(0, h)
            g.closePath()
            const gr = g.createLinearGradient(0, 0, 0, h)
            gr.addColorStop(0, color + '66')
            gr.addColorStop(1, color + '00')
            g.fillStyle = gr
            g.fill()
          }
        }
        g.strokeStyle = 'rgba(94,214,232,0.07)'
        g.lineWidth = 1
        for (let i = 1; i < 4; i++) {
          g.beginPath()
          g.moveTo(0, (h / 4) * i)
          g.lineTo(w, (h / 4) * i)
          g.stroke()
        }
        draw(hourly24, COLORS.cyan, true)
        draw(activity24, COLORS.purple, false)
      }
      const delegatingCount = people.filter(p => (p.delegating || []).some(v => v > 0)).length
      const setBar = (b, v, total) => {
        const pct = total ? Math.round((v / total) * 100) : 0
        b.p.textContent = pct + '%'
        b.i.style.width = pct + '%'
      }
      setBar(barOnline, online, people.length)
      setBar(barRunning, counts.working, online)
      setBar(barAi, delegatingCount, online)
      // event stream
      // luồng sự kiện
      ev.replaceChildren(
        ...events.map(e => {
          const r = o('div')
          const label = { 'b-ok': 'SUCCESS', 'b-warn': 'WARNING', 'b-info': 'INFO', 'b-off': 'OFFLINE', 'b-ai': 'HAND-OFF' }[e.label] || 'INFO'
          r.append(o('time', '', e.t), o('span', e.label, label), o('em', '', e.text))
          return r
        }),
      )
      if (selected >= 0) selectPerson(selected, true)
    }

    function selectPerson(i, keep) {
      if (!keep && i === selected) i = -1
      selected = i
      ;[...list.children].forEach((r, k) => r.classList.toggle('selected', k === selected))
      const p = people[i]
      if (!p) {
        hoverCard.hidden = true
        return
      }
      const rate = snapshot.usdRate || 26000
      hoverCard.replaceChildren(cardCloseButton, o('b', '', p.name), o('br'))
      for (const lines of M && M.cardLines ? M.cardLines(p) : [
        wallMode ? '' : `${p.account}${p.lanIps.length ? ' · ' + p.lanIps.join(', ') : ''}`,
        `STATUS   ${STATUS_INFO[p.status].name}`,
        ...(subagentNames(p) ? [tx('ASSISTANTS {list}', { list: subagentNames(p) })] : []),
        `MODEL    ${Object.keys(p.models || {}).map(modelName).join(', ') || '—'}`,
        `TODAY    ${money(p.usdToday, rate)} · 7D ${money(p.usd7d, rate)}`,
        `TOKENS   ${compact(p.tokensIn)} in / ${compact(p.tokensOut)} out`,
        `AI TASKS Gemini ${p.tasks[0]} · ChatGPT ${p.tasks[1]} · Gemma ${p.tasks[2]}`,
      ]) hoverCard.append(lines, o('br'))
      hoverCard.hidden = false
      keepCardInside()
    }

    // ---- animated diagram ----
    // cubic curve through the two control points c1, c2
    // ---- sơ đồ động ----
    // đường cong bậc ba qua hai điểm điều khiển c1, c2
    function bezier(a, c1, c2, b, t) {
      const u = 1 - t
      return [0, 1].map(k => u * u * u * a[k] + 3 * u * u * t * c1[k] + 3 * u * t * t * c2[k] + t * t * t * b[k])
    }
    function card(g, x, y, w, h, heading, sub, color, bright, money) {
      g.save()
      roundRect(g, x, y, w, h, 6)
      g.fillStyle = 'rgba(8,22,32,0.92)'
      g.fill()
      g.strokeStyle = color
      g.globalAlpha = bright ? 1 : 0.5
      g.lineWidth = bright ? 1.6 : 1
      g.shadowColor = color
      g.shadowBlur = bright ? 14 : 0
      g.stroke()
      g.shadowBlur = 0
      g.globalAlpha = 1
      g.fillStyle = color
      g.beginPath()
      g.arc(x + 12, y + 15, 3.5, 0, Math.PI * 2)
      g.fill()
      g.fillStyle = '#e8fbff'
      g.font = '700 11px ui-monospace,Menlo,Consolas,monospace'
      g.textBaseline = 'middle'
      let t = heading.toUpperCase()
      while (t.length > 2 && g.measureText(t).width > w - 30) t = t.slice(0, -2) + '…'
      g.fillText(t, x + 22, y + 15)
      g.fillStyle = COLORS.muted
      g.font = '500 10px ui-monospace,Menlo,Consolas,monospace'
      let s = sub
      while (s.length > 2 && g.measureText(s).width > w - 30) s = s.slice(0, -2) + '…'
      g.fillText(s, x + 22, y + 30)
      if (money !== undefined) {
        g.fillStyle = 'rgba(255,255,255,0.06)'
        g.fillRect(x + 12, y + h - 8, w - 24, 2.5)
        g.fillStyle = color
        g.fillRect(x + 12, y + h - 8, (w - 24) * Math.min(1, money), 2.5)
      }
      g.restore()
    }

    function drawDiagram(t) {
      if (mode === '3d') return
      const people = drawPeople()
      const { g, w, h } = fit(gcv)
      g.clearRect(0, 0, w, h)
      // floating specks of light as the diagram's background
      // bụi sáng lơ lửng như nền của sơ đồ
      for (const [bx, by, r] of stars) {
        g.fillStyle = `rgba(94,230,240,${0.15 + 0.15 * Math.sin(t * 1.3 + bx * 10)})`
        g.beginPath()
        g.arc(bx * w, by * h, r, 0, Math.PI * 2)
        g.fill()
      }
      if (!snapshot) return
      const cardH = 42
      const n = people.length
      // arrange people in vertical columns on the left, each column holding as many cards as fit the height
      // xếp người thành cột dọc bên trái, mỗi cột nhiều nhất số thẻ vừa chiều cao
      const perColumn = Math.max(1, Math.min(9, Math.floor((h - 16) / (cardH + 10))))
      const columnCount = Math.max(1, Math.ceil(n / perColumn))
      const cw = Math.min(180, Math.max(130, (w * 0.44) / columnCount - 18))
      const peopleWidth = columnCount * (cw + 18)
      // narrow screen (phone, unfolded foldable): stack vertically, AI on top, Claude in the middle, people below in two columns,
      // when a horizontal row has no room for the people column + Claude + AI column without overlapping
      // màn hình hẹp (điện thoại, máy gập mở ra): xếp dọc, AI trên cùng, Claude ở giữa, người ở dưới hai cột,
      // khi hàng ngang không đủ chỗ cho cột người + Claude + cột AI mà không đè nhau
      const doc = w < 560 || peopleWidth + 40 + cw + 30 + cw + 14 > w
      // stacked layout with a big team: make the diagram frame taller to fit every person card (only when the panels are in one column)
      // xếp dọc mà team đông: khung sơ đồ cao thêm cho đủ mọi thẻ người (chỉ khi các khung xếp một cột)
      const neededHeight = 190 + Math.ceil(n / 2) * (cardH + 12) + 8
      if (doc && innerWidth <= 1100 && neededHeight > h) graph.style.height = Math.ceil(neededHeight + 60) + 'px'
      let nodeN, hub, nodeA
      if (doc) {
        const helperW = (w - 32) / 3
        nodeA = HELPERS.map((a, k) => ({ x: 8 + k * (helperW + 8), y: 8, w: helperW, h: cardH, k }))
        hub = { x: w / 2 - Math.min(110, w / 2 - 12), y: 92, w: Math.min(220, w - 24), h: 50 }
        // people: 2 columns, add columns (up to 4) when the frame cannot grow taller and there is still not enough room
        // người: 2 cột, thêm cột (tới 4) khi khung không cao thêm được mà vẫn thiếu chỗ
        let pc = 2
        while (pc < 4 && 190 + Math.ceil(n / pc) * (cardH + 12) > h && (w - 16) / (pc + 1) >= 120) pc++
        const pw = (w - 16 - (pc - 1) * 12) / pc
        nodeN = people.map((p, i) => ({ x: 8 + (i % pc) * (pw + 12), y: 190 + Math.floor(i / pc) * (cardH + 12), w: pw, h: cardH, p, i }))
      } else {
        nodeN = people.map((p, i) => {
          const c = Math.floor(i / perColumn)
          const r = i % perColumn
          const inColumn = Math.min(perColumn, n - c * perColumn)
          const x = 10 + c * (cw + 18)
          const y = h / 2 - (inColumn * (cardH + 10)) / 2 + r * (cardH + 10)
          return { x, y, w: cw, h: cardH, p, i }
        })
        hub = { x: Math.max(peopleWidth + 40, w * 0.52 - cw / 2), y: h / 2 - 26, w: cw, h: 52 }
        nodeA = HELPERS.map((a, k) => ({ x: w - cw - 14, y: h / 2 - 1.5 * (cardH + 24) + k * (cardH + 24) + 12, w: cw, h: cardH, k }))
      }
      // the whole diagram (people, Claude, AI) and the zoom that fits the frame; until the viewer zooms or drags, it always fits
      // cả sơ đồ (người, Claude, AI) và độ phóng vừa khung; người xem chưa tự phóng/kéo thì luôn vừa khung
      const height = Math.max(...[...nodeN, hub, ...nodeA].map(node => node.y + node.h)) + 8
      view.fit = Math.min(1, h / height)
      if (!view.free) {
        view.s = view.fit
        view.x = (w - w * view.s) / 2
        view.y = 0
      }
      g.save()
      g.translate(view.x, view.y)
      g.scale(view.s, view.s)
      if (tilted) {
        // grid background like a floor, drifting slowly toward the viewer
        // nền lưới như mặt sàn, trôi chậm về phía người xem
        const o = 40
        const x0 = Math.floor(-view.x / view.s / o) * o - o
        const y0 = Math.floor(-view.y / view.s / o) * o - o
        const x1 = (w - view.x) / view.s + o
        const y1 = (h - view.y) / view.s + o
        const drift = (t * 6) % o
        g.strokeStyle = 'rgba(94,230,240,0.07)'
        g.lineWidth = 1 / view.s
        g.beginPath()
        for (let x = x0; x <= x1; x += o) g.moveTo(x, y0), g.lineTo(x, y1)
        for (let y = y0 + drift; y <= y1; y += o) g.moveTo(x0, y), g.lineTo(x1, y)
        g.stroke()
        // a shadow under every card: the cards seem to float above the floor
        // bóng đổ dưới mọi thẻ: thẻ như nổi lên khỏi sàn
        g.fillStyle = 'rgba(0,0,0,0.55)'
        for (const node of [...nodeN, hub, ...nodeA]) {
          g.save()
          g.shadowColor = 'rgba(0,0,0,0.8)'
          g.shadowBlur = 14
          g.shadowOffsetY = 10 * view.s
          roundRect(g, node.x + 3, node.y + 6, node.w - 6, node.h, 6)
          g.fill()
          g.restore()
        }
      }
      const counts = people.filter(p => p.status === 'working').length
      const delegatingByHelper = [0, 1, 2].map(k => people.filter(p => (p.delegating || [])[k] > 0))

      const drawLine = (a, b, color, active, particles, speed) => {
        // horizontal: from the right edge of a to the left edge of b; vertical: from the top edge of a up to the bottom edge of b
        // ngang: từ mép phải a sang mép trái b; dọc: từ mép trên a lên mép dưới b
        const A = doc ? [a.x + a.w / 2, a.y] : [a.x + a.w, a.y + a.h / 2]
        const B = doc ? [b.x + b.w / 2, b.y + b.h] : [b.x, b.y + b.h / 2]
        const C1 = doc ? [A[0], (A[1] + B[1]) / 2] : [(A[0] + B[0]) / 2, A[1]]
        const C2 = doc ? [B[0], (A[1] + B[1]) / 2] : [(A[0] + B[0]) / 2, B[1]]
        g.beginPath()
        g.moveTo(A[0], A[1])
        g.bezierCurveTo(C1[0], C1[1], C2[0], C2[1], B[0], B[1])
        g.strokeStyle = color
        g.globalAlpha = active ? 0.75 : 0.18
        g.lineWidth = active ? 1.5 : 1
        if (!active) g.setLineDash([3, 5])
        g.stroke()
        g.setLineDash([])
        g.globalAlpha = 1
        for (let q = 0; q < particles; q++) {
          const f = (t * speed + q / particles) % 1
          const [x, y] = bezier(A, C1, C2, B, f)
          g.fillStyle = active ? '#ffffff' : color
          g.shadowColor = color
          g.shadowBlur = active ? 10 : 4
          g.beginPath()
          g.arc(x, y, active ? 2.2 : 1.4, 0, Math.PI * 2)
          g.fill()
          g.shadowBlur = 0
        }
      }
      for (const node of nodeN) {
        const s = node.p.status
        if (s === 'offline') continue
        drawLine(node, hub, STATUS_INFO[s].color, s === 'working' || s === 'waiting', s === 'working' ? 3 : 1, s === 'working' ? 0.45 : 0.12)
      }
      nodeA.forEach((a, k) => drawLine(hub, a, HELPERS[k].color, delegatingByHelper[k].length > 0, delegatingByHelper[k].length ? 4 : 1, delegatingByHelper[k].length ? 0.55 : 0.1))

      const maxUsd = Math.max(...people.map(p => p.usdToday), 1e-9)
      rects = []
      for (const node of nodeN) {
        const p = node.p
        const st = STATUS_INFO[p.status]
        const pulse = p.status === 'waiting' ? 0.5 + 0.5 * Math.abs(Math.sin(t * 3)) : 1
        g.globalAlpha = p.status === 'offline' ? 0.45 : pulse
        // account close to its quota: red, blinking card, visible even from far away
        // tài khoản sắp hết hạn mức: ô đỏ, nhấp nháy, nhìn từ xa cũng thấy
        const critical = nearQuotaLimit(p)
        if (critical) g.globalAlpha = 0.55 + 0.45 * Math.abs(Math.sin(t * 2.5))
        card(g, node.x, node.y, node.w, node.h, p.name, critical ? tx('⛔ QUOTA {pct}%', { pct: critical }) : `${st.name} · ${mainModel(p) || compact(p.tokensIn) + ' tok'}`, critical ? COLORS.red : st.color, critical > 0 || p.status === 'working' || node.i === selected, p.usdToday / maxUsd)
        g.globalAlpha = 1
        rects.push(node)
      }
      card(g, hub.x, hub.y, hub.w, hub.h, 'CLAUDE // CORE', `${counts} RUNNING · ${people.length} NODES`, COLORS.cyan, true, people.length ? counts / people.length : 0)
      nodeA.forEach((a, k) => {
        const members = delegatingByHelper[k]
        const sub = members.length ? 'PROCESSING ← ' + members.map(p => p.name).join(', ') : `STANDBY · ${people.reduce((s, p) => s + p.tasks[k], 0)} today`
        card(g, a.x, a.y, a.w, a.h, HELPERS[k].name, sub, HELPERS[k].color, members.length > 0)
      })
      g.restore()
    }

    gcv.addEventListener('click', e => {
      if (justDragged) return void (justDragged = false)
      const [lx, ly] = pointOf(e.clientX, e.clientY)
      const x = (lx - view.x) / view.s
      const y = (ly - view.y) / view.s
      const hit = rects.find(n => x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h)
      selectPerson(hit ? hit.i : -1)
    })

    let last = 0
    function frame(ts) {
      requestAnimationFrame(frame)
      // about 30 frames per second
      // khoảng 30 khung hình/giây
      if (ts - last < 33) return
      last = ts
      if (mode !== 'map') drawDiagram(ts / 1000)
    }
    requestAnimationFrame(frame)
    setMode(mode)
    if (wallMode) {
      document.body.classList.add('wall')
      document.title = tx('AI Worker · Wall display')
      // if there are branches, the diagram and the map take turns every 30 seconds
      // có chi nhánh thì sơ đồ và bản đồ thay nhau mỗi 30 giây
      setInterval(() => {
        if (!snapshot || !(snapshot.branches || []).length) return
        // fade out with a scan line; switch the scene once fully faded so there is no jump
        // mờ dần kèm một vạch quét; đổi cảnh lúc đã mờ hẳn để không thấy giật
        stage.classList.add('o-switching', 'o-scan')
        setTimeout(() => {
          setMode(mode === 'map' ? 'default' : 'map')
          stage.classList.replace('o-switching', 'o-in')
          setTimeout(() => stage.classList.remove('o-in', 'o-scan'), 500)
        }, 400)
      }, 30000)
    }
    setInterval(() => (clock.textContent = hourNow()), 1000)
    clock.textContent = hourNow()
    window.addEventListener('resize', () => snapshot && prevCounts && drawStatic(prevCounts))
    return { update }
  }

  window.OpsBoard = { create }
})()
