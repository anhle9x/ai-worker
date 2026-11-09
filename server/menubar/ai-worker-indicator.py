#!/usr/bin/env python3
# Ubuntu menu bar icon for managers, as an AppIndicator (the tray icons Ubuntu shows by default): no Argos needed.
# Biểu tượng thanh menu Ubuntu cho quản lý, dạng AppIndicator (biểu tượng khay Ubuntu hiện sẵn): không cần Argos.
# The talking to the server is shared with ai-worker.1m.py; this file only adds the icon, the menu and a timer.
# Phần nói chuyện với máy chủ dùng chung với ai-worker.1m.py; file này chỉ thêm biểu tượng, menu và hẹn giờ.
# Run with --once to print what the icon would show, as JSON, without a screen (used by the tests).
# Chạy với --once để in ra những gì biểu tượng sẽ hiện, dạng JSON, không cần màn hình (dùng cho bài thử).
import importlib.util
import json
import math
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("menubar_core", os.path.join(HERE, "ai-worker.1m.py"))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

# the .deb puts the board's address in config.json next to this file; a per-user menubar.json still wins
# gói .deb để địa chỉ bảng trong config.json cạnh file này; menubar.json riêng của người dùng vẫn được ưu tiên
# the language the person chose in the window's Settings is kept in their own menubar.json and wins over everything
# ngôn ngữ người dùng chọn trong Cài đặt của khung được giữ trong menubar.json của họ và thắng mọi thứ khác
CHOSEN_LANG = core.CFG.get("lang") if core.CFG.get("lang") in ("en", "vi") else ""
if not core.CFG.get("server"):
    core.CFG = core.load_json(os.path.join(HERE, "config.json"), {})
    lang = CHOSEN_LANG or core.CFG.get("lang") or "auto"
    core.LANG = lang if lang in ("en", "vi") else ("vi" if os.environ.get("LANG", "").startswith("vi") else "en")


def set_language(code):
    """Keep the language chosen in the window's Settings for this person, for the menu and the notifications.
    Giữ ngôn ngữ chọn trong Cài đặt của khung cho người dùng này, cho menu và thông báo."""
    if code not in ("en", "vi") or code == core.LANG:
        return False
    core.LANG = code
    mine = core.load_json(core.CONFIG, {})
    mine["lang"] = code
    core.save_private(core.CONFIG, json.dumps(mine))
    return True
tx = core.tx

POLL_SECONDS = 60
PAIR_POLL_SECONDS = 5
NAME = core.CFG.get("name") or "AI Worker"


