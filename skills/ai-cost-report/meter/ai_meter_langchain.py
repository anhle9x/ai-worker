"""Measures an app built with LangChain or LangGraph (Python): a callback that counts every LLM call of a user turn into ai_meter.
  Đo một app dựng bằng LangChain hay LangGraph (Python): một callback đếm mọi lần gọi LLM của một lượt người dùng vào ai_meter.
Copy this file next to ai_meter.py. It needs nothing but the langchain-core the app already has (0.3.9 or later for cache counts).
  Chép file này cạnh ai_meter.py. Nó không cần gì ngoài langchain-core mà app đã có sẵn (0.3.9 trở lên để có số cache).
It never reads a prompt, an answer or an error message: token counts, the model's name and times only.
  Không bao giờ đọc câu hỏi, câu trả lời hay thông báo lỗi: chỉ số token, tên model và thời gian.

    from ai_meter import Meter
    from ai_meter_langchain import MeterCallback
    meter = Meter("ai-meter.jsonl", env="prod")
    with meter.turn() as t:
        answer = chain.invoke(question, config={"callbacks": [MeterCallback(t)]})   # a chain, an agent or a LangGraph graph
"""
import threading

try:
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:
    # the file still loads where LangChain is not installed, as in this skill's own tests
    # file vẫn nạp được ở nơi chưa cài LangChain, như trong test của chính skill này
    BaseCallbackHandler = object

# LangChain's name for a provider (ls_provider), where it differs from the name the price file uses
# Tên LangChain đặt cho một hãng (ls_provider), ở chỗ nó khác tên mà bảng giá dùng
PROVIDERS = {
    "google_genai": "google", "google_vertexai": "google", "google-genai": "google", "vertexai": "google",
    "amazon_bedrock": "bedrock", "bedrock_converse": "bedrock", "aws": "bedrock",
    "mistralai": "mistral", "azure": "openai", "azure_openai": "openai", "together": "togetherai",
}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _dict(obj, name):
    v = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return v if isinstance(v, dict) else {}


def usage_counts(usage):
    """The meter's counts from LangChain's usage_metadata, each input token counted once; None when it cannot be told.
    Số đếm của bộ đo từ usage_metadata của LangChain, mỗi token đầu vào chỉ đếm một lần; None khi không xác định được.

    input_tokens is the sum of every kind of input, cache reads and writes included; input_token_details splits them.
    input_tokens là tổng mọi loại đầu vào, gồm cả đọc và ghi cache; input_token_details tách chúng ra.
    """
    if not isinstance(usage, dict):
        return None
    total, out = _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))
    det = usage.get("input_token_details") if isinstance(usage.get("input_token_details"), dict) else {}
    read = _int(det.get("cache_read") or 0)
    write = _int(det.get("cache_creation") or 0)
    # Anthropic through LangChain may split the cache writes by how long they are kept
    # Anthropic qua LangChain có thể tách phần ghi cache theo thời gian giữ
    short, long_ = _int(det.get("ephemeral_5m_input_tokens") or 0), _int(det.get("ephemeral_1h_input_tokens") or 0)
    if None in (total, out, read, write, short, long_):
        return None
    if write == 0:
        write = short + long_
    if long_ > write or read + write > total:
        return None
    return {"input": total - read - write, "output": out, "cache_read": read, "cache_write": write, "cache_write_long": long_}


def _provider(name):
    p = str(name or "").strip().lower()
    return PROVIDERS.get(p, p) or None


class MeterCallback(BaseCallbackHandler):
    """Pass one of these, made for the turn, in config={"callbacks": [...]}: every model call under it is counted.
    Truyền một cái này, tạo cho lượt đó, vào config={"callbacks": [...]}: mọi lần gọi model bên dưới đều được đếm."""

    raise_error = False

    def __init__(self, turn):
        self._turn = turn
        self._lock = threading.Lock()
        # what each running call said about itself when it started: (provider, model)
        # điều mỗi lần gọi đang chạy tự khai khi bắt đầu: (hãng, model)
        self._runs = {}

    def _start(self, run_id, metadata, kwargs):
        try:
            meta = metadata if isinstance(metadata, dict) else {}
            params = kwargs.get("invocation_params") if isinstance(kwargs.get("invocation_params"), dict) else {}
            model = meta.get("ls_model_name") or params.get("model") or params.get("model_name")
            with self._lock:
                self._runs[run_id] = (_provider(meta.get("ls_provider")), model if isinstance(model, str) else None)
        except Exception:
            pass

    def on_chat_model_start(self, serialized, messages, *, run_id=None, metadata=None, **kwargs):
        self._start(run_id, metadata, kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id=None, metadata=None, **kwargs):
        self._start(run_id, metadata, kwargs)

    def on_llm_new_token(self, token, *, run_id=None, **kwargs):
        try:
            self._turn.first_token()
        except Exception:
            pass

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        try:
            with self._lock:
                provider, model = self._runs.pop(run_id, (None, None))
                llm_output = _dict(response, "llm_output")
                rows = getattr(response, "generations", None) or [[None]]
                for row in rows:
                    # one call per prompt of the batch; several candidates of one prompt share that call's usage
                    # mỗi câu hỏi trong lô là một lần gọi; nhiều phương án của một câu hỏi dùng chung usage của lần gọi đó
                    message = getattr(row[0], "message", None) if row else None
                    info = _dict(message, "response_metadata")
                    name = info.get("model_name") or info.get("model") or llm_output.get("model_name") or llm_output.get("model") or model
                    name = name if isinstance(name, str) else model
                    # pieces of a streamed answer that each carried the name are joined into the name written several times over
                    # các mẩu của câu trả lời streaming, mẩu nào cũng mang tên, bị nối lại thành cái tên viết lặp nhiều lần
                    if model and name and name != model and name.replace(model, "") == "":
                        name = model
                    who = provider or _provider(info.get("model_provider"))
                    counts = usage_counts(getattr(message, "usage_metadata", None))
                    if counts is not None:
                        self._turn.count(who or self._guess(name), name, **counts)
                    else:
                        # an older integration or a plain LLM: the provider's own usage, as the meter already reads it
                        # tích hợp cũ hoặc LLM thường: usage của chính hãng, đúng dạng bộ đo vốn đã đọc
                        raw = info.get("usage") or info.get("token_usage") or llm_output.get("token_usage") or llm_output.get("usage") or {}
                        self._turn.record(raw if isinstance(raw, dict) else {}, provider=who or self._guess(name), model=name)
        except Exception:
            pass

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        # only that it failed: the error's text is never read
        # chỉ ghi là nó lỗi: chữ của lỗi không bao giờ được đọc
        try:
            with self._lock:
                provider, model = self._runs.pop(run_id, (None, None))
                self._turn.fail(provider or self._guess(model), model)
        except Exception:
            pass

    @staticmethod
    def _guess(model):
        try:
            from ai_meter import guess_provider
            return guess_provider(model)
        except Exception:
            return "other"
