"""HTML pages and their scripts: login, board, TV, small window, 3D and admin.
Trang HTML và script đi kèm: đăng nhập, bảng, TV, khung nhỏ, 3D và quản trị."""

import html
import json
import re
from datetime import datetime

from board.assets import UI_VERSION, asset_version
from board.devices import group_by_person, read_all_devices
from board.lang import current_lang, tx
from board.security import WALL
from board.settings import (
    LOCAL_TZ,
    MINI_NOTIFY_MINUTES,
    OFFLINE_SECONDS,
    STALE_DEVICE_SECONDS,
    USD_RATE,
)
from board.stores import ACCOUNTS, TV, is_tv
from board.views import role_view

CSS = """
:root{--bg:#050c13;--fg:#cfe9ef;--muted:#6f8d99;--border:rgba(94,214,232,.14);--cell:rgba(12,26,36,.82);--green:#3df5a7;--yellow:#ffc24b;--red:#ff5a7a;--cyan:#5ee6f0}
*{box-sizing:border-box}
body{margin:0;color:var(--fg);font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;
  background:radial-gradient(ellipse at 50% -10%,#0d2230 0,#050c13 60%) fixed,#050c13}
main{max-width:1440px;margin:0 auto;padding:22px 16px}
h1{font-size:15px;margin:0 0 4px;letter-spacing:.28em;color:#e8fbff;text-transform:uppercase;text-shadow:0 0 12px rgba(94,230,240,.35)}
.muted{color:var(--muted);font-size:12px}
.card{position:relative;background:linear-gradient(180deg,rgba(16,34,46,.82),rgba(7,16,24,.88));border:1px solid var(--border);border-radius:10px;overflow-x:auto;margin-top:16px}
.card::before{content:'';position:absolute;left:14px;top:0;width:64px;height:2px;background:var(--cyan);box-shadow:0 0 10px var(--cyan)}
table{border-collapse:collapse;width:100%;min-width:900px}
th,td{padding:9px 8px;text-align:left;border-bottom:1px solid rgba(94,214,232,.07);white-space:nowrap}
td{font-size:13px}
/* long text columns wrap so the whole table fits one screen */
/* cột chữ dài được xuống dòng để cả bảng vừa một màn hình */
th,td.person{white-space:normal}td.person{min-width:170px;max-width:260px;overflow-wrap:break-word}td.person .ip,td.person .account,td .note{display:block}
/* Plugin column: one block per device, notes wrap inside the column / cột Plugin: mỗi máy một khối, chữ phụ xuống dòng trong cột */
td.pv{white-space:normal;min-width:150px;max-width:300px}.device+.device{margin-top:7px}
.account{color:#a9cbd4;font-size:12px}
.note{color:var(--muted);font-size:11.5px}
th{font-size:10.5px;color:#8fe3ee;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:rgba(94,230,240,.05)}
tr:last-child td{border-bottom:0}tfoot td{font-weight:700;color:#e8fbff;border-top:1px solid rgba(94,214,232,.14)}
.ip{color:var(--muted);font-size:12px}
.tag{font-size:10px;border:1px solid rgba(94,214,232,.3);border-radius:4px;padding:0 4px;margin-left:6px;color:var(--cyan);letter-spacing:.08em}
.working{color:var(--green);text-shadow:0 0 6px rgba(61,245,167,.4)}.waiting{color:var(--yellow);text-shadow:0 0 6px rgba(255,194,75,.4)}.off{color:var(--muted)}.error{color:var(--red)}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.actions{display:flex;gap:8px;flex-wrap:wrap}
/* narrow screens cannot fit 9 columns (phones, folding screens): one card per person, totals first; judged by width */
/* màn hẹp không đủ chỗ cho 9 cột (điện thoại, màn gập): mỗi người một thẻ, tổng lên đầu; xét theo bề ngang, không theo dòng máy */
@media (max-width:1060px){
  .card{overflow:visible}
  table{display:flex;flex-direction:column;min-width:0}
  thead{display:none}
  tfoot{display:block;order:-1;border-bottom:1px solid rgba(94,214,232,.2)}
  tbody{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
  tr{display:block;padding:12px 14px;border-bottom:1px solid rgba(94,214,232,.1);min-width:0}
  td{display:grid;grid-template-columns:104px minmax(0,1fr);gap:8px;padding:3px 0;border:0!important;text-align:left!important;white-space:normal;overflow-wrap:anywhere}
  td::before{content:attr(data-label);color:var(--muted);font-size:11.5px;font-weight:400}
  td.person,td.muted{display:block;max-width:none;font-size:14px;padding-bottom:6px}
  td.person::before,td.muted::before{content:none}
  td:empty{display:none}
  tbody td .note{display:inline;margin-left:6px}tfoot td .note{display:inline;margin-left:6px}
}
.actions a,.actions button{font:inherit;font-size:11px;letter-spacing:.08em;color:var(--fg);background:rgba(94,230,240,.06);border:1px solid var(--border);border-radius:6px;padding:6px 11px;cursor:pointer;text-decoration:none;white-space:nowrap}
.actions a:hover,.actions button:hover{border-color:var(--cyan)}
"""


def render_page(title: str, body: str, auto_refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="60">' if auto_refresh else ""
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">%s<title>%s</title><style>%s</style></head>'
            '<body><main>%s</main></body></html>' % (meta, html.escape(title), CSS, body)).encode()


