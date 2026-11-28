"""The Gemma server an admin set on the Admin page, told to the staff computers in the answer to their sends.
  Máy chủ Gemma do quản trị đặt trên trang Quản trị, được báo cho máy nhân viên trong câu trả lời cho các lần gửi của chúng.

Only the address and the model go down to the computers; nothing comes up. The text for Gemma goes from each computer straight to
Ollama behind Caddy (server/gemma.caddy), never through this program, which only answers /gemma/auth.
  Chỉ địa chỉ và mô hình đi xuống máy; không có gì đi lên. Chữ gửi cho Gemma đi từ từng máy thẳng tới Ollama đứng sau Caddy
  (server/gemma.caddy), không bao giờ qua chương trình này, vốn chỉ trả lời /gemma/auth.
"""
import json
import re
import time
import urllib.error
import urllib.request

from board.db import data_db
from board.lang import tx
from board.stores import DocumentStore

GEMMA = DocumentStore(data_db(), "gemma-server")
# the same rules the plugin keeps (hooks/workers.ts, readGemmaServer): https only, no user:password@, no query
# cùng luật mà plugin giữ (hooks/workers.ts, readGemmaServer): chỉ https, không có user:password@, không có query
URL_RE = re.compile(r"https://([a-z0-9.-]+|\[[0-9a-f:]+\])(:\d{1,5})?(/[^\s?#@\\]*)?", re.I)
MODEL_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,59}", re.I)
LOCAL_OLLAMA = "http://127.0.0.1:11434"
CHECK_SECONDS = 10


def clean(url, model) -> dict:
    """The address and model an admin typed, cleaned; {} for an empty address (no Gemma server). ValueError for a wrong one.
    Địa chỉ và mô hình quản trị đã gõ, đã làm sạch; {} khi địa chỉ trống (không có máy chủ Gemma). ValueError khi sai."""
    url = (url if isinstance(url, str) else "").strip().rstrip("/")
    model = (model if isinstance(model, str) else "").strip()
    if not url:
        return {}
    if len(url) > 200 or not URL_RE.fullmatch(url):
        raise ValueError(tx("the address must start with https:// and hold no password or ?"))
    if model and not MODEL_RE.fullmatch(model):
        raise ValueError(tx("invalid model name"))
    return {"url": url, **({"model": model} if model else {})}


def current() -> dict:
    """The Gemma server in force: {"url", "model"?}, or {} when none is set.
    Máy chủ Gemma đang có hiệu lực: {"url", "model"?}, hoặc {} khi chưa đặt."""
    d = GEMMA.read()
    return {k: d[k] for k in ("url", "model") if isinstance(d.get(k), str) and d[k]}


def set_server(url, model, user: str, now: float) -> dict:
    """Saves the address (empty turns it off) and returns the audit details: what it was and what it is now.
    Lưu địa chỉ (trống là tắt) và trả về chi tiết cho nhật ký: trước đây là gì và bây giờ là gì."""
    new = clean(url, model)
    old = current()

    def edit(d):
        d.clear()
        if new:
            d.update(new, setBy=user, setAt=int(now * 1000))
    GEMMA.mutate(edit)
    return {"action": "gemma-server-set" if new else "gemma-server-off", "fromUrl": old.get("url", ""), "toUrl": new.get("url", ""),
            "fromModel": old.get("model", ""), "toModel": new.get("model", "")}


def for_computer() -> dict:
    """The field the answer to a computer's send carries: the server, or null so a computer drops the one it held.
    Trường mà câu trả lời cho lần gửi của một máy mang theo: máy chủ, hoặc null để máy bỏ máy chủ nó đang giữ."""
    return {"gemmaServer": current() or None}


def _get(url: str, seconds: float):
    """(HTTP code, body) of a GET with no key; (0, reason) when nothing answered.
    (Mã HTTP, thân) của một lệnh GET không kèm khoá; (0, lý do) khi không có gì trả lời."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ai-worker-board"}), timeout=seconds) as r:
            return r.status, r.read(256 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, str(getattr(e, "reason", e))[:160]


def probe(url: str, model: str, local: str = LOCAL_OLLAMA, seconds: float = CHECK_SECONDS) -> dict:
    """What the Check button reports. The address is asked with no key: a refusal (401/403) means the gate in front of Ollama is on,
    an answer means anyone could use it. Ollama on this server is asked for its models, since Gemma usually runs here.
    Điều nút Kiểm tra báo. Địa chỉ được hỏi mà không kèm khoá: bị từ chối (401/403) nghĩa là cổng đứng trước Ollama đang bật,
    trả lời được nghĩa là ai cũng dùng được. Ollama trên máy chủ này được hỏi danh sách mô hình, vì Gemma thường chạy ở đây."""
    started = time.monotonic()
    code, text = _get(url + "/api/tags", seconds)
    out = {"status": code, "reachable": code != 0, "guarded": code in (401, 403), "open": code == 200, "error": text if code == 0 else "",
           "ms": int((time.monotonic() - started) * 1000)}
    code, text = _get(local + "/api/tags", 3)
    names = []
    if code == 200:
        try:
            names = [m.get("name") for m in json.loads(text).get("models", []) if isinstance(m, dict) and isinstance(m.get("name"), str)]
        except (ValueError, AttributeError):
            names = []
    out["localOllama"] = code == 200
    out["localModels"] = names[:20]
    out["hasModel"] = (model or "gemma4:31b") in names if code == 200 else None
    return out
