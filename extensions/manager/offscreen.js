// Hidden page: tells the service worker whether the browser is in dark mode, when it opens and whenever that changes.
// A hidden page does not draw, so Chrome may never fire the media query's change event here: the mode is also read every few seconds.
// Trang ẩn: báo cho service worker trình duyệt có đang ở chế độ tối không, lúc mở và mỗi khi đổi.
// Trang ẩn không vẽ nên Chrome có thể không bao giờ phát sự kiện đổi của media query ở đây: chế độ được đọc lại mỗi vài giây.
/* global chrome */
;(function () {
  'use strict'
  const dark = matchMedia('(prefers-color-scheme: dark)')
  let told = null
  const tell = () => {
    if (dark.matches === told) return
    told = dark.matches
    chrome.runtime.sendMessage({ type: 'theme', dark: told }).catch(() => { told = null })
  }
  dark.addEventListener('change', tell)
  setInterval(tell, 5000)
  tell()
})()