CSS_LOGIN = """
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:flex;align-items:center;justify-content:center;padding:16px;color:#cfe9ef;
  font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;
  background:radial-gradient(ellipse at 50% -10%,#0d2230 0,#050c13 62%),#050c13}
/* faint grid and a vertical scan line, like a monitoring screen */
/* lưới mờ và vạch quét chạy dọc như màn hình giám sát */
body::before{content:'';position:fixed;inset:0;pointer-events:none;opacity:.5;
  background:linear-gradient(rgba(94,214,232,.05) 1px,transparent 1px) 0 0/44px 44px,linear-gradient(90deg,rgba(94,214,232,.05) 1px,transparent 1px) 0 0/44px 44px}
body::after{content:'';position:fixed;left:0;right:0;height:120px;top:-120px;pointer-events:none;
  background:linear-gradient(transparent,rgba(94,230,240,.06),transparent);animation:scan 6s linear infinite}
@keyframes scan{to{top:100%}}
@keyframes blink{50%{opacity:.25}}
.login-box{position:relative;width:100%;max-width:400px;padding:26px 26px 22px;border-radius:12px;
  background:linear-gradient(180deg,rgba(16,34,46,.86),rgba(7,16,24,.92));border:1px solid rgba(94,214,232,.2);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 0 40px rgba(0,190,230,.08)}
.login-box::before{content:'';position:absolute;left:22px;top:0;width:86px;height:2px;background:#5ee6f0;box-shadow:0 0 12px #5ee6f0}
.login-box::after{content:'';position:absolute;right:12px;top:12px;width:6px;height:6px;border-radius:50%;background:#5ee6f0;opacity:.6}
.top{display:flex;align-items:center;gap:10px;margin-bottom:18px}
.dots{display:flex;gap:5px}.dots i{width:7px;height:7px;border-radius:50%;background:#6f8d99}.dots i:first-child{background:#5ee6f0}
.pill{font-size:10.5px;letter-spacing:.14em;padding:2px 9px;border-radius:20px;border:1px solid rgba(255,194,75,.45);color:#ffc24b;margin-left:auto}
.pill b{display:inline-block;width:6px;height:6px;border-radius:50%;background:#ffc24b;margin-right:6px;box-shadow:0 0 8px #ffc24b;animation:blink 1.6s infinite}
h1{margin:0;font-size:16px;font-weight:800;letter-spacing:.3em;color:#e8fbff;text-shadow:0 0 12px rgba(94,230,240,.35)}
.sub{margin:4px 0 22px;font-size:10.5px;letter-spacing:.24em;color:#6f8d99}
label{display:block;font-size:11px;letter-spacing:.16em;color:#8fe3ee;margin-bottom:8px}
input.account{font:600 16px ui-monospace,Menlo,Consolas,monospace!important;letter-spacing:.02em!important;text-indent:0!important;text-align:left!important}
input{width:100%;font:800 30px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.62em;text-indent:.62em;text-align:center;
  padding:12px 6px;border-radius:8px;border:1px solid rgba(94,214,232,.28);background:rgba(3,10,16,.8);color:#5ee6f0;outline:none;
  caret-color:#3df5a7;text-shadow:0 0 10px rgba(94,230,240,.45)}
input:focus{border-color:#5ee6f0;box-shadow:0 0 0 3px rgba(94,230,240,.12),0 0 18px rgba(94,230,240,.18)}
input::placeholder{color:#24414c;text-shadow:none}
.hint{margin:10px 0 18px;font-size:12px;color:#6f8d99}
button{width:100%;font:700 13px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.24em;padding:12px;border-radius:8px;cursor:pointer;
  color:#03140d;background:linear-gradient(90deg,#3df5a7,#5ee6f0);border:0;box-shadow:0 0 22px rgba(61,245,167,.25)}
button:hover{filter:brightness(1.08)}
.error{margin:0 0 14px;padding:8px 10px;border-radius:6px;font-size:12.5px;color:#ff8aa0;border:1px solid rgba(255,90,122,.45);background:rgba(255,90,122,.07)}
.error::before{content:'[ DENIED ] ';color:#ff5a7a;font-weight:700}
.foot{display:flex;justify-content:space-between;margin-top:18px;padding-top:12px;border-top:1px solid rgba(94,214,232,.08);font-size:10px;letter-spacing:.14em;color:#4f6b76}
.foot b{color:#3df5a7;font-weight:600}
.off{font-size:13px;color:#cfe9ef}.off code{color:#ffc24b}
.lang-switch{position:fixed;top:10px;right:12px;display:flex;gap:4px;z-index:2}
.lang-switch button{width:auto;font:600 10.5px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.1em;padding:3px 8px;border-radius:5px;
  color:#6f8d99;background:transparent;border:1px solid rgba(94,214,232,.2);box-shadow:none}
.lang-switch button.on{color:#5ee6f0;border-color:#5ee6f0;cursor:default}
@media (prefers-reduced-motion:reduce){body::after,.pill b{animation:none}}
"""


def page_login(error: str = "") -> bytes:
    """The OTP login page, in the same style as the dashboard.
    Trang nhập mã OTP, cùng phong cách bảng điều khiển."""
    head = ('<div class="top"><div class="dots"><i></i><i></i><i></i></div>'
           '<span class="pill"><b></b>AUTH REQUIRED</span></div>'
           '<h1>AI WORKER</h1><p class="sub">AGENT OPERATIONS MATRIX · SECURE ACCESS</p>')
    footer = ('<p class="hint"><a href="/tv" style="color:inherit">' + html.escape(tx("Wall screen: pair with a code")) + '</a></p>'
            '<div class="foot"><span>2FA · TOTP 30S</span><span>' + html.escape(tx("COMPANY NETWORK ONLY")) + ' · <b>●</b></span></div>')
    if not ACCOUNTS.d.get("accounts"):
        body = ('<div class="login-box">' + head + '<p class="off">' + tx("No account yet. Your IT team runs {command} on the server.",
                command='<code>sudo bash manage-otp.sh --rescue admin-name</code>') + '</p>' + footer + '</div>')
    else:
        body = ('<form class="login-box" method="post" action="/login">' + head +
                '<label for="account">&gt; ACCOUNT</label>'
                '<input id="account" class="account" name="account" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="60" required autofocus>'
                '<label for="code">&gt; ACCESS CODE</label>'
                '<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" '
                'placeholder="••••••" required>'
                '<p class="hint">' + html.escape(tx("Enter your account name and the 6-digit code from the Google Authenticator app.")) + '</p>'
                '%s<button>AUTHENTICATE ▸</button>' % ('<p class="error">%s</p>' % html.escape(error) if error else "") + footer + '</form>')
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Worker · Secure access</title>'
            '<style>%s</style></head><body>%s<script src="/login.js"></script></body></html>' % (CSS_LOGIN, body)).encode()


