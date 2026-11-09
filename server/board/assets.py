"""Static files of the pages and the version that busts their cache.
File tĩnh của các trang và số phiên bản để trình duyệt tải bản mới."""

import os
import re

from board.settings import SERVER_DIR

# files of the 3D page: only these files, next to webhook.py in the static/ folder
# file của trang 3D: chỉ những file này, nằm cạnh webhook.py trong thư mục static/
STATIC_DIR = os.path.join(SERVER_DIR, "static")
RELEASES_DIR = os.environ.get("RELEASES_DIR", os.path.join(SERVER_DIR, "releases"))
RELEASE_NAME_RE = re.compile(r"^(latest\.json|latest\.json\.sig|ai-worker-[0-9A-Za-z.-]{1,20}\.zip)$")
STATIC_FILES = {"i18n.js": "text/javascript", "ops.vi.js": "text/javascript", "admin.vi.js": "text/javascript", "page.js": "text/javascript", "mini.js": "text/javascript", "mini.css": "text/css", "ops.js": "text/javascript", "ops.css": "text/css",
             "ops3d.js": "text/javascript", "three.js": "text/javascript",
             "admin.js": "text/javascript", "admin.css": "text/css", "qrcode.js": "text/javascript",
             "map-common.js": "text/javascript", "map2d.js": "text/javascript", "map25d.js": "text/javascript", "map3d.js": "text/javascript",
             "land.json": "application/json", "globe-grid.json": "application/json", "globe-nodes.json": "application/json"}


def current_ui_version() -> str:
    """UI version number: changes on every install, so an open page knows to reload.
    Số phiên bản giao diện: đổi mỗi lần cài, để trang đang mở biết mà tải lại."""
    cutoff = 0.0
    for file_name in STATIC_FILES:
        try:
            cutoff = max(cutoff, os.path.getmtime(os.path.join(STATIC_DIR, file_name)))
        except OSError:
            continue
    return str(int(cutoff))


def asset_version(file_name: str) -> str:
    """File modified time: changes when a new version is installed, so the browser does not use an old cached copy.
    Giờ sửa file: đổi khi cài bản mới, để trình duyệt không dùng bản cũ đã lưu."""
    try:
        return str(int(os.path.getmtime(os.path.join(STATIC_DIR, file_name))))
    except OSError:
        return "0"


UI_VERSION = current_ui_version()


def has_3d_page() -> bool:
    return all(os.path.isfile(os.path.join(STATIC_DIR, f)) for f in STATIC_FILES)
