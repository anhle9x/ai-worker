#!/usr/bin/env python3
# <xbar.title>AI Worker</xbar.title> i18n-allow
# <xbar.desc>Who is waiting for an answer, from the AI Worker board</xbar.desc> i18n-allow
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# Menu bar icon for managers: SwiftBar on macOS, Argos on Ubuntu. Standard library only.
# Biểu tượng thanh menu cho quản lý: SwiftBar trên macOS, Argos trên Ubuntu. Chỉ dùng thư viện chuẩn.
# It pairs once like a wall screen, then every minute asks the server who is waiting and prints the icon.
# Ghép một lần như màn hình treo tường, rồi mỗi phút hỏi máy chủ ai đang chờ và in ra biểu tượng.
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zlib

# the color of a wait past the limit: a deep blue that does not glare on a dark menu bar
# màu của lần chờ quá hạn: xanh lam đậm, không chói trên thanh menu tối
ALERT_RGB = (26, 86, 200)
ALERT_HEX = "#1A56C8"
import urllib.error
import urllib.parse
import urllib.request

MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")
CONFIG_DIR = os.environ.get("AI_WORKER_MENUBAR_DIR") or os.path.join(HOME, ".config", "ai-worker")
CONFIG = os.path.join(CONFIG_DIR, "menubar.json")
SESSION = os.path.join(CONFIG_DIR, "menubar-session")
PENDING = os.path.join(CONFIG_DIR, "menubar-pending.json")
NOTIFIED = os.path.join(CONFIG_DIR, "menubar-notified.json")
TIMEOUT = 8
UA = "AI Worker menu bar (%s)" % ("macOS" if MAC else "Linux")
# the one-time window code from the server: anything else (a hostile server, a tampered reply) is not put in a menu line or a command
# mã mở khung dùng một lần từ máy chủ: thứ khác (máy chủ xấu, câu trả lời bị sửa) không được đưa vào dòng menu hay câu lệnh
HANDOFF_CODE = re.compile(r"[A-Za-z0-9_-]{8,128}")



def server_ok(server):
    """The board address: https, or http only to this very computer (the host exactly localhost, 127.0.0.1 or ::1, not a name that starts with it).
    It holds only letters, digits and - _ . : / [ ], so it is safe in a SwiftBar line and an Argos command.
    Địa chỉ bảng: https, hoặc http chỉ tới chính máy này (máy chủ đúng là localhost, 127.0.0.1 hoặc ::1, không phải tên bắt đầu bằng mấy chữ đó).
    Chỉ gồm chữ, số và - _ . : / [ ], nên an toàn trong dòng SwiftBar và câu lệnh Argos."""
    if not isinstance(server, str) or not re.fullmatch(r"[A-Za-z0-9._:/\[\]-]+", server):
        return False
    try:
        parts = urllib.parse.urlsplit(server)
        host = parts.hostname
        # reading the port raises ValueError when it is not a number
        # đọc cổng sẽ báo ValueError khi cổng không phải số
        parts.port  # noqa: B018
    except ValueError:
        return False
    if parts.scheme == "https":
        return bool(host)
    return parts.scheme == "http" and host in ("localhost", "127.0.0.1", "::1")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_private(path, text):
    """Write a file only this user can read: it holds the session.
    Ghi file chỉ người dùng này đọc được: trong đó có phiên."""
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


CFG = load_json(CONFIG, {})
LANG = CFG.get("lang") or ("vi" if os.environ.get("LANG", "").startswith("vi") else "en")
# Vietnamese words: vi.json in the settings folder, else next to this script
# Chữ tiếng Việt: vi.json trong thư mục cài đặt, không thì cạnh script này
VI = load_json(os.path.join(CONFIG_DIR, "menubar-vi.json"), None) or load_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vi.json"), {})


def tx(text, **params):
    found = VI.get(text, text) if LANG == "vi" else text
    return found.format(**params) if params else found


