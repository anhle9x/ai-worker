// Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
// Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
// Copy this one file into the project. .NET 6 or newer, nothing else to install. Same line format and the same reading of usage as
// ai_meter.py; it never writes a prompt, an answer, a user id or an error message.
// Chép đúng file này vào dự án. .NET 6 trở lên, không cần cài gì thêm. Cùng định dạng dòng và cùng cách đọc usage như
// ai_meter.py; không bao giờ ghi câu hỏi, câu trả lời, mã người dùng hay thông báo lỗi.
//
//   var meter = new AiMeter.Meter("ai-meter.jsonl");
//   using (var t = meter.Turn()) {
//       string body = await response.Content.ReadAsStringAsync();   // the provider's answer, as JSON text
//       t.Record(body);
//   }
//   t.Count("myprovider", "my-model", input: 812, output: 95);      // any provider, counts by hand
#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace AiMeter
{
    // Token counts of one call: input billed at the normal price, output, cache reads, cache writes and the part of them kept longer
    // Số token của một lần gọi: đầu vào tính giá thường, đầu ra, đọc cache, ghi cache và phần ghi cache giữ lâu hơn
    public sealed record Counts(long Input, long Output, long CacheRead = 0, long CacheWrite = 0, long CacheWriteLong = 0);

    public static class Usage
    {
        static readonly Regex ProviderRe = new Regex("^[a-z0-9][a-z0-9_.-]{0,31}$");
        static readonly Regex ModelRe = new Regex("^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$");

        public static string CleanProvider(string? p)
        {
            var s = (p ?? "other").Trim().ToLowerInvariant();
            return ProviderRe.IsMatch(s) ? s : "other";
        }

        public static string CleanModel(string? m) => m != null && ModelRe.IsMatch(m) ? m : "unknown";

        // Only used when neither the caller nor the usage shape names the provider
        // Chỉ dùng khi cả người gọi lẫn hình dạng usage đều không cho biết hãng
        public static string GuessProvider(string? model)
        {
            var m = (model ?? "").ToLowerInvariant().Split('/').Last();
            if (m.Contains("claude")) return "anthropic";
            if (Regex.IsMatch(m, "^(gpt-|o1|o3|o4|chatgpt)")) return "openai";
            if (m.StartsWith("gemini") || m.StartsWith("gemma")) return "google";
            foreach (var (prefix, name) in new[] { ("deepseek", "deepseek"), ("mistral", "mistral"), ("mixtral", "mistral"), ("codestral", "mistral"), ("grok", "xai"), ("command", "cohere") })
                if (m.StartsWith(prefix)) return name;
            return "other";
        }

        static JsonElement? Get(JsonElement d, params string[] keys)
        {
            if (d.ValueKind != JsonValueKind.Object) return null;
            foreach (var k in keys)
                if (d.TryGetProperty(k, out var v) && v.ValueKind != JsonValueKind.Null) return v;
            return null;
        }

        // A token count is a whole number of zero or more; anything else is "not measured"
        // Số token là số nguyên từ 0 trở lên; thứ khác là "không đo được"
        static long? Int(JsonElement? v)
        {
            if (v is JsonElement e && e.ValueKind == JsonValueKind.Number && e.TryGetInt64(out var n) && n >= 0) return n;
            return null;
        }

        static long? IntOr0(JsonElement? v) => v == null ? 0 : Int(v);

        static string? Str(JsonElement? v) => v is JsonElement e && e.ValueKind == JsonValueKind.String ? e.GetString() : null;

        static Counts? Make(long? i, long? o, long? r = 0, long? w = 0, long? l = 0)
        {
            if (i == null || o == null || r == null || w == null || l == null || l > w) return null;
            return new Counts(i.Value, o.Value, r.Value, w.Value, l.Value);
        }

        /// <summary>Reads (provider, model, counts) from a provider's answer; counts is null when it carries no usage.
        /// Same shapes as ai_meter.py: Anthropic, OpenAI and every API that copies it, Gemini, Bedrock Converse, Ollama, Cohere v2, Vercel AI SDK.
        /// Đọc (hãng, model, số đếm) từ câu trả lời của hãng; số đếm là null khi không có usage. Cùng các dạng như ai_meter.py.</summary>
        public static (string? Provider, string? Model, Counts? Counts) Read(JsonElement d, string? provider = null)
        {
            if (d.ValueKind != JsonValueKind.Object) return (provider, null, null);
            var model = Str(Get(d, "model", "modelVersion", "model_version", "modelId"));
            // Gemini: promptTokenCount includes the cache; thinking tokens are billed as output
            // Gemini: promptTokenCount đã gồm cache; token suy nghĩ tính tiền như output
            var gem = Get(d, "usageMetadata", "usage_metadata");
            if (gem == null && Get(d, "promptTokenCount", "prompt_token_count") != null) gem = d;
            if (gem is JsonElement g && g.ValueKind == JsonValueKind.Object)
            {
                var prompt = Int(Get(g, "promptTokenCount", "prompt_token_count"));
                var cached = IntOr0(Get(g, "cachedContentTokenCount", "cached_content_token_count"));
                var cand = IntOr0(Get(g, "candidatesTokenCount", "candidates_token_count"));
                var think = IntOr0(Get(g, "thoughtsTokenCount", "thoughts_token_count"));
                if (prompt == null || cached == null || cand == null || think == null || cached > prompt) return (provider ?? "google", model, null);
                return (provider ?? "google", model, Make(prompt - cached, cand + think, cached));
            }
            // Ollama /api/chat: prompt_eval_count and eval_count on the answer itself
            // /api/chat của Ollama: prompt_eval_count và eval_count nằm ngay trên câu trả lời
            if (d.TryGetProperty("eval_count", out _) || d.TryGetProperty("prompt_eval_count", out _))
                return (provider ?? "ollama", model, Make(Int(Get(d, "prompt_eval_count")), Int(Get(d, "eval_count"))));
            var u = Get(d, "usage") is JsonElement ue && ue.ValueKind == JsonValueKind.Object ? ue : d;
            // Vercel AI SDK: inputTokens include the cache; inputTokenDetails splits them
            // Vercel AI SDK: inputTokens đã gồm cache; inputTokenDetails tách ra
            if (Get(u, "inputTokenDetails") is JsonElement det0 && det0.ValueKind == JsonValueKind.Object)
            {
                var read0 = IntOr0(Get(det0, "cacheReadTokens"));
                var write0 = IntOr0(Get(det0, "cacheWriteTokens"));
                var plain = Int(Get(det0, "noCacheTokens"));
                var total0 = Int(Get(u, "inputTokens"));
                if (plain == null && total0 != null && read0 != null && write0 != null) plain = total0 - read0 - write0;
                return (provider ?? GuessProvider(model), model, Make(plain, Int(Get(u, "outputTokens")), read0, write0));
            }
            // Bedrock Converse: inputTokens are only the tokens not read from or written to the cache
            // Bedrock Converse: inputTokens chỉ là phần không đọc từ cache và không ghi vào cache
            if (u.TryGetProperty("inputTokens", out _) || u.TryGetProperty("outputTokens", out _))
                return (provider ?? "bedrock", model, Make(Int(Get(u, "inputTokens")), Int(Get(u, "outputTokens")),
                                                          IntOr0(Get(u, "cacheReadInputTokens")), IntOr0(Get(u, "cacheWriteInputTokens"))));
            // Cohere v2: the billed units are what costs money
            // Cohere v2: billed_units là phần bị tính tiền
            if (Get(u, "billed_units") is JsonElement b && b.ValueKind == JsonValueKind.Object)
                return (provider ?? "cohere", model, Make(Int(Get(b, "input_tokens")), Int(Get(b, "output_tokens"))));
            // Anthropic: input_tokens excludes the cache
            // Anthropic: input_tokens không gồm cache
            if (u.TryGetProperty("cache_read_input_tokens", out _) || u.TryGetProperty("cache_creation_input_tokens", out _) || provider == "anthropic")
            {
                long? lng = 0;
                if (Get(u, "cache_creation") is JsonElement cc) lng = IntOr0(Get(cc, "ephemeral_1h_input_tokens"));
                return (provider ?? "anthropic", model, Make(Int(Get(u, "input_tokens")), Int(Get(u, "output_tokens")),
                                                            IntOr0(Get(u, "cache_read_input_tokens")), IntOr0(Get(u, "cache_creation_input_tokens")), lng));
            }
            // OpenAI and every API that copies it: input or prompt tokens include cache reads and writes
            // OpenAI và mọi API chép theo nó: input hay prompt tokens đã gồm cache đọc và ghi
            var total = Int(Get(u, "input_tokens", "prompt_tokens"));
            var outp = Int(Get(u, "output_tokens", "completion_tokens"));
            var p = provider ?? GuessProvider(model);
            if (total == null && outp == null) return (p, model, null);
            var det = Get(u, "input_tokens_details", "prompt_tokens_details") ?? default;
            var read = IntOr0(Get(det, "cached_tokens", "prompt_cache_hit_tokens") ?? Get(u, "prompt_cache_hit_tokens"));
            var write = IntOr0(Get(det, "cache_write_tokens"));
            long? lg = 0;
            if (Get(det, "cache_write_tokens_details") is JsonElement cw) lg = IntOr0(Get(cw, "ttl_12h_tokens"));
            if (total == null || outp == null || read == null || write == null || lg == null || read + write > total) return (p, model, null);
            // Some of these APIs (xAI's Chat Completions) leave reasoning tokens out of completion_tokens; total_tokens shows it
            // Vài API loại này (Chat Completions của xAI) không tính token suy nghĩ vào completion_tokens; total_tokens cho thấy điều đó
            long think2 = 0;
            if (Get(u, "completion_tokens_details", "output_tokens_details") is JsonElement od) think2 = IntOr0(Get(od, "reasoning_tokens")) ?? 0;
            var output = think2 > 0 && Int(Get(u, "total_tokens")) == total + outp + think2 ? outp + think2 : outp;
            return (p, model, Make(total - read - write, output, read, write, lg));
        }
    }

    // One user turn: every LLM call made to answer it. Get one from Meter.Turn(); disposing it writes the line.
    // Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Lấy từ Meter.Turn(); Dispose thì ghi dòng.
    public sealed class Turn : IDisposable
    {
        sealed class Slot
        {
            public long Calls, Errors, Retries, Unmeasured, Input, Output, CacheRead, CacheWrite, CacheWriteLong;
        }

        readonly Meter meter;
        readonly DateTime started = DateTime.UtcNow;
        readonly Stopwatch clock = Stopwatch.StartNew();
        readonly Dictionary<(string, string), Slot> models = new();
        readonly object gate = new();
        long? ttftMs;
        bool done;

        /// <summary>"ok", "error" or "timeout"; set it when the turn did not end well.
        /// "ok", "error" hay "timeout"; đặt khi lượt không kết thúc tốt.</summary>
        public string Outcome { get; set; } = "ok";

        internal Turn(Meter meter) => this.meter = meter;

        void Add(string? provider, string? model, Counts? c, bool retry, bool failed = false)
        {
            lock (gate)
            {
                var key = (Usage.CleanProvider(provider), Usage.CleanModel(model));
                if (!models.TryGetValue(key, out var s)) models[key] = s = new Slot();
                s.Calls++;
                if (retry) s.Retries++;
                if (failed) { s.Errors++; return; }
                if (c == null) { s.Unmeasured++; return; }
                s.Input += c.Input; s.Output += c.Output; s.CacheRead += c.CacheRead; s.CacheWrite += c.CacheWrite; s.CacheWriteLong += c.CacheWriteLong;
            }
        }

        /// <summary>Counts one LLM call from the provider's answer, as JSON text.
        /// Đếm một lần gọi LLM từ câu trả lời của hãng, dạng chữ JSON.</summary>
        public void Record(string json, string? provider = null, string? model = null, bool retry = false)
        {
            try
            {
                using var doc = JsonDocument.Parse(json);
                Record(doc.RootElement, provider, model, retry);
            }
            catch { Add(provider, model, null, retry); }
        }

        /// <summary>Counts one LLM call from the provider's answer, already parsed.
        /// Đếm một lần gọi LLM từ câu trả lời của hãng, đã đọc sẵn.</summary>
        public void Record(JsonElement answer, string? provider = null, string? model = null, bool retry = false)
        {
            try
            {
                var (p, m, c) = Usage.Read(answer, provider);
                Add(p, model ?? m, c, retry);
            }
            catch { }
        }

        /// <summary>Counts one LLM call from numbers read by hand. input is billed at the normal price, without cache reads and writes; null means not measured.
        /// Đếm một lần gọi LLM từ số tự đọc. input là đầu vào tính giá thường, không gồm đọc và ghi cache; null nghĩa là không đo được.</summary>
        public void Count(string provider, string model, long? input = null, long? output = null, long cacheRead = 0, long cacheWrite = 0, long cacheWriteLong = 0, bool retry = false)
        {
            try
            {
                Counts? c = input is long i && output is long o && i >= 0 && o >= 0 && cacheRead >= 0 && cacheWrite >= 0 && cacheWriteLong >= 0 && cacheWriteLong <= cacheWrite
                    ? new Counts(i, o, cacheRead, cacheWrite, cacheWriteLong) : null;
                Add(provider, model, c, retry);
            }
            catch { }
        }

        /// <summary>Counts one LLM call that failed (no answer, so no usage). Pass no error text.
        /// Đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi.</summary>
        public void Fail(string provider, string model, bool retry = false)
        {
            try { Add(provider, model, null, retry, failed: true); } catch { }
        }

        /// <summary>Marks the first streamed piece of the answer; only the first mark counts.
        /// Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.</summary>
        public void FirstToken()
        {
            lock (gate) ttftMs ??= clock.ElapsedMilliseconds;
        }

        /// <summary>Writes the line; Dispose calls it for you.
        /// Ghi dòng; Dispose tự gọi.</summary>
        public void End(string? outcome = null)
        {
            try
            {
                string line;
                lock (gate)
                {
                    if (done) return;
                    done = true;
                    var o = outcome ?? Outcome;
                    var sb = new StringBuilder();
                    sb.Append("{\"v\":1,\"turnId\":\"").Append(Convert.ToHexString(RandomNumberGenerator.GetBytes(8)).ToLowerInvariant())
                      .Append("\",\"at\":\"").Append(started.ToString("yyyy-MM-ddTHH:mm:ss.fffZ", System.Globalization.CultureInfo.InvariantCulture))
                      .Append("\",\"durationMs\":").Append(clock.ElapsedMilliseconds)
                      .Append(",\"outcome\":\"").Append(o == "ok" || o == "timeout" ? o : "error")
                      .Append("\",\"env\":\"").Append(meter.Env).Append('"');
                    if (ttftMs is long t) sb.Append(",\"ttftMs\":").Append(t);
                    sb.Append(",\"models\":[");
                    var first = true;
                    foreach (var ((p, m), s) in models)
                    {
                        if (!first) sb.Append(',');
                        first = false;
                        // every answered call lacked usage: the tokens are unknown, not zero
                        // mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
                        var unknown = s.Unmeasured > 0 && s.Calls - s.Errors == s.Unmeasured;
                        string N(long v) => unknown ? "null" : v.ToString(System.Globalization.CultureInfo.InvariantCulture);
                        sb.Append("{\"provider\":").Append(JsonSerializer.Serialize(p)).Append(",\"model\":").Append(JsonSerializer.Serialize(m))
                          .Append(",\"calls\":").Append(s.Calls).Append(",\"errors\":").Append(s.Errors).Append(",\"retries\":").Append(s.Retries)
                          .Append(",\"unmeasured\":").Append(s.Unmeasured).Append(",\"input\":").Append(N(s.Input)).Append(",\"output\":").Append(N(s.Output))
                          .Append(",\"cacheRead\":").Append(N(s.CacheRead)).Append(",\"cacheWrite\":").Append(N(s.CacheWrite))
                          .Append(",\"cacheWriteLong\":").Append(N(s.CacheWriteLong)).Append('}');
                    }
                    sb.Append("]}");
                    line = sb.ToString();
                }
                meter.Write(line);
            }
            catch { }
        }

        public void Dispose()
        {
            End();
        }
    }

    // Where the lines go. env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off.
    // AI_METER_URL and AI_METER_KEY (or sendUrl and sendKey) also send each turn to an AI Worker board, in the background.
    // Nơi ghi các dòng. env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt.
    // AI_METER_URL và AI_METER_KEY (hoặc sendUrl và sendKey) gửi thêm từng lượt lên bảng AI Worker, ở nền.
    public sealed class Meter
    {
        static readonly object FileLock = new();
        readonly string path;
        readonly bool off;
        readonly Sender? sender;
        public string Env { get; }

        public Meter(string path = "ai-meter.jsonl", string env = "prod", string? sendUrl = null, string? sendKey = null)
        {
            this.path = Environment.GetEnvironmentVariable("AI_METER_FILE") is { Length: > 0 } f ? f : path;
            var e = Environment.GetEnvironmentVariable("AI_METER_ENV") is { Length: > 0 } ev ? ev : env;
            Env = e == "test" ? "test" : "prod";
            off = Environment.GetEnvironmentVariable("AI_METER_OFF") == "1";
            var url = Environment.GetEnvironmentVariable("AI_METER_URL") is { Length: > 0 } u ? u : sendUrl ?? "";
            var key = Environment.GetEnvironmentVariable("AI_METER_KEY") is { Length: > 0 } k ? k : sendKey ?? "";
            try
            {
                if (url.Length > 0 && key.Length > 0 && !off && Sender.Allowed(url)) sender = new Sender(url, key);
            }
            catch { sender = null; }
        }

        public Turn Turn() => new Turn(this);

        /// <summary>Sends what is waiting now (for example before the program ends); never throws.
        /// Gửi những gì đang chờ ngay bây giờ (ví dụ trước khi chương trình kết thúc); không bao giờ ném lỗi.</summary>
        public Task FlushAsync() => sender?.FlushAsync() ?? Task.CompletedTask;

        internal void Write(string line)
        {
            if (off) return;
            try { sender?.Add(line); } catch { }
            try
            {
                lock (FileLock) File.AppendAllText(path, line + "\n", new UTF8Encoding(false));
            }
            catch { }
        }
    }

    // Sending to the board: batches in the background; a full queue drops the oldest turn, a failed send is tried once more,
    // and the project never waits on it. The key goes only over HTTPS, or to this machine itself
    // Gửi lên bảng: các lô đi ở nền; hàng đợi đầy thì bỏ lượt cũ nhất, gửi lỗi thì thử lại một lần,
    // và dự án không bao giờ phải chờ. Khoá chỉ đi qua HTTPS, hoặc tới chính máy này
    sealed class Sender
    {
        const int QueueMax = 1000, BatchTurns = 100, BatchBytes = 200 * 1024;
        static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(5) };
        readonly string url, key;
        readonly ConcurrentQueue<string> queue = new();
        readonly SemaphoreSlim busy = new(1, 1);
        readonly Timer timer;
        List<string> retry = new();

        public static bool Allowed(string url) =>
            url.StartsWith("https://") || Regex.IsMatch(url, @"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/");

        public Sender(string url, string key)
        {
            this.url = url;
            this.key = key;
            timer = new Timer(_ => { _ = FlushAsync(); }, null, 10000, 10000);
            AppDomain.CurrentDomain.ProcessExit += (_, _) => { try { FlushAsync().Wait(6000); } catch { } };
        }

        public void Add(string line)
        {
            queue.Enqueue(line);
            while (queue.Count > QueueMax && queue.TryDequeue(out _)) { }
            if (queue.Count >= BatchTurns) _ = FlushAsync();
        }

        public async Task FlushAsync()
        {
            if (!await busy.WaitAsync(0).ConfigureAwait(false)) return;
            try
            {
                while (!queue.IsEmpty || retry.Count > 0)
                {
                    var again = retry.Count > 0;
                    var batch = retry;
                    retry = new List<string>();
                    var size = 0;
                    while (batch.Count < BatchTurns && size < BatchBytes && queue.TryDequeue(out var line))
                    {
                        size += line.Length;
                        batch.Add(line);
                    }
                    try
                    {
                        using var req = new HttpRequestMessage(HttpMethod.Post, url)
                        {
                            Content = new StringContent("{\"turns\":[" + string.Join(",", batch) + "]}", Encoding.UTF8, "application/json"),
                        };
                        req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + key);
                        req.Headers.TryAddWithoutValidation("User-Agent", "ai-meter/1");
                        using var res = await Http.SendAsync(req).ConfigureAwait(false);
                        if ((int)res.StatusCode >= 500 || (int)res.StatusCode == 429) throw new HttpRequestException("later");
                    }
                    catch
                    {
                        // tried once more at the next send, then let go; the file still has every turn
                        // thử lại một lần ở lần gửi sau, rồi bỏ; file vẫn còn đủ mọi lượt
                        if (!again) retry = batch;
                        return;
                    }
                }
            }
            catch { }
            finally { busy.Release(); }
        }
    }
}