def page_tv(ua: str = "") -> bytes:
    # only a computer plugged into a TV can use this file; a smart TV and a phone do not see it
    # chỉ máy tính cắm TV mới dùng được file này; TV thông minh và điện thoại thì không hiện
    install_html = ""
    if not is_tv(ua):
        if "Windows" in ua:
            install_html = '<a href="/tv/install-windows.bat" download="AI-Worker-TV.bat" style="color:inherit">' + html.escape(tx("Download the file for Windows")) + '</a>'
        elif "Macintosh" in ua:
            install_html = '<a href="/tv/install-mac.zip" download="AI-Worker-TV.zip" style="color:inherit">' + html.escape(tx("Download the file for macOS")) + '</a>'
    if install_html:
        install_html = '<p>' + tx("A computer plugged into the TV, opens full screen when it starts: {link}", link=install_html) + '</p>'
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(tx("AI Worker · Pair a screen")) + '</title>'
            '<style>%s #tv{position:relative;text-align:center;padding:16px}#tv-code{font-size:min(9vw,12vh);font-weight:700;letter-spacing:.04em;color:#e8fbff;white-space:nowrap}'
            '#tv p{margin:8px 0;font-size:min(3vw,20px)}#tv-left{color:#7f9aa5}#tv-qr{display:block;width:min(46vh,70vw);height:min(46vh,70vw);margin:0 auto 8px;background:#fff;border-radius:8px;image-rendering:pixelated}#tv-qr[hidden]{display:none}</style></head><body>'
            '<div id="tv"><p>' % CSS_LOGIN + html.escape(tx("Scan with a phone camera on the company network, or enter the code on the Admin page")) +
            '</p><img id="tv-qr" alt="' + html.escape(tx("QR code to pair the screen")) + '" hidden>'
            '<div id="tv-code">····-····</div><p id="tv-status">' + html.escape(tx("Requesting a code…")) + '</p>'
            '<p id="tv-left"></p><p>' + html.escape(tx("Only an admin can approve. Do not share the code with anyone.")) + '</p>' + install_html + '</div>'
            '<script src="/tv-qr.js"></script><script src="/tv.js"></script></body></html>').encode()


def mini_state(token: str, now: float) -> dict:
    """What the menu bar script needs each minute: who is waiting and since when, and this computer's notification settings.
    Only names as the wall screen shows them.
    Những gì script thanh menu cần mỗi phút: ai đang chờ và từ lúc nào, cùng cài đặt thông báo của máy này. Chỉ có tên như màn hình treo tường."""
    view = role_view(WALL, now)
    waiting = [{"name": p["name"], "since": p.get("waitingSince")} for p in view["people"] if p.get("waiting") and p.get("status") != "offline"]
    working = sum(1 for p in view["people"] if p.get("working") and p.get("status") != "offline")
    return {"waiting": waiting, "working": working, **TV.mini_settings(token, now)}


def ext_state(now: float) -> dict:
    """What the manager browser extension reads each minute: a part of the wall view, never more. Only people waiting or working,
    by the name the wall screen shows; the extension counts how long they wait by itself.
    Những gì tiện ích trình duyệt cho quản lý đọc mỗi phút: một phần của phần treo tường, không bao giờ hơn. Chỉ người đang chờ hoặc đang làm,
    theo tên như màn hình treo tường; tiện ích tự đếm họ đã chờ bao lâu."""
    view = role_view(WALL, now)
    people = [{"name": p["name"], "waiting": bool(p.get("waiting")), "working": bool(p.get("working"))}
              for p in view["people"] if p.get("status") != "offline" and (p.get("waiting") or p.get("working"))]
    return {"updatedAt": view.get("updatedAt"), "people": people}




def page_mini_pair() -> bytes:
    """The page the unpaired menu bar opens: the manager enters their own account and OTP to pair this computer.
    The pairing code comes in the address after #, so it never reaches the server's logs.
    Trang thanh menu chưa ghép mở ra: quản lý nhập tài khoản và OTP của chính mình để ghép máy này.
    Mã ghép nằm sau dấu # trong địa chỉ, nên không bao giờ vào nhật ký của máy chủ."""
    words = {"done": tx("Paired. The icon changes within a minute; you can close this window."),
             "nocode": tx("Open this page from the menu bar icon."), "sending": tx("Checking…"),
             "fail": tx("Could not reach the server, try again.")}
    return ('<!doctype html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>%s</title><style>'
            ':root{--bg:#f6f6f4;--fg:#1d1d1b;--muted:#6b6a65;--line:rgba(0,0,0,.12);--accent:#1a56c8;--bad:#a32d2d}'
            '@media (prefers-color-scheme:dark){:root{--bg:#1f1f1e;--fg:#ecebe6;--muted:#a3a29b;--line:rgba(255,255,255,.14);--accent:#4a7fd6;--bad:#f09595}}'
            '*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Ubuntu,sans-serif}'
            'main{padding:16px;max-width:420px;margin:0 auto}h1{font-size:16px;margin:0 0 4px}p{margin:6px 0;color:var(--muted)}'
            '.code-label{margin-top:12px;font-size:12px;color:var(--muted)}#code{font:600 18px/1.2 ui-monospace,Menlo,monospace;letter-spacing:.06em;color:var(--muted);margin:2px 0 6px}'
            'label{display:block;margin:10px 0 4px;color:var(--fg)}input{width:100%%;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:7px;background:transparent;color:var(--fg)}'
            'button{margin-top:14px;width:100%%;font:inherit;padding:9px;border:0;border-radius:7px;background:var(--accent);color:#fff;cursor:pointer}'
            'html.app,html.app body{background:transparent}#msg{min-height:1.4em;margin-top:10px}#msg.bad{color:var(--bad)}small{display:block;margin-top:14px;color:var(--muted)}'
            '</style></head><body data-words="%s"><main><h1>%s</h1><p>%s</p><div class="code-label">%s</div><div id="code" aria-live="polite"></div>'
            '<form id="pair"><label for="account">%s</label><input id="account" autocomplete="username" required>'
            '<label for="otp">%s</label><input id="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required>'
            '<button type="submit">%s</button></form><div id="msg" role="status"></div><small>%s</small></main>'
            '<script src="/mini-pair.js"></script></body></html>' % (
                current_lang(), html.escape(tx("Pair this computer")), html.escape(json.dumps(words, ensure_ascii=False), quote=True),
                html.escape(tx("Pair this computer")), html.escape(tx("Use your own account and the 6-digit code in Google Authenticator. No admin needs to approve.")),
                html.escape(tx("This computer's code (no need to type it)")),
                html.escape(tx("Account")), html.escape(tx("6-digit code")), html.escape(tx("This computer is mine")),
                html.escape(tx("The computer will see short names, status and costs, like a wall screen. An admin can see and revoke it on the Admin page.")))).encode()


