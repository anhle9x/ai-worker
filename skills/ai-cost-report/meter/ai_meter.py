"""Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
  Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
Copy this one file into the project. Python 3.8+, standard library only.
  Chép đúng file này vào dự án. Python 3.8+, chỉ thư viện chuẩn.
It never writes a prompt, an answer, a user id or an error message: counts and times only.
  Không bao giờ ghi câu hỏi, câu trả lời, mã người dùng hay thông báo lỗi: chỉ số đếm và thời gian.
The line format is in FORMAT.md next to this folder; any language can write it.
  Định dạng dòng nằm trong FORMAT.md cạnh thư mục này; ngôn ngữ nào cũng ghi được.

    from ai_meter import Meter
    meter = Meter("ai-meter.jsonl", env="prod")
    with meter.turn() as t:
        resp = client.messages.create(...)
        t.record(resp)                                   # any provider whose answer has a usage shape below
        t.count("myprovider", "my-model", input=812, output=95)   # any other provider, counts by hand
"""
import atexit
import collections
import json
import os
import re
import secrets
import threading
import time
import urllib.request
from datetime import datetime, timezone

VERSION = 1
# A provider is a short name: lowercase letters, digits, "_", "." and "-", at most 32; anything else is written as "other"
# Hãng là một tên ngắn: chữ thường, số, "_", "." và "-", tối đa 32 ký tự; tên khác ghi thành "other"
PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,31}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$")
COUNTS = ("input", "output", "cacheRead", "cacheWrite", "cacheWriteLong")
_lock = threading.Lock()


def _int(v):
    # A token count is a whole number of zero or more; anything else is "not measured"
    # Số token là số nguyên từ 0 trở lên; thứ khác là "không đo được"
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        return None
    return v


_FIELDS = ("usage", "usage_metadata", "usageMetadata", "model", "model_version", "modelVersion", "modelId",
           "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens",
           "cache_read_input_tokens", "cache_creation_input_tokens", "cache_creation", "ephemeral_1h_input_tokens",
           "input_tokens_details", "prompt_tokens_details", "cached_tokens", "cache_write_tokens",
           "cache_write_tokens_details", "ttl_12h_tokens", "prompt_cache_hit_tokens",
           "prompt_token_count", "candidates_token_count", "cached_content_token_count", "thoughts_token_count",
           "promptTokenCount", "candidatesTokenCount", "cachedContentTokenCount", "thoughtsTokenCount",
           "inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens",
           "prompt_eval_count", "eval_count", "billed_units", "meta", "total_tokens", "completion_tokens_details",
           "output_tokens_details", "reasoning_tokens", "inputTokenDetails", "noCacheTokens", "cacheReadTokens", "cacheWriteTokens")


def _plain(obj, depth=0):
    # SDK objects (pydantic, protobuf wrappers) become dicts; only the fields this file reads are looked at
    # Đối tượng của SDK (pydantic, protobuf) thành dict; chỉ đọc các trường file này cần
    if obj is None or isinstance(obj, (dict, int, float, str, bool)) or depth > 3:
        return obj
    for name in ("model_dump", "to_dict", "dict"):
        f = getattr(obj, name, None)
        if callable(f):
            try:
                d = f()
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
    out = {}
    for key in _FIELDS:
        v = getattr(obj, key, None)
        if v is not None:
            out[key] = _plain(v, depth + 1)
    return out


