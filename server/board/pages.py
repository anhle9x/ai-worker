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
from board.telegram import bot_name
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
.ok{margin:0 0 14px;padding:8px 10px;border-radius:6px;font-size:12.5px;color:#9ff5cf;border:1px solid rgba(61,245,167,.4);background:rgba(61,245,167,.07)}
.tg-or{text-align:center;margin:14px 0 10px}.unlink{margin:4px 0 18px}a.go{display:block;text-align:center;text-decoration:none;font:700 13px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.24em;padding:12px;margin:0 0 14px;border-radius:8px;color:#03140d;background:linear-gradient(90deg,#3df5a7,#5ee6f0);box-shadow:0 0 22px rgba(61,245,167,.25)}.unlink summary{cursor:pointer;font-size:12px;color:#6f8d99}.unlink[open] summary{margin-bottom:12px}button.quiet{color:#ff8aa0;background:transparent;border:1px solid rgba(255,90,122,.45);box-shadow:none}.tg{display:flex;justify-content:center;min-height:40px}.tg-link{display:block;width:219px;height:40px;border-radius:6px}.tg-face{display:block;width:219px;height:40px}.tg-link:hover .tg-face{filter:brightness(.94)}.tg-link:focus-visible{outline:2px solid #5ee6f0;outline-offset:2px}
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
        body = ('<div class="login-box">' + head + '<p class="off">' + tx("No account yet. An admin runs {command} on the server.",
                command='<code>sudo bash manage-otp.sh --rescue admin-name</code>') + '</p>' + footer + '</div>')
    else:
        body = ('<form class="login-box" method="post" action="/login">' + head +
                '<label for="account">&gt; ACCOUNT</label>'
                # with Telegram on, most people press its button: a focused name box would only open the browser's saved-password list over the page
                # khi bật Telegram, phần lớn người dùng bấm nút đó: ô tên tự nhận con trỏ chỉ làm trình duyệt mở danh sách mật khẩu đã lưu đè lên trang
                '<input id="account" class="account" name="account" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="60" required' +
                ('>' if bot_name() else ' autofocus>') +
                '<label for="code">&gt; ACCESS CODE</label>'
                '<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" '
                'placeholder="••••••" required>'
                '<p class="hint">' + html.escape(tx("Enter your account name and the 6-digit code from the Google Authenticator app.")) + '</p>'
                '%s<button>AUTHENTICATE ▸</button>' % ('<p class="error">%s</p>' % html.escape(error) if error else "") + telegram_button() + footer + '</form>')
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Worker · Secure access</title>'
            '<style>%s</style></head><body>%s<script src="/login.js"></script></body></html>' % (CSS_LOGIN, body)).encode()


TELEGRAM_FACE = '<svg class="tg-face" aria-hidden="true" focusable="false" viewBox="0 0 219 40" width="219" height="40"><rect width="219" height="40" rx="6" fill="#54a9eb"/><g transform="translate(14 8)"><path d="m1.95617055 11.392196c5.77764656-2.42328736 9.63031585-4.02086673 11.55800785-4.79273807 5.5039525-2.20384954 6.6476266-2.5866818 7.3930574-2.59932314.1639507-.00278035.5305319.0363352.7679878.22182361.2005031.15662277.2556695.36819788.2820684.51669348.026399.1484956.0592719.48677234.0331404.75109194-.2982611 3.0169019-1.5888322 10.33812718-2.2454015 13.71710898-.2778191 1.4297738-.8288514 1.7357846-1.3584441 1.7826999-1.1509274.1019576-2.0208916-.5588425-3.1356211-1.2622918-1.7443316-1.1007592-2.3854935-1.3972358-4.0786694-2.4713734-1.95675765-1.2413519-.8891962-1.8911034.2259543-3.0061212.2918402-.2918054 5.3989024-4.83750096 5.497052-5.24030969.0122753-.05037796-.1557336-.55407742-.2716182-.65323489-.1158847-.09915747-.2869204-.06524947-.4103446-.03828214-.17495.03822537-2.9615423 1.81132342-8.35977698 5.31929412-.79096496.5228681-1.50739646.7776269-2.1492945.7642766-.70764107-.0147176-2.06885864-.3851791-3.08078398-.7018404-1.24116762-.388398-1.69932554-.5713149-1.61342745-1.2309348.04474105-.3435709.36011227-.7024173.94611366-1.0765391z" fill="#fff" fill-rule="evenodd"/></g><path fill="#fff" d="M54.13 23.42H59.3V25H52.16V13.62H54.13ZM60.27 20.7Q60.27 19.45 60.77 18.46Q61.26 17.46 62.15 16.93Q63.04 16.39 64.2 16.39Q65.91 16.39 66.97 17.49Q68.04 18.59 68.12 20.41L68.13 20.86Q68.13 22.11 67.65 23.09Q67.17 24.08 66.28 24.62Q65.38 25.16 64.21 25.16Q62.42 25.16 61.35 23.96Q60.27 22.77 60.27 20.79ZM62.17 20.86Q62.17 22.16 62.71 22.9Q63.25 23.64 64.21 23.64Q65.17 23.64 65.71 22.89Q66.24 22.14 66.24 20.7Q66.24 19.41 65.69 18.66Q65.14 17.91 64.2 17.91Q63.27 17.91 62.72 18.65Q62.17 19.39 62.17 20.86ZM69.41 20.71Q69.41 18.74 70.33 17.57Q71.26 16.39 72.79 16.39Q74.23 16.39 75.06 17.4L75.15 16.55H76.86V24.74Q76.86 26.41 75.82 27.37Q74.79 28.33 73.03 28.33Q72.1 28.33 71.21 27.94Q70.33 27.55 69.87 26.93L70.77 25.79Q71.64 26.83 72.92 26.83Q73.87 26.83 74.41 26.32Q74.96 25.8 74.96 24.81V24.24Q74.14 25.16 72.77 25.16Q71.29 25.16 70.35 23.98Q69.41 22.8 69.41 20.71ZM71.3 20.88Q71.3 22.15 71.82 22.88Q72.34 23.61 73.26 23.61Q74.41 23.61 74.96 22.62V18.91Q74.42 17.95 73.27 17.95Q72.34 17.95 71.82 18.69Q71.3 19.43 71.3 20.88ZM84.81 25H82.91V16.55H84.81ZM82.8 14.35Q82.8 13.91 83.07 13.62Q83.35 13.34 83.87 13.34Q84.38 13.34 84.66 13.62Q84.95 13.91 84.95 14.35Q84.95 14.78 84.66 15.07Q84.38 15.35 83.87 15.35Q83.35 15.35 83.07 15.07Q82.8 14.78 82.8 14.35ZM88.64 16.55 88.7 17.52Q89.63 16.39 91.16 16.39Q93.8 16.39 93.84 19.41V25H91.95V19.52Q91.95 18.72 91.6 18.33Q91.25 17.95 90.46 17.95Q89.31 17.95 88.75 18.98V25H86.85V16.55ZM107.19 22.38 108.53 16.55H110.38L108.08 25H106.52L104.7 19.2L102.92 25H101.36L99.05 16.55H100.9L102.27 22.32L104 16.55H105.43ZM113.67 25H111.77V16.55H113.67ZM111.66 14.35Q111.66 13.91 111.93 13.62Q112.21 13.34 112.73 13.34Q113.24 13.34 113.52 13.62Q113.8 13.91 113.8 14.35Q113.8 14.78 113.52 15.07Q113.24 15.35 112.73 15.35Q112.21 15.35 111.93 15.07Q111.66 14.78 111.66 14.35ZM118.12 14.49V16.55H119.61V17.95H118.12V22.67Q118.12 23.16 118.31 23.37Q118.5 23.59 118.99 23.59Q119.32 23.59 119.66 23.51V24.98Q119.01 25.16 118.41 25.16Q116.22 25.16 116.22 22.74V17.95H114.83V16.55H116.22V14.49ZM122.93 17.47Q123.86 16.39 125.28 16.39Q127.98 16.39 128.02 19.48V25H126.12V19.55Q126.12 18.67 125.75 18.31Q125.37 17.95 124.63 17.95Q123.49 17.95 122.93 18.96V25H121.03V13H122.93ZM142.33 15.22H138.78V25H136.82V15.22H133.3V13.62H142.33ZM147.36 25.16Q145.55 25.16 144.43 24.02Q143.31 22.88 143.31 20.99V20.76Q143.31 19.49 143.8 18.5Q144.29 17.5 145.17 16.95Q146.05 16.39 147.14 16.39Q148.87 16.39 149.81 17.49Q150.75 18.59 150.75 20.61V21.38H145.23Q145.31 22.42 145.93 23.03Q146.54 23.64 147.47 23.64Q148.77 23.64 149.59 22.59L150.62 23.56Q150.11 24.32 149.26 24.74Q148.41 25.16 147.36 25.16ZM147.13 17.91Q146.35 17.91 145.87 18.46Q145.39 19.01 145.26 19.98H148.88V19.84Q148.81 18.89 148.37 18.4Q147.92 17.91 147.13 17.91ZM154.24 25H152.34V13H154.24ZM160.03 25.16Q158.23 25.16 157.11 24.02Q155.98 22.88 155.98 20.99V20.76Q155.98 19.49 156.47 18.5Q156.96 17.5 157.84 16.95Q158.73 16.39 159.81 16.39Q161.54 16.39 162.48 17.49Q163.42 18.59 163.42 20.61V21.38H157.9Q157.98 22.42 158.6 23.03Q159.21 23.64 160.14 23.64Q161.45 23.64 162.27 22.59L163.29 23.56Q162.78 24.32 161.93 24.74Q161.09 25.16 160.03 25.16ZM159.8 17.91Q159.02 17.91 158.54 18.46Q158.06 19.01 157.93 19.98H161.55V19.84Q161.48 18.89 161.04 18.4Q160.59 17.91 159.8 17.91ZM164.56 20.71Q164.56 18.74 165.49 17.57Q166.41 16.39 167.95 16.39Q169.39 16.39 170.22 17.4L170.3 16.55H172.02V24.74Q172.02 26.41 170.98 27.37Q169.95 28.33 168.19 28.33Q167.26 28.33 166.37 27.94Q165.48 27.55 165.02 26.93L165.92 25.79Q166.8 26.83 168.08 26.83Q169.02 26.83 169.57 26.32Q170.12 25.8 170.12 24.81V24.24Q169.3 25.16 167.93 25.16Q166.45 25.16 165.5 23.98Q164.56 22.8 164.56 20.71ZM166.45 20.88Q166.45 22.15 166.97 22.88Q167.49 23.61 168.41 23.61Q169.56 23.61 170.12 22.62V18.91Q169.58 17.95 168.43 17.95Q167.49 17.95 166.97 18.69Q166.45 19.43 166.45 20.88ZM178.39 18.28Q178.02 18.22 177.62 18.22Q176.31 18.22 175.86 19.22V25H173.96V16.55H175.77L175.82 17.49Q176.51 16.39 177.73 16.39Q178.13 16.39 178.4 16.5ZM184.64 25Q184.52 24.76 184.42 24.21Q183.52 25.16 182.2 25.16Q180.93 25.16 180.12 24.43Q179.32 23.7 179.32 22.63Q179.32 21.28 180.32 20.56Q181.33 19.84 183.2 19.84H184.36V19.28Q184.36 18.62 183.99 18.23Q183.62 17.84 182.88 17.84Q182.23 17.84 181.81 18.16Q181.4 18.48 181.4 18.98H179.5Q179.5 18.29 179.96 17.68Q180.42 17.08 181.21 16.73Q182.01 16.39 182.98 16.39Q184.47 16.39 185.35 17.14Q186.23 17.88 186.26 19.23V23.05Q186.26 24.19 186.58 24.87V25ZM182.55 23.63Q183.12 23.63 183.61 23.36Q184.11 23.09 184.36 22.62V21.03H183.34Q182.28 21.03 181.75 21.4Q181.22 21.77 181.22 22.44Q181.22 22.98 181.58 23.31Q181.95 23.63 182.55 23.63ZM190.03 16.55 190.09 17.43Q190.98 16.39 192.52 16.39Q194.22 16.39 194.84 17.69Q195.77 16.39 197.44 16.39Q198.84 16.39 199.52 17.16Q200.2 17.94 200.22 19.45V25H198.32V19.5Q198.32 18.7 197.97 18.32Q197.62 17.95 196.8 17.95Q196.16 17.95 195.75 18.29Q195.34 18.64 195.17 19.2L195.18 25H193.28V19.44Q193.24 17.95 191.76 17.95Q190.62 17.95 190.14 18.88V25H188.24V16.55Z"/></svg>'


def telegram_button(link_code: str = "", alone: bool = False) -> str:
    """The "Log in with Telegram" button, when a bot is set up: a plain link that goes to Telegram's login page and back.
    Nothing from Telegram runs on this page, so the button looks the same from the first frame; the label is drawn as
    Roboto Medium outlines (Apache License 2.0), the font of Telegram's own button.
    Nút "Log in with Telegram", khi đã cài bot: một liên kết thường đi sang trang đăng nhập của Telegram rồi quay về.
    Không có gì của Telegram chạy trên trang này, nên nút giống nhau ngay từ lúc hiện; chữ vẽ bằng đường viền phông
    Roboto Medium (giấy phép Apache 2.0), đúng phông nút của Telegram."""
    if not bot_name():
        return ""
    href = "/telegram/go" + ("?n=" + link_code if link_code else "")
    return (('' if alone else '<p class="hint tg-or">' + html.escape(tx("or")) + '</p>') +
            '<div class="tg"><a class="tg-link" href="%s" aria-label="Log in with Telegram">%s</a></div>' % (html.escape(href), TELEGRAM_FACE))


def page_telegram_back() -> bytes:
    """Telegram sends the browser back here with the signed login after # (the server never sees that part); the script
    hands it to /login/telegram or /telegram/link, which check the signature.
    Telegram đưa trình duyệt về đây, phần đăng nhập đã ký nằm sau dấu # (máy chủ không thấy phần này); đoạn mã chuyển
    nó cho /login/telegram hoặc /telegram/link để kiểm chữ ký."""
    body = ('<div class="login-box"><h1>AI WORKER</h1><p class="sub">' + html.escape(tx("Logging in with Telegram…")) + '</p>'
            '<p class="hint"><a href="/" style="color:inherit">' + html.escape(tx("▸ Dashboard")) + '</a></p></div>')
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Worker · Telegram</title>'
            '<style>%s</style></head><body>%s<script src="/login.js"></script></body></html>' % (CSS_LOGIN, body)).encode()


