"""The language of each request and the tx() lookup into the Vietnamese dictionary.
Ngôn ngữ của từng yêu cầu và hàm tx() tra từ điển tiếng Việt."""

import os
import re
import threading

from webhook_vi import VI

# English in this file is the source text; webhook_vi.py holds the Vietnamese. One request runs on one thread.
# Chữ tiếng Anh trong file này là bản gốc; webhook_vi.py giữ bản tiếng Việt. Mỗi yêu cầu chạy trên một luồng.
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "") if os.environ.get("DEFAULT_LANG", "") in ("en", "vi") else ""
REQUEST = threading.local()


def lang_from(cookie: str, accept_language: str) -> str:
    """Language for one request: the visitor's cookie, DEFAULT_LANG, the browser, then English.
    Ngôn ngữ của một yêu cầu: cookie của người xem, DEFAULT_LANG, trình duyệt, rồi tiếng Anh."""
    m = re.search(r"(?:^|;\s*)lang=(en|vi)\b", cookie or "")
    if m:
        return m.group(1)
    if DEFAULT_LANG:
        return DEFAULT_LANG
    return "vi" if re.match(r"\s*vi\b", accept_language or "", re.I) else "en"


def current_lang() -> str:
    return getattr(REQUEST, "lang", DEFAULT_LANG or "en")


def tx(text: str, **params) -> str:
    """Translate for this request, filling {name} parameters; text missing from the dictionary falls back to English.
    Dịch cho yêu cầu này và điền các tham số {name}; chữ chưa có trong từ điển thì hiện tiếng Anh."""
    found = VI.get(text, text) if current_lang() == "vi" else text
    return found.format(**params) if params else found