def call(server, method, path, cookie="", body=None):
    """One request; returns (status, json, set-cookie). Never follows a redirect, so a session cannot leak to another host.
    Một yêu cầu; trả (mã, json, set-cookie). Không đi theo chuyển hướng, để phiên không lọt sang máy khác."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    # a POST goes with an empty body unless one is given: the pairing routes do not read one
    # POST gửi thân rỗng nếu không có gì để gửi: đường ghép mã không đọc thân
    req = urllib.request.Request(server.rstrip("/") + path, method=method, data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None),
                                 headers={"User-Agent": UA, "Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            raw = r.read()
            return r.status, json.loads(raw or b"{}"), r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), []
        except ValueError:
            return e.code, {}, []


def cookie_value(set_cookies, name):
    for c in set_cookies:
        first = c.split(";", 1)[0]
        k, _, v = first.partition("=")
        if k.strip() == name and v:
            return v
    return ""


# the round badge in a notification: the first letter of the person's name on a colour fixed by the name, like a chat app
# ô tròn trong thông báo: chữ cái đầu của tên người trên một màu cố định theo tên, như ứng dụng nhắn tin
AVATAR_COLORS = ("#e17076", "#faa774", "#a695e7", "#7bc862", "#6ec9cb", "#65aadd", "#ee7aae")


def initial_of(name):
    """First letter or digit of the name, upper case ("Phòng IT" -> "P"); "?" when there is none.
    Chữ cái hay chữ số đầu của tên, viết hoa ("Phòng IT" -> "P"); không có thì "?"."""
    return next((c for c in name or "" if c.isalnum()), "?").upper()


def avatar_color(name):
    """The same name always gets the same colour (sum of its UTF-8 bytes); the Mac and Windows apps use the same rule.
    Cùng một tên luôn cùng một màu (tổng các byte UTF-8); app Mac và Windows dùng đúng quy tắc này."""
    return AVATAR_COLORS[sum((name or "").encode("utf-8")) % len(AVATAR_COLORS)]


def avatar_png(name):
    """Draws the badge once per letter and colour into the settings folder; None when cairo is missing (the notification goes without it).
    Vẽ ô tròn một lần cho mỗi chữ và màu vào thư mục cài đặt; thiếu cairo thì trả None (thông báo đi không kèm ô)."""
    letter, color = initial_of(name), avatar_color(name)
    path = os.path.join(CONFIG_DIR, "avatars", "%s-%s.png" % ("%x" % ord(letter[0]), color[1:]))
    if os.path.isfile(path):
        return path
    try:
        import cairo
        size = 128
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(surface)
        cr.set_source_rgb(*(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
        cr.arc(size / 2, size / 2, size / 2, 0, 6.2832)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(size * 0.5)
        x, y, w, h, _, _ = cr.text_extents(letter)
        cr.move_to(size / 2 - w / 2 - x, size / 2 - h / 2 - y)
        cr.show_text(letter)
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        surface.write_to_png(path)
        return path
    # no cairo, or a broken one, must never stop the reminder
    # thiếu hay hỏng cairo không được chặn lời nhắc
    except Exception:  # noqa: BLE001
        return None


def notify(title, text, who=None):
    """An operating system notification; the text goes as an argument, never inside the script, so a name cannot run as code.
    On Ubuntu the badge of the person who waits (who) is the notification's image (GNOME shows it large on the left; the header keeps the small app logo).
    Thông báo của hệ điều hành; chữ đi dưới dạng tham số, không nằm trong mã, nên tên người không chạy được như lệnh.
    Trên Ubuntu ô tròn của người đang chờ (who) là ảnh của thông báo (GNOME hiện to bên trái; dòng tiêu đề giữ logo app nhỏ)."""
    try:
        if MAC:
            subprocess.run(["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                            "-e", "end run", title, text], timeout=5, capture_output=True)
        elif shutil.which("notify-send"):
            # "--" ends the options: a name starting with "-" stays text
            # "--" kết thúc phần tuỳ chọn: tên bắt đầu bằng "-" vẫn chỉ là chữ
            icon = avatar_png(who) if who else None
            # --icon goes to the header, small and grey on GNOME 46; the badge goes as the image hint so it shows large
            # --icon nằm ở dòng tiêu đề, nhỏ và xám trên GNOME 46; ô tròn đi dạng ảnh của thông báo nên hiện to
            image = ["--hint=string:image-path:" + icon] if icon else []
            subprocess.run(["notify-send", "--app-name=AI Worker", "--icon=ai-worker-menubar"] + image + ["--", title, text], timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def open_window(url):
    """Ubuntu: open the window in a compact browser window when one is installed, else the default browser.
    Ubuntu: mở khung trong cửa sổ trình duyệt gọn nếu có, không thì trình duyệt mặc định."""
    for browser in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        path = shutil.which(browser)
        if path:
            subprocess.Popen([path, "--app=" + url, "--window-size=380,560"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def logo(color):
    """The logo as base64 PNG: the company's own (icon-black.png, icon-white.png in the settings folder) if the installer put one there,
    else the one shipped next to this script. Empty when neither is found.
    Logo dạng PNG base64: logo riêng của công ty (icon-black.png, icon-white.png trong thư mục cài đặt) nếu file cài đã chép vào,
    không thì logo đi kèm script. Rỗng khi không có cả hai."""
    for path in (os.path.join(CONFIG_DIR, "icon-%s.png" % color), os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "generic-%s.png" % color)):
        try:
            if os.path.getsize(path) <= 20000:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode()
        except OSError:
            continue
    return ""


def recolor_png(data, rgb):
    """Paint every pixel of an 8-bit RGBA PNG one color, keeping its transparency. Standard library only.
    Tô mọi điểm ảnh của PNG RGBA 8 bit một màu, giữ độ trong suốt. Chỉ dùng thư viện chuẩn."""
    pos, chunks = 8, []
    while pos < len(data):
        n = int.from_bytes(data[pos:pos + 4], "big")
        chunks.append((data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]))
        pos += 12 + n
    header = dict(chunks)[b"IHDR"]
    width, height, depth, kind = int.from_bytes(header[:4], "big"), int.from_bytes(header[4:8], "big"), header[8], header[9]
    if depth != 8 or kind != 6 or header[12] != 0:
        raise ValueError("not an 8-bit RGBA PNG")
    raw = zlib.decompress(b"".join(c for k, c in chunks if k == b"IDAT"))
    stride, prev, out = width * 4, bytearray(width * 4), bytearray()
    for y in range(height):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        for i in range(0, stride, 4):
            line[i:i + 3] = bytes(rgb)
        out += b"\x00" + line
    def chunk(kind, body):
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")
    extra = b"".join(chunk(k, c) for k, c in chunks if k == b"pHYs")
    return data[:8] + chunk(b"IHDR", header) + extra + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b"")


def alert_logo():
    """The logo in ALERT_RGB, for a wait past the limit. SwiftBar does not open the window when a template logo gets a text color,
    so the color is painted into a plain image instead.
    Logo tô màu ALERT_RGB, khi có người chờ quá hạn. SwiftBar không mở khung khi logo dạng mẫu đi kèm màu chữ,
    nên màu được tô thẳng vào ảnh thường."""
    black = logo("black")
    if not black:
        return ""
    try:
        return base64.b64encode(recolor_png(base64.b64decode(black), ALERT_RGB)).decode()
    except (ValueError, zlib.error, KeyError):
        return ""


def icon_line(count, state):
    """state: ok, long (someone waited past the limit), off (no connection), pair (not paired yet).
    state: ok, long (có người chờ quá hạn), off (mất kết nối), pair (chưa ghép)."""
    text = str(count) if count else ""
    color = " color=" + ALERT_HEX if state == "long" else ""
    if MAC:
        # no text color next to a logo: SwiftBar then shows an empty menu instead of the window
        # không đặt màu chữ cạnh logo: khi đó SwiftBar hiện menu rỗng thay cho khung
        alert = alert_logo() if state == "long" else ""
        if alert:
            return "%s | image=%s" % (text, alert)
        image = logo("black") if state in ("ok", "long") else ""
        if image:
            return "%s | templateImage=%s" % (text, image)
        symbol = {"off": "person.2.slash", "pair": "person.badge.key"}.get(state, "person.2.fill")
        return "%s | sfimage=%s%s" % (text, symbol, " sfcolor=" + ALERT_HEX if state == "long" else "")
    image = logo("white") if state in ("ok", "long") else ""
    if image:
        return "%s | image=%s imageHeight=18%s" % (text, image, color)
    icon = {"off": "network-offline-symbolic", "pair": "dialog-password-symbolic"}.get(state, "system-users-symbolic")
    return "%s | iconName=%s%s" % (text, icon, color)


def show_code(code, server):
    """While not paired: macOS opens the pairing page under the icon; Ubuntu lists pairing with one's account, the code, copy, and the Admin link.
    The code sits after # in every address, so it is not sent to the server.
    Khi chưa ghép: macOS mở trang ghép dưới biểu tượng; Ubuntu liệt kê ghép bằng tài khoản, mã, nút chép, đường tới trang Quản trị.
    Mã luôn nằm sau dấu # trong địa chỉ, nên không gửi lên máy chủ."""
    if not re.fullmatch(r"\d{8}", str(code)):
        print(icon_line(0, "pair"))
        print("---")
        print(tx("The server refused the pairing, try again later"))
        return
    pair_url = "%s/mini/pair#c=%s" % (server.rstrip("/"), code)
    if MAC:
        # a click opens the pairing page under the icon: the manager enters their own account and OTP there
        # bấm vào là mở trang ghép ngay dưới biểu tượng: quản lý nhập tài khoản và OTP của mình ở đó
        title, _, params = icon_line(0, "pair").partition(" | ")
        print("%s | webview=true webvieww=360 webviewh=500 href=%s %s" % (title, pair_url, params))
        return
    print(icon_line(0, "pair"))
    print("---")
    print("%s | bash='%s %s --open %s' terminal=false" % (tx("Pair with my account"), sys.executable, os.path.abspath(__file__), pair_url))
    print("%s: %s-%s | font=Menlo" % (tx("Pairing code"), code[:4], code[4:]))
    print("%s | bash='%s %s --copy %s' terminal=false" % (tx("Copy the code"), sys.executable, os.path.abspath(__file__), code))
    print("%s | href=%s/admin#pair=%s" % (tx("Open the approval page"), server.rstrip("/"), code))
    print(tx("Ask an admin to approve this code on the Admin page"))