MINI_PAIR_JS = """
(function () {
  'use strict'
  if (/AIWorkerApp\\//.test(navigator.userAgent)) document.documentElement.classList.add('app')
  var words = JSON.parse(document.body.getAttribute('data-words') || '{}')
  var m = /^#c=(\\d{8})$/.exec(location.hash)
  var code = m ? m[1] : ''
  var msg = document.getElementById('msg')
  document.getElementById('code').textContent = code ? code.slice(0, 4) + '-' + code.slice(4) : ''
  if (!code) { msg.textContent = words.nocode; msg.className = 'bad'; document.getElementById('pair').hidden = true; return }
  document.getElementById('pair').addEventListener('submit', function (e) {
    e.preventDefault()
    msg.textContent = words.sending
    msg.className = ''
    fetch('/mini/pair', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: document.getElementById('account').value, otp: document.getElementById('otp').value, code: code }) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d } }) })
      .then(function (x) {
        msg.textContent = x.ok ? words.done : (x.d && x.d.error) || words.fail
        msg.className = x.ok ? '' : 'bad'
        if (x.ok) document.getElementById('pair').hidden = true
        else document.getElementById('otp').value = ''
      })
      .catch(function () { msg.textContent = words.fail; msg.className = 'bad' })
  })
})()
"""


def page_mini(paired: bool, browser: bool = False) -> bytes:
    """The small window under the menu bar icon (about 360x480). Its words come translated in data-words; the numbers come from /data.
    browser=True is the same window for the manager browser extension (/ext/mini): only the unpair words say "this browser".
    Khung nhỏ dưới biểu tượng thanh menu (khoảng 360x480). Chữ được dịch sẵn trong data-words; số liệu lấy từ /data.
    browser=True là cùng khung đó cho tiện ích trình duyệt của quản lý (/ext/mini): chỉ chữ bỏ ghép ghi "trình duyệt này"."""
    unpair = tx("Unpair this browser") if browser else tx("Unpair this computer")
    # in the apps the three buttons (unpair, quit, uninstall) share one row, so their labels are short; the questions stay in full
    # trong app ba nút (bỏ ghép, thoát, gỡ app) nằm cùng một dòng nên chữ trên nút ngắn; câu hỏi vẫn ghi đủ
    words = json.dumps({
        "Waiting": tx("Waiting"),
        "Working": tx("Working"),
        "Quota": tx("Quota"),
        "Cost today": tx("Cost today"),
        "Nobody is waiting": tx("Nobody is waiting"),
        "Nobody is working": tx("Nobody is working"),
        "No quota reading yet": tx("No quota reading yet"),
        "{n} min": tx("{n} min"),
        "just now": tx("just now"),
        "Updated {time}": tx("Updated {time}"),
        "Cannot reach the server": tx("Cannot reach the server"),
        "Notify when a wait passes": tx("Notify when a wait passes"),
        "minutes": tx("minutes"),
        "Open board": tx("Open board"),
        # mini.js looks the words up by these keys; the extension gets its own text under the same key
        # mini.js tra chữ theo các khoá này; tiện ích nhận chữ riêng của nó dưới cùng khoá
        "Unpair this computer": unpair,
        "Remove the app": tx("Remove the app"),
        "Cancel": tx("Cancel"),
        "Unpair this computer? You will need a new code from an admin.": tx("Unpair this browser? You will need a new code from an admin.") if browser
        else tx("Unpair this computer? You will need a new code from an admin."),
        "Saved": tx("Saved"),
        "Could not save": tx("Could not save"),
        "5-hour": tx("5-hour"),
        "7-day": tx("7-day"),
        "7-day Opus": tx("7-day Opus"),
        "7-day Sonnet": tx("7-day Sonnet"),
        "spending": tx("spending"),
        "Whole team": tx("Whole team"),
        "offline": tx("offline"),
        "Settings": tx("Settings"),
        "Remove the app from this Mac? This computer is unpaired and the app goes to the Trash.": tx("Remove the app from this Mac? This computer is unpaired and the app goes to the Trash."),
        "Remove the app from this computer? This computer is unpaired and the app is removed.": tx("Remove the app from this computer? This computer is unpaired and the app is removed."),
    }, ensure_ascii=False)
    head = ('<!doctype html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>%s</title><link rel="stylesheet" href="/static/mini.css?v=__V_MINI_CSS__"></head>'
            % (current_lang(), html.escape(tx("AI Worker")))).replace("__V_MINI_CSS__", asset_version("mini.css"))
    if not paired:
        return (head + '<body><main class="mini" style="font:14px -apple-system,Segoe UI,sans-serif;padding:16px"><header><span class="logo" aria-hidden="true"></span><b>%s</b></header>'
                '<p class="empty">%s</p></main></body></html>' % (
                    html.escape(tx("AI Worker")), html.escape(tx("This computer is not paired. Click the menu bar icon to see the pairing code, and ask an admin to approve it."))
                )).encode()
    return (head + '<body data-words="%s" data-lang="%s" data-rate="%s"><main class="mini">'
            '<header><span class="logo" aria-hidden="true"></span><div><b>%s</b><small id="updated"></small></div><span id="badge" class="badge" hidden></span></header>'
            '<nav role="tablist">'
            '<button role="tab" data-tab="waiting" aria-selected="true" title="%s"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></button>'
            '<button role="tab" data-tab="working" title="%s"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 5l12 7-12 7z"/></svg></button>'
            '<button role="tab" data-tab="quota" title="%s"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/></svg></button>'
            '<button role="tab" data-tab="cost" title="%s"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></svg></button>'
            '<button role="tab" data-tab="settings" title="%s"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2.2"/><path stroke-width="3" stroke-linecap="butt" d="M12 2.6v3M12 18.4v3M2.6 12h3M18.4 12h3M5.4 5.4l2.1 2.1M16.5 16.5l2.1 2.1M5.4 18.6l2.1-2.1M16.5 7.5l2.1-2.1"/></svg></button></nav>'
            '<h2 id="title"></h2><ul id="list"></ul>'
            '<section id="settings" class="settings" hidden>'
            '<div class="row"><label><input type="checkbox" id="notify"> <span>%s</span></label> <select id="minutes">%s</select> <span>%s</span></div>'
            '<div class="row app-only"><label><input type="checkbox" id="login"> <span>%s</span></label></div>'
            '<div class="row"><label for="lang">%s</label> <select id="lang"><option value="en">English</option><option value="vi">Tiếng Việt</option></select></div>'  # i18n-allow: each language is named in itself
            '<small id="saved" role="status"></small>'
            '<div class="actions"><button id="unpair" class="btn">%s</button><button id="quit" class="btn app-only">%s</button><button id="uninstall" class="btn danger app-only">%s</button></div></section>'
            '<footer><a class="btn" href="/board" target="_blank" rel="noopener">%s</a></footer>'
            '</main><script src="/static/mini.js?v=__V_MINI_JS__"></script></body></html>' % (
                html.escape(words, quote=True), current_lang(), USD_RATE, html.escape(tx("AI Worker")),
                html.escape(tx("Waiting")), html.escape(tx("Working")), html.escape(tx("Quota")), html.escape(tx("Cost today")), html.escape(tx("Settings")),
                html.escape(tx("Notify when a wait passes")),
                "".join('<option value="%d">%d</option>' % (m, m) for m in MINI_NOTIFY_MINUTES), html.escape(tx("min")),
                html.escape(tx("Start at login")), html.escape(tx("Language")), html.escape(unpair if browser else tx("Unpair")), html.escape(tx("Quit")), html.escape(tx("Uninstall")),
                html.escape(tx("Open board")))).replace("__V_MINI_JS__", asset_version("mini.js")).encode()