def read_session():
    try:
        with open(core.SESSION, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def pair_step(server):
    """One pairing step: returns ('paired', '') once approved, ('pair', code) while waiting, ('off', '') when refused.
    Một bước ghép: trả ('paired', '') khi đã duyệt, ('pair', mã) khi đang chờ, ('off', '') khi bị từ chối."""
    pending = core.load_json(core.PENDING, {})
    if pending.get("key"):
        status, d, cookies = core.call(server, "POST", "/tv/poll", cookie="tv-pending=" + pending["key"])
        if status == 200 and d.get("status") == "done":
            token = core.cookie_value(cookies, "session")
            if token:
                core.save_private(core.SESSION, token)
                core.remove(core.PENDING)
                return "paired", ""
        if status == 200 and d.get("status") == "pending":
            return "pair", pending["code"]
        core.remove(core.PENDING)
    status, d, cookies = core.call(server, "POST", "/tv/request-code")
    key = core.cookie_value(cookies, "tv-pending")
    if status != 200 or not key or not re.fullmatch(r"\d{8}", str(d.get("code", ""))):
        return "off", ""
    core.save_private(core.PENDING, json.dumps({"key": key, "code": d["code"]}))
    return "pair", d["code"]


def look():
    """What the icon shows now: {state, count, people, code, server}. state is ok, long, off, pair or unset.
    Biểu tượng đang hiện gì: {state, count, people, code, server}. state là ok, long, off, pair hoặc unset."""
    server = core.CFG.get("server", "")
    view = {"state": "off", "count": 0, "people": [], "code": "", "server": server.rstrip("/")}
    if not core.server_ok(server):
        return dict(view, state="unset")
    try:
        token = read_session()
        if not token:
            state, code = pair_step(server)
            if state != "paired":
                return dict(view, state=state, code=code)
            token = read_session()
        status, data, _ = core.call(server, "GET", "/mini/state", cookie="session=" + token)
        if status in (401, 403):
            core.remove(core.SESSION)
            state, code = pair_step(server)
            return dict(view, state=state, code=code)
        if status != 200:
            return view
    except (OSError, ValueError):
        return view
    core.remind(data)
    now_ms = time.time() * 1000
    limit = data.get("notifyMinutes", 10)
    people, long_wait = [], False
    for p in sorted(data.get("waiting", []), key=lambda p: p.get("since") or now_ms):
        minutes = int((now_ms - p["since"]) / 60000) if p.get("since") else 0
        long_wait = long_wait or (bool(p.get("since")) and minutes >= limit)
        people.append({"name": str(p.get("name", "?"))[:40], "minutes": minutes})
    view = dict(view, state="long" if long_wait else "ok", count=len(people), people=people,
                notify=bool(data.get("notify", True)), notifyMinutes=limit, working=[], quota=[], cost=[], rate=0)
    # the same wall view the small window reads, for the Working, Quota and Cost today sections
    # cùng phần màn hình treo tường mà khung nhỏ đọc, cho các mục Đang làm, Hạn mức, Chi phí hôm nay
    try:
        status, wall, _ = core.call(server, "GET", "/data", cookie="session=" + token)
    except (OSError, ValueError):
        status, wall = 0, {}
    if status == 200:
        view.update(sections(wall))
    return view


KINDS = {"five_hour": "5-hour", "seven_day": "7-day", "seven_day_opus": "7-day Opus", "seven_day_sonnet": "7-day Sonnet", "spend_limit": "spending"}


def model_label(model):
    """claude-opus-4-1 becomes Opus 4.1, as in the small window.
    claude-opus-4-1 thành Opus 4.1, như trong khung nhỏ."""
    m = re.match(r"^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?", model or "")
    return "%s %s%s" % (m.group(1).capitalize(), m.group(2), "." + m.group(3) if m.group(3) else "") if m else (model or "")


def sections(wall):
    """Working, Quota and Cost today from the wall view, the way the small window draws its tabs.
    Đang làm, Hạn mức và Chi phí hôm nay từ phần treo tường, như cách khung nhỏ vẽ các thẻ."""
    everyone = [p for p in wall.get("people", []) if isinstance(p, dict)]
    online = [p for p in everyone if p.get("status") != "offline"]
    working = [{"name": str(p.get("name", "?"))[:40], "model": model_label(next(iter(p.get("models") or {}), ""))}
               for p in online if p.get("working") and not p.get("waiting")]
    quota = []
    for p in everyone:
        windows = [w for w in (p.get("quota") or {}).get("windows", []) if isinstance(w, dict) and isinstance(w.get("pct"), (int, float))]
        if windows:
            worst = max(windows, key=lambda w: w["pct"])
            quota.append({"name": str(p.get("name", "?"))[:40], "pct": round(worst["pct"]), "kind": KINDS.get(worst.get("kind"), str(worst.get("kind", "")))})
    cost = sorted(({"name": str(p.get("name", "?"))[:40], "usd": float(p.get("usdToday") or 0)} for p in everyone if p.get("usdToday")),
                  key=lambda c: -c["usd"])
    return {"working": working, "quota": quota, "cost": cost, "rate": float(wall.get("usdRate") or 0)}


AUTOSTART = os.path.join(os.path.expanduser("~"), ".config", "autostart", "ai-worker-menubar.desktop")


def starts_at_login():
    """The .deb starts the icon for everyone; a user turns it off with their own copy marked Hidden.
    Gói .deb cho biểu tượng chạy với mọi người; mỗi người tắt bằng bản riêng có Hidden.""" 
    try:
        with open(AUTOSTART, encoding="utf-8") as f:
            return "Hidden=true" not in f.read()
    except OSError:
        return True


def set_start_at_login(on):
    if on:
        core.remove(AUTOSTART)
        return
    os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
    with open(AUTOSTART, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\nName=AI Worker\nExec=/usr/bin/ai-worker-menubar\nHidden=true\n")


def window_url(server):
    """The small window's address with a one-time code, so the browser opens it already signed in; the board when that fails.
    Địa chỉ khung nhỏ kèm mã dùng một lần, để trình duyệt mở ra đã đăng nhập; không được thì mở bảng."""
    token = read_session()
    try:
        _, handoff, _ = core.call(server, "POST", "/mini/handoff", cookie="session=" + token)
        code = str(handoff.get("code", ""))
        if core.HANDOFF_CODE.fullmatch(code):
            return "%s/mini?h=%s&lang=%s" % (server, code, core.LANG)
    except (OSError, ValueError):
        pass
    return server + "/board"


def icon_file(state):
    """A picture file for the icon, or a theme icon name when there is no logo.
    File ảnh cho biểu tượng, hoặc tên biểu tượng của giao diện khi không có logo."""
    if state in ("ok", "long"):
        for path in (os.path.join(core.CONFIG_DIR, "icon-white.png"), os.path.join(HERE, "icons", "icon-white.png"), os.path.join(HERE, "icons", "generic-white.png")):
            if os.path.isfile(path):
                if state == "ok":
                    return path
                try:
                    with open(path, "rb") as f:
                        alert = core.recolor_png(f.read(), core.ALERT_RGB)
                    out = os.path.join(core.CONFIG_DIR, "icon-alert.png")
                    os.makedirs(core.CONFIG_DIR, mode=0o700, exist_ok=True)
                    with open(out, "wb") as f:
                        f.write(alert)
                    return out
                except (OSError, ValueError):
                    return path
    return {"off": "network-offline-symbolic", "pair": "dialog-password-symbolic", "unset": "dialog-warning-symbolic"}.get(state, "system-users-symbolic")


def run_gui():
    import gi
    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as Indicator
    except (ValueError, ImportError):
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as Indicator
    from gi.repository import GLib, Gtk

    ind = Indicator.Indicator.new("ai-worker-menubar", "system-users-symbolic", Indicator.IndicatorCategory.APPLICATION_STATUS)
    ind.set_status(Indicator.IndicatorStatus.ACTIVE)
    ind.set_title(NAME)
    busy = threading.Lock()

    def item(label, action=None):
        it = Gtk.MenuItem(label=label)
        if action:
            it.connect("activate", lambda _w: action())
        else:
            it.set_sensitive(False)
        return it

    def in_background(work):
        threading.Thread(target=work, daemon=True).start()

    # The small window: the same /mini page the Mac app shows, in a window of its own with no address bar.
    # Without the web view library (an older or newer Ubuntu) it falls back to a compact browser window.
    # Khung nhỏ: đúng trang /mini app Mac hiện, trong cửa sổ riêng không có thanh địa chỉ.
    # Không có thư viện hiển thị trang web (Ubuntu cũ hoặc mới hơn) thì quay về cửa sổ trình duyệt gọn.
    web = {}
    try:
        for version in ("4.1", "4.0"):
            try:
                gi.require_version("WebKit2", version)
                break
            except ValueError:
                continue
        from gi.repository import Gdk, WebKit2
        web["kit"] = WebKit2
    except (ValueError, ImportError):
        pass

    def window():
        if "window" in web:
            return web["window"]
        WebKit2 = web["kit"]
        win = Gtk.Window(title=NAME)
        win.set_default_size(380, 420)
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_keep_above(True)
        win.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        # near the icon where the desktop lets a window choose its place (X11); Wayland places it itself
        # gần biểu tượng nếu màn hình cho cửa sổ tự chọn chỗ (X11); Wayland tự đặt
        screen = Gdk.Screen.get_default()
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0) if display is not None else None
        if monitor is not None:
            area = monitor.get_geometry()
            win.move(max(0, area.x + area.width - 400), area.y + 36)
        # the page reports its height, as it does for the Mac app, and the window follows it (between 220 and 640 pixels)
        # trang báo chiều cao, như với app Mac, và cửa sổ co theo (từ 220 tới 640 điểm ảnh)
        content = WebKit2.UserContentManager()
        content.add_script(WebKit2.UserScript(
            "(function(){var last=0;function send(){var m=document.querySelector('main');"
            "var h=Math.ceil(m?m.offsetTop+m.offsetHeight+16:document.body.scrollHeight);"
            "if(h!==last){last=h;window.webkit.messageHandlers.size.postMessage(h)}}"
            "var r=new ResizeObserver(send);r.observe(document.documentElement);"
            "var m=document.querySelector('main');if(m)r.observe(m);send()})()",
            WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.END, None, None))
        content.register_script_message_handler("size")
        # short messages from the page: lang:en|vi, hello, login:on|off; the start-at-login row is shown (class host-login)
        # tin ngắn từ trang: lang:en|vi, hello, login:on|off; dòng tự chạy khi đăng nhập được hiện (lớp host-login)
        content.add_script(WebKit2.UserScript("addEventListener('DOMContentLoaded',function(){document.documentElement.classList.add('host-login')})",
                                              WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.START, None, None))
        content.register_script_message_handler("host")

        def tell_login():
            web["view"].run_javascript("window.appState&&window.appState({login:%s})" % ("true" if starts_at_login() else "false"), None, None, None)

        def heard(_content, message):
            # only the small window's own page may ask for these; a page the window was led to elsewhere is ignored
            # chỉ chính trang của khung nhỏ được xin mấy việc này; trang lạ mà khung bị dẫn tới thì bỏ qua
            if not (web["view"].get_uri() or "").startswith(server + "/mini"):
                return
            try:
                text = message.get_js_value().to_string()
            except (AttributeError, TypeError):
                return
            if text.startswith("lang:"):
                if set_language(text[5:]):
                    in_background(refresh)
            elif text == "hello":
                tell_login()
            elif text in ("login:on", "login:off"):
                set_start_at_login(text == "login:on")
                tell_login()
            elif text == "uninstall":
                win.hide()
                in_background(remove_app)
            elif text == "quit":
                Gtk.main_quit()

        # The package is installed for the whole computer, so removing it asks for an admin password in Ubuntu's own dialog (pkexec).
        # Cancelled or refused: nothing changes. Removed: this person's settings go too, and the icon quits.
        # Gói cài cho cả máy, nên gỡ thì hỏi mật khẩu quản trị bằng hộp có sẵn của Ubuntu (pkexec).
        # Huỷ hay bị từ chối: không đổi gì. Gỡ xong: cài đặt của người dùng này cũng xoá, và biểu tượng thoát.
        def remove_app():
            import shutil
            import subprocess
            try:
                done = subprocess.run(["pkexec", "/usr/bin/apt-get", "remove", "-y", "ai-worker-menubar"], capture_output=True, timeout=600).returncode == 0
            except (OSError, subprocess.SubprocessError):
                done = False
            if done:
                shutil.rmtree(core.CONFIG_DIR, ignore_errors=True)
                GLib.idle_add(Gtk.main_quit)
        content.connect("script-message-received::host", heard)

        # while the window shows, it grows or shrinks smoothly (about 0.24 s, slowing at the end); while hidden it is set at once
        # khung đang hiện thì co giãn từ từ (khoảng 0,24 giây, chậm dần về cuối); đang ẩn thì đặt ngay
        motion = {"from": 0, "to": 0, "start": 0.0, "running": False}

        def animate_to(target):
            current = win.get_size()[1]
            if not win.get_visible() or target == current:
                win.resize(380, target)
                return
            motion.update({"from": current, "to": target, "start": time.time()})
            if not motion["running"]:
                motion["running"] = True
                GLib.timeout_add(15, step)

        def step():
            x = min(1.0, (time.time() - motion["start"]) / 0.24)
            eased = 1 - (1 - x) ** 3
            win.resize(380, int(round(motion["from"] + (motion["to"] - motion["from"]) * eased)))
            if x >= 1:
                motion["running"] = False
                return False
            return True

        def fit(_content, message):
            try:
                value = message.get_js_value()
                height = int(value.to_double())
            except (AttributeError, TypeError, ValueError):
                return
            animate_to(min(640, max(220, height)))
        content.connect("script-message-received::size", fit)
        # rounded corners like the Mac popover: a see-through window, and the page draws its own rounded frame.
        # Only where the desktop composites windows; elsewhere the corners stay square instead of turning black.
        # góc bo như khung trên Mac: cửa sổ trong suốt, trang tự vẽ khung bo góc.
        # Chỉ khi màn hình có hiệu ứng trong suốt; không có thì góc giữ vuông thay vì bị đen.
        visual = screen.get_rgba_visual() if screen is not None and screen.is_composited() else None
        print("rounded corners: %s" % ("on" if visual is not None else "off, the desktop does not composite windows"), file=sys.stderr, flush=True)
        if visual is not None:
            win.set_visual(visual)
            win.set_app_paintable(True)
            # the theme paints a background behind the page; take it away so the page's rounded corners show
            # giao diện sơn một lớp nền sau trang; bỏ lớp đó để góc bo của trang hiện ra
            css = Gtk.CssProvider()
            css.load_from_data(b"window, window.background, decoration { background: transparent; box-shadow: none; border-radius: 14px; }")
            win.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            content.add_style_sheet(WebKit2.UserStyleSheet(
                "html{background:transparent!important}"
                "body{position:fixed;top:0;right:0;bottom:0;left:0;overflow-y:auto;border-radius:14px;box-sizing:border-box;border:1px solid rgba(127,127,127,.28)}",
                WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserStyleLevel.USER, None, None))
        view = WebKit2.WebView.new_with_user_content_manager(content)
        if visual is not None:
            view.set_background_color(Gdk.RGBA(0, 0, 0, 0))
            # the web view keeps a see-through background only when it draws without graphics acceleration; the page is small
            # phần hiển thị trang chỉ giữ nền trong suốt khi vẽ không dùng tăng tốc đồ hoạ; trang nhỏ nên vẫn mượt
            view.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        # On X11 the window itself is cut to a rounded rectangle, so the corners are round even when see-through drawing fails
        # Trên X11 cửa sổ được cắt hẳn thành chữ nhật bo góc, để góc vẫn tròn khi vẽ trong suốt không được
        if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
            try:
                import cairo

                def round_shape(widget, alloc):
                    w, h, r = alloc.width, alloc.height, 14
                    region = cairo.Region(cairo.RectangleInt(0, r, w, max(0, h - 2 * r)))
                    for y in range(r):
                        inset = r - int(math.sqrt(r * r - (r - y - 0.5) ** 2))
                        region.union(cairo.RectangleInt(inset, y, w - 2 * inset, 1))
                        region.union(cairo.RectangleInt(inset, h - 1 - y, w - 2 * inset, 1))
                    widget.shape_combine_region(region)
                win.connect("size-allocate", round_shape)
            except ImportError:
                pass
        view.get_settings().set_user_agent_with_application_details("AIWorkerLinux", "1")
        server = core.CFG.get("server", "").rstrip("/")

        def keep_inside(_view, decision, kind):
            # pages of the small window stay here; anything else (the board, a link) goes to the browser
            # trang của khung nhỏ ở lại đây; còn lại (bảng, đường dẫn) mở bằng trình duyệt
            if kind != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
                return False
            uri = decision.get_navigation_action().get_request().get_uri() or ""
            if uri.startswith(server + "/mini") or uri.startswith(server + "/tinh/") or uri.startswith(server + "/static/") or uri == "about:blank":
                return False
            decision.ignore()
            core.open_window(uri)
            return True
        view.connect("decide-policy", keep_inside)
        win.add(view)
        # like the Mac popover: a click elsewhere or Escape closes it
        # như khung trên Mac: bấm ra ngoài hoặc Escape là đóng
        win.connect("focus-out-event", lambda w, _e: w.hide() or False)
        win.connect("key-press-event", lambda w, e: e.keyval == Gdk.KEY_Escape and (w.hide() or True))
        win.connect("delete-event", lambda w, _e: w.hide() or True)
        web.update(window=win, view=view)
        # the window is open: the person already sees the list, so no notification on top of it
        # khung đang mở: người dùng đã thấy danh sách, khỏi bật thông báo đè lên
        plain_notify = core.notify
        core.notify = lambda title, text, who=None: None if win.get_visible() else plain_notify(title, text, who)
        return win

    def show_page(url, server):
        if "kit" not in web:
            core.open_window(url)
            return
        win = window()
        web["view"].load_uri(url)
        win.show_all()
        win.present()

    def open_small(server):
        # the one-time code is fetched off the screen's thread, then the page loads in the window
        # mã dùng một lần được lấy ngoài luồng màn hình, rồi trang mở trong cửa sổ
        in_background(lambda: (lambda url: GLib.idle_add(show_page, url, server))(window_url(server)))

    def show(view):
        menu = Gtk.Menu()
        server = view["server"]
        state = view["state"]
        icon = icon_file(state)
        ind.set_icon_full(icon, NAME)
        ind.set_label(str(view["count"]) if view["count"] else "", "99")
        if state == "unset":
            menu.append(item(tx("Not set up: run the installer again")))
        elif state == "off":
            menu.append(item(tx("Cannot reach the server") if not view["code"] else tx("The server refused the pairing, try again later")))
            if server:
                menu.append(item(tx("Open board"), lambda: core.open_window(server + "/board")))
        elif state == "pair":
            code = view["code"]
            menu.append(item(tx("Pair with my account"), lambda: show_page("%s/mini/pair#c=%s" % (server, code), server)))
            menu.append(item("%s: %s-%s" % (tx("Pairing code"), code[:4], code[4:])))
            menu.append(item(tx("Copy the code"), lambda: core.copy_code(code)))
            menu.append(item(tx("Open the approval page"), lambda: core.open_window("%s/admin#pair=%s" % (server, code))))
            menu.append(item(tx("Ask an admin to approve this code on the Admin page")))
        else:
            # the menu stays short; the small window is where everything is, as on the Mac
            # menu giữ ngắn; mọi thứ nằm trong khung nhỏ, như trên Mac
            if view["people"]:
                first = view["people"][0]
                summary = "%s · %s %s" % (tx("{n} waiting", n=view["count"]), first["name"], tx("{n} min", n=first["minutes"]) if first["minutes"] else tx("just now"))
            else:
                summary = tx("Nobody is waiting")
            menu.append(item(summary, lambda: open_small(server)))
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(item(tx("Open {name}", name=NAME), lambda: open_small(server)))
            menu.append(item(tx("Open board"), lambda: core.open_window(server + "/board")))
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(item(tx("Quit"), Gtk.main_quit))
        menu.show_all()
        ind.set_menu(menu)
        return False

    def refresh():
        # after a change from the menu: look again now, without starting a second timer
        # sau khi đổi từ menu: xem lại ngay, không bật thêm bộ hẹn giờ thứ hai
        view = look()
        GLib.idle_add(show, view)

    def tick():
        # the server is asked off the screen's thread, so a slow network never freezes the menu
        # hỏi máy chủ ngoài luồng của màn hình, nên mạng chậm không làm đơ menu
        def work():
            if not busy.acquire(blocking=False):
                return
            try:
                view = look()
            finally:
                busy.release()
            GLib.idle_add(show, view)
            GLib.timeout_add_seconds(PAIR_POLL_SECONDS if view["state"] == "pair" else POLL_SECONDS, tick)
        in_background(work)
        return False

    show({"state": "off", "count": 0, "people": [], "code": "", "server": core.CFG.get("server", "").rstrip("/")})
    tick()
    Gtk.main()


if __name__ == "__main__":
    if sys.argv[1:] == ["--once"]:
        print(json.dumps(look(), ensure_ascii=False))
    else:
        run_gui()