def copy_code(code):
    """Copy the pairing code to the clipboard and say so; only exactly 8 digits are accepted.
    Chép mã ghép vào bộ nhớ tạm rồi báo; chỉ nhận đúng 8 chữ số."""
    if not re.fullmatch(r"\d{8}", code):
        return
    tools = [["pbcopy"]] if MAC else [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for tool in tools:
        if shutil.which(tool[0]):
            try:
                subprocess.run(tool, input=code.encode(), timeout=5, check=True)
                notify("AI Worker", tx("Pairing code {code} copied", code="%s-%s" % (code[:4], code[4:])))
                return
            except (OSError, subprocess.SubprocessError):
                continue


def pairing(server):
    """Ask for a code, or check whether the code shown before has been approved. Prints the menu and returns.
    Xin mã, hoặc hỏi mã đã hiện trước đó được duyệt chưa. In menu rồi trả về."""
    pending = load_json(PENDING, {})
    if pending.get("key"):
        status, d, cookies = call(server, "POST", "/tv/poll", cookie="tv-pending=" + pending["key"])
        if status == 200 and d.get("status") == "done":
            token = cookie_value(cookies, "session")
            if token:
                save_private(SESSION, token)
                remove(PENDING)
                return False
        if status == 200 and d.get("status") == "pending":
            show_code(pending["code"], server)
            return True
        remove(PENDING)
    status, d, cookies = call(server, "POST", "/tv/request-code")
    key = cookie_value(cookies, "tv-pending")
    if status != 200 or not key or not d.get("code"):
        print(icon_line(0, "off"))
        print("---")
        print(tx("The server refused the pairing, try again later"))
        return True
    save_private(PENDING, json.dumps({"key": key, "code": d["code"]}))
    show_code(d["code"], server)
    return True


def remind(state):
    """One notification per wait that passed the limit; forget waits that ended.
    Mỗi lần chờ quá hạn chỉ báo một lần; quên những lần chờ đã xong."""
    done = set(load_json(NOTIFIED, []))
    now_ms = time.time() * 1000
    current = set()
    for p in state.get("waiting", []):
        if not p.get("since"):
            continue
        key = "%s|%s" % (p.get("name"), p["since"])
        current.add(key)
        minutes = int((now_ms - p["since"]) / 60000)
        if state.get("notify") and minutes >= state.get("notifyMinutes", 10) and key not in done:
            notify(tx("Waiting for an answer"), tx("{name} has waited {n} minutes", name=p.get("name", "?"), n=minutes), p.get("name") or "?")
            done.add(key)
    save_private(NOTIFIED, json.dumps(sorted(done & current)))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--copy":
        return copy_code(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--open":
        return open_window(sys.argv[2])
    server = CFG.get("server", "")
    if not server_ok(server):
        print(icon_line(0, "off"))
        print("---")
        print(tx("Not set up: run the installer again"))
        return
    try:
        token = open(SESSION, encoding="utf-8").read().strip()
    except OSError:
        token = ""
    try:
        if not token:
            if pairing(server):
                return
            token = open(SESSION, encoding="utf-8").read().strip()
        status, state, _ = call(server, "GET", "/mini/state", cookie="session=" + token)
        if status in (401, 403):
            remove(SESSION)
            pairing(server)
            return
        if status != 200:
            raise OSError(status)
        _, handoff, _ = call(server, "POST", "/mini/handoff", cookie="session=" + token)
    except (OSError, ValueError):
        print(icon_line(0, "off"))
        print("---")
        print(tx("Cannot reach the server"))
        print("%s | href=%s/board" % (tx("Open board"), server.rstrip("/")))
        return
    remind(state)
    waiting = state.get("waiting", [])
    limit_ms = state.get("notifyMinutes", 10) * 60000
    long_wait = any(p.get("since") and time.time() * 1000 - p["since"] >= limit_ms for p in waiting)
    code = str(handoff.get("code", "")) if isinstance(handoff, dict) else ""
    url = "%s/mini?h=%s" % (server.rstrip("/"), code) if HANDOFF_CODE.fullmatch(code) else server.rstrip("/") + "/board"
    if MAC:
        # the window parameters go first: SwiftBar reads them before the long logo value
        # tham số của khung đặt trước: SwiftBar đọc chúng trước giá trị logo dài
        title, _, params = icon_line(len(waiting), "long" if long_wait else "ok").partition(" | ")
        print("%s | webview=true webvieww=360 webviewh=420 href=%s %s" % (title, url, params))
    else:
        print(icon_line(len(waiting), "long" if long_wait else "ok"))
        print("---")
        # Argos runs the bash value as one command line; the address holds only letters, digits and - _ . : /
        # Argos chạy giá trị bash như một dòng lệnh; địa chỉ chỉ có chữ, số và - _ . : /
        print("%s | bash='%s %s --open %s' terminal=false" % (tx("Open the window"), sys.executable, os.path.abspath(__file__), url))
        print("%s | href=%s/board" % (tx("Open board"), server.rstrip("/")))


if __name__ == "__main__":
    main()