# EN / VI switch for the two public pages, which do not load i18n.js. Both pages run this from their own script (the CSP forbids inline scripts).
# Nút chuyển EN / VI cho hai trang công khai, không nạp i18n.js. Cả hai trang chạy đoạn này trong script riêng (CSP cấm script nằm trong trang).
LANG_SWITCH_JS = """
  function langSwitch() {
    var box = document.createElement('div')
    box.className = 'lang-switch'
    var current = document.documentElement.lang === 'vi' ? 'vi' : 'en'
    ;['en', 'vi'].forEach(function (code) {
      var b = document.createElement('button')
      b.type = 'button'
      b.textContent = code.toUpperCase()
      b.title = code === 'vi' ? 'Ti\\u1ebfng Vi\\u1ec7t' : 'English'
      b.setAttribute('aria-pressed', String(code === current))
      if (code === current) b.className = 'on'
      b.addEventListener('click', function () {
        if (code === current) return
        document.cookie = 'lang=' + code + '; path=/; max-age=31536000; SameSite=Lax'
        if (location.pathname === '/login') location.replace('/')
        else location.reload()
      })
      box.appendChild(b)
    })
    document.body.appendChild(box)
  }
  langSwitch()
"""


def js_tv() -> bytes:
    """Script of the /tv page. Built per request, so the text follows the visitor's language.
    Script của trang /tv. Dựng theo từng yêu cầu, nên chữ theo ngôn ngữ của người xem."""
    text = {
        "noCode": tx("Could not get a code, try again later."),
        "waiting": tx("Waiting for an admin to approve"),
        "lost": tx("Connection lost, retrying…"),
        "paired": tx("Paired: {name}"),
        "changes": tx("Code changes in {time}"),
    }
    return (JS_TV.replace("__TEXT__", json.dumps(text, ensure_ascii=False)).replace("__LANG_SWITCH__", LANG_SWITCH_JS)).encode()


JS_TV = """(function () {
  var T = __TEXT__
  function fill(s, o) { return s.replace(/\\{(\\w+)\\}/g, function (all, k) { return k in o ? o[k] : all }) }
  var codeEl = document.getElementById('tv-code'), statusEl = document.getElementById('tv-status'), leftEl = document.getElementById('tv-left'), qr = document.getElementById('tv-qr')
  // the code sits after the #, so it never reaches the server's access log
  // mã nằm sau dấu #, nên không đi vào nhật ký truy cập của máy chủ
  function drawQr(num) {
    try {
      var q = window.qrcode(0, 'M')
      q.addData(location.origin + '/admin#pair=' + num)
      q.make()
      qr.src = q.createDataURL(8)
      qr.hidden = false
    } catch (e) {
      qr.hidden = true
    }
  }
  var endsAt = 0, timer = null
  function post(url) {
    return fetch(url, { method: 'POST', credentials: 'same-origin' }).then(function (r) {
      return r.json().catch(function () { return {} }).then(function (d) { d.httpStatus = r.status; return d })
    })
  }
  function requestCode() {
    clearTimeout(timer)
    post('/tv/request-code').then(function (d) {
      if (!d.code) {
        statusEl.textContent = d.error || T.noCode
        timer = setTimeout(requestCode, 60000)
        return
      }
      codeEl.textContent = d.code.slice(0, 4) + '-' + d.code.slice(4)
      drawQr(d.code)
      statusEl.textContent = T.waiting
      endsAt = Date.now() + d.secondsLeft * 1000
      timer = setTimeout(poll, 10000)
    }).catch(function () {
      statusEl.textContent = T.lost
      timer = setTimeout(requestCode, 15000)
    })
  }
  function poll() {
    post('/tv/poll').then(function (d) {
      if (d.status === 'done') {
        statusEl.textContent = fill(T.paired, { name: d.name })
        setTimeout(function () { location.href = '/' }, 3000)
      } else if (d.status === 'pending') {
        timer = setTimeout(poll, 10000)
      } else {
        requestCode()
      }
    }).catch(function () { timer = setTimeout(poll, 15000) })
  }
  setInterval(function () {
    var s = Math.max(0, Math.round((endsAt - Date.now()) / 1000))
    leftEl.textContent = endsAt ? fill(T.changes, { time: Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2) }) : ''
  }, 1000)
__LANG_SWITCH__
  requestCode()
})()
"""


