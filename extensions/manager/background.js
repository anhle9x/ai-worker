// Service worker: wires the browser APIs to core.js, asks the board once a minute, opens the board when a notification is clicked.
// Service worker: nối API trình duyệt với core.js, hỏi bảng mỗi phút một lần, bấm thông báo thì mở bảng.
/* global chrome, importScripts, ManagerCore */
importScripts('core.js')

const ALARM = 'tick'

// The words of the language chosen in the popup (notifications, the icon's title); chrome.i18n would only give the browser's language.
// Chữ theo ngôn ngữ chọn trong cửa sổ nhỏ (thông báo, tiêu đề biểu tượng); chrome.i18n chỉ cho ngôn ngữ của trình duyệt.
let messages = null
async function loadLang () {
  const x = await chrome.storage.local.get(ManagerCore.LANG_KEY)
  const lang = ManagerCore.pickLang(x[ManagerCore.LANG_KEY], chrome.i18n.getUILanguage())
  try {
    messages = await (await fetch(chrome.runtime.getURL('_locales/' + lang + '/messages.json'))).json()
  } catch (e) {
    messages = null
  }
}
let langReady = loadLang()
const t = (key, subs) => messages && messages[key] ? ManagerCore.formatMessage(messages, key, subs) : chrome.i18n.getMessage(key, subs)

const manager = ManagerCore.createManager({
  storage: {
    get: keys => chrome.storage.local.get(keys),
    set: obj => chrome.storage.local.set(obj),
    remove: keys => chrome.storage.local.remove(keys)
  },
  fetch: (url, options) => fetch(url, options),
  hasPermission: origin => chrome.permissions.contains({ origins: [ManagerCore.originPattern(origin)] }),
  ui: {
    t,
    setBadge: async ({ text, color, title }) => {
      await chrome.action.setBadgeBackgroundColor({ color })
      if (chrome.action.setBadgeTextColor) await chrome.action.setBadgeTextColor({ color: '#ffffff' })
      await chrome.action.setBadgeText({ text })
      await chrome.action.setTitle({ title })
    },
    notify: (id, title, message) => chrome.notifications.create(id, { type: 'basic', iconUrl: 'icons/icon128.png', title, message, priority: 1 })
  }
})

// The toolbar icon is a G drawn in one colour: dark on a light toolbar, light on a dark one, like the macOS menu bar icon.
// A service worker cannot see the light or dark mode, so a hidden page (offscreen.html) watches it and reports here; the popup reports too.
// Biểu tượng trên thanh công cụ là chữ G một màu: tối trên thanh sáng, sáng trên thanh tối, như biểu tượng thanh menu macOS.
// Service worker không thấy chế độ sáng hay tối, nên một trang ẩn (offscreen.html) theo dõi rồi báo về đây; cửa sổ nhỏ cũng báo.
function toolbarIcon (dark) {
  const tone = dark ? 'light' : 'dark'
  chrome.action.setIcon({ path: { 16: 'icons/toolbar-' + tone + '-16.png', 32: 'icons/toolbar-' + tone + '-32.png' } }).catch(() => {})
}
async function watchTheme () {
  if (!chrome.offscreen) return
  try {
    if (await chrome.offscreen.hasDocument()) return
    await chrome.offscreen.createDocument({ url: 'offscreen.html', reasons: ['MATCH_MEDIA'], justification: 'Pick the toolbar icon that shows on a light or dark toolbar' })
  } catch (e) {
    // already open (two wake-ups at once) or not allowed: the popup still reports the mode when it opens
    // đã mở (hai lần thức cùng lúc) hoặc không được phép: cửa sổ nhỏ vẫn báo chế độ khi mở
  }
}
watchTheme()

// One beat at a time: the alarm and the popup can ask together, and two answers must not overwrite each other.
// Mỗi lần một nhịp: báo thức và cửa sổ nhỏ có thể cùng hỏi, hai câu trả lời không được ghi đè nhau.
let running = Promise.resolve()
function serial (work) {
  running = running.then(() => langReady).then(work, work)
  return running
}

function ensureAlarm () {
  chrome.alarms.get(ALARM, a => {
    if (!a) chrome.alarms.create(ALARM, { periodInMinutes: ManagerCore.POLL_MINUTES, delayInMinutes: ManagerCore.POLL_MINUTES })
  })
}

