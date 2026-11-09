// Main page of the webhook: fetches /data every 10 seconds and hands it to the dashboard (ops.js).
// Trang chính của webhook: lấy /data 10 giây một lần và đưa cho bảng điều khiển (ops.js).
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
  const board = window.OpsBoard.create(root, { viewerName: document.body.dataset.user || '' })
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

  async function fetchData() {
    try {
      const r = await fetch('/data?ui=' + encodeURIComponent(ui), { cache: 'no-store', credentials: 'same-origin' })
      // signed out: go back to the code entry page
      // hết phiên đăng nhập: về trang nhập mã
      if (r.status === 401) return location.reload()
      const d = await r.json()
      board.update(d)
      if (d.reload) reload(true)
      else if (ui && d.uiVersion && d.uiVersion !== ui) newVersionNotice()
      document.body.classList.remove('disconnected')
    } catch (e) {
      document.body.classList.add('disconnected')
    }
  }
  fetchData()
  setInterval(fetchData, 10000)
})()