JS_LOGIN = b"""(function () {
  // quet ma TV khi chua dang nhap, hoac trinh duyet khong gui cookie vi link mo tu app camera
  var h = location.hash
  if (/^#pair=[0-9]{8}$/.test(h)) {
    try { sessionStorage.setItem('pair', h.slice(6)) } catch (e) {}
    if (location.search.indexOf('open=1') < 0) return location.replace('/admin?open=1' + h)
  }
""" + LANG_SWITCH_JS.encode() + b"""  var o = document.getElementById('code')
  if (!o) return
  var sent = false
  o.addEventListener('input', function () {
    var digits = o.value.replace(/[^0-9]/g, '').slice(0, 6)
    if (o.value !== digits) o.value = digits
    if (digits.length === 6 && !sent && document.getElementById('account').value.trim()) {
      sent = true
      o.readOnly = true
      o.form.submit()
    }
  })
  o.addEventListener('keydown', function (e) {
    if (e.key.length === 1 && !/[0-9]/.test(e.key) && !e.ctrlKey && !e.metaKey) e.preventDefault()
  })
})()
"""


def format_money(amount: float) -> str:
    """Vietnamese: dong at USD_RATE. English: US dollars, no conversion.
    Tiếng Việt: đồng theo USD_RATE. Tiếng Anh: đô la Mỹ, không quy đổi."""
    if current_lang() != "vi":
        return "${:,.2f}".format(amount)
    return tx("{amount} VND", amount="{:,.0f}".format(amount * USD_RATE).replace(",", "."))


def compact(n: int) -> str:
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%.0fK" % (n / 1e3) if n >= 1e3 else str(n)


def page_3d(viewer_name: str, role: str) -> bytes:
    """The dashboard of the whole team (drawn by static/ops.js); with no file it falls back to the text board.
    Bảng điều khiển vận hành cả team (vẽ bằng static/ops.js); không có file thì quay về bảng chữ."""
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Worker · Operations</title>'
            '<link rel="stylesheet" href="/static/ops.css?v=%s"></head><body class="ops-mode" data-user="%s" data-role="%s" data-ui="%s">'
            '<div id="ops"></div>'
            '<script src="/static/i18n.js?v=%s"></script><script src="/static/ops.vi.js?v=%s"></script>'
            '<script src="/static/ops.js?v=%s"></script><script src="/static/page.js?v=%s"></script>'
            '</body></html>' % (asset_version("ops.css"), html.escape(viewer_name), role, UI_VERSION, asset_version("i18n.js"), asset_version("ops.vi.js"), asset_version("ops.js"), asset_version("page.js"))).encode()


def page_admin(viewer_name: str) -> bytes:
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(tx("AI Worker · Admin")) + '</title>'
            '<link rel="stylesheet" href="/static/admin.css?v=%s"></head><body data-user="%s"><div id="admin"></div>'
            '<script src="/static/i18n.js?v=%s"></script><script src="/static/admin.vi.js?v=%s"></script>'
            '<script src="/static/qrcode.js?v=%s"></script><script src="/static/admin.js?v=%s"></script>'
            '</body></html>' % (asset_version("admin.css"), html.escape(viewer_name), asset_version("i18n.js"), asset_version("admin.vi.js"), asset_version("qrcode.js"), asset_version("admin.js"))).encode()


def window_label(kind: str) -> str:
    if kind == "five_hour":
        return tx("5 hours")
    if kind == "seven_day":
        return tx("7 days")
    if kind == "seven_day_opus":
        return tx("7 days Opus")
    if kind == "seven_day_sonnet":
        return tx("7 days Sonnet")
    if kind == "spend_limit":
        return tx("spending")
    return html.escape(kind)


def quota_cell(quota, now: float) -> str:
    """Quota cell on /board: one line per window ("5 hours 23%" / "7 days 41%"), red from 80%, yellow from 60%; hover to see the reset time.
    Ô hạn mức trên /board: mỗi khung một dòng ("5 giờ 23%" / "7 ngày 41%"), đỏ từ 80%, vàng từ 60%; rê chuột xem giờ làm mới."""
    if not quota:
        return '<span class="off">—</span>'
    part = []
    for c in quota["windows"]:
        css_class = "error" if c["pct"] >= 80 else "waiting" if c["pct"] >= 60 else ""
        title = ""
        if c.get("resetsAt"):
            title = ' title="%s"' % tx("resets at {time}", time=datetime.fromtimestamp(c["resetsAt"] / 1000, LOCAL_TZ).strftime(tx("%H:%M %b %d")))
        part.append('<span class="%s"%s>%s%s %s%%</span>' % (css_class, title, "⚠ " if c["pct"] >= 80 else "", window_label(c["kind"]), "{:g}".format(c["pct"])))
    return "<br>".join(part)


