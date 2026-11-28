#!/usr/bin/env python3
"""Tests of the meter for AI projects and applications and its report (skills/ai-cost-report): python3 tests/appmeter/test_appmeter.py
Everything is written in a temporary folder. The meters for Node, TypeScript, Go, C#, Java, Rust and C/C++ are built and run against
the same answers when their tools are installed, and skipped when they are not.
  Test bộ đo cho dự án hay ứng dụng AI và báo cáo của nó (skills/ai-cost-report): python3 tests/appmeter/test_appmeter.py
  Mọi thứ ghi trong một thư mục tạm. Bộ đo cho Node, TypeScript, Go, C#, Java, Rust và C/C++ được dịch và chạy với cùng đáp án khi máy
  có công cụ của chúng, và được bỏ qua khi không có."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "ai-cost-report")
sys.path.insert(0, os.path.join(SKILL, "meter"))
sys.path.insert(0, SKILL)
import ai_meter  # noqa: E402
import ai_meter_langchain  # noqa: E402
import report  # noqa: E402

# words that sit in the sample answers and must never reach a line or a report
# các từ nằm trong câu trả lời mẫu và không bao giờ được vào một dòng hay báo cáo
PRIVATE = ("customer-plate-51A", "private-answer-text", "someone@example.com")

# sample responses, by provider, and the counts the meter must read from them
# phản hồi mẫu theo từng hãng, và số đếm bộ đo phải đọc ra từ chúng
SAMPLES = [
    ("anthropic", {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": PRIVATE[1]}],
                   "usage": {"input_tokens": 100, "output_tokens": 40, "cache_read_input_tokens": 900,
                             "cache_creation_input_tokens": 300, "cache_creation": {"ephemeral_1h_input_tokens": 100}}},
     {"input": 100, "output": 40, "cacheRead": 900, "cacheWrite": 300, "cacheWriteLong": 100}),
    ("openai", {"model": "gpt-6.1-terra", "choices": [{"message": {"content": PRIVATE[1]}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 50,
                          "prompt_tokens_details": {"cached_tokens": 300, "cache_write_tokens": 200}}},
     {"input": 500, "output": 50, "cacheRead": 300, "cacheWrite": 200, "cacheWriteLong": 0}),
    ("openai", {"model": "gpt-6.2-sol", "output_text": PRIVATE[1],
                "usage": {"input_tokens": 12000, "output_tokens": 10,
                          "input_tokens_details": {"cached_tokens": 4000, "cache_write_tokens": 7000,
                                                   "cache_write_tokens_details": {"ttl_30m_tokens": 3000, "ttl_12h_tokens": 4000}}}},
     {"input": 1000, "output": 10, "cacheRead": 4000, "cacheWrite": 7000, "cacheWriteLong": 4000}),
    ("google", {"modelVersion": "gemini-3.8-flash", "candidates": [{"content": {"parts": [{"text": PRIVATE[1]}]}}],
                "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 300, "thoughtsTokenCount": 50,
                                  "cachedContentTokenCount": 200}},
     {"input": 1000, "output": 350, "cacheRead": 200, "cacheWrite": 0, "cacheWriteLong": 0}),
    # OpenAI counts reasoning inside completion_tokens: total_tokens adds up without it, so it is not added twice
    # OpenAI tính token suy nghĩ trong completion_tokens: total_tokens cộng đủ mà không cần nó, nên không cộng hai lần
    ("openai", {"model": "gpt-6-luna", "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
                                                 "completion_tokens_details": {"reasoning_tokens": 30}}},
     {"input": 1000, "output": 50, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}),
    # xAI's own Chat Completions example: reasoning tokens sit outside completion_tokens (32 + 9 + 110 = 151)
    # ví dụ Chat Completions của chính xAI: token suy nghĩ nằm ngoài completion_tokens (32 + 9 + 110 = 151)
    ("xai", {"model": "grok-4.7", "choices": [{"message": {"content": PRIVATE[1]}}],
             "usage": {"prompt_tokens": 32, "completion_tokens": 9, "total_tokens": 151,
                       "prompt_tokens_details": {"text_tokens": 32, "cached_tokens": 8},
                       "completion_tokens_details": {"reasoning_tokens": 110}}},
     {"input": 24, "output": 119, "cacheRead": 8, "cacheWrite": 0, "cacheWriteLong": 0}),
    # the Vercel AI SDK's usage, as in xAI's docs: inputTokens include the cache
    # usage của Vercel AI SDK, như trong tài liệu xAI: inputTokens đã gồm cache
    ("xai", {"modelId": "grok-4.3", "text": PRIVATE[1],
             "usage": {"inputTokens": 129, "inputTokenDetails": {"noCacheTokens": 1, "cacheReadTokens": 128}, "outputTokens": 477,
                       "outputTokenDetails": {"textTokens": 477, "reasoningTokens": 0}, "totalTokens": 606}},
     {"input": 1, "output": 477, "cacheRead": 128, "cacheWrite": 0, "cacheWriteLong": 0}),
    # an API that copies OpenAI's shape and names its cache hits its own way (DeepSeek)
    # một API chép dạng của OpenAI và gọi phần trúng cache theo kiểu riêng (DeepSeek)
    ("deepseek", {"model": "deepseek-chat", "usage": {"prompt_tokens": 800, "completion_tokens": 60, "total_tokens": 860,
                                                      "prompt_cache_hit_tokens": 500, "prompt_cache_miss_tokens": 300}},
     {"input": 300, "output": 60, "cacheRead": 500, "cacheWrite": 0, "cacheWriteLong": 0}),
    ("bedrock", {"modelId": "amazon.nova-pro-v1:0", "output": {"message": {"content": [{"text": PRIVATE[1]}]}},
                 "usage": {"inputTokens": 120, "outputTokens": 30, "totalTokens": 650, "cacheReadInputTokens": 400, "cacheWriteInputTokens": 100}},
     {"input": 120, "output": 30, "cacheRead": 400, "cacheWrite": 100, "cacheWriteLong": 0}),
    ("ollama", {"model": "llama3.2:3b", "message": {"role": "assistant", "content": PRIVATE[1]}, "done": True,
                "prompt_eval_count": 26, "eval_count": 290, "total_duration": 5191566416},
     {"input": 26, "output": 290, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}),
    ("cohere", {"message": {"content": [{"text": PRIVATE[1]}]},
                "usage": {"billed_units": {"input_tokens": 17, "output_tokens": 12}, "tokens": {"input_tokens": 215, "output_tokens": 12}}},
     {"input": 17, "output": 12, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}),
]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="test-appmeter-")
        self.file = os.path.join(self.dir, "m.jsonl")
        for k in ("AI_METER_FILE", "AI_METER_ENV", "AI_METER_OFF"):
            os.environ.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def raw(self):
        with open(self.file, encoding="utf-8") as f:
            return f.read()

    def lines(self):
        with open(self.file, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def run_report(self, *args, files=None):
        out = os.path.join(self.dir, "out")
        with contextlib.redirect_stdout(io.StringIO()):
            report.main([*(files or [self.file]), "--out", out, *args])
        with open(os.path.join(out, "ai-cost-report.html"), encoding="utf-8") as f:
            page = f.read()
        with open(os.path.join(out, "ai-cost-report.csv"), encoding="utf-8") as f:
            table = f.read()
        return page, table


class ReadUsage(Tmp):
    def test_each_provider_counts_every_token_once(self):
        for provider, resp, want in SAMPLES:
            p, model, counts = ai_meter.read_usage(resp)
            self.assertEqual(p, provider)
            self.assertEqual(counts, want, model)
            inp = resp.get("usage", {}).get("prompt_tokens") or resp.get("usage", {}).get("input_tokens")
            if provider in ("openai", "deepseek") and "prompt_tokens" in resp.get("usage", {}):
                # the cache is inside OpenAI's input count: the parts add back up to it, never more
                # cache nằm trong số input của OpenAI: các phần cộng lại đúng bằng nó, không hơn
                self.assertEqual(counts["input"] + counts["cacheRead"] + counts["cacheWrite"], inp)

    def test_sdk_objects_are_read_like_dicts(self):
        class Usage:
            input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 5, 6, 7, 0

        class Msg:
            model = "claude-opus-5-5"
            usage = Usage()
        p, model, counts = ai_meter.read_usage(Msg())
        self.assertEqual((p, model, counts["input"], counts["cacheRead"]), ("anthropic", "claude-opus-5-5", 5, 7))

    def test_no_usage_is_not_measured_and_never_zero(self):
        for resp in ({"model": "gemini-3.8-flash"}, {"model": "gpt-6-luna", "usage": None}, None, "text",
                     {"usage": {"prompt_tokens": "12", "completion_tokens": 3}}, {"usage": {"input_tokens": -1, "output_tokens": 2}}):
            self.assertIsNone(ai_meter.read_usage(resp)[2], resp)
        self.assertEqual(ai_meter.read_usage({"model": "gemini-3.8-flash"})[0], "google")


class AnyProvider(Tmp):
    def test_counts_by_hand_for_a_provider_the_meter_does_not_know(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            t.count("Example-Cloud", "example-model-large", input=812, output=95, cache_read=40)
            t.count("example-cloud", "example-model-large", input=None, output=7)
            t.count("a provider name that is far too long to be a short name", "x", input=1, output=1)
        rows = {r["provider"]: r for r in self.lines()[0]["models"]}
        self.assertEqual(set(rows), {"example-cloud", "other"})
        r = rows["example-cloud"]
        self.assertEqual((r["calls"], r["unmeasured"], r["input"], r["output"], r["cacheRead"]), (2, 1, 812, 95, 40))

    def test_provider_names_are_short_and_safe(self):
        for bad in ("", "Has Space", "a" * 33, "x;rm", "-dash", PRIVATE[2]):
            self.assertEqual(ai_meter._clean_provider(bad), "other", bad)
        for good in ("openrouter", "azure-openai", "vllm", "my_gpu.box"):
            self.assertEqual(ai_meter._clean_provider(good), good)
        self.assertIsNotNone(report.clean_line(line("a" * 16, 5, [model("m", provider="my_gpu.box")])))
        self.assertIsNone(report.clean_line(line("a" * 16, 5, [model("m", provider="Has Space")])))

    def test_a_self_hosted_model_costs_nothing_but_shows_its_tokens(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            t.record([s for s in SAMPLES if s[0] == "ollama"][0][1])
            t.record({"model": "Qwen/Qwen3-32B", "usage": {"prompt_tokens": 400, "completion_tokens": 50}}, provider="vllm")
            t.record({"model": "claude-sonnet-5-5", "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 0}})
        turns = report.read_lines([self.file])[0]
        r = report.analyse(turns, report.Prices(os.path.join(SKILL, "prices.json")))
        self.assertEqual((r["measured"], r["priced"], r["unpriced"]), (1, 1, []))
        self.assertEqual(r["local"], ["Qwen/Qwen3-32B", "llama3.2:3b"])
        self.assertEqual(r["costTurn"], (1000 * 2 + 100 * 10) * 10 ** 6)
        self.assertEqual(r["tokTurn"]["input"], 26 + 400 + 1000)
        page, table = self.run_report("--lang", "vi")
        self.assertIn("chạy trên máy, không tính tiền API", page)  # i18n-allow
        self.assertIn("llama3.2:3b,ollama,1,1,0,0,26,290,0,0,0.000000000,,,,local", table)

    def test_your_own_price_file_adds_and_replaces_prices(self):
        mine = os.path.join(SKILL, "my-prices.example.json")
        p = report.Prices(os.path.join(SKILL, "prices.json"), [mine])
        self.assertEqual(p.at("example-model-large", "2026-11-20")["input"], 500000)
        self.assertEqual(p.at("gpt-6.1-terra", "2026-11-20")["input"], 900000)
        self.assertTrue(p.is_local("my-gpu-box", "anything"))
        self.assertTrue(p.is_local("openrouter", "Qwen/Qwen3-32B"))
        self.assertFalse(p.is_local("ollama", "example-model-large"))
        rows = [line("%016x" % 1, 100, [model("example-model-large", provider="example-cloud", input=1000, output=100)]),
                line("%016x" % 2, 100, [model("unknown-model", provider="example-cloud", input=10, output=1)])]
        with open(self.file, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in rows) + "\n")
        plain = report.analyse(report.read_lines([self.file])[0], report.Prices(os.path.join(SKILL, "prices.json")))
        self.assertEqual((plain["priced"], plain["costTurn"]), (0, None))
        r = report.analyse(report.read_lines([self.file])[0], p)
        self.assertEqual((r["priced"], r["unpriced"]), (1, ["unknown-model"]))
        self.assertEqual(r["costTurn"], (1000 * 0.5 + 100 * 1.5) * 10 ** 6)
        page, _ = self.run_report("--add-prices", mine)
        self.assertIn("my-prices.example.json", page)


class Meter(Tmp):
    def test_a_line_holds_counts_only(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            for _, resp, _ in SAMPLES:
                t.record(resp)
            t.record({"model": PRIVATE[0] + " with spaces", "usage": {"input_tokens": 1, "output_tokens": 1}}, provider=PRIVATE[2])
        raw = self.raw()
        for word in PRIVATE:
            self.assertNotIn(word, raw)
        line = self.lines()[0]
        self.assertEqual(set(line), {"v", "turnId", "at", "durationMs", "outcome", "env", "models"})
        self.assertRegex(line["turnId"], r"^[0-9a-f]{16}$")
        self.assertIn({"provider": "other", "model": "unknown"}, [{"provider": r["provider"], "model": r["model"]} for r in line["models"]])
        self.assertIsNotNone(report.clean_line(line))

    def test_missing_usage_writes_null_and_counts_the_call(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            t.record({"model": "gpt-6-luna"})
        row = self.lines()[0]["models"][0]
        self.assertEqual((row["calls"], row["unmeasured"], row["input"], row["output"]), (1, 1, None, None))

    def test_streaming_marks_the_first_token_once(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            t.first_token()
            first = t._ttft
            t.first_token()
            self.assertEqual(t._ttft, first)
            t.record(SAMPLES[0][1])
        line = self.lines()[0]
        self.assertIn("ttftMs", line)
        self.assertLessEqual(line["ttftMs"], line["durationMs"])

    def test_retries_and_failures_are_counted(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            t.fail("anthropic", "claude-sonnet-5-5")
            t.record(SAMPLES[0][1], retry=True)
        row = self.lines()[0]["models"][0]
        self.assertEqual((row["calls"], row["errors"], row["retries"], row["input"]), (2, 1, 1, 100))

    def test_the_app_error_is_kept_and_the_outcome_written(self):
        class ReadTimeout(Exception):
            pass
        m = ai_meter.Meter(self.file)
        with self.assertRaises(ValueError):
            with m.turn():
                raise ValueError(PRIVATE[1])
        with self.assertRaises(ReadTimeout):
            with m.turn():
                raise ReadTimeout()
        self.assertEqual([x["outcome"] for x in self.lines()], ["error", "timeout"])
        self.assertNotIn(PRIVATE[1], self.raw())

    def test_the_meter_never_breaks_the_app(self):
        m = ai_meter.Meter(os.path.join(self.dir, "no-such-folder", "m.jsonl"))
        with m.turn() as t:
            t.record(object())
            t.record(SAMPLES[0][1])
        os.environ["AI_METER_OFF"] = "1"
        with ai_meter.Meter(self.file).turn() as t:
            t.record(SAMPLES[0][1])
        self.assertFalse(os.path.exists(self.file))

    def test_env_comes_from_the_environment(self):
        os.environ["AI_METER_ENV"] = "test"
        with ai_meter.Meter(self.file).turn():
            pass
        self.assertEqual(self.lines()[0]["env"], "test")

    def test_a_redirect_is_not_followed_with_the_key(self):
        # the board answers 302 to another address: nothing reaches that address, so the key stays where it was sent
        # bảng trả 302 sang địa chỉ khác: không gì tới được địa chỉ đó, nên khoá ở lại nơi nó được gửi tới
        with Board() as other:
            class Redirect(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.send_response(302)
                    self.send_header("Location", other.url)
                    self.end_headers()

                def log_message(self, *args):
                    pass

            first = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
            threading.Thread(target=first.serve_forever, daemon=True).start()
            try:
                sender = ai_meter._Sender("http://127.0.0.1:%d/projects/ingest" % first.server_address[1], "test-key")
                sender.add({"turnId": "t1"})
                sender.flush()
            finally:
                first.shutdown()
                first.server_close()
            self.assertEqual(other.sent, [])


def line(tid, ms, models, outcome="ok", at="2026-11-20T08:00:00.000Z", **more):
    d = {"v": 1, "turnId": tid, "at": at, "durationMs": ms, "outcome": outcome, "env": "prod", "models": models}
    d.update(more)
    return d


def model(name, provider="anthropic", **counts):
    row = {"provider": provider, "model": name, "calls": 1, "errors": 0, "retries": 0, "unmeasured": 0,
           "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}
    row.update(counts)
    return row


class LangChainMeter(Tmp):
    """The callback for apps built with LangChain or LangGraph, fed the events LangChain sends (langchain-core's own shapes).
    Callback cho app dựng bằng LangChain hay LangGraph, được đưa các sự kiện LangChain gửi (đúng dạng của langchain-core)."""

    @staticmethod
    def answer(usage=None, info=None, llm_output=None, plain=False):
        from types import SimpleNamespace as N
        message = None if plain else N(content=PRIVATE[1], usage_metadata=usage, response_metadata=info or {})
        return N(generations=[[N(text=PRIVATE[1], message=message)]], llm_output=llm_output)

    def test_every_call_of_a_turn_is_counted_with_each_input_token_once(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            cb = ai_meter_langchain.MeterCallback(t)
            cb.on_chat_model_start({}, [[PRIVATE[0]]], run_id=1, metadata={"ls_provider": "anthropic", "ls_model_name": "claude-sonnet-4-5"})
            cb.on_llm_end(self.answer({"input_tokens": 350, "output_tokens": 240, "total_tokens": 590,
                                       "input_token_details": {"cache_creation": 200, "cache_read": 100}}, {"model_name": "claude-sonnet-4-5"}), run_id=1)
            cb.on_chat_model_start({}, [[PRIVATE[0]]], run_id=2, metadata={"ls_provider": "google_genai"})
            cb.on_llm_end(self.answer({"input_tokens": 50, "output_tokens": 5, "total_tokens": 55}, {"model_name": "gemini-2.5-pro"}), run_id=2)
            cb.on_chat_model_start({}, [[PRIVATE[0]]], run_id=3, metadata={"ls_provider": "anthropic", "ls_model_name": "claude-sonnet-4-5"})
            cb.on_llm_end(self.answer({"input_tokens": 1000, "output_tokens": 1, "total_tokens": 1001,
                                       "input_token_details": {"cache_read": 0, "ephemeral_5m_input_tokens": 300, "ephemeral_1h_input_tokens": 600}}), run_id=3)
        rows = {(r["provider"], r["model"]): r for r in self.lines()[0]["models"]}
        claude = rows[("anthropic", "claude-sonnet-4-5")]
        self.assertEqual([claude[k] for k in ("calls", "input", "output", "cacheRead", "cacheWrite", "cacheWriteLong")], [2, 150, 241, 100, 1100, 600])
        gemini = rows[("google", "gemini-2.5-pro")]
        self.assertEqual([gemini[k] for k in ("calls", "input", "output", "cacheRead", "cacheWrite")], [1, 50, 5, 0, 0])
        for word in PRIVATE:
            self.assertNotIn(word, self.raw())

    def test_usage_that_does_not_add_up_is_not_measured_and_never_guessed(self):
        counts = ai_meter_langchain.usage_counts
        self.assertEqual(counts({"input_tokens": 10, "output_tokens": 2}), {"input": 10, "output": 2, "cache_read": 0, "cache_write": 0, "cache_write_long": 0})
        self.assertIsNone(counts({"input_tokens": 10, "output_tokens": 2, "input_token_details": {"cache_read": 11}}))
        self.assertIsNone(counts({"input_tokens": 10, "output_tokens": 2, "input_token_details": {"cache_creation": 4, "ephemeral_1h_input_tokens": 5}}))
        self.assertIsNone(counts({"input_tokens": True, "output_tokens": 2}))
        self.assertIsNone(counts({"output_tokens": 2}))
        self.assertIsNone(counts(None))

    def test_an_answer_with_no_standard_usage_falls_back_to_the_providers_own(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            cb = ai_meter_langchain.MeterCallback(t)
            cb.on_chat_model_start({}, [[]], run_id=1, metadata={"ls_provider": "openai", "ls_model_name": "gpt-6-luna"})
            cb.on_llm_end(self.answer(None, {"token_usage": {"prompt_tokens": 9, "completion_tokens": 4, "prompt_tokens_details": {"cached_tokens": 3}}}), run_id=1)
            cb.on_llm_start({}, [PRIVATE[0]], run_id=2, metadata={"ls_provider": "openai"}, invocation_params={"model_name": "gpt-6-luna"})
            cb.on_llm_end(self.answer(plain=True, llm_output={"token_usage": {"prompt_tokens": 2, "completion_tokens": 1}, "model_name": "gpt-6-luna"}), run_id=2)
            cb.on_chat_model_start({}, [[]], run_id=3, metadata={"ls_provider": "ollama", "ls_model_name": "llama-local"})
            cb.on_llm_end(self.answer(), run_id=3)
        rows = {(r["provider"], r["model"]): r for r in self.lines()[0]["models"]}
        gpt = rows[("openai", "gpt-6-luna")]
        self.assertEqual([gpt[k] for k in ("calls", "unmeasured", "input", "output", "cacheRead")], [2, 0, 8, 5, 3])
        local = rows[("ollama", "llama-local")]
        self.assertEqual((local["calls"], local["unmeasured"], local["input"]), (1, 1, None))

    def test_a_failed_call_and_the_first_streamed_piece_are_marked_without_their_text(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            cb = ai_meter_langchain.MeterCallback(t)
            cb.on_chat_model_start({}, [[]], run_id=1, metadata={"ls_provider": "anthropic", "ls_model_name": "claude-sonnet-4-5"})
            cb.on_llm_new_token(PRIVATE[1], run_id=1)
            cb.on_llm_error(RuntimeError(PRIVATE[2]), run_id=1)
            cb.on_llm_error(RuntimeError(PRIVATE[2]), run_id="never started")
        line = self.lines()[0]
        self.assertIn("ttftMs", line)
        rows = {(r["provider"], r["model"]): r for r in line["models"]}
        self.assertEqual((rows[("anthropic", "claude-sonnet-4-5")]["calls"], rows[("anthropic", "claude-sonnet-4-5")]["errors"]), (1, 1))
        self.assertEqual(rows[("other", "unknown")]["errors"], 1)
        for word in PRIVATE:
            self.assertNotIn(word, self.raw())

    def test_the_callback_never_breaks_the_app(self):
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            cb = ai_meter_langchain.MeterCallback(t)
            cb.on_chat_model_start(None, None, run_id=None, metadata="odd", invocation_params=7)
            cb.on_llm_end(None, run_id=None)
            cb.on_llm_end(self.answer({"input_tokens": "many"}), run_id=5)
            cb.on_llm_error(None)
            cb.on_llm_new_token(None)
        self.assertEqual(len(self.lines()), 1)

    def test_it_counts_under_the_real_langchain_when_installed(self):
        try:
            from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
            from langchain_core.messages import AIMessage
        except Exception:
            self.skipTest("langchain-core is not installed")
        usage = {"input_tokens": 350, "output_tokens": 240, "total_tokens": 590, "input_token_details": {"cache_creation": 200, "cache_read": 100}}
        model = GenericFakeChatModel(messages=iter([AIMessage(content=PRIVATE[1], usage_metadata=usage, response_metadata={"model_name": "claude-sonnet-4-5"})]))
        m = ai_meter.Meter(self.file)
        with m.turn() as t:
            model.invoke(PRIVATE[0], config={"callbacks": [ai_meter_langchain.MeterCallback(t)]})
        row = self.lines()[0]["models"][0]
        self.assertEqual([row[k] for k in ("calls", "input", "output", "cacheRead", "cacheWrite")], [1, 50, 240, 100, 200])
        for word in PRIVATE:
            self.assertNotIn(word, self.raw())


class Report(Tmp):
    def write(self, rows, extra=()):
        with open(self.file, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
            for x in extra:
                f.write(x + "\n")

    def test_p95_is_nearest_rank(self):
        self.assertEqual(report.p95(list(range(1, 21))), 19)
        self.assertEqual(report.p95(list(range(100, 0, -1))), 95)
        self.assertEqual(report.p95([7]), 7)
        self.assertEqual(report.p95([1, 2]), 2)
        self.assertIsNone(report.p95([]))

    def test_p95_in_the_report_uses_raw_turns(self):
        self.write([line("%016x" % i, i * 10, []) for i in range(1, 41)])
        r = report.analyse(report.read_lines([self.file])[0], report.Prices(os.path.join(SKILL, "prices.json")))
        self.assertEqual((r["ms"]["p95"], r["ms"]["max"]), (380, 400))

    def test_unknown_fields_and_bad_lines_are_dropped(self):
        good = line("a" * 16, 100, [model("claude-sonnet-5-5", input=1000, output=100, note=PRIVATE[1])], prompt=PRIVATE[1], user=PRIVATE[2])
        bad = [line("b" * 16, 100, [model(PRIVATE[0] + " x")]), line("c" * 16, -1, []), line("d" * 16, 5, [], ttftMs=9),
               line("e" * 16, 5, [model("x", provider=PRIVATE[2])]), line("f" * 16, 5, [model("x", input=None, output=3)])]
        self.write([good, good] + bad, extra=["not json", "{}"])
        turns, skipped, dupes = report.read_lines([self.file])
        self.assertEqual((len(turns), skipped, dupes), (1, 7, 1))
        page, table = self.run_report()
        for word in PRIVATE:
            self.assertNotIn(word, page + table)

    def test_cost_is_exact_and_cache_is_not_counted_twice(self):
        # Sonnet 5.5: input 2, output 10, cache read 0.10, 5-minute write 2.50, 1-hour write 4 dollars per million tokens
        # Sonnet 5.5: đầu vào 2, đầu ra 10, đọc cache 0,10, ghi 5 phút 2,50, ghi 1 giờ 4 đô mỗi triệu token
        p = report.Prices(os.path.join(SKILL, "prices.json"))
        row = model("claude-sonnet-5-5", input=1000, output=100, cacheRead=10000, cacheWrite=3000, cacheWriteLong=1000)
        cost = p.cost(row, p.at("claude-sonnet-5-5", "2026-11-20"))
        want = 1000 * 2 + 100 * 10 + 10000 * 0.10 + 2000 * 2.50 + 1000 * 4
        self.assertEqual(cost, round(want * 10 ** 6))

    def test_price_follows_the_day_and_the_model_name_variants(self):
        p = report.Prices(os.path.join(SKILL, "prices.json"))
        self.assertLess(p.at("gemini-4-carbon", "2026-11-30")["input"], p.at("gemini-4-carbon", "2026-12-01")["input"])
        self.assertIsNone(p.at("gpt-5.6-sol", "2026-12-02")["input"])
        self.assertEqual(p.at("grok-4.20", "2026-11-20"), p.at("grok-4.20-0309-reasoning", "2026-11-20"))
        self.assertEqual(p.at("grok-4.7", "2026-11-20")["output"], 6 * 10 ** 6)
        for name in ("claude-haiku-4-5-20251001", "global.anthropic.claude-fable-5-2", "models/gemini-3.8-flash", "claude-opus-4-6@20260101"):
            self.assertIsNotNone(p.entry(name), name)
        self.assertIsNone(p.entry("my-own-model"))

    def test_unpriced_and_unmeasured_are_shown_not_zeroed(self):
        rows = [line("%016x" % 1, 100, [model("claude-sonnet-5-5", input=1000, output=100)]),
                line("%016x" % 2, 100, [model("my-own-model", provider="example-cloud", input=500, output=50)]),
                line("%016x" % 3, 100, [model("gpt-6-luna", provider="openai", unmeasured=1, input=None, output=None)])]
        self.write(rows)
        turns = report.read_lines([self.file])[0]
        r = report.analyse(turns, report.Prices(os.path.join(SKILL, "prices.json")))
        self.assertEqual((r["turns"], r["measured"], r["priced"]), (3, 2, 1))
        self.assertEqual(r["unpriced"], ["my-own-model"])
        self.assertEqual(r["costTurn"], (1000 * 2 + 100 * 10) * 10 ** 6)
        self.assertEqual(r["tokTurn"]["input"], 750)
        page, table = self.run_report("--lang", "vi")
        self.assertIn("chưa có giá", page)  # i18n-allow
        self.assertIn("không đo được", page)  # i18n-allow
        self.assertIn("my-own-model,example-cloud,1,1,0,0,500,50", table)

    def test_compare_is_an_estimate_on_the_same_tokens(self):
        self.write([line("%016x" % 1, 100, [model("claude-sonnet-5-5", input=1000, output=100)])])
        r = report.analyse(report.read_lines([self.file])[0], report.Prices(os.path.join(SKILL, "prices.json")), ["claude-haiku-5-5", "nope"])
        self.assertEqual(r["alt"][0]["costTurn"], round((1000 * 0.10 + 100 * 0.50) * 10 ** 6))
        self.assertIsNone(r["alt"][1]["costTurn"])

    def test_env_and_days_filter(self):
        self.write([line("%016x" % 1, 100, []), line("%016x" % 2, 100, [], env="test"),
                    line("%016x" % 3, 100, [], at="2026-11-25T01:00:00Z")])
        page, table = self.run_report("--from", "2026-11-21")
        self.assertIn("perTurnAverage,all,,1,", table)

    def test_prices_file_is_whole(self):
        with open(os.path.join(SKILL, "prices.json"), encoding="utf-8") as f:
            doc = json.load(f)
        for m in doc["models"]:
            self.assertIn(m["provider"], doc["providers"])
            for row in m["prices"]:
                for k in ("input", "output", "cacheRead", "cacheWrite", "cacheWriteLong"):
                    self.assertTrue(row[k] is None or (isinstance(row[k], int) and row[k] >= 0), m["model"])
        for p in doc["providers"].values():
            self.assertRegex(p["checked"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(p["source"].startswith("https://"))


NODE = shutil.which("node")
NODE_SCRIPT = r"""
const { Meter, readUsage } = require(process.argv[1])
const samples = JSON.parse(process.argv[2])
const file = process.argv[3]
const out = samples.map((s) => readUsage(s))
const m = new Meter({ file, sync: true })
;(async () => {
  await m.turn(async (t) => { t.firstToken(); for (const s of samples) t.record(s); t.fail('anthropic', 'claude-sonnet-5-5', { retry: true }) })
  await m.turn(async (t) => { t.record({ model: 'gpt-6-luna' }); t.count('Example-Cloud', 'example-model-large', { input: 5, output: 2 }); t.count('Bad Name', 'x', { output: 1 }) })
  try { await m.turn(async () => { const e = new Error('x'); e.name = 'TimeoutError'; throw e }) } catch (e) { out.push('rethrown') }
  const t = m.start(); t.record(null); t.end(); t.end()
  console.log(JSON.stringify(out))
})()
"""


@unittest.skipUnless(NODE, "node is not installed")
class NodeMeter(Tmp):
    def test_node_reads_and_writes_like_python(self):
        samples = [s[1] for s in SAMPLES]
        res = subprocess.run([NODE, "-e", NODE_SCRIPT, os.path.join(SKILL, "meter", "ai-meter.cjs"), json.dumps(samples), self.file],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        for (provider, _, want), got in zip(SAMPLES, out):
            self.assertEqual((got["provider"], got["counts"]), (provider, want))
        self.assertEqual(out[-1], "rethrown")
        lines = self.lines()
        self.assertEqual([x["outcome"] for x in lines], ["ok", "ok", "timeout", "ok"])
        for x in lines:
            self.assertIsNotNone(report.clean_line(x), x)
        self.assertIn("ttftMs", lines[0])
        son = [r for r in lines[0]["models"] if r["model"] == "claude-sonnet-5-5"][0]
        self.assertEqual((son["calls"], son["errors"], son["retries"]), (2, 1, 1))
        self.assertEqual(lines[1]["models"][0]["input"], None)
        by = {r["provider"]: r for r in lines[1]["models"]}
        self.assertEqual((by["example-cloud"]["input"], by["example-cloud"]["output"]), (5, 2))
        self.assertEqual((by["other"]["unmeasured"], by["other"]["input"]), (1, None))
        raw = self.raw()
        for word in PRIVATE:
            self.assertNotIn(word, raw)


# The events LangChain.js sends to a handler, fed by hand to the callbacks: the same cases as LangChainMeter above
# Các sự kiện LangChain.js gửi tới một handler, đưa bằng tay cho các callback: cùng các trường hợp với LangChainMeter ở trên
NODE_LANGCHAIN_SCRIPT = r"""
const [dir, file, priv] = process.argv.slice(1)
const { Meter } = require(dir + '/ai-meter.cjs')
const { meterCallback, usageCounts } = require(dir + '/ai-meter-langchain.cjs')
const meter = new Meter({ file, sync: true })
const answer = (usage, info, llmOutput) => ({ generations: [[{ text: priv, message: { content: priv, usage_metadata: usage, response_metadata: info || {} } }]], llmOutput })
const t = meter.start(), cb = meterCallback(t)
cb.handleChatModelStart({}, [[priv]], 'r1', undefined, {}, [], { ls_provider: 'anthropic', ls_model_name: 'claude-sonnet-4-5' })
cb.handleLLMNewToken(priv)
cb.handleLLMEnd(answer({ input_tokens: 350, output_tokens: 240, total_tokens: 590, input_token_details: { cache_creation: 200, cache_read: 100 } },
  { model_name: 'claude-sonnet-4-5claude-sonnet-4-5' }), 'r1')
cb.handleChatModelStart({}, [[priv]], 'r2', undefined, {}, [], { ls_provider: 'google_genai' })
cb.handleLLMEnd(answer({ input_tokens: 50, output_tokens: 5, total_tokens: 55 }, { model_name: 'gemini-2.5-pro' }), 'r2')
cb.handleLLMStart({}, [priv], 'r3', undefined, { invocation_params: { model: 'gpt-6-luna' } }, [], { ls_provider: 'openai' })
cb.handleLLMEnd(answer(undefined, {}, { tokenUsage: { promptTokens: 9, completionTokens: 4, totalTokens: 13 } }), 'r3')
cb.handleChatModelStart({}, [[priv]], 'r4', undefined, {}, [], { ls_provider: 'ollama', ls_model_name: 'llama-local' })
cb.handleLLMEnd(answer(), 'r4')
cb.handleChatModelStart({}, [[priv]], 'r5', undefined, {}, [], { ls_provider: 'anthropic', ls_model_name: 'claude-sonnet-4-5' })
cb.handleLLMError(new Error(priv), 'r5')
cb.handleLLMEnd(null, null); cb.handleLLMError(null); cb.handleChatModelStart(null, null, null, null, 7, null, 'odd')
t.end()
console.log(JSON.stringify([usageCounts({ input_tokens: 10, output_tokens: 2, input_token_details: { cache_read: 11 } }),
  usageCounts({ input_tokens: 1000, output_tokens: 1, input_token_details: { ephemeral_5m_input_tokens: 300, ephemeral_1h_input_tokens: 600 } }), usageCounts(null)]))
"""


class NodeLangChainMeter(Tmp):
    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_node_callbacks_count_like_the_python_one(self):
        res = subprocess.run([NODE, "-e", NODE_LANGCHAIN_SCRIPT, os.path.join(SKILL, "meter"), self.file, PRIVATE[1]], capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), [None, {"input": 100, "output": 1, "cacheRead": 0, "cacheWrite": 900, "cacheWriteLong": 600}, None])
        line = self.lines()[0]
        self.assertIn("ttftMs", line)
        self.assertIsNotNone(report.clean_line(line))
        rows = {(r["provider"], r["model"]): r for r in line["models"]}
        claude = rows[("anthropic", "claude-sonnet-4-5")]
        self.assertEqual([claude[k] for k in ("calls", "errors", "input", "output", "cacheRead", "cacheWrite")], [2, 1, 50, 240, 100, 200])
        self.assertEqual([rows[("google", "gemini-2.5-pro")][k] for k in ("calls", "input", "output")], [1, 50, 5])
        self.assertEqual([rows[("openai", "gpt-6-luna")][k] for k in ("calls", "unmeasured", "input", "output")], [1, 0, 9, 4])
        self.assertEqual((rows[("ollama", "llama-local")]["unmeasured"], rows[("ollama", "llama-local")]["input"]), (1, None))
        self.assertNotIn(PRIVATE[1], self.raw())


METER = os.path.join(SKILL, "meter")
COUNT_FIELDS = ("input", "output", "cacheRead", "cacheWrite", "cacheWriteLong")


def lower_keys(counts):
    # Go and C# write their Counts with capital letters (Input, CacheRead): compare them under the line's own names
    # Go và C# ghi Counts bằng chữ hoa đầu (Input, CacheRead): so sánh theo đúng tên trong dòng
    return None if counts is None else {k[0].lower() + k[1:]: v for k, v in counts.items()}


class Board:
    """A board on this machine that only keeps what each send carried.
    Một bảng chạy trên máy này, chỉ giữ lại những gì mỗi lần gửi mang tới."""

    def __enter__(self):
        sent = self.sent = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                sent.append({"path": self.path, "auth": self.headers.get("Authorization"),
                             "type": self.headers.get("Content-Type", ""), "body": json.loads(body.decode("utf-8"))})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/projects/ingest" % self.server.server_address[1]
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def turns(self):
        return [t for s in self.sent for t in s["body"]["turns"]]


def run(cmd, cwd, timeout=300, env=None):
    full = dict(os.environ, **(env or {}))
    for k in ("AI_METER_FILE", "AI_METER_ENV", "AI_METER_OFF", "AI_METER_URL", "AI_METER_KEY"):
        if k not in (env or {}):
            full.pop(k, None)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=full)


class SameAsPython(Tmp):
    """What the Go, C# and Java meters must give for the same program: the same counts as ai_meter.py for every sample, the same three
    lines in the file, and the same three lines on the board.
    Điều bộ đo Go, C# và Java phải cho ra với cùng một chương trình: cùng số đếm như ai_meter.py cho mọi mẫu, cùng ba dòng trong file,
    và cùng ba dòng trên bảng."""

    def samples_file(self):
        path = os.path.join(self.dir, "samples.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([s[1] for s in SAMPLES], f)
        return path

    def check(self, out, board):
        self.assertEqual(len(out), len(SAMPLES))
        for (provider, _, want), got in zip(SAMPLES, out):
            self.assertEqual((got["provider"], lower_keys(got["counts"])), (provider, want), got.get("model"))
        lines = self.lines()
        self.assertEqual([x["outcome"] for x in lines], ["ok", "ok", "timeout"])
        for x in lines:
            self.assertIsNotNone(report.clean_line(x), x)
            self.assertEqual(x["env"], "prod")
        self.assertIn("ttftMs", lines[0])
        son = [r for r in lines[0]["models"] if r["model"] == "claude-sonnet-5-5"][0]
        self.assertEqual((son["calls"], son["errors"], son["retries"], son["input"]), (2, 1, 1, 100))
        grok = [r for r in lines[0]["models"] if r["model"] == "grok-4.7"][0]
        self.assertEqual((grok["input"], grok["output"], grok["cacheRead"]), (24, 119, 8))
        luna = lines[1]["models"][0]
        self.assertEqual((luna["model"], luna["calls"], luna["unmeasured"]), ("gpt-6-luna", 1, 1))
        self.assertEqual([luna[k] for k in COUNT_FIELDS], [None] * 5)
        by = {r["provider"]: r for r in lines[1]["models"]}
        self.assertEqual((by["example-cloud"]["input"], by["example-cloud"]["output"]), (5, 2))
        self.assertEqual((by["other"]["unmeasured"], by["other"]["input"]), (1, None))
        self.assertEqual(lines[2]["models"], [])
        raw = self.raw()
        for word in PRIVATE:
            self.assertNotIn(word, raw)
        # the board got every line of the file, with the key, as one JSON body
        # bảng nhận đủ mọi dòng của file, kèm khoá, trong một thân JSON
        self.assertTrue(board.sent, "nothing was sent to the board")
        for s in board.sent:
            self.assertEqual((s["path"], s["auth"]), ("/projects/ingest", "Bearer prj_test"))
            self.assertTrue(s["type"].startswith("application/json"), s["type"])
        self.assertEqual(board.turns(), lines)


GO = shutil.which("go")
GO_MAIN = r"""package main

import (
	"encoding/json"
	"fmt"
	"os"

	"apptest/aimeter"
)

func main() {
	var samples []json.RawMessage
	b, _ := os.ReadFile(os.Args[1])
	if json.Unmarshal(b, &samples) != nil {
		os.Exit(2)
	}
	out := []any{}
	for _, s := range samples {
		p, m, c := aimeter.Read(s, "")
		out = append(out, map[string]any{"provider": p, "model": m, "counts": c})
	}
	m := aimeter.NewSending(os.Args[2], "prod", os.Args[3], "prj_test")
	t := m.Turn()
	t.FirstToken()
	for _, s := range samples {
		t.Record(s)
	}
	t.Fail("anthropic", "claude-sonnet-5-5", true)
	t.End()
	t2 := m.Turn()
	t2.Record([]byte(`{"model":"gpt-6-luna"}`))
	t2.Count("Example-Cloud", "example-model-large", &aimeter.Counts{Input: 5, Output: 2})
	t2.Count("Bad Name", "x", nil)
	t2.End()
	t2.End()
	t3 := m.Turn()
	t3.SetOutcome("timeout")
	t3.End()
	m.Close()
	e, _ := json.Marshal(out)
	fmt.Println(string(e))
}
"""


@unittest.skipUnless(GO, "go is not installed")
class GoMeter(SameAsPython):
    def test_go_reads_writes_and_sends_like_python(self):
        src = os.path.join(self.dir, "go")
        os.makedirs(os.path.join(src, "aimeter"))
        shutil.copy(os.path.join(METER, "aimeter.go"), os.path.join(src, "aimeter"))
        with open(os.path.join(src, "go.mod"), "w", encoding="utf-8") as f:
            f.write("module apptest\n\ngo 1.21\n")
        with open(os.path.join(src, "main.go"), "w", encoding="utf-8") as f:
            f.write(GO_MAIN)
        env = {"GOTOOLCHAIN": "local", "GOFLAGS": "-mod=mod"}
        res = run([GO, "vet", "./..."], src, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        with Board() as board:
            res = run([GO, "run", ".", self.samples_file(), self.file, board.url], src, env=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.check(json.loads(res.stdout), board)


DOTNET = shutil.which("dotnet")
CS_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net$(BundledNETCoreAppTargetFrameworkVersion)</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <InvariantGlobalization>true</InvariantGlobalization>
  </PropertyGroup>
</Project>
"""
CS_MAIN = r"""using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

var samples = JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
var output = new List<object?>();
foreach (var s in samples.EnumerateArray())
{
    var (p, m, c) = AiMeter.Usage.Read(s);
    output.Add(new Dictionary<string, object?> { ["provider"] = p, ["model"] = m, ["counts"] = c });
}
var meter = new AiMeter.Meter(args[1], "prod", args[2], "prj_test");
using (var t = meter.Turn())
{
    t.FirstToken();
    foreach (var s in samples.EnumerateArray()) t.Record(s);
    t.Fail("anthropic", "claude-sonnet-5-5", retry: true);
}
var t2 = meter.Turn();
t2.Record("{\"model\":\"gpt-6-luna\"}");
t2.Count("Example-Cloud", "example-model-large", input: 5, output: 2);
t2.Count("Bad Name", "x", output: 1);
t2.End();
t2.End();
var t3 = meter.Turn();
t3.Outcome = "timeout";
t3.Dispose();
await meter.FlushAsync();
Console.WriteLine(JsonSerializer.Serialize(output));
"""


@unittest.skipUnless(DOTNET, "dotnet is not installed")
class CSharpMeter(SameAsPython):
    def test_csharp_reads_writes_and_sends_like_python(self):
        src = os.path.join(self.dir, "cs")
        os.makedirs(src)
        shutil.copy(os.path.join(METER, "AiMeter.cs"), src)
        with open(os.path.join(src, "apptest.csproj"), "w", encoding="utf-8") as f:
            f.write(CS_PROJECT)
        with open(os.path.join(src, "Program.cs"), "w", encoding="utf-8") as f:
            f.write(CS_MAIN)
        env = {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"}
        build = os.path.join(src, "build")
        res = run([DOTNET, "build", "-c", "Release", "-o", build, "-nologo", "-v", "q"], src, env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with Board() as board:
            res = run([DOTNET, os.path.join(build, "apptest.dll"), self.samples_file(), self.file, board.url], src, env=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.check(json.loads(res.stdout), board)


def find_jdk():
    # a JDK that works: JAVA_HOME, then the usual Homebrew folders, then PATH (on macOS /usr/bin/javac is only a stub)
    # một JDK chạy được: JAVA_HOME, rồi các thư mục Homebrew hay gặp, rồi PATH (trên macOS /usr/bin/javac chỉ là lối tắt)
    places = [os.path.join(os.environ.get("JAVA_HOME", ""), "bin")] if os.environ.get("JAVA_HOME") else []
    for base in ("/opt/homebrew/opt", "/usr/local/opt"):
        if os.path.isdir(base):
            places += [os.path.join(base, d, "bin") for d in sorted(os.listdir(base), reverse=True) if d.startswith("openjdk")]
    places.append(None)
    for bin_dir in places:
        javac = os.path.join(bin_dir, "javac") if bin_dir else shutil.which("javac")
        java = os.path.join(bin_dir, "java") if bin_dir else shutil.which("java")
        if javac and java and os.path.exists(javac):
            try:
                if subprocess.run([javac, "-version"], capture_output=True, timeout=30).returncode == 0:
                    return javac, java
            except (OSError, subprocess.SubprocessError):
                pass
    return None, None


JAVAC, JAVA = find_jdk()
JAVA_MAIN = r"""import aimeter.AiMeter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

public class Main {
    static String reading(AiMeter.Reading r) {
        return "{\"provider\":" + (r.provider == null ? "null" : "\"" + r.provider + "\"") + ",\"counts\":" + r.counts + "}";
    }

    public static void main(String[] args) throws Exception {
        List<String> samples = Files.readAllLines(Paths.get(args[0]), StandardCharsets.UTF_8);
        StringBuilder out = new StringBuilder("[");
        for (String s : samples) out.append(out.length() > 1 ? "," : "").append(reading(AiMeter.read(s, null)));
        // an answer already parsed by Jackson or Gson is a Map with Integer or Long numbers
        // câu trả lời Jackson hay Gson đã đọc là một Map có số kiểu Integer hay Long
        Map<String, Object> parsed = Map.of("model", "gpt-6-luna", "usage", Map.of("prompt_tokens", 5, "completion_tokens", 2L));
        out.append(",").append(reading(AiMeter.read(parsed, null)));
        for (String bad : new String[] {"not json", "{\"usage\":{\"prompt_tokens\":12.0,\"completion_tokens\":3}}", "[1,2]", "{\"a\":"})
            out.append(",").append(reading(AiMeter.read(bad, null)));
        out.append("]");
        AiMeter meter = new AiMeter(args[1], "prod", args[2], "prj_test");
        try (AiMeter.Turn t = meter.turn()) {
            t.firstToken();
            for (String s : samples) t.record(s);
            t.fail("anthropic", "claude-sonnet-5-5", true);
        }
        AiMeter.Turn t2 = meter.turn();
        t2.record("{\"model\":\"gpt-6-luna\"}");
        t2.count("Example-Cloud", "example-model-large", 5L, 2L);
        t2.count("Bad Name", "x", null, 1L);
        t2.end();
        t2.end();
        try {
            meter.turn(t -> { throw new java.net.http.HttpTimeoutException("customer-plate-51A"); });
        } catch (java.net.http.HttpTimeoutException e) {
            // rethrown as it was
            // ném lại đúng như cũ
        }
        meter.close();
        System.out.println(out);
    }
}
"""


@unittest.skipUnless(JAVAC, "no working JDK (javac)")
class JavaMeter(SameAsPython):
    def test_java_reads_writes_and_sends_like_python(self):
        src = os.path.join(self.dir, "java")
        os.makedirs(os.path.join(src, "aimeter"))
        shutil.copy(os.path.join(METER, "AiMeter.java"), os.path.join(src, "aimeter"))
        with open(os.path.join(src, "Main.java"), "w", encoding="utf-8") as f:
            f.write(JAVA_MAIN)
        res = run([JAVAC, "--release", "11", "-Xlint:all", "-Werror", "-d", "out", "aimeter/AiMeter.java", "Main.java"], src)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        samples = os.path.join(self.dir, "samples.txt")
        with open(samples, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(s[1]) for s in SAMPLES) + "\n")
        with Board() as board:
            res = run([JAVA, "-cp", "out", "Main", samples, self.file, board.url], src)
            self.assertEqual(res.returncode, 0, res.stderr)
            out = json.loads(res.stdout)
            n = len(SAMPLES)
            self.assertEqual(out[n], {"provider": "openai", "counts": {"input": 5, "output": 2, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}})
            self.assertEqual([x["counts"] for x in out[n + 1:]], [None] * 4)
            self.check(out[:n], board)


class FileOnly(Tmp):
    """The Rust and C/C++ meters only take counts by hand and only write the file. The same program in each must give these lines.
    Bộ đo Rust và C/C++ chỉ nhận số đếm tay và chỉ ghi file. Cùng một chương trình ở mỗi ngôn ngữ phải cho ra các dòng này."""

    def check(self, env="test"):
        lines = self.lines()
        self.assertEqual([x["outcome"] for x in lines], ["ok", "ok", "timeout", "ok"])
        for x in lines:
            self.assertIsNotNone(report.clean_line(x), x)
            self.assertEqual(x["env"], env)
            self.assertRegex(x["turnId"], r"^[0-9a-f]{16}$")
            self.assertRegex(x["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
        self.assertEqual(len({x["turnId"] for x in lines}), 4)
        self.assertIn("ttftMs", lines[0])
        self.assertLessEqual(lines[0]["ttftMs"], lines[0]["durationMs"])
        first = lines[0]["models"]
        self.assertEqual([(r["provider"], r["model"]) for r in first],
                         [("anthropic", "claude-sonnet-5-5"), ("example-cloud", "example-model-large")])
        son, ex = first
        self.assertEqual((son["calls"], son["errors"], son["retries"], son["unmeasured"]), (3, 1, 1, 0))
        self.assertEqual([son[k] for k in COUNT_FIELDS], [1100, 135, 900, 300, 100])
        self.assertEqual([ex[k] for k in COUNT_FIELDS], [812, 95, 40, 0, 0])
        # a call without counts is "not measured": null, never zero; a bad provider name is written as "other"
        # một lần gọi không có số đếm là "không đo được": null, không bao giờ là 0; tên hãng sai ghi thành "other"
        luna, other = lines[1]["models"]
        self.assertEqual((luna["provider"], luna["model"], luna["calls"], luna["unmeasured"]), ("openai", "gpt-6-luna", 1, 1))
        self.assertEqual([luna[k] for k in COUNT_FIELDS], [None] * 5)
        self.assertEqual((other["provider"], other["model"], other["input"], other["output"]), ("other", "unknown", 7, 3))
        self.assertNotIn("ttftMs", lines[1])
        self.assertEqual(lines[2]["models"], [])
        # a call with one measured answer and one without keeps the measured tokens
        # một model có một lần đo được và một lần không thì giữ số token đã đo
        mixed = lines[3]["models"][0]
        self.assertEqual((mixed["calls"], mixed["unmeasured"], mixed["input"], mixed["output"]), (2, 1, 10, 1))
        raw = self.raw()
        for word in PRIVATE:
            self.assertNotIn(word, raw)
        self.assertTrue(raw.endswith("}\n") and "\n\n" not in raw)


RUSTC = shutil.which("rustc")
RUST_MAIN = r"""mod ai_meter;
use ai_meter::{Counts, Meter};

fn main() {
    let meter = Meter::new("ignored.jsonl", "prod");
    {
        let mut t = meter.turn();
        t.first_token();
        t.count("anthropic", "claude-sonnet-5-5", Some(Counts { input: 100, output: 40, cache_read: 900, cache_write: 300, cache_write_long: 100 }));
        t.count_with("anthropic", "claude-sonnet-5-5", Some(Counts { input: 1000, output: 95, ..Default::default() }), true);
        t.fail("anthropic", "claude-sonnet-5-5", false);
        t.count("Example-Cloud", "example-model-large", Some(Counts { input: 812, output: 95, cache_read: 40, ..Default::default() }));
        t.end();
    }
    {
        let mut t = meter.turn();
        t.count("openai", "gpt-6-luna", None);
        t.count("Bad Name", "customer-plate-51A with spaces", Some(Counts { input: 7, output: 3, ..Default::default() }));
    }
    {
        let mut t = meter.turn();
        t.set_outcome("timeout");
        t.end();
        t.end();
    }
    let mut t = meter.turn();
    t.count("openai", "gpt-6-luna", Some(Counts { input: 10, output: 1, ..Default::default() }));
    t.count("openai", "gpt-6-luna", Some(Counts { cache_write_long: 5, ..Default::default() }));
}
"""


@unittest.skipUnless(RUSTC, "rustc is not installed")
class RustMeter(FileOnly):
    def test_rust_writes_lines_the_report_reads(self):
        src = os.path.join(self.dir, "rs")
        os.makedirs(src)
        shutil.copy(os.path.join(METER, "ai_meter.rs"), src)
        with open(os.path.join(src, "main.rs"), "w", encoding="utf-8") as f:
            f.write(RUST_MAIN)
        res = run([RUSTC, "--edition", "2021", "-D", "warnings", "-O", "main.rs", "-o", "apptest"], src)
        self.assertEqual(res.returncode, 0, res.stderr)
        res = run([os.path.join(src, "apptest")], src, env={"AI_METER_FILE": self.file, "AI_METER_ENV": "test"})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.check()
        res = run([os.path.join(src, "apptest")], src, env={"AI_METER_FILE": self.file, "AI_METER_OFF": "1"})
        self.assertEqual((res.returncode, len(self.lines())), (0, 4))


CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
CXX = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
C_MAIN = r"""#include "ai_meter.h"

int main(void) {
    ai_meter m;
    ai_turn t;
    ai_meter_init(&m, "ignored.jsonl", "prod");

    ai_turn_begin(&t, &m);
    ai_turn_first_token(&t);
    ai_turn_count(&t, "anthropic", "claude-sonnet-5-5", 100, 40, 900, 300, 100);
    ai_turn_count_retry(&t, "anthropic", "claude-sonnet-5-5", 1000, 95, 0, 0, 0, 1);
    ai_turn_fail(&t, "anthropic", "claude-sonnet-5-5", 0);
    ai_turn_count(&t, "Example-Cloud", "example-model-large", 812, 95, 40, 0, 0);
    ai_turn_end(&t);

    ai_turn_begin(&t, &m);
    ai_turn_count(&t, "openai", "gpt-6-luna", -1, -1, 0, 0, 0);
    ai_turn_count(&t, "Bad Name", "customer-plate-51A with spaces", 7, 3, 0, 0, 0);
    ai_turn_end(&t);

    ai_turn_begin(&t, &m);
    ai_turn_set_outcome(&t, "timeout");
    ai_turn_end(&t);
    ai_turn_end(&t);

    ai_turn_begin(&t, &m);
    ai_turn_count(&t, "openai", "gpt-6-luna", 10, 1, 0, 0, 0);
    ai_turn_count(&t, "openai", "gpt-6-luna", 0, 0, 0, 0, 5);
    ai_turn_end(&t);
    return 0;
}
"""


class CMeter(FileOnly):
    def build_and_check(self, compiler, *flags):
        src = os.path.join(self.dir, "c")
        os.makedirs(src, exist_ok=True)
        shutil.copy(os.path.join(METER, "ai_meter.h"), src)
        with open(os.path.join(src, "main.c"), "w", encoding="utf-8") as f:
            f.write(C_MAIN)
        res = run([compiler, *flags, "-Wall", "-Wextra", "-Werror", "main.c", "-o", "apptest"], src)
        self.assertEqual(res.returncode, 0, res.stderr)
        res = run([os.path.join(src, "apptest")], src, env={"AI_METER_FILE": self.file, "AI_METER_ENV": "test"})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.check()

    @unittest.skipUnless(CC, "no C compiler")
    def test_c99_writes_lines_the_report_reads(self):
        self.build_and_check(CC, "-std=c99", "-pedantic")

    @unittest.skipUnless(CXX, "no C++ compiler")
    def test_cpp11_writes_lines_the_report_reads(self):
        self.build_and_check(CXX, "-x", "c++", "-std=c++11", "-pedantic")


NPX = shutil.which("npx")
TS_GOOD = """import { Meter, readUsage, type Counts } from './ai-meter.cjs'

const meter = new Meter({ file: process.argv[2], env: 'test', sync: true })
const main = async (): Promise<void> => {
  const answer = await meter.turn(async (t) => {
    t.firstToken()
    t.record({ model: 'claude-sonnet-5-5', usage: { input_tokens: 100, output_tokens: 40, cache_read_input_tokens: 900 } })
    t.count('Example-Cloud', 'example-model-large', { input: 812, output: 95 })
    t.count('openai', 'gpt-6-luna', {})
    t.fail('anthropic', 'claude-sonnet-5-5', { retry: true })
    return 'done'
  })
  const read: Counts | null = readUsage({ usage: { prompt_tokens: 5, completion_tokens: 2 } }).counts
  const t = meter.start()
  t.end('timeout')
  console.log(JSON.stringify({ answer, input: read === null ? null : read.input }))
}
void main()
"""
# each line is a call TypeScript must refuse
# mỗi dòng là một lần gọi TypeScript phải từ chối
TS_BAD = """import { Meter } from './ai-meter.cjs'
const meter = new Meter({ env: 'staging' })
meter.start().count('openai', 'gpt-6-luna', { input: '12' })
meter.start().end('failed')
meter.start().record()
"""
TS_FLAGS = ["--strict", "--module", "nodenext", "--moduleResolution", "nodenext", "--target", "es2022", "--lib", "es2022", "--types", "node"]


@unittest.skipUnless(NPX and NODE, "npx or node is not installed")
class TypeScriptTypes(Tmp):
    def tsc(self, *args):
        cmd = [NPX, "-y", "-p", "typescript@5.9.3", "tsc", *args]
        return run(cmd, self.src, env={"npm_config_update_notifier": "false", "npm_config_fund": "false"})

    def setUp(self):
        super().setUp()
        self.src = os.path.join(self.dir, "ts")
        os.makedirs(self.src)
        for name in ("ai-meter.cjs", "ai-meter.d.cts"):
            shutil.copy(os.path.join(METER, name), self.src)
        # the only Node names the example uses, so the test needs no @types/node
        # các tên Node duy nhất ví dụ dùng, để test không cần @types/node
        os.makedirs(os.path.join(self.src, "node_modules", "@types", "node"))
        with open(os.path.join(self.src, "node_modules", "@types", "node", "index.d.ts"), "w", encoding="utf-8") as f:
            f.write("declare const process: { argv: string[] }\ndeclare const console: { log(...a: unknown[]): void }\n")

    def test_types_accept_the_guide_and_run(self):
        with open(os.path.join(self.src, "use.ts"), "w", encoding="utf-8") as f:
            f.write(TS_GOOD)
        res = self.tsc(*TS_FLAGS, "use.ts")
        if res.returncode != 0 and "error TS" not in res.stdout:
            self.skipTest("typescript@5.9.3 could not be fetched: " + (res.stderr or res.stdout)[-300:])
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        res = run([NODE, "use.js", self.file], self.src)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), {"answer": "done", "input": 5})
        lines = self.lines()
        self.assertEqual([x["outcome"] for x in lines], ["ok", "timeout"])
        for x in lines:
            self.assertIsNotNone(report.clean_line(x), x)
        by = {r["model"]: r for r in lines[0]["models"]}
        self.assertEqual((by["claude-sonnet-5-5"]["calls"], by["claude-sonnet-5-5"]["errors"]), (2, 1))
        self.assertEqual(by["gpt-6-luna"]["input"], None)

    def test_types_refuse_wrong_calls(self):
        with open(os.path.join(self.src, "bad.ts"), "w", encoding="utf-8") as f:
            f.write(TS_BAD)
        res = self.tsc(*TS_FLAGS, "--noEmit", "bad.ts")
        if res.returncode != 0 and "error TS" not in res.stdout:
            self.skipTest("typescript@5.9.3 could not be fetched: " + (res.stderr or res.stdout)[-300:])
        refused = {int(line.split("(")[1].split(",")[0]) for line in res.stdout.splitlines() if line.startswith("bad.ts(")}
        self.assertEqual(refused, {2, 3, 4, 5}, res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
