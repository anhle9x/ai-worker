"""Install packages built on request: TV, menu bar for Mac, Windows (.msi, .zip) and Ubuntu (.deb).
Gói cài dựng khi được yêu cầu: TV, thanh menu cho Mac, Windows (.msi, .zip) và Ubuntu (.deb)."""

import hashlib
import io
import json
import os
import re
import tarfile
import zipfile

from board import lang
from board.settings import SERVER_DIR

# only digits are accepted; at 6 digits it submits by itself, no button needed
# File for the computer plugged into the TV: it holds only the board address, no code or key. The Windows version is plain ASCII so cmd's code page is no problem.
# The Windows version copies itself into the startup folder with type, not copy: the new file does not carry the "downloaded from the internet" mark, so it is not asked about again at startup.
# chỉ nhận chữ số; đủ 6 số thì tự gửi, không cần bấm nút
# File cho máy tính cắm TV: chỉ chứa địa chỉ bảng, không có mã hay khoá. Bản Windows chỉ dùng ký tự ASCII để khỏi vướng bảng mã của cmd.
# Bản Windows chép mình vào thư mục khởi động bằng type, không dùng copy: file mới không mang dấu "tải từ mạng", nên bật máy không bị hỏi lại.
TV_INSTALL_WINDOWS = r"""@echo off
setlocal
set "BOARD_URL=__BOARD_URL__"
set "STARTUP_FILE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI Worker TV.bat"
if /i "%~f0"=="%STARTUP_FILE%" goto open
echo AI Worker wall screen
echo.
echo   1. Open full screen every time this computer starts
echo   2. Remove it, stop opening
choice /c 12 /m "Choose"
if errorlevel 2 goto remove
type "%~f0" > "%STARTUP_FILE%"
if errorlevel 1 goto copyerror
echo Installed. It opens every time the computer starts. Exit full screen: Alt+F4.
goto open
:remove
del "%STARTUP_FILE%" >nul 2>&1
echo Removed. It will not open at startup any more.
pause
exit /b 0
:copyerror
echo Could not write to the Startup folder.
pause
exit /b 1
:open
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto run
echo Google Chrome is not installed on this computer. Install Chrome, then run this file again.
pause
exit /b 1
:run
start "" "%CHROME%" --kiosk --no-first-run --user-data-dir="%LOCALAPPDATA%\AI-Worker-TV" "%BOARD_URL%"
exit /b 0
""".replace("\n", "\r\n")

TV_INSTALL_MAC = r"""#!/bin/bash
BOARD_URL="__BOARD_URL__"
PLIST="$HOME/Library/LaunchAgents/com.ai-worker.tv.plist"
if ! [ -d "/Applications/Google Chrome.app" ] && ! [ -d "$HOME/Applications/Google Chrome.app" ]; then
  echo "Google Chrome is not installed on this computer. Install Chrome, then run this file again."
  read -r -p "Press Enter to close " _
  exit 1
fi
echo "AI Worker wall screen"
echo
echo "  1. Open full screen every time you log in to this computer"
echo "  2. Remove it, stop opening"
echo
read -r -p "Choose 1 or 2: " CHOICE
launchctl unload "$PLIST" 2>/dev/null
if [ "$CHOICE" = 2 ]; then
  rm -f "$PLIST"
  echo "Removed."
  read -r -p "Press Enter to close " _
  exit 0
fi
[ "$CHOICE" = 1 ] || { echo "Nothing chosen, nothing changed."; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.ai-worker.tv</string>
<key>RunAtLoad</key><true/>
<key>ProgramArguments</key><array>
<string>/usr/bin/open</string><string>-na</string><string>Google Chrome</string><string>--args</string>
<string>--kiosk</string><string>--no-first-run</string><string>--user-data-dir=$HOME/AI-Worker-TV</string><string>$BOARD_URL</string>
</array>
</dict></plist>
EOF
launchctl load "$PLIST"
echo "Installed and opening now. Exit full screen: Cmd+Q."
"""