def _version_tuple(version: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", version)[:4])


def latest_plugin_version(rows: list) -> str:
    """Newest plugin version in the team: a device below it has not been updated.
    Bản plugin mới nhất có trong team: máy nào thấp hơn là chưa cập nhật."""
    all_items = [version for r in rows for version in r["pluginVersion"]]
    return max(all_items, key=_version_tuple) if all_items else ""


def physical_devices(r: dict) -> list:
    """Device ids with the same hardware mark become one device: version, IP and time from the newest send; IP histories joined.
    Gộp các mã máy cùng dấu phần cứng thành một máy: phiên bản, IP, lúc gửi lấy theo lần gửi mới nhất; lịch sử IP gộp chung."""
    groups = {}
    for m in r.get("devices", []):
        groups.setdefault(m["mark"], []).append(m)
    out = []
    for items in groups.values():
        newest = max(items, key=lambda m: m["at"])
        seen = {}
        for m in items:
            for e in m.get("ipHistory", []) + ([{"ip": m["ip"], "from": m["at"], "to": m["at"]}] if m["ip"] else []):
                c = seen.setdefault(e["ip"], {"ip": e["ip"], "from": e["from"], "to": e["to"]})
                c["from"], c["to"] = min(c["from"], e["from"]), max(c["to"], e["to"])
        earlier = sorted((e for e in seen.values() if e["ip"] != newest["ip"]), key=lambda e: -e["to"])
        out.append(dict(newest, earlier=earlier, ids=len(items)))
    return out


def active_devices(r: dict, now: float) -> list:
    """This person's devices (merged by mark) that sent within STALE_DEVICE_SECONDS; all of them if none did.
    Các máy (đã gộp theo dấu) của người này còn gửi trong STALE_DEVICE_SECONDS; nếu không máy nào còn gửi thì trả mọi máy."""
    everything = physical_devices(r)
    active = [m for m in everything if now - m["at"] / 1000 < STALE_DEVICE_SECONDS]
    return active or everything


def short_time(at_ms: float, now: float) -> str:
    """HH:MM on the same day, otherwise the date too.
    HH:MM nếu cùng ngày, không thì kèm ngày."""
    t = datetime.fromtimestamp(at_ms / 1000, LOCAL_TZ)
    return t.strftime("%H:%M") if t.date() == datetime.fromtimestamp(now, LOCAL_TZ).date() else t.strftime(tx("%b %d %H:%M"))


def device_version_cell(r: dict, latest_version: str, now: float) -> str:
    """The Plugin column on /board: one device shows only its version; several show one line each with IP, last send and earlier IPs; quiet ones dimmed.
    Cột Plugin trên /board: một máy thì chỉ phiên bản; nhiều máy thì mỗi máy một dòng kèm IP, lần gửi, IP trước; máy lâu không gửi làm mờ."""
    items = sorted(physical_devices(r), key=lambda m: -m["at"])
    if not items:
        return version_cell(r["pluginVersion"], latest_version)
    if len(items) == 1 and not items[0]["earlier"]:
        return version_cell([items[0]["version"]] if items[0]["version"] else [], latest_version)
    lines = []
    for m in items:
        stale = now - m["at"] / 1000 >= STALE_DEVICE_SECONDS
        if not m["version"]:
            version = '<span class="off">%s</span>' % tx("old")
        elif stale:
            version = html.escape(m["version"])
        else:
            version = '<span class="%s">%s</span>' % ("waiting" if _version_tuple(m["version"]) < _version_tuple(latest_version) else "", html.escape(m["version"]))
        sent = short_time(m["at"], now)
        before = ", ".join(tx("{ip} until {time}", ip=html.escape(e["ip"]), time=short_time(e["to"], now)) for e in m["earlier"][:3])
        note = " · ".join(x for x in (html.escape(m["ip"]), html.escape(tx("sent {time}", time=sent))) if x)
        # earlier IPs sit on their own line and wrap, so the column never stretches the table past the screen
        # các IP trước nằm dòng riêng và được xuống dòng, để cột không kéo cả bảng rộng quá màn hình
        note = ' <span class=note>%s</span>' % note + (' <span class=note>%s%s</span>' % (html.escape(tx("before: ")), before) if before else "")
        if stale:
            lines.append('<div class="device off" title="%s">%s%s</div>' % (html.escape(tx("This device has not sent since {time}", time=sent)), version, note))
        else:
            lines.append('<div class=device>%s%s</div>' % (version, note))
    return "".join(lines)


def version_cell(versions: list, latest_version: str) -> str:
    if not versions:
        return '<span class="off" title="%s">%s</span>' % (html.escape(tx("This computer runs an old version that has not reported its version")), tx("old"))
    return ", ".join('<span class="%s">%s</span>' % ("waiting" if _version_tuple(version) < _version_tuple(latest_version) else "", html.escape(version)) for version in versions)


def model_label(model_id: str) -> str:
    """claude-opus-5-5 -> Opus 5.5; an unknown name is kept as it is.
    claude-opus-5-5 -> Opus 5.5; tên lạ giữ nguyên."""
    m = re.match(r"^claude-([a-z]+)-(\d+)(?:-(\d+))?", model_id or "")
    if not m:
        return model_id
    return m.group(1).capitalize() + " " + m.group(2) + ("." + m.group(3) if m.group(3) and len(m.group(3)) < 3 else "")


def page_board(viewer_name: str, now: float) -> bytes:
    rows = group_by_person(read_all_devices(), now)
    latest_version = latest_plugin_version(rows)
    row_html, total = [], {"usdToday": 0.0, "usd7d": 0.0, "tokensIn": 0, "tokensOut": 0, "tasks": [0, 0, 0], "openSessions": 0}
    lit = lambda text: html.escape(text, quote=True).replace("%", "%%")
    label_status, label_model, label_quota, label_today = (lit(x) for x in (tx("Status"), tx("Model"), tx("Quota"), tx("Today")))
    label_tokens, label_tasks, label_updated = (lit(x) for x in (tx("Tokens in / out"), tx("Delegated"), tx("Updated")))
    for r in rows:
        ip = ", ".join(r["lanIps"] or r["ip"])
        device_count = len(active_devices(r, now)) if r.get("devices") else r["deviceCount"]
        stale_count = len(physical_devices(r)) - device_count if r.get("devices") else 0
        if now - r["updatedAt"] / 1000 >= OFFLINE_SECONDS:
            status_text = '<span class="off">%s</span>' % html.escape(tx("offline"))
        elif r["waiting"]:
            status_text = '<span class="waiting">%s</span>' % html.escape(tx("waiting for reply ({n})", n=r["waiting"]))
        elif r["working"]:
            status_text = '<span class="working">%s</span>' % html.escape(tx("working ({n})", n=r["working"]))
        else:
            status_text = html.escape(tx("{n} sessions open", n=r["openSessions"])) if r["openSessions"] else '<span class="off">%s</span>' % html.escape(tx("idle"))
        updated = datetime.fromtimestamp(r["updatedAt"] / 1000, LOCAL_TZ)
        updated_text = updated.strftime("%H:%M") if updated.date() == datetime.fromtimestamp(now, LOCAL_TZ).date() else updated.strftime(tx("%b %d, %Y %H:%M"))
        model_names = ", ".join(model_label(k) for k in sorted(r["models"], key=lambda k: -r["models"][k])) or "—"
        row_html.append((
            "<tr><td class=person>%s %s<span class=account>%s</span>%s</td><td data-label='" + label_status + "'><div>%s</div></td><td data-label='" + label_model + "'><div>%s</div></td><td data-label='" + label_quota + "'><div>%s</div></td>"
            "<td class=num data-label='" + label_today + "'><div>%s<span class=note>%s</span></div></td><td class=num data-label='" + label_tokens + "'><div>%s / %s</div></td>"
            "<td class=num data-label='" + label_tasks + "'><div>%d · %d · %d</div></td><td class=pv data-label='Plugin'><div>%s</div></td><td class=num data-label='" + label_updated + "'><div>%s</div></td></tr>") % (
                html.escape(r["name"]), '<span class="tag">%s</span>' % html.escape(tx("shared")) if r["shared"] else "",
                html.escape(r["account"]).replace("@", "<wbr>@", 1) + (' · ' + html.escape(tx("{n} devices", n=device_count)) if device_count > 1 else "")
                + (' · ' + html.escape(tx("{n} old devices", n=stale_count) if stale_count > 1 else tx("1 old device")) if stale_count else "")
                + ('<br>' + html.escape(tx("entered at install: {accounts}", accounts=", ".join(r["enteredAccounts"]))) if r["enteredAccounts"] else ""),
                '<span class="ip">%s</span>' % html.escape(ip) if ip else "",
                status_text, html.escape(model_names), quota_cell(r["quota"], now), format_money(r["usdToday"]), html.escape(tx("7 days {amount}", amount=format_money(r["usd7d"]))),
                compact(r["tokensIn"]), compact(r["tokensOut"]),
                r["tasks"][0], r["tasks"][1], r["tasks"][2], device_version_cell(r, latest_version, now), updated_text))
        for k in ("usdToday", "usd7d", "tokensIn", "tokensOut", "openSessions"):
            total[k] += r[k]
        total["tasks"] = [a + b for a, b in zip(total["tasks"], r["tasks"])]
    if not row_html:
        row_html.append('<tr><td colspan=9 class="muted">%s</td></tr>' % html.escape(tx("No computer has sent data yet.")))
    now_local = datetime.fromtimestamp(now, LOCAL_TZ)
    if current_lang() == "vi":
        cost_note = tx("costs follow API prices, converted at {rate} VND per USD", rate="{:,.0f}".format(USD_RATE).replace(",", "."))
    else:
        cost_note = tx("costs follow API prices, shown in US dollars")
    body = ((
        '<div class="head"><div><h1>' + lit(tx("AI Worker // detail board")) + '</h1><p class="muted">%s</p></div>'
        '<div class="actions"><a href="/">' + lit(tx("▸ Dashboard")) + '</a><form method="post" action="/logout" style="margin:0"><button>%s</button></form></div></div>'
        '<div class="card"><table><thead><tr><th>' + lit(tx("Person · account · internal IP")) + '</th><th>' + lit(tx("Status")) + '</th><th>' + lit(tx("Model")) + '</th>'
        '<th title="' + lit(tx("Share used of the 5-hour and 7-day windows of the Claude account (subscription plan); at 100% you wait for the reset")) + '">' + lit(tx("Quota")) + '</th>'
        '<th class=num>' + lit(tx("Cost today")) + '</th><th class=num>' + lit(tx("Tokens in / out")) + '</th>'
        '<th class=num title="' + lit(tx("Tasks handed to Gemini · ChatGPT · Gemma today")) + '">' + lit(tx("Delegated")) + '</th>'
        '<th title="' + lit(tx("Plugin version on the computer; yellow means not on the newest version in the team")) + '">Plugin</th><th class=num>' + lit(tx("Updated")) + '</th></tr></thead><tbody>%s</tbody>'
        '<tfoot><tr><td class=person>%s</td><td data-label="' + lit(tx("Open")) + '"><div>%s</div></td><td></td><td></td><td class=num data-label="' + label_today + '"><div>%s<span class=note>%s</span></div></td><td class=num data-label="' + label_tokens + '"><div>%s / %s</div></td>'
        '<td class=num data-label="' + label_tasks + '"><div>%d · %d · %d</div></td><td></td><td></td></tr></tfoot></table></div>'
        '<p class="muted">' + lit(tx("No chat content or file names: staff computers only send numbers.")) + '</p>') % (
            html.escape(tx("Today {date} · updated {time} · refreshes every minute · {cost_note}", date=now_local.strftime(tx("%b %d, %Y")), time=now_local.strftime("%H:%M"), cost_note=cost_note)),
            html.escape(tx("Log out ({name})", name=viewer_name)), "".join(row_html),
            html.escape(tx("Whole team ({n} people)", n=len(rows))), html.escape(tx("{n} open sessions", n=total["openSessions"])), format_money(total["usdToday"]),
            html.escape(tx("7 days {amount}", amount=format_money(total["usd7d"]))), compact(total["tokensIn"]), compact(total["tokensOut"]), *total["tasks"]))
    return render_page(tx("AI Worker dashboard"), body, auto_refresh=True)
