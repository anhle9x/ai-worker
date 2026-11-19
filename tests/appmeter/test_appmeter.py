#!/usr/bin/env python3
"""Tests of the meter for AI projects and applications and its report (skills/ai-cost-report): python3 tests/appmeter/test_appmeter.py
Everything is written in a temporary folder. The Node meter is checked against the same answers when node is installed.
  Test bộ đo cho dự án hay ứng dụng AI và báo cáo của nó (skills/ai-cost-report): python3 tests/appmeter/test_appmeter.py
  Mọi thứ ghi trong một thư mục tạm. Bộ đo Node được kiểm với cùng đáp án khi máy có node."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "ai-cost-report")
sys.path.insert(0, os.path.join(SKILL, "meter"))
sys.path.insert(0, SKILL)
import ai_meter  # noqa: E402
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


def line(tid, ms, models, outcome="ok", at="2026-11-20T08:00:00.000Z", **more):
    d = {"v": 1, "turnId": tid, "at": at, "durationMs": ms, "outcome": outcome, "env": "prod", "models": models}
    d.update(more)
    return d


def model(name, provider="anthropic", **counts):
    row = {"provider": provider, "model": name, "calls": 1, "errors": 0, "retries": 0, "unmeasured": 0,
           "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "cacheWriteLong": 0}
    row.update(counts)
    return row


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


if __name__ == "__main__":
    unittest.main(verbosity=1)
