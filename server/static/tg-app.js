// The board's window inside Telegram: runs before mini.js and gives it window.MiniApi, so the menu bar window's own script draws it.
// Telegram puts its signed fields (tgWebAppData) after the # of the address, which never reaches the server's logs. They are sent once
// to /tg/session for a session that lives in this page only: no cookie, no storage. Telegram's own script is not loaded, so nothing
// from another site runs in a page that shows the team's numbers; the two calls the window needs go through the bridge Telegram's apps put in the page.
// Khung bảng bên trong Telegram: chạy trước mini.js và đưa cho nó window.MiniApi, để chính script của khung thanh menu vẽ nó.
// Telegram đặt các trường đã ký (tgWebAppData) sau dấu # của địa chỉ, phần này không bao giờ vào nhật ký của máy chủ. Chúng được gửi một lần
// tới /tg/session để lấy một phiên chỉ sống trong trang này: không cookie, không lưu trữ. Không nạp script của chính Telegram, nên không có gì
// từ trang khác chạy trong trang hiện số liệu của team; hai lời gọi khung cần đi qua cầu nối mà app Telegram đặt sẵn trong trang.
;(function () {
  'use strict'
  var words = JSON.parse(document.body.getAttribute('data-words') || '{}')
  var params = new URLSearchParams((location.hash || '').slice(1))
  var initData = params.get('tgWebAppData') || ''
  var token = null
  var asking = null
  var problem = ''

  // Telegram's apps listen on TelegramWebviewProxy (Android, iOS) or window.external.notify (Desktop)
  // các app Telegram nghe qua TelegramWebviewProxy (Android, iOS) hoặc window.external.notify (bản cho máy tính)
  function postEvent (type, data) {
    try {
      if (window.TelegramWebviewProxy && window.TelegramWebviewProxy.postEvent) window.TelegramWebviewProxy.postEvent(type, JSON.stringify(data || {}))
      else if (window.external && 'notify' in window.external) window.external.notify(JSON.stringify({ eventType: type, eventData: data || {} }))
    } catch (e) {}
  }

  function fail (text) {
    problem = text
    throw new Error(text)
  }

  function session () {
    if (token) return Promise.resolve(token)
    if (!initData) {
      problem = words['Open this window from the bot\'s menu button in Telegram.'] || 'Open this window from the bot\'s menu button in Telegram.'
      return Promise.reject(new Error(problem))
    }
    if (!asking) {
      asking = fetch('/tg/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ initData: initData }), cache: 'no-store' })
        .then(function (r) {
          return r.json().catch(function () { return {} }).then(function (d) {
            if (!r.ok || !d.token) fail(d.error || words['Close this window and open it again from the chat.'] || 'Close this window and open it again from the chat.')
            problem = ''
            token = d.token
            return token
          })
        })
      asking.then(function () { asking = null }, function () { asking = null })
    }
    return asking
  }

  // a call with the session; a session the server no longer knows (it restarted, or an hour passed) is asked for once more
  // một lời gọi kèm phiên; phiên máy chủ không còn biết (nó khởi động lại, hoặc đã qua một giờ) thì xin lại một lần
  function call (path, method, again) {
    return session().then(function (t) {
      return fetch(path, { method: method || 'GET', headers: { Authorization: 'Bearer ' + t }, cache: 'no-store' })
    }).then(function (r) {
      if (r.status === 401 && !again) { token = null; return call(path, method, true) }
      if (!r.ok) return r.json().catch(function () { return {} }).then(function (d) { fail(d.error || String(r.status)) })
      return r
    })
  }

  // mini.js writes "Cannot reach the server" when a call fails; the real reason is put in its place a moment later
  // mini.js ghi "Không tới được máy chủ" khi lời gọi hỏng; lý do thật được đặt vào chỗ đó ngay sau
  function showProblem () {
    setTimeout(function () {
      var line = document.getElementById('updated')
      if (line && problem) { line.textContent = problem; line.className = 'err' }
    }, 0)
  }

  window.MiniApi = {
    data: function () { return call('/tg/data').then(function (r) { return r.json() }).catch(function (e) { showProblem(); throw e }) },
    // a chat has no alert setting yet: the row is hidden, and nothing is read or saved
    // chat chưa có cài đặt báo: dòng đó bị ẩn, không đọc hay lưu gì
    state: function () { return Promise.resolve(null) },
    save: function () { return Promise.resolve(false) },
    unpair: function () { return call('/tg/unpair', 'POST').then(function () { postEvent('web_app_close') }) },
    // the language is chosen in the address; the part after # stays, so the session can be asked for again
    // ngôn ngữ được chọn qua địa chỉ; phần sau dấu # được giữ, để còn xin lại phiên
    setLang: function (code) { location.replace('/tg/app?lang=' + (code === 'vi' ? 'vi' : 'en') + location.hash) },
    openLink: function () {}
  }
  postEvent('web_app_ready')
  postEvent('web_app_expand')
})()