chrome.runtime.onInstalled.addListener(() => {
  ensureAlarm()
  serial(() => manager.tick())
})
chrome.runtime.onStartup.addListener(() => {
  ensureAlarm()
  serial(() => manager.tick())
})
chrome.alarms.onAlarm.addListener(a => {
  if (a.name === ALARM) serial(() => manager.tick())
})
ensureAlarm()

// a new language from the popup: load its words, then redraw the icon's title in it
// ngôn ngữ mới từ cửa sổ nhỏ: nạp chữ của nó, rồi vẽ lại tiêu đề biểu tượng
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local' || !changes[ManagerCore.LANG_KEY]) return
  langReady = loadLang()
  serial(async () => manager.showBadge(await manager.load()))
})

// Chrome closes the popup while it asks for access to the board, so the popup's own code stops there.
// The popup notes the address first; once access is given, the pairing starts here and the code is waiting when the popup opens again.
// Chrome đóng cửa sổ nhỏ trong lúc hỏi quyền vào bảng, nên code của cửa sổ dừng ở đó.
// Cửa sổ ghi lại địa chỉ trước; được cấp quyền xong thì việc ghép bắt đầu ở đây, mở lại cửa sổ là đã có mã.
const PENDING_KEY = 'pendingPairing'
const PENDING_MS = 10 * 60 * 1000
async function pairPending () {
  const x = await chrome.storage.session.get(PENDING_KEY)
  const p = x[PENDING_KEY]
  if (!p || !p.origin) return null
  if (p.error || !(Date.now() - p.at < PENDING_MS)) {
    // an error from a pairing started while the popup was closed is shown once, then forgotten
    // lỗi của lần ghép chạy khi cửa sổ đã đóng chỉ hiện một lần rồi bỏ
    await chrome.storage.session.remove(PENDING_KEY)
    return p.error ? { error: p.error } : null
  }
  if (!(await chrome.permissions.contains({ origins: [ManagerCore.originPattern(p.origin)] }))) return null
  await chrome.storage.session.remove(PENDING_KEY)
  const before = await manager.load()
  const result = await manager.startPairing(p.origin)
  if (result && result.error) {
    await chrome.storage.session.set({ [PENDING_KEY]: { origin: p.origin, error: result.error } })
    return result
  }
  // access to an older address is given back, so only the current board stays allowed; only now, after the old key was revoked there
  // trả lại quyền của địa chỉ cũ, để chỉ còn bảng hiện tại được phép; chỉ làm lúc này, sau khi khoá cũ đã bị thu hồi ở đó
  if (before.boardUrl && ManagerCore.originPattern(before.boardUrl) !== ManagerCore.originPattern(p.origin)) {
    chrome.permissions.remove({ origins: [ManagerCore.originPattern(before.boardUrl)] })
  }
  return result
}
chrome.permissions.onAdded.addListener(() => { serial(pairPending) })

async function openBoard () {
  const s = await manager.load()
  if (s.boardUrl) await chrome.tabs.create({ url: s.boardUrl + '/board' })
}

chrome.notifications.onClicked.addListener(id => {
  chrome.notifications.clear(id)
  openBoard()
})

// Messages from the popup. Only the extension's own pages can send them.
// Tin nhắn từ cửa sổ nhỏ. Chỉ trang của chính tiện ích gửi được.
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (sender.id !== chrome.runtime.id || !msg || typeof msg.type !== 'string') return false
  if (msg.type === 'theme') {
    toolbarIcon(msg.dark === true)
    return false
  }
  const jobs = {
    refresh: () => manager.tick(),
    pairPending: () => pairPending(),
    saveSettings: () => manager.saveSettings(msg.settings),
    forget: () => manager.forget(),
    miniPage: () => manager.miniPage(msg.lang),
    wallData: () => manager.wallData(),
    state: () => manager.load(),
    openBoard: () => openBoard()
  }
  const job = jobs[msg.type]
  if (!job) return false
  serial(job).then(result => reply({ ok: true, result }), e => reply({ ok: false, error: String(e && e.message) }))
  return true
})