def page_telegram(viewer_name: str, link_code: str = "", error: str = "", notice: str = "", go_home: bool = False) -> bytes:
    """Link or unlink one's own Telegram. Both start with the 6-digit code, so a stolen session alone cannot add a way in.
    Liên kết hoặc gỡ Telegram của chính mình. Cả hai bắt đầu bằng mã 6 số, để chỉ lấy được phiên thôi thì không thêm được đường vào."""
    linked = ACCOUNTS.telegram_of(viewer_name)
    def code_input(focus: bool) -> str:
        return ('<label for="code">&gt; ACCESS CODE</label>'
                '<input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="••••••" required'
                + (' autofocus>' if focus else '>'))
    if link_code:
        middle = ('<p class="hint">' + html.escape(tx("Press the button and confirm in Telegram. This step works for 5 minutes.")) + '</p>' +
                  telegram_button(link_code, alone=True))
    elif go_home:
        # just linked: lead on to the dashboard, and leave the one-time link address so a reload does not show an error
        # vừa liên kết: dẫn tiếp tới bảng điều khiển, và rời địa chỉ liên kết dùng một lần để tải lại trang không báo lỗi
        middle = '<a class="go" href="/">' + html.escape(tx("GO TO THE DASHBOARD ▸")) + '</a>'
    elif linked:
        # one message only: the one just shown after linking, or the state; unlinking is rare, so its button is the quiet one
        # chỉ một thông báo: lời báo vừa liên kết, hoặc trạng thái; gỡ liên kết hiếm khi dùng nên nút của nó là nút mờ
        middle = (('' if notice else '<p class="ok">' + html.escape(tx("Linked to Telegram. You can log in with the Telegram button.") if linked == "linked" else
                                                                tx("Linked to Telegram {who}. You can log in with the Telegram button.", who=linked)) + '</p>') +
                  '<details class="unlink"' + (' open' if error else '') + '><summary>' + html.escape(tx("Unlink Telegram")) + '</summary>'
                  '<form method="post" action="/telegram/unlink">' + code_input(False) +
                  '<p class="hint">' + html.escape(tx("To unlink, enter the 6-digit code from the Google Authenticator app.")) + '</p>'
                  '<button class="quiet">' + html.escape(tx("UNLINK TELEGRAM ▸")) + '</button></form></details>')
    else:
        middle = ('<p class="hint">' + html.escape(tx("Link once, then log in with the Telegram button instead of typing your name and code.")) + '</p>'
                  '<form method="post" action="/telegram/start">' + code_input(True) +
                  '<p class="hint">' + html.escape(tx("First enter the 6-digit code from the Google Authenticator app.")) + '</p>'
                  '<button>' + html.escape(tx("CONTINUE ▸")) + '</button></form>')
    body = ('<div class="login-box"><div class="top"><div class="dots"><i></i><i></i><i></i></div><span class="pill"><b></b>TELEGRAM</span></div>'
            '<h1>AI WORKER</h1><p class="sub">' + html.escape(tx("Log in with Telegram · account {name}", name=viewer_name)) + '</p>' +
            ('<p class="error">%s</p>' % html.escape(error) if error else "") + ('<p class="ok">%s</p>' % html.escape(notice) if notice else "") + middle +
            ('' if go_home else '<p class="hint"><a href="/" style="color:inherit">' + html.escape(tx("▸ Dashboard")) + '</a></p>') + '</div>')
    return ('<!doctype html><html lang="' + current_lang() + '" data-lang="' + current_lang() + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Worker · Telegram</title>' +
            ('<meta http-equiv="refresh" content="3;url=/">' if go_home else '') +
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
  // back from Telegram's login page: pass the signed login after # to the server, which checks it
  // ve tu trang dang nhap Telegram: chuyen phan dang nhap da ky sau dau # cho may chu kiem tra
  if (location.pathname === '/telegram/back') {
    var m = /[#&]tgAuthResult=([A-Za-z0-9_=-]+)/.exec(location.hash)
    var to = '/'
    try {
      if (m) {
        var b = m[1].replace(/-/g, '+').replace(/_/g, '/')
        while (b.length % 4) b += '='
        var user = JSON.parse(atob(b)), q = []
        for (var k in user) if (Object.prototype.hasOwnProperty.call(user, k)) q.push(encodeURIComponent(k) + '=' + encodeURIComponent(user[k]))
        var n = /[?&]n=([A-Za-z0-9_-]+)/.exec(location.search)
        to = (n ? '/telegram/link?n=' + n[1] + '&' : '/login/telegram?') + q.join('&')
      }
    } catch (e) {}
    return location.replace(to)
  }
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
    var account = document.getElementById('account')
    if (digits.length === 6 && !sent && (!account || account.value.trim())) {
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
        '<div class="actions"><a href="/">' + lit(tx("▸ Dashboard")) + '</a>' + ('<a href="/telegram">Telegram</a>' if bot_name() else '') +
        '<form method="post" action="/logout" style="margin:0"><button>%s</button></form></div></div>'
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
