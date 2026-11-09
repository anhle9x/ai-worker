// Picks the display language and translates text. English in the code is the source; *.vi.js holds the Vietnamese.
// Chọn ngôn ngữ hiển thị và dịch chữ. Chữ tiếng Anh trong mã là bản gốc; các file *.vi.js giữ bản tiếng Việt.
;(function () {
  'use strict'
  const LANGS = ['en', 'vi']
  const VI = {}
  // Order: the visitor's own choice, what the server picked, the install choice, the local config, the browser, then English.
  // Thứ tự: lựa chọn của người xem, ngôn ngữ máy chủ đã chọn, lựa chọn lúc cài, cấu hình trên máy, trình duyệt, rồi tiếng Anh.
  function detect() {
    const cookie = /(?:^|;\s*)lang=(en|vi)\b/.exec(document.cookie || '')
    if (cookie) return cookie[1]
    try {
      const saved = localStorage.getItem('lang')
      if (LANGS.includes(saved)) return saved
    } catch {
      // The browser blocks storage: carry on with the next source.
      // Trình duyệt chặn lưu trữ: dùng nguồn kế tiếp.
    }
    const fromServer = document.documentElement.dataset.lang
    if (LANGS.includes(fromServer)) return fromServer
    // The language chosen when installing the plugin; only the plugin page has it.
    // Ngôn ngữ đã chọn khi cài plugin; chỉ trang plugin mới có.
    if (LANGS.includes(window.__aiWorkerLang)) return window.__aiWorkerLang
    const fromConfig = (window.__aiWorkerConfig || {}).language
    if (LANGS.includes(fromConfig)) return fromConfig
    return /^vi\b/i.test(navigator.language || '') ? 'vi' : 'en'
  }
  const lang = detect()
  document.documentElement.lang = lang

  // tx('{n} online', { n: 3 }): text missing from the dictionary falls back to English.
  // tx('{n} online', { n: 3 }): chữ chưa có trong từ điển thì hiện tiếng Anh.
  function tx(text, params) {
    const found = lang === 'vi' && Object.prototype.hasOwnProperty.call(VI, text) ? VI[text] : text
    return params ? found.replace(/\{(\w+)\}/g, (all, name) => (name in params ? String(params[name]) : all)) : found
  }
  function setLang(next) {
    if (!LANGS.includes(next)) return
    document.cookie = 'lang=' + next + '; path=/; max-age=31536000; SameSite=Lax'
    try {
      localStorage.setItem('lang', next)
    } catch {
      // The cookie above is enough on this browser.
      // Trên trình duyệt này chỉ cần cookie ở trên.
    }
    location.reload()
  }
  // Small EN / VI switch; the language in use is marked, the other one is the button.
  // Nút chuyển EN / VI nhỏ; ngôn ngữ đang dùng được đánh dấu, ngôn ngữ còn lại là nút bấm.
  function switcher() {
    const box = document.createElement('span')
    box.className = 'lang-switch'
    for (const code of LANGS) {
      const b = document.createElement('button')
      b.type = 'button'
      b.textContent = code.toUpperCase()
      b.setAttribute('aria-pressed', String(code === lang))
      b.title = code === 'vi' ? 'Tiếng Việt' : 'English' // i18n-allow
      if (code === lang) b.className = 'on'
      b.onclick = () => setLang(code)
      box.append(b)
    }
    return box
  }
  window.I18n = {
    lang,
    tx,
    setLang,
    switcher,
    locale: lang === 'vi' ? 'vi-VN' : 'en-US',
    add(dict) {
      Object.assign(VI, dict)
    },
  }
  window.tx = tx
})()