def tv_mac_zip(board_url: str) -> bytes:
    """A zip to keep the run permission of the .command file; a file downloaded directly cannot be double-clicked on macOS.
    Zip để giữ quyền chạy của file .command; tải thẳng file thì macOS không cho bấm đúp."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("AI-Worker-TV.command", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o100755 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, TV_INSTALL_MAC.replace("__BOARD_URL__", board_url))
    return out.getvalue()


MENUBAR_DIR = os.path.join(SERVER_DIR, "menubar")
# the company's own logo for the menu bar (icon-black.png, icon-white.png); unset means the logo shipped in menubar/icons
# logo riêng của công ty cho thanh menu (icon-black.png, icon-white.png); không đặt thì dùng logo trong menubar/icons
MENUBAR_ICON_DIR = os.environ.get("MENUBAR_ICON_DIR", "")
# the macOS app built for this server by menubar/macos-app/build.sh (a .zip); set, the Mac download gives the app instead of the SwiftBar installer
# app macOS đã đóng gói cho máy chủ này bằng menubar/macos-app/build.sh (file .zip); có đặt thì nút tải cho Mac trả app thay cho gói SwiftBar
# build.sh also leaves the same app as a .dmg next to the .zip; when it is there, Admin offers it too
# build.sh còn để cùng app dạng .dmg cạnh file .zip; có file đó thì trang Quản trị cho tải thêm
MENUBAR_MAC_APP = os.environ.get("MENUBAR_MAC_APP", "")


# the manager browser extension zipped by packaging/build-extension.sh; when it is there, Admin offers it
# tiện ích trình duyệt cho quản lý do packaging/build-extension.sh nén; có file đó thì trang Quản trị cho tải
def menubar_extension() -> str:
    """The extension zip in menubar/, or '' when there is none.
    File zip tiện ích trong menubar/, hoặc '' khi không có."""
    path = os.path.join(MENUBAR_DIR, "AI-Worker-extension.zip")
    return path if os.path.isfile(path) else ""


def menubar_mac_dmg() -> str:
    """The .dmg build.sh made next to MENUBAR_MAC_APP, or '' when there is none.
    File .dmg build.sh tạo cạnh MENUBAR_MAC_APP, hoặc '' khi không có."""
    dmg = re.sub(r"\.zip$", ".dmg", MENUBAR_MAC_APP) if MENUBAR_MAC_APP.endswith(".zip") else ""
    return dmg if dmg and os.path.isfile(dmg) else ""


# AI Worker.msi (built on GitHub's Windows from menubar/windows-app, fetched by fetch-msi.sh) carries this placeholder in its SERVER property;
# the server replaces it with its own address padded with spaces, so one package serves every server.
# AI Worker.msi (dựng trên Windows của GitHub từ menubar/windows-app, lấy về bằng fetch-msi.sh) mang chuỗi giữ chỗ này ở thuộc tính SERVER;
# máy chủ thay bằng địa chỉ của nó, đệm dấu cách, nên một gói dùng được cho mọi máy chủ.
MSI_PLACEHOLDER = b"AIWORKER-SERVER-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX"


def menubar_msi(board_url: str):
    """The .msi with this server's address filled in; None without a package, with an odd or too long address, or a placeholder not found exactly once.
    Gói .msi đã điền địa chỉ máy chủ này; None khi không có gói, địa chỉ lạ hay quá dài, hoặc chuỗi giữ chỗ không đúng một lần."""
    # the board address comes with a trailing slash; the app adds its own paths
    # địa chỉ bảng có dấu / ở cuối; app tự thêm đường dẫn của nó
    board_url = board_url.rstrip("/")
    path = os.path.join(MENUBAR_DIR, "AI-Worker.msi")
    if not os.path.isfile(path) or not re.fullmatch(r"https?://[A-Za-z0-9.:\[\]-]+", board_url) or len(board_url) > len(MSI_PLACEHOLDER):
        return None
    with open(path, "rb") as f:
        package = f.read()
    if package.count(MSI_PLACEHOLDER) != 1:
        return None
    return package.replace(MSI_PLACEHOLDER, board_url.encode("ascii").ljust(len(MSI_PLACEHOLDER)))


def menubar_zip(board_url: str, system: str) -> bytes:
    """The menu bar installer for one system, with this server's address written in. Holds no key and no session: pairing happens after.
    Gói cài thanh menu cho một hệ điều hành, đã ghi sẵn địa chỉ máy chủ này. Không có khoá hay phiên nào: ghép máy làm sau."""
    files = {"mac": [("install-mac.command", "Install AI Worker menu bar.command", 0o755), ("ai-worker.1m.py", "ai-worker.1m.py", 0o755)],
             "windows": [("install-windows.bat", "Install AI Worker icon.bat", 0o644), ("install-menubar.ps1", "install-menubar.ps1", 0o644),
                         ("ai-worker-tray.ps1", "ai-worker-tray.ps1", 0o644)]}[system]
    files.append(("vi.json", "vi.json", 0o644))
    if system == "windows":
        # the small window like the Mac app: its code (compiled at run time) and Microsoft's WebView2 libraries with their license
        # khung nhỏ giống app Mac: mã khung (dịch lúc chạy) và thư viện WebView2 của Microsoft, kèm giấy phép
        files.append(("menubar-popup.cs", "menubar-popup.cs", 0o644))
        root = os.path.join(MENUBAR_DIR, "webview2")
        for folder, _, names in sorted(os.walk(root)):
            for name in sorted(names):
                relative = os.path.relpath(os.path.join(folder, name), MENUBAR_DIR).replace(os.sep, "/")
                files.append((relative, relative, 0o644))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name, data, mode):
            info = zipfile.ZipInfo("AI-Worker-menu-bar/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
        for source, name, mode in files:
            with open(os.path.join(MENUBAR_DIR, source), "rb") as f:
                add(name, f.read().replace(b"__BOARD_URL__", board_url.encode()), mode)
        for color in ("black", "white"):
            own = os.path.join(MENUBAR_ICON_DIR, "icon-%s.png" % color) if MENUBAR_ICON_DIR else ""
            path = own if own and os.path.isfile(own) else os.path.join(MENUBAR_DIR, "icons", "generic-%s.png" % color)
            with open(path, "rb") as f:
                add("icon-%s.png" % color, f.read(), 0o644)
        # the app's logo (the same as the Mac and Ubuntu apps), used as the logo of Windows notifications
        # logo của app (cùng logo app Mac và Ubuntu), dùng làm logo trong thông báo Windows
        with open(os.path.join(MENUBAR_DIR, "icons", "app-icon.png"), "rb") as f:
            add("app-icon.png", f.read(), 0o644)
    return out.getvalue()


MENUBAR_DEB_NAME = "ai-worker-menubar"
MENUBAR_DEB_VERSION = "2.4"


def menubar_deb(board_url: str) -> bytes:
    """The Ubuntu menu bar icon as a .deb, with this server's address written in: apt installs the AppIndicator libraries it needs,
    the icon starts at login for every user, and apt remove takes it away. Built here with the standard library, so no Linux build machine.
    Biểu tượng thanh menu Ubuntu dạng .deb, đã ghi sẵn địa chỉ máy chủ này: apt tự cài thư viện AppIndicator cần thiết,
    biểu tượng tự chạy khi đăng nhập cho mọi người dùng, apt remove là gỡ. Đóng gói ngay tại đây bằng thư viện chuẩn, không cần máy Linux để dựng."""
    lib = "usr/lib/" + MENUBAR_DEB_NAME
    files: list = []

    def add(path: str, data: bytes, mode: int = 0o644) -> None:
        files.append((path, data, mode))

    for source, mode in (("ai-worker-indicator.py", 0o755), ("ai-worker.1m.py", 0o644), ("vi.json", 0o644)):
        with open(os.path.join(MENUBAR_DIR, source), "rb") as f:
            add("%s/%s" % (lib, source), f.read(), mode)
    add(lib + "/config.json", json.dumps({"server": board_url.rstrip("/"), "lang": lang.DEFAULT_LANG or "auto", "name": "AI Worker"}).encode())
    for color in ("black", "white"):
        own = os.path.join(MENUBAR_ICON_DIR, "icon-%s.png" % color) if MENUBAR_ICON_DIR else ""
        path = own if own and os.path.isfile(own) else os.path.join(MENUBAR_DIR, "icons", "generic-%s.png" % color)
        with open(path, "rb") as f:
            add("%s/icons/icon-%s.png" % (lib, color), f.read())
    # the app's logo in the app list: /usr/share/pixmaps needs no icon cache rebuild
    # logo của app trong danh sách ứng dụng: /usr/share/pixmaps không cần dựng lại bộ đệm biểu tượng
    with open(os.path.join(MENUBAR_DIR, "icons", "app-icon.png"), "rb") as f:
        add("usr/share/pixmaps/%s.png" % MENUBAR_DEB_NAME, f.read())
    # on a Wayland session GNOME ignores where an app puts its windows, so the small window would open mid-screen; through XWayland
    # (when the session has it) the window sits under the icon as on X11; the icon and notifications go through D-Bus either way
    # trên phiên Wayland GNOME bỏ qua vị trí app đặt cửa sổ, khung nhỏ sẽ ra giữa màn hình; qua XWayland (khi phiên có)
    # khung nằm ngay dưới biểu tượng như trên X11; biểu tượng và thông báo đi qua D-Bus nên không đổi
    launcher = ("#!/bin/sh\nif [ \"$XDG_SESSION_TYPE\" = wayland ] && [ -n \"$DISPLAY\" ]; then export GDK_BACKEND=x11; fi\n"
                "exec /usr/bin/python3 /%s/ai-worker-indicator.py \"$@\"\n" % lib)
    add("usr/bin/" + MENUBAR_DEB_NAME, launcher.encode(), 0o755)
    desktop = ("[Desktop Entry]\nType=Application\nName=AI Worker\nComment=Who is waiting for an answer\nExec=/usr/bin/%s\n"
               "Icon=%s\nTerminal=false\nCategories=Office;\n" % (MENUBAR_DEB_NAME, MENUBAR_DEB_NAME))
    add("usr/share/applications/%s.desktop" % MENUBAR_DEB_NAME, desktop.encode())
    add("etc/xdg/autostart/%s.desktop" % MENUBAR_DEB_NAME, (desktop + "X-GNOME-Autostart-enabled=true\n").encode())
    control = (
        "Package: %s\nVersion: %s\nArchitecture: all\nMaintainer: AI Worker <noreply@localhost>\nSection: utils\nPriority: optional\n"
        "Depends: python3, python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0\n"
        "Recommends: libnotify-bin, google-chrome-stable | chromium | chromium-browser, wl-clipboard | xclip\n"
        "Installed-Size: %d\nDescription: AI Worker menu bar icon for managers\n"
        " Shows in the top bar how many people are waiting for an answer, from the board at %s.\n"
    ) % (MENUBAR_DEB_NAME, MENUBAR_DEB_VERSION, max(1, sum(len(d) for _, d, _ in files) // 1024), board_url.rstrip("/"))
    md5 = "".join("%s  %s\n" % (hashlib.md5(d).hexdigest(), p) for p, d, _ in files)

    def tar_gz(entries: list) -> bytes:
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
            made: set = set()
            for path, data, mode in entries:
                parts = path.split("/")[:-1]
                for i in range(1, len(parts) + 1):
                    d = "/".join(parts[:i])
                    if d and d not in made:
                        made.add(d)
                        info = tarfile.TarInfo("./" + d)
                        info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, 1767225600
                        tar.addfile(info)
                info = tarfile.TarInfo("./" + path)
                info.size, info.mode, info.mtime = len(data), mode, 1767225600
                tar.addfile(info, io.BytesIO(data))
        return out.getvalue()

    members = [("debian-binary", b"2.0\n"),
               ("control.tar.gz", tar_gz([("control", control.encode(), 0o644), ("md5sums", md5.encode(), 0o644)])),
               ("data.tar.gz", tar_gz(files))]
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        out.write(("%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (name, 1767225600, 0, 0, "100644", len(data))).encode())
        out.write(data + (b"\n" if len(data) % 2 else b""))
    return out.getvalue()