def _g(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d.get(k)
    return None


def guess_provider(model):
    # Only used when neither the caller nor the usage shape names the provider
    # Chỉ dùng khi cả người gọi lẫn hình dạng usage đều không cho biết hãng
    m = str(model or "").lower().split("/")[-1]
    if "claude" in m:
        return "anthropic"
    if m.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if m.startswith(("gemini", "gemma")):
        return "google"
    for prefix, name in (("deepseek", "deepseek"), ("mistral", "mistral"), ("mixtral", "mistral"), ("codestral", "mistral"),
                         ("grok", "xai"), ("command", "cohere")):
        if m.startswith(prefix):
            return name
    return "other"


def _counts(inp, out, read=0, write=0, long_=0):
    vals = [_int(inp), _int(out), _int(read), _int(write), _int(long_)]
    if None in vals or vals[4] > vals[3]:
        return None
    return dict(zip(COUNTS, vals))


def read_usage(resp, provider=None):
    """Reads (provider, model, counts) from an API response or its usage; counts is None when there is no usage.
    Đọc (hãng, model, số đếm) từ phản hồi API hay phần usage của nó; số đếm là None khi không có usage.

    Shapes read, each input token counted once (FORMAT.md has the table):
    Các dạng đọc được, mỗi token đầu vào chỉ đếm một lần (bảng trong FORMAT.md):
    Anthropic Messages; OpenAI Chat Completions and Responses, and every API that copies them (Azure OpenAI,
    DeepSeek, Mistral, Groq, OpenRouter, xAI, vLLM, Ollama's /v1, LM Studio...); Gemini; Bedrock Converse;
    Ollama's own /api/chat; Cohere v2 chat.
    Anthropic Messages; OpenAI Chat Completions và Responses, cùng mọi API chép theo chúng (Azure OpenAI,
    DeepSeek, Mistral, Groq, OpenRouter, xAI, vLLM, /v1 của Ollama, LM Studio...); Gemini; Bedrock Converse;
    /api/chat riêng của Ollama; Cohere v2 chat.
    """
    d = _plain(resp)
    if not isinstance(d, dict):
        return provider, None, None
    model = _g(d, "model", "modelVersion", "model_version", "modelId")
    # Gemini: promptTokenCount includes the cache; thinking tokens are billed as output
    # Gemini: promptTokenCount đã gồm cache; token suy nghĩ tính tiền như output
    gem = _g(d, "usageMetadata", "usage_metadata")
    if gem is None and _g(d, "promptTokenCount", "prompt_token_count") is not None:
        gem = d
    if isinstance(gem, dict):
        prompt = _int(_g(gem, "promptTokenCount", "prompt_token_count"))
        cached = _int(_g(gem, "cachedContentTokenCount", "cached_content_token_count") or 0)
        cand = _int(_g(gem, "candidatesTokenCount", "candidates_token_count") or 0)
        think = _int(_g(gem, "thoughtsTokenCount", "thoughts_token_count") or 0)
        if None in (prompt, cached, cand, think) or cached > prompt:
            return provider or "google", model, None
        return provider or "google", model, _counts(prompt - cached, cand + think, cached)
    # Ollama /api/chat: prompt_eval_count and eval_count on the answer itself
    # /api/chat của Ollama: prompt_eval_count và eval_count nằm ngay trên câu trả lời
    if "eval_count" in d or "prompt_eval_count" in d:
        return provider or "ollama", model, _counts(d.get("prompt_eval_count"), d.get("eval_count"))
    u = d.get("usage") if isinstance(d.get("usage"), dict) else d
    # Vercel AI SDK: inputTokens include the cache; inputTokenDetails splits them
    # Vercel AI SDK: inputTokens đã gồm cache; inputTokenDetails tách ra
    if isinstance(u.get("inputTokenDetails"), dict):
        det = u["inputTokenDetails"]
        read, write = det.get("cacheReadTokens") or 0, det.get("cacheWriteTokens") or 0
        plain = det.get("noCacheTokens")
        if plain is None and _int(u.get("inputTokens")) is not None and _int(read) is not None and _int(write) is not None:
            plain = u["inputTokens"] - read - write
        return provider or guess_provider(model), model, _counts(plain, u.get("outputTokens"), read, write)
    # Bedrock Converse: inputTokens are only the tokens not read from or written to the cache
    # Bedrock Converse: inputTokens chỉ là phần không đọc từ cache và không ghi vào cache
    if "inputTokens" in u or "outputTokens" in u:
        return provider or "bedrock", model, _counts(u.get("inputTokens"), u.get("outputTokens"),
                                                     u.get("cacheReadInputTokens") or 0, u.get("cacheWriteInputTokens") or 0)
    # Cohere v2: the billed units are what costs money
    # Cohere v2: billed_units là phần bị tính tiền
    if isinstance(u.get("billed_units"), dict):
        b = u["billed_units"]
        return provider or "cohere", model, _counts(b.get("input_tokens"), b.get("output_tokens"))
    # Anthropic: input_tokens excludes the cache
    # Anthropic: input_tokens không gồm cache
    if "cache_read_input_tokens" in u or "cache_creation_input_tokens" in u or provider == "anthropic":
        long_ = _g(u.get("cache_creation") or {}, "ephemeral_1h_input_tokens") or 0
        return provider or "anthropic", model, _counts(u.get("input_tokens"), u.get("output_tokens"),
                                                       u.get("cache_read_input_tokens") or 0,
                                                       u.get("cache_creation_input_tokens") or 0, long_)
    # OpenAI and every API that copies it: input or prompt tokens include cache reads and writes
    # OpenAI và mọi API chép theo nó: input hay prompt tokens đã gồm cache đọc và ghi
    total = _int(_g(u, "input_tokens", "prompt_tokens"))
    out = _int(_g(u, "output_tokens", "completion_tokens"))
    if total is None and out is None:
        return provider or guess_provider(model), model, None
    det = _g(u, "input_tokens_details", "prompt_tokens_details") or {}
    read = _int(_g(det, "cached_tokens", "prompt_cache_hit_tokens") or _g(u, "prompt_cache_hit_tokens") or 0)
    write = _int(_g(det, "cache_write_tokens") or 0)
    long_ = _int(_g(_g(det, "cache_write_tokens_details") or {}, "ttl_12h_tokens") or 0)
    p = provider or guess_provider(model)
    if None in (total, out, read, write, long_) or read + write > total:
        return p, model, None
    # Some of these APIs (xAI's Chat Completions) leave reasoning tokens out of completion_tokens; total_tokens shows it
    # Vài API loại này (Chat Completions của xAI) không tính token suy nghĩ vào completion_tokens; total_tokens cho thấy điều đó
    think = _int(_g(_g(u, "completion_tokens_details", "output_tokens_details") or {}, "reasoning_tokens") or 0)
    if think and _int(u.get("total_tokens")) == total + out + think:
        out += think
    return p, model, _counts(total - read - write, out, read, write, long_)


def _clean_provider(p):
    p = str(p or "other").strip().lower()
    return p if PROVIDER_RE.match(p) else "other"


def _clean_model(m):
    m = str(m or "")
    return m if MODEL_RE.match(m) else "unknown"


class Turn:
    """One user turn: every LLM call made to answer it. Use through Meter.turn().
    Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Dùng qua Meter.turn()."""

    def __init__(self, meter):
        self._meter = meter
        self._started = datetime.now(timezone.utc)
        self._t0 = time.monotonic()
        self._ttft = None
        self._models = {}
        self.outcome = "ok"
        self._done = False

    def _slot(self, provider, model):
        key = (_clean_provider(provider), _clean_model(model))
        if key not in self._models:
            self._models[key] = {"calls": 0, "errors": 0, "retries": 0, "unmeasured": 0,
                                 "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}
        return self._models[key]

    def _add(self, provider, model, counts, retry):
        s = self._slot(provider, model)
        s["calls"] += 1
        s["retries"] += 1 if retry else 0
        if counts is None:
            s["unmeasured"] += 1
        else:
            for k in COUNTS:
                s[k] += counts[k]

    def record(self, resp, provider=None, model=None, retry=False):
        """Counts one LLM call from its response (or its usage). provider/model override what the response says.
        Đếm một lần gọi LLM từ phản hồi (hay usage) của nó. provider/model thay cho điều phản hồi ghi."""
        try:
            p, m, counts = read_usage(resp, provider)
            self._add(p, model or m, counts, retry)
        except Exception:
            pass

    def count(self, provider, model, input=None, output=None, cache_read=0, cache_write=0, cache_write_long=0, retry=False):
        """Counts one LLM call from numbers you read yourself, for a provider whose answer this file does not know.
        Đếm một lần gọi LLM từ số bạn tự đọc, cho hãng mà file này chưa biết dạng câu trả lời.
        input is the input tokens billed at the normal price (without cache reads and writes); None means not measured.
        input là token đầu vào tính giá thường (không gồm đọc và ghi cache); None nghĩa là không đo được."""
        try:
            counts = None if input is None or output is None else _counts(input, output, cache_read, cache_write, cache_write_long)
            self._add(provider, model, counts, retry)
        except Exception:
            pass

    def fail(self, provider, model, retry=False):
        """Counts one LLM call that failed (no answer, so no usage). Pass no error text.
        Đếm một lần gọi LLM bị lỗi (không có trả lời nên không có usage). Không truyền chữ của lỗi."""
        try:
            s = self._slot(provider, model)
            s["calls"] += 1
            s["errors"] += 1
            s["retries"] += 1 if retry else 0
        except Exception:
            pass

    def first_token(self):
        """Marks the first streamed piece of the answer; only the first mark counts.
        Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính."""
        if self._ttft is None:
            self._ttft = time.monotonic()

    def end(self, outcome=None):
        """Writes the line. Called by the `with` block; call it yourself when not using one.
        Ghi dòng. Khối `with` tự gọi; tự gọi khi không dùng khối đó."""
        if self._done:
            return
        self._done = True
        try:
            o = outcome or self.outcome
            now = self._started
            line = {
                "v": VERSION,
                "turnId": secrets.token_hex(8),
                "at": now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000),
                "durationMs": int((time.monotonic() - self._t0) * 1000),
                "outcome": o if o in ("ok", "error", "timeout") else "error",
                "env": self._meter.env,
                "models": [],
            }
            if self._ttft is not None:
                line["ttftMs"] = int((self._ttft - self._t0) * 1000)
            for (p, m), s in self._models.items():
                row = {"provider": p, "model": m}
                row.update(s)
                if s["unmeasured"] and s["calls"] - s["errors"] == s["unmeasured"]:
                    # every answered call lacked usage: the tokens are unknown, not zero
                    # mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
                    for k in COUNTS:
                        row[k] = None
                line["models"].append(row)
            self._meter._write(line)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, kind, value, tb):
        if kind is not None:
            self.outcome = "timeout" if "timeout" in kind.__name__.lower() else "error"
        self.end()
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, kind, value, tb):
        return self.__exit__(kind, value, tb)


