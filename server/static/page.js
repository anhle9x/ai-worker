// Main page of the webhook: fetches /data and hands it to the dashboard (ops.js). With the receiver's live feed (docs/RECEIVER.md,
// section 3) the board reads one scope at a time, the whole organisation or one branch, and its numbers come from the feed.
// Trang chính của webhook: lấy /data và đưa cho bảng điều khiển (ops.js). Khi có luồng số trực tiếp của bộ nhận (docs/RECEIVER.vi.md,
// mục 3), bảng đọc từng phạm vi một, cả tổ chức hay một chi nhánh, và các con số đến từ luồng.
;(function () {
  'use strict'
  // just signed in to approve a TV screen: go back to exactly what was being done
  // vừa đăng nhập để duyệt màn hình TV: quay lại đúng việc đang làm
  try {
    const pair = sessionStorage.getItem('pair')
    if (pair) {
      sessionStorage.removeItem('pair')
      if (document.body.dataset.role === 'admin' && /^[0-9]{8}$/.test(pair)) return location.replace('/admin#pair=' + pair)
    }
  } catch {
    // the browser blocks storage: stay on the board
    // trình duyệt chặn lưu trữ: ở lại bảng
  }
  const root = document.getElementById('ops')
  const board = window.OpsBoard.create(root, { viewerName: document.body.dataset.user || '', onScope: (scope, page) => setScope(scope, page) })
  const ui = document.body.dataset.ui || ''

  function toast(label) {
    const b = document.createElement('div')
    b.className = 'o-toast'
    b.textContent = label
    document.body.append(b)
    setTimeout(() => b.remove(), 5000)
  }
  try {
    if (sessionStorage.getItem('just-updated')) {
      sessionStorage.removeItem('just-updated')
      toast(tx('Interface updated'))
    }
  } catch {
    // the browser blocks storage: skip the notice
    // trình duyệt chặn lưu trữ: bỏ qua dòng báo
  }

  let loading = false
  // fade out before reloading so there is no jump; stop endless reloads if the version numbers keep disagreeing
  // mờ đi rồi mới tải để không thấy giật; chặn tải lại liên tục nếu số phiên bản cứ lệch
  function reload(on) {
    if (loading) return
    let last = 0
    try {
      last = +sessionStorage.getItem('reload-at') || 0
    } catch {
      // the browser blocks storage: carry on without it
      // trình duyệt chặn lưu trữ: bỏ qua và chạy tiếp
    }
    if (!on && Date.now() - last < 300000) return nudgeButton()
    loading = true
    try {
      sessionStorage.setItem('reload-at', String(Date.now()))
      sessionStorage.setItem('just-updated', '1')
    } catch {
      // the browser blocks storage: carry on without it
      // trình duyệt chặn lưu trữ: bỏ qua và chạy tiếp
    }
    const stage = document.querySelector('.o-stage')
    if (stage) stage.classList.add('o-switching', 'o-scan')
    setTimeout(() => location.reload(), 400)
  }
  function nudgeButton() {
    const n = document.querySelector('[data-reload]')
    if (n) {
      n.textContent = tx('New version, reload')
      n.classList.add('new')
    }
  }
  function newVersionNotice() {
    const focused = document.activeElement
    if ((focused && /^(INPUT|SELECT|TEXTAREA)$/.test(focused.tagName)) || document.querySelector('dialog[open]')) return nudgeButton()
    reload(false)
  }

  // the board asks every second while it is on screen, so a change shows within a few seconds;
  // a tab in the background asks every 10 seconds; one question at a time, and an answer that did not change is not drawn again
  // bảng hỏi mỗi giây khi đang hiện trên màn hình, để một thay đổi hiện trong vài giây;
  // tab nằm dưới nền hỏi mỗi 10 giây; mỗi lần một câu hỏi, và câu trả lời không đổi thì không vẽ lại
  const ASK_EVERY_MS = 1000
  const ASK_HIDDEN_MS = 10000
  // with the live feed the numbers come from the feed as they change: /data of the scope is asked only for the names and the rest of the board
  // khi có luồng số trực tiếp, các con số đến từ luồng ngay khi đổi: /data của phạm vi chỉ được hỏi để lấy tên và phần còn lại của bảng
  const NAMES_EVERY_MS = 20000
  // after the feed drops: a new ticket after 1 second, then twice as long each time, at most 30 seconds
  // sau khi luồng rớt: xin vé mới sau 1 giây, rồi mỗi lần lâu gấp đôi, tối đa 30 giây
  const RETRY_FIRST_MS = 1000
  const RETRY_MAX_MS = 30000
  // the numbers of a person that the feed carries, put over the same fields of /data
  // các con số của một người mà luồng mang, đặt đè lên đúng các trường đó của /data
  const ROW_FIELDS = ['status', 'openSessions', 'working', 'waiting', 'delegating', 'tools', 'usdToday', 'tokensIn', 'tokensOut', 'tasks']

  // the scope and page come from the address (?scope=branch:hn&page=1), so a reload or a TV screen keeps them
  // phạm vi và trang lấy từ địa chỉ (?scope=branch:hn&page=1), để tải lại hay màn hình TV vẫn giữ nguyên
  const params = new URLSearchParams(location.search)
  let scope = /^(org|branch:.{0,200})$/.test(params.get('scope') || '') ? params.get('scope') : 'org'
  let page = Math.max(0, parseInt(params.get('page'), 10) || 0)
  // 'plain': /data as it always was (a server without the live feed); 'scope': /data?scope= every second, for the whole organisation
  // while it lists its people (their numbers are only there); 'live': /data?scope= every 20 seconds, the numbers from the feed
  // 'plain': /data như xưa nay (máy chủ không có luồng); 'scope': /data?scope= mỗi giây, cho cả tổ chức khi nó còn liệt kê người
  // (số của họ chỉ có ở đó); 'live': /data?scope= mỗi 20 giây, các con số từ luồng
  let mode = 'plain'
  // grows at every change of scope, so an answer asked for the one before is dropped
  // tăng mỗi lần đổi phạm vi, để câu trả lời hỏi cho phạm vi trước bị bỏ qua
  let generation = 0
  let base = null
  // the code of a row (or the id of a branch, for the whole organisation) -> its last numbers from the feed
  // mã của một dòng (hay mã chi nhánh, với cả tổ chức) -> các con số cuối cùng của nó từ luồng
  let liveRows = new Map()
  let feed = null
  let retryMs = RETRY_FIRST_MS
  let retryTimer = 0

  let asking = false
  let askedAt = 0
  let lastText = ''
  const dataUrl = () => (mode === 'plain' ? '/data?ui=' : '/data?scope=' + encodeURIComponent(scope) + (page ? '&page=' + page : '') + '&ui=') + encodeURIComponent(ui)
  async function fetchData() {
    const every = mode === 'live' ? NAMES_EVERY_MS : document.hidden ? ASK_HIDDEN_MS : 0
    if (asking || Date.now() - askedAt < every) return
    asking = true
    askedAt = Date.now()
    const asked = generation
    try {
      const r = await fetch(dataUrl(), { cache: 'no-store', credentials: 'same-origin' })
      // signed out: go back to the code entry page
      // hết phiên đăng nhập: về trang nhập mã
      if (r.status === 401) return location.reload()
      // a branch that no longer exists (removed on the Admin page): back to the whole organisation
      // chi nhánh không còn nữa (đã bỏ ở trang Quản trị): về cả tổ chức
      if (r.status === 400 && mode !== 'plain') return setScope('org', 0)
      const text = await r.text()
      if (asked !== generation) return
      if (!feed || mode !== 'live') document.body.classList.remove('disconnected')
      // the server stamps every answer with its time: compare without that stamp, so only a real change is drawn
      // máy chủ đóng dấu giờ lên mọi câu trả lời: so mà bỏ dấu đó, để chỉ thay đổi thật mới được vẽ
      const same = text.replace(/"updatedAt": ?\d+/, '')
      if (same === lastText) return
      lastText = same
      const d = JSON.parse(text)
      base = d
      if (mode !== 'plain') choose()
      draw()
      if (d.reload) reload(true)
      else if (ui && d.uiVersion && d.uiVersion !== ui) newVersionNotice()
    } catch (e) {
      document.body.classList.add('disconnected')
    } finally {
      asking = false
    }
  }

  // the whole organisation lists its people while they are 500 or fewer, and the feed of the whole organisation carries only the totals
  // of the branches: so that page keeps asking /data every second, and every other page takes its numbers from the feed
  // cả tổ chức còn liệt kê người khi có 500 người trở xuống, mà luồng của cả tổ chức chỉ mang tổng của các chi nhánh: nên trang đó vẫn
  // hỏi /data mỗi giây, còn mọi trang khác lấy số từ luồng
  function choose() {
    const next = base.scope === 'org' && (base.people || []).length ? 'scope' : 'live'
    if (next === mode) return
    mode = next
    if (mode === 'live') openFeed()
    else closeFeed()
  }

  // /data with the last numbers of the feed put over it; a row of the feed that is not on this page is left out
  // /data có các con số cuối cùng của luồng đặt đè lên; dòng của luồng không có trên trang này thì bỏ qua
  function draw() {
    if (!base) return
    if (mode !== 'live' || !liveRows.size) return board.update(base)
    if (base.scope === 'org') return board.update(Object.assign({}, base, { branchTotals: (base.branchTotals || []).map(b => (liveRows.has(b.id) ? Object.assign({}, b, liveRows.get(b.id)) : b)) }))
    board.update(Object.assign({}, base, {
      people: (base.people || []).map(p => {
        const v = p.row && liveRows.get(p.row)
        if (!v) return p
        const q = Object.assign({}, p)
        for (const k of ROW_FIELDS) if (k in v) q[k] = v[k]
        return q
      }),
    }))
  }

  function closeFeed() {
    if (feed) feed.close()
    feed = null
    clearTimeout(retryTimer)
    liveRows = new Map()
  }
  function retryFeed() {
    const asked = generation
    clearTimeout(retryTimer)
    retryTimer = setTimeout(() => mode === 'live' && asked === generation && openFeed(), retryMs)
    retryMs = Math.min(RETRY_MAX_MS, retryMs * 2)
  }
  const askTicket = () => fetch('/sse/ticket', {
    method: 'POST', cache: 'no-store', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope }),
  })
  // a ticket for the scope (5 minutes), then the feed: snap holds the whole scope, d the rows changed and the codes gone; bye at the end
  // of the ticket or of the session, and any error, ask a new ticket and open again
  // vé cho phạm vi (5 phút), rồi luồng: snap mang cả phạm vi, d các dòng đã đổi và mã các dòng đã đi; bye khi hết vé hay hết phiên,
  // và mọi lỗi, thì xin vé mới rồi mở lại
  async function openFeed() {
    closeFeed()
    const asked = generation
    let t
    try {
      const r = await askTicket()
      if (asked !== generation || mode !== 'live') return
      if (r.status === 401) return location.reload()
      // the server no longer has the live feed: back to /data as before
      // máy chủ không còn luồng số trực tiếp: về /data như trước
      if (r.status === 404) return plain()
      if (r.status === 400) return setScope('org', 0)
      if (!r.ok) throw new Error('ticket ' + r.status)
      t = await r.json()
    } catch (e) {
      document.body.classList.add('disconnected')
      return retryFeed()
    }
    if (asked !== generation || mode !== 'live') return
    const es = new EventSource(t.live + '?t=' + encodeURIComponent(t.ticket) + '&scope=' + encodeURIComponent(t.scope))
    feed = es
    const [field, key] = t.scope === 'org' ? ['branches', 'id'] : ['rows', 'row']
    const take = (e, whole) => {
      if (feed !== es) return
      let m
      try {
        m = JSON.parse(e.data)
      } catch {
        return
      }
      if (whole) liveRows = new Map()
      for (const v of m[field] || []) liveRows.set(v[key], v)
      // a row gone from the scope: its numbers are dropped, and the next /data says whether the person is still on this page
      // dòng đã rời phạm vi: bỏ các con số của nó, và lần /data kế tiếp cho biết người đó còn trên trang này không
      for (const k of m.gone || []) liveRows.delete(k)
      retryMs = RETRY_FIRST_MS
      document.body.classList.remove('disconnected')
      draw()
    }
    es.addEventListener('snap', e => take(e, true))
    es.addEventListener('d', e => take(e, false))
    es.addEventListener('bye', () => feed === es && openFeed())
    es.onerror = () => {
      if (feed !== es) return
      closeFeed()
      document.body.classList.add('disconnected')
      draw()
      retryFeed()
    }
  }

  function plain() {
    generation++
    mode = 'plain'
    closeFeed()
    lastText = ''
    askedAt = 0
    fetchData()
  }
  // the picker of ops.js chose another scope or page: the address keeps it, and the board starts again on it
  // ô chọn của ops.js chọn phạm vi hay trang khác: địa chỉ giữ lại, và bảng bắt đầu lại trên đó
  function setScope(s, p) {
    if (mode === 'plain') return
    generation++
    scope = s
    page = p || 0
    closeFeed()
    retryMs = RETRY_FIRST_MS
    // until the first answer says whether this scope needs the feed
    // cho tới khi câu trả lời đầu tiên cho biết phạm vi này có cần luồng không
    mode = 'scope'
    lastText = ''
    askedAt = 0
    if (scope === 'org') params.delete('scope')
    else params.set('scope', scope)
    if (page) params.set('page', String(page))
    else params.delete('page')
    const query = params.toString()
    history.replaceState(null, '', location.pathname + (query ? '?' + query : '') + location.hash)
    fetchData()
  }

  // a server with the live feed gives a ticket; without it (RECEIVER off: a small company) the answer is 404 and the board asks /data
  // as it always did. No answer at all (no network yet, a TV that starts before it): ask again in 5 seconds
  // máy chủ có luồng thì cấp vé; không có (RECEIVER tắt: công ty nhỏ) thì trả 404 và bảng hỏi /data như xưa nay. Không có câu trả lời
  // nào (chưa có mạng, TV bật trước khi có mạng): 5 giây sau hỏi lại
  async function start() {
    let r
    try {
      r = await askTicket()
    } catch (e) {
      document.body.classList.add('disconnected')
      return setTimeout(start, 5000)
    }
    if (r.status === 401) return location.reload()
    if (r.status === 400 && scope !== 'org') {
      scope = 'org'
      page = 0
      return start()
    }
    if (r.ok) mode = 'scope'
    fetchData()
    setInterval(fetchData, ASK_EVERY_MS)
  }
  start()
})()