# Sending to the board (optional): batches go from a background thread; a full queue drops the oldest turn, a failed send is tried once more,
# and nothing here ever waits on the network in the project's own thread
# Gửi lên bảng (tuỳ chọn): các lô đi từ một luồng nền; hàng đợi đầy thì bỏ lượt cũ nhất, gửi lỗi thì thử lại một lần,
# và không chỗ nào ở đây bắt luồng của chính dự án chờ mạng
SEND_QUEUE_MAX = 1000
SEND_EVERY_SECONDS = 10
SEND_BATCH_TURNS = 100
SEND_BATCH_BYTES = 200 * 1024
SEND_TIMEOUT_SECONDS = 5


def _send_allowed(url):
    # the key goes only over HTTPS, or to this machine itself
    # khoá chỉ đi qua HTTPS, hoặc tới chính máy này
    return url.startswith("https://") or re.match(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/", url) is not None


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    # a redirect is not followed: urllib would carry the key to the new address, another host or plain http included
    # không theo chuyển hướng: urllib sẽ mang khoá tới địa chỉ mới, kể cả máy khác hay http thường
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT = urllib.request.build_opener(_RefuseRedirect)


class _Sender:
    def __init__(self, url, key):
        self.url, self.key = url, key
        self.queue = collections.deque(maxlen=SEND_QUEUE_MAX)
        self.retry = []
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ai-meter-send", daemon=True)
        self.thread.start()
        self.lock = threading.Lock()
        atexit.register(self.flush)

    def add(self, line):
        self.queue.append(line)
        if len(self.queue) >= SEND_BATCH_TURNS:
            self.wake.set()

    def _run(self):
        while True:
            self.wake.wait(SEND_EVERY_SECONDS)
            self.wake.clear()
            try:
                self.flush()
            except Exception:
                pass

    def flush(self):
        with self.lock:
            self._flush()

    def _flush(self):
        while self.queue or self.retry:
            batch, size, again = self.retry, 0, bool(self.retry)
            self.retry = []
            while self.queue and len(batch) < SEND_BATCH_TURNS and size < SEND_BATCH_BYTES:
                line = self.queue.popleft()
                size += len(json.dumps(line))
                batch.append(line)
            body = json.dumps({"turns": batch}, separators=(",", ":")).encode()
            req = urllib.request.Request(self.url, data=body, method="POST", headers={
                "Authorization": "Bearer " + self.key, "Content-Type": "application/json", "User-Agent": "ai-meter/1"})
            try:
                with _NO_REDIRECT.open(req, timeout=SEND_TIMEOUT_SECONDS) as r:
                    r.read()
            except Exception:
                # tried once more at the next send, then let go; the file still has every turn
                # thử lại một lần ở lần gửi sau, rồi bỏ; file vẫn còn đủ mọi lượt
                if not again:
                    self.retry = batch
                return


class Meter:
    """Where the lines go. env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off.
    Nơi ghi các dòng. env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt."""

    def __init__(self, path="ai-meter.jsonl", env="prod", send_url=None, send_key=None):
        """send_url and send_key (or AI_METER_URL and AI_METER_KEY) also send each turn to the board, in the background; the file is still written.
        send_url và send_key (hoặc AI_METER_URL và AI_METER_KEY) gửi thêm từng lượt lên bảng, ở nền; file vẫn được ghi."""
        self.path = os.environ.get("AI_METER_FILE") or path
        e = os.environ.get("AI_METER_ENV") or env
        self.env = e if e in ("prod", "test") else "prod"
        self.off = os.environ.get("AI_METER_OFF") == "1"
        self.sender = None
        url, key = os.environ.get("AI_METER_URL") or send_url or "", os.environ.get("AI_METER_KEY") or send_key or ""
        try:
            if url and key and not self.off and _send_allowed(url):
                self.sender = _Sender(url, key)
        except Exception:
            self.sender = None

    def turn(self):
        return Turn(self)

    def _write(self, line):
        if self.off:
            return
        if self.sender:
            try:
                self.sender.add(line)
            except Exception:
                pass
        try:
            data = json.dumps(line, separators=(",", ":")) + "\n"
            with _lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(data)
        except Exception:
            pass
