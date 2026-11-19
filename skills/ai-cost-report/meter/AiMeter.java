// Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
// Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
//
// Copy this one file to src/main/java/aimeter/AiMeter.java (any folder aimeter/ on the source path). Java 11 or newer, standard
// library only; works the same from Kotlin, Scala, Groovy and every JVM language. Same line format and the same reading of usage
// as ai_meter.py; it never writes a prompt, an answer, a user id or an error message. Java has no JSON reader of its own, so this
// file carries a small one: record() takes the provider's answer as JSON text, or as a Map already parsed by Jackson or Gson.
// Chép đúng file này vào src/main/java/aimeter/AiMeter.java (thư mục aimeter/ bất kỳ trong mã nguồn). Java 11 trở lên, chỉ thư
// viện chuẩn; dùng y như vậy từ Kotlin, Scala, Groovy và mọi ngôn ngữ JVM. Cùng định dạng dòng và cùng cách đọc usage như
// ai_meter.py; không bao giờ ghi câu hỏi, câu trả lời, mã người dùng hay thông báo lỗi. Java không có sẵn bộ đọc JSON, nên file
// này mang theo một bộ nhỏ: record() nhận câu trả lời của hãng dạng chữ JSON, hoặc dạng Map mà Jackson hay Gson đã đọc.
//
//   AiMeter meter = new AiMeter("ai-meter.jsonl");                // once
//   try (AiMeter.Turn t = meter.turn()) {
//       t.record(response.body());                                // the provider's answer, as JSON text
//   }
//   t.count("myprovider", "my-model", 812L, 95L);                 // any provider, counts by hand
package aimeter;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

public final class AiMeter implements AutoCloseable {
    static final Pattern PROVIDER = Pattern.compile("^[a-z0-9][a-z0-9_.-]{0,31}$");
    static final Pattern MODEL = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$");
    static final Pattern OPENAI = Pattern.compile("^(gpt-|o1|o3|o4|chatgpt).*");
    static final Pattern LOCAL_URL = Pattern.compile("^http://(localhost|127\\.0\\.0\\.1|\\[::1\\])(:\\d+)?/.*");
    static final DateTimeFormatter AT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);
    static final SecureRandom RANDOM = new SecureRandom();
    static final Object FILE_LOCK = new Object();

    // Token counts of one call: input billed at the normal price, output, cache reads, cache writes and the part of them kept longer.
    // Số token của một lần gọi: đầu vào tính giá thường, đầu ra, đọc cache, ghi cache và phần ghi cache giữ lâu hơn.
    public static final class Counts {
        public final long input, output, cacheRead, cacheWrite, cacheWriteLong;

        public Counts(long input, long output, long cacheRead, long cacheWrite, long cacheWriteLong) {
            this.input = input;
            this.output = output;
            this.cacheRead = cacheRead;
            this.cacheWrite = cacheWrite;
            this.cacheWriteLong = cacheWriteLong;
        }

        public Counts(long input, long output) {
            this(input, output, 0, 0, 0);
        }

        static Counts of(long i, long o, long r, long w, long l) {
            return i < 0 || o < 0 || r < 0 || w < 0 || l < 0 || l > w ? null : new Counts(i, o, r, w, l);
        }

        @Override
        public String toString() {
            return "{\"input\":" + input + ",\"output\":" + output + ",\"cacheRead\":" + cacheRead + ",\"cacheWrite\":" + cacheWrite
                + ",\"cacheWriteLong\":" + cacheWriteLong + "}";
        }
    }

    // What read() found in an answer; counts is null when it carries no usage.
    // Điều read() tìm thấy trong một câu trả lời; counts là null khi không có usage.
    public static final class Reading {
        public final String provider, model;
        public final Counts counts;

        Reading(String provider, String model, Counts counts) {
            this.provider = provider;
            this.model = model;
            this.counts = counts;
        }
    }

    static String cleanProvider(String p) {
        String s = p == null ? "" : p.trim().toLowerCase(Locale.ROOT);
        return PROVIDER.matcher(s).matches() ? s : "other";
    }

    static String cleanModel(String m) {
        return m != null && MODEL.matcher(m).matches() ? m : "unknown";
    }

    // Only used when neither the caller nor the usage shape names the provider.
    // Chỉ dùng khi cả người gọi lẫn hình dạng usage đều không cho biết hãng.
    public static String guessProvider(String model) {
        String m = model == null ? "" : model.toLowerCase(Locale.ROOT);
        m = m.substring(m.lastIndexOf('/') + 1);
        if (m.contains("claude")) return "anthropic";
        if (OPENAI.matcher(m).matches()) return "openai";
        if (m.startsWith("gemini") || m.startsWith("gemma")) return "google";
        if (m.startsWith("deepseek")) return "deepseek";
        if (m.startsWith("mistral") || m.startsWith("mixtral") || m.startsWith("codestral")) return "mistral";
        if (m.startsWith("grok")) return "xai";
        if (m.startsWith("command")) return "cohere";
        return "other";
    }

    static Object get(Object d, String... keys) {
        if (!(d instanceof Map)) return null;
        Map<?, ?> o = (Map<?, ?>) d;
        for (String k : keys) {
            Object v = o.get(k);
            if (v != null) return v;
        }
        return null;
    }

    static boolean has(Object d, String key) {
        return d instanceof Map && ((Map<?, ?>) d).containsKey(key);
    }

    // a token count is a whole number of zero or more; anything else is "not measured" (-1)
    // số token là số nguyên từ 0 trở lên; thứ khác là "không đo được" (-1)
    static long num(Object v) {
        long n;
        if (v instanceof Long || v instanceof Integer || v instanceof Short || v instanceof Byte) n = ((Number) v).longValue();
        else if (v instanceof BigInteger && ((BigInteger) v).bitLength() < 64) n = ((BigInteger) v).longValue();
        else return -1;
        return n < 0 ? -1 : n;
    }

    static long num0(Object v) {
        return v == null ? 0 : num(v);
    }

    static String str(Object v) {
        return v instanceof String ? (String) v : null;
    }

    // Reads the provider, the model and the counts of a provider's answer (JSON text, or a Map already parsed).
    // Same shapes as ai_meter.py: Anthropic, OpenAI and every API that copies it, Gemini, Bedrock Converse, Ollama, Cohere v2, Vercel AI SDK.
    // Đọc hãng, model và số đếm của câu trả lời (chữ JSON, hoặc Map đã đọc sẵn). Cùng các dạng như ai_meter.py.
    public static Reading read(Object answer, String provider) {
        Object d = answer;
        if (answer instanceof String) {
            try {
                d = Json.parse((String) answer);
            } catch (RuntimeException e) {
                return new Reading(provider, null, null);
            }
        }
        if (!(d instanceof Map)) return new Reading(provider, null, null);
        String model = str(get(d, "model", "modelVersion", "model_version", "modelId"));
        // Gemini: promptTokenCount includes the cache; thinking tokens are billed as output
        // Gemini: promptTokenCount đã gồm cache; token suy nghĩ tính tiền như output
        Object gem = get(d, "usageMetadata", "usage_metadata");
        if (gem == null && get(d, "promptTokenCount", "prompt_token_count") != null) gem = d;
        if (gem instanceof Map) {
            long prompt = num(get(gem, "promptTokenCount", "prompt_token_count"));
            long cached = num0(get(gem, "cachedContentTokenCount", "cached_content_token_count"));
            long cand = num0(get(gem, "candidatesTokenCount", "candidates_token_count"));
            long think = num0(get(gem, "thoughtsTokenCount", "thoughts_token_count"));
            String p = or(provider, "google");
            if (prompt < 0 || cached < 0 || cand < 0 || think < 0 || cached > prompt) return new Reading(p, model, null);
            return new Reading(p, model, Counts.of(prompt - cached, cand + think, cached, 0, 0));
        }
        // Ollama /api/chat: prompt_eval_count and eval_count on the answer itself
        // /api/chat của Ollama: prompt_eval_count và eval_count nằm ngay trên câu trả lời
        if (has(d, "eval_count") || has(d, "prompt_eval_count")) {
            return new Reading(or(provider, "ollama"), model, Counts.of(num(get(d, "prompt_eval_count")), num(get(d, "eval_count")), 0, 0, 0));
        }
        Object u = get(d, "usage") instanceof Map ? get(d, "usage") : d;
        // Vercel AI SDK: inputTokens include the cache; inputTokenDetails splits them
        // Vercel AI SDK: inputTokens đã gồm cache; inputTokenDetails tách ra
        Object det = get(u, "inputTokenDetails");
        if (det instanceof Map) {
            long read = num0(get(det, "cacheReadTokens")), write = num0(get(det, "cacheWriteTokens"));
            long plain = num(get(det, "noCacheTokens"));
            if (plain < 0) {
                long total = num(get(u, "inputTokens"));
                if (total >= 0 && read >= 0 && write >= 0) plain = total - read - write;
            }
            return new Reading(or(provider, guessProvider(model)), model, Counts.of(plain, num(get(u, "outputTokens")), read, write, 0));
        }
        // Bedrock Converse: inputTokens are only the tokens not read from or written to the cache
        // Bedrock Converse: inputTokens chỉ là phần không đọc từ cache và không ghi vào cache
        if (has(u, "inputTokens") || has(u, "outputTokens")) {
            return new Reading(or(provider, "bedrock"), model, Counts.of(num(get(u, "inputTokens")), num(get(u, "outputTokens")),
                num0(get(u, "cacheReadInputTokens")), num0(get(u, "cacheWriteInputTokens")), 0));
        }
        // Cohere v2: the billed units are what costs money
        // Cohere v2: billed_units là phần bị tính tiền
        Object billed = get(u, "billed_units");
        if (billed instanceof Map) {
            return new Reading(or(provider, "cohere"), model, Counts.of(num(get(billed, "input_tokens")), num(get(billed, "output_tokens")), 0, 0, 0));
        }
        // Anthropic: input_tokens excludes the cache
        // Anthropic: input_tokens không gồm cache
        if (has(u, "cache_read_input_tokens") || has(u, "cache_creation_input_tokens") || "anthropic".equals(provider)) {
            long lng = num0(get(get(u, "cache_creation"), "ephemeral_1h_input_tokens"));
            return new Reading(or(provider, "anthropic"), model, Counts.of(num(get(u, "input_tokens")), num(get(u, "output_tokens")),
                num0(get(u, "cache_read_input_tokens")), num0(get(u, "cache_creation_input_tokens")), lng));
        }
        // OpenAI and every API that copies it: input or prompt tokens include cache reads and writes
        // OpenAI và mọi API chép theo nó: input hay prompt tokens đã gồm cache đọc và ghi
        String p = or(provider, guessProvider(model));
        if (get(u, "input_tokens", "prompt_tokens") == null && get(u, "output_tokens", "completion_tokens") == null) return new Reading(p, model, null);
        long total = num(get(u, "input_tokens", "prompt_tokens")), out = num(get(u, "output_tokens", "completion_tokens"));
        Object idet = get(u, "input_tokens_details", "prompt_tokens_details");
        Object readV = get(idet, "cached_tokens", "prompt_cache_hit_tokens");
        if (readV == null) readV = get(u, "prompt_cache_hit_tokens");
        long read = num0(readV), write = num0(get(idet, "cache_write_tokens"));
        long lng = num0(get(get(idet, "cache_write_tokens_details"), "ttl_12h_tokens"));
        if (total < 0 || out < 0 || read < 0 || write < 0 || lng < 0 || read + write > total) return new Reading(p, model, null);
        // Some of these APIs (xAI's Chat Completions) leave reasoning tokens out of completion_tokens; total_tokens shows it
        // Vài API loại này (Chat Completions của xAI) không tính token suy nghĩ vào completion_tokens; total_tokens cho thấy điều đó
        long think = num0(get(get(u, "completion_tokens_details", "output_tokens_details"), "reasoning_tokens"));
        if (think > 0 && num(get(u, "total_tokens")) == total + out + think) out += think;
        return new Reading(p, model, Counts.of(total - read - write, out, read, write, lng));
    }

    static String or(String given, String found) {
        return given != null && !given.isEmpty() ? given : found;
    }

    // Runs the work of one turn, writes the line when it ends, and returns or rethrows what the work did.
    // Chạy phần việc của một lượt, ghi dòng khi xong, và trả về hay ném lại đúng điều phần việc đó làm.
    @FunctionalInterface
    public interface Work<T> {
        T run(Turn t) throws Exception;
    }

    // One user turn: every LLM call made to answer it. Get one from meter.turn(); close() or end() writes the line.
    // Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Lấy từ meter.turn(); close() hay end() thì ghi dòng.
    public final class Turn implements AutoCloseable {
        final class Slot {
            final String provider, model;
            long calls, errors, retries, unmeasured, input, output, cacheRead, cacheWrite, cacheWriteLong;

            Slot(String provider, String model) {
                this.provider = provider;
                this.model = model;
            }
        }

        final Instant at = Instant.now();
        final long t0 = System.nanoTime();
        final Map<String, Slot> models = new LinkedHashMap<>();
        long ttftMs = -1;
        String outcome = "ok";
        boolean done;

        Turn() {
        }

        synchronized void add(String provider, String model, Counts c, boolean retry, boolean failed) {
            String p = cleanProvider(provider), m = cleanModel(model);
            Slot s = models.computeIfAbsent(p + "\n" + m, k -> new Slot(p, m));
            s.calls++;
            if (retry) s.retries++;
            if (failed) s.errors++;
            else if (c == null) s.unmeasured++;
            else {
                s.input += c.input;
                s.output += c.output;
                s.cacheRead += c.cacheRead;
                s.cacheWrite += c.cacheWrite;
                s.cacheWriteLong += c.cacheWriteLong;
            }
        }

        // Counts one LLM call from the provider's answer: JSON text, or a Map already parsed.
        // Đếm một lần gọi LLM từ câu trả lời của hãng: chữ JSON, hoặc Map đã đọc sẵn.
        public void record(Object answer) {
            record(answer, null, null, false);
        }

        // record() with the provider's name, for a provider the answer does not name (for example "deepseek").
        // record() kèm tên hãng, cho hãng mà câu trả lời không ghi (ví dụ "deepseek").
        public void record(Object answer, String provider) {
            record(answer, provider, null, false);
        }

        public void record(Object answer, String provider, String model, boolean retry) {
            try {
                Reading r = read(answer, provider);
                add(r.provider, model != null ? model : r.model, r.counts, retry, false);
            } catch (RuntimeException | StackOverflowError e) {
                // the meter never breaks the project
                // bộ đo không bao giờ làm hỏng dự án
            }
        }

        // Counts one LLM call from numbers read by hand. input is billed at the normal price, without cache reads and writes;
        // null input or output means the answer carried no token counts (not measured, never zero).
        // Đếm một lần gọi LLM từ số tự đọc. input là đầu vào tính giá thường, không gồm đọc và ghi cache; input hay output
        // null nghĩa là câu trả lời không kèm số token (không đo được, không bao giờ là 0).
        public void count(String provider, String model, Long input, Long output) {
            count(provider, model, input, output, 0, 0, 0, false);
        }

        public void count(String provider, String model, Long input, Long output, long cacheRead, long cacheWrite, long cacheWriteLong, boolean retry) {
            Counts c = input == null || output == null ? null : Counts.of(input, output, cacheRead, cacheWrite, cacheWriteLong);
            add(provider, model, c, retry, false);
        }

        // Counts one LLM call that failed (no answer, so no usage). Pass no error text.
        // Đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi.
        public void fail(String provider, String model) {
            add(provider, model, null, false, true);
        }

        public void fail(String provider, String model, boolean retry) {
            add(provider, model, null, retry, true);
        }

        // Marks the first streamed piece of the answer; only the first mark counts.
        // Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.
        public synchronized void firstToken() {
            if (ttftMs < 0) ttftMs = (System.nanoTime() - t0) / 1_000_000;
        }

        // "error" or "timeout" when the turn did not end well.
        // "error" hay "timeout" khi lượt không kết thúc tốt.
        public synchronized void setOutcome(String o) {
            outcome = "ok".equals(o) || "timeout".equals(o) ? o : "error";
        }

        // Writes the line, once.
        // Ghi dòng, một lần.
        public void end() {
            try {
                String line;
                synchronized (this) {
                    if (done) return;
                    done = true;
                    byte[] id = new byte[8];
                    RANDOM.nextBytes(id);
                    StringBuilder b = new StringBuilder(256);
                    b.append("{\"v\":1,\"turnId\":\"");
                    for (byte x : id) b.append(String.format("%02x", x & 0xff));
                    b.append("\",\"at\":\"").append(AT.format(at)).append("\",\"durationMs\":").append((System.nanoTime() - t0) / 1_000_000)
                        .append(",\"outcome\":\"").append(outcome).append("\",\"env\":\"").append(env).append('"');
                    if (ttftMs >= 0) b.append(",\"ttftMs\":").append(ttftMs);
                    b.append(",\"models\":[");
                    boolean first = true;
                    for (Slot s : models.values()) {
                        if (!first) b.append(',');
                        first = false;
                        // every answered call lacked usage: the tokens are unknown, not zero
                        // mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
                        boolean unknown = s.unmeasured > 0 && s.calls - s.errors == s.unmeasured;
                        b.append("{\"provider\":\"").append(s.provider).append("\",\"model\":\"").append(s.model)
                            .append("\",\"calls\":").append(s.calls).append(",\"errors\":").append(s.errors).append(",\"retries\":").append(s.retries)
                            .append(",\"unmeasured\":").append(s.unmeasured)
                            .append(",\"input\":").append(unknown ? "null" : String.valueOf(s.input))
                            .append(",\"output\":").append(unknown ? "null" : String.valueOf(s.output))
                            .append(",\"cacheRead\":").append(unknown ? "null" : String.valueOf(s.cacheRead))
                            .append(",\"cacheWrite\":").append(unknown ? "null" : String.valueOf(s.cacheWrite))
                            .append(",\"cacheWriteLong\":").append(unknown ? "null" : String.valueOf(s.cacheWriteLong)).append('}');
                    }
                    line = b.append("]}").toString();
                }
                write(line);
            } catch (RuntimeException e) {
                // the meter never breaks the project
                // bộ đo không bao giờ làm hỏng dự án
            }
        }

        @Override
        public void close() {
            end();
        }
    }

    final Path path;
    final String env;
    final boolean off;
    final Sender sender;

    // env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off. AI_METER_URL and AI_METER_KEY
    // (or sendUrl and sendKey) also send each turn to an AI Worker board, in the background.
    // env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt. AI_METER_URL và AI_METER_KEY
    // (hoặc sendUrl và sendKey) gửi thêm từng lượt lên bảng AI Worker, ở nền.
    public AiMeter(String file, String env, String sendUrl, String sendKey) {
        String f = envOr("AI_METER_FILE", file == null ? "ai-meter.jsonl" : file);
        this.path = Paths.get(f);
        this.env = "test".equals(envOr("AI_METER_ENV", env)) ? "test" : "prod";
        this.off = "1".equals(System.getenv("AI_METER_OFF"));
        String url = envOr("AI_METER_URL", sendUrl), key = envOr("AI_METER_KEY", sendKey);
        Sender s = null;
        try {
            if (!off && url != null && !url.isEmpty() && key != null && !key.isEmpty() && Sender.allowed(url)) s = new Sender(url, key);
        } catch (RuntimeException e) {
            s = null;
        }
        this.sender = s;
    }

    public AiMeter(String file, String env) {
        this(file, env, null, null);
    }

    public AiMeter(String file) {
        this(file, "prod", null, null);
    }

    static String envOr(String name, String fallback) {
        String v = System.getenv(name);
        return v != null && !v.isEmpty() ? v : fallback;
    }

    public String env() {
        return env;
    }

    // Starts a user turn; use it in try-with-resources.
    // Bắt đầu một lượt người dùng; dùng trong try-with-resources.
    public Turn turn() {
        return new Turn();
    }

    // Runs work(turn), writes the line when it ends, and returns or rethrows what work did; an exception whose name says
    // timeout is written as "timeout", any other as "error".
    // Chạy work(turn), ghi dòng khi xong, và trả về hay ném lại đúng điều work làm; lỗi có tên chứa timeout ghi là "timeout",
    // lỗi khác ghi là "error".
    public <T> T turn(Work<T> work) throws Exception {
        Turn t = new Turn();
        try {
            return work.run(t);
        } catch (Exception | Error e) {
            t.setOutcome(e.getClass().getSimpleName().toLowerCase(Locale.ROOT).contains("timeout") ? "timeout" : "error");
            throw e;
        } finally {
            t.end();
        }
    }

    // Sends what is waiting now, for example before the program ends; never throws.
    // Gửi những gì đang chờ ngay bây giờ, ví dụ trước khi chương trình kết thúc; không bao giờ ném lỗi.
    public void flush() {
        if (sender != null) sender.flush();
    }

    // Sends what is waiting and stops the background sender.
    // Gửi những gì đang chờ và dừng phần gửi ở nền.
    @Override
    public void close() {
        if (sender != null) sender.close();
    }

    void write(String line) {
        if (off) return;
        try {
            if (sender != null) sender.add(line);
        } catch (RuntimeException e) {
            // sending is extra: the file still gets the line
            // gửi chỉ là phần thêm: file vẫn nhận dòng
        }
        try {
            synchronized (FILE_LOCK) {
                Files.write(path, (line + "\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND,
                    StandardOpenOption.WRITE);
            }
        } catch (Exception e) {
            // a failure to write never reaches the project
            // ghi lỗi không bao giờ tới được dự án
        }
    }

    // Sending to the board: batches in the background; a full queue drops the oldest turn, a failed send is tried once more,
    // and the project never waits on it. The key goes only over HTTPS, or to this machine itself
    // Gửi lên bảng: các lô đi ở nền; hàng đợi đầy thì bỏ lượt cũ nhất, gửi lỗi thì thử lại một lần,
    // và dự án không bao giờ phải chờ. Khoá chỉ đi qua HTTPS, hoặc tới chính máy này
    static final class Sender {
        static final int QUEUE_MAX = 1000, BATCH_TURNS = 100, BATCH_BYTES = 200 * 1024;
        final String url, key;
        final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
        final ArrayDeque<String> queue = new ArrayDeque<>();
        final ScheduledExecutorService timer;
        List<String> retry = new ArrayList<>();
        boolean closed;

        static boolean allowed(String url) {
            return url.startsWith("https://") || LOCAL_URL.matcher(url).matches();
        }

        Sender(String url, String key) {
            this.url = url;
            this.key = key;
            timer = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "ai-meter-send");
                t.setDaemon(true);
                return t;
            });
            timer.scheduleWithFixedDelay(this::flush, 10, 10, TimeUnit.SECONDS);
            Runtime.getRuntime().addShutdownHook(new Thread(this::flush, "ai-meter-exit"));
        }

        void add(String line) {
            boolean full;
            synchronized (queue) {
                queue.addLast(line);
                while (queue.size() > QUEUE_MAX) queue.pollFirst();
                full = queue.size() >= BATCH_TURNS;
            }
            if (full) {
                try {
                    timer.execute(this::flush);
                } catch (RuntimeException e) {
                    // the sender has stopped; the file still has the turn
                    // phần gửi đã dừng; file vẫn còn lượt đó
                }
            }
        }

        synchronized void flush() {
            try {
                while (true) {
                    boolean again;
                    List<String> batch;
                    synchronized (queue) {
                        again = !retry.isEmpty();
                        batch = retry;
                        retry = new ArrayList<>();
                        int size = 0;
                        while (!queue.isEmpty() && batch.size() < BATCH_TURNS && size < BATCH_BYTES) {
                            String l = queue.pollFirst();
                            size += l.length();
                            batch.add(l);
                        }
                    }
                    if (batch.isEmpty()) return;
                    boolean ok;
                    try {
                        HttpRequest req = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5))
                            .header("Authorization", "Bearer " + key).header("Content-Type", "application/json").header("User-Agent", "ai-meter/1")
                            .POST(HttpRequest.BodyPublishers.ofString("{\"turns\":[" + String.join(",", batch) + "]}", StandardCharsets.UTF_8)).build();
                        int code = http.send(req, HttpResponse.BodyHandlers.discarding()).statusCode();
                        ok = code < 500 && code != 429;
                    } catch (Exception e) {
                        if (e instanceof InterruptedException) Thread.currentThread().interrupt();
                        ok = false;
                    }
                    if (!ok) {
                        // tried once more at the next send, then let go; the file still has every turn
                        // thử lại một lần ở lần gửi sau, rồi bỏ; file vẫn còn đủ mọi lượt
                        if (!again) synchronized (queue) {
                            retry = batch;
                        }
                        return;
                    }
                }
            } catch (RuntimeException e) {
                // the meter never breaks the project
                // bộ đo không bao giờ làm hỏng dự án
            }
        }

        void close() {
            synchronized (this) {
                if (closed) return;
                closed = true;
            }
            timer.shutdown();
            flush();
        }
    }

    // A small JSON reader, enough for an LLM answer: objects become Maps, arrays Lists, whole numbers Long (BigInteger when too
    // big), other numbers BigDecimal. It refuses anything that is not JSON, and nesting deeper than 200.
    // Một bộ đọc JSON nhỏ, đủ cho câu trả lời của LLM: object thành Map, mảng thành List, số nguyên thành Long (BigInteger khi
    // quá lớn), số khác thành BigDecimal. Từ chối mọi thứ không phải JSON, và lồng sâu hơn 200 tầng.
    static final class Json {
        final String s;
        int i;

        Json(String s) {
            this.s = s;
        }

        static Object parse(String text) {
            Json j = new Json(text);
            Object v = j.value(0);
            j.space();
            if (j.i != j.s.length()) throw new IllegalArgumentException("json");
            return v;
        }

        void space() {
            while (i < s.length() && (s.charAt(i) == ' ' || s.charAt(i) == '\n' || s.charAt(i) == '\r' || s.charAt(i) == '\t')) i++;
        }

        char peek() {
            if (i >= s.length()) throw new IllegalArgumentException("json");
            return s.charAt(i);
        }

        Object value(int depth) {
            if (depth > 200) throw new IllegalArgumentException("json");
            space();
            char c = peek();
            if (c == '{') {
                i++;
                Map<String, Object> o = new LinkedHashMap<>();
                space();
                if (peek() == '}') {
                    i++;
                    return o;
                }
                while (true) {
                    space();
                    if (peek() != '"') throw new IllegalArgumentException("json");
                    String k = string();
                    space();
                    if (peek() != ':') throw new IllegalArgumentException("json");
                    i++;
                    o.put(k, value(depth + 1));
                    space();
                    char n = peek();
                    i++;
                    if (n == '}') return o;
                    if (n != ',') throw new IllegalArgumentException("json");
                }
            }
            if (c == '[') {
                i++;
                List<Object> a = new ArrayList<>();
                space();
                if (peek() == ']') {
                    i++;
                    return a;
                }
                while (true) {
                    a.add(value(depth + 1));
                    space();
                    char n = peek();
                    i++;
                    if (n == ']') return a;
                    if (n != ',') throw new IllegalArgumentException("json");
                }
            }
            if (c == '"') return string();
            if (s.startsWith("true", i)) {
                i += 4;
                return Boolean.TRUE;
            }
            if (s.startsWith("false", i)) {
                i += 5;
                return Boolean.FALSE;
            }
            if (s.startsWith("null", i)) {
                i += 4;
                return null;
            }
            return number();
        }

        String string() {
            i++;
            StringBuilder b = new StringBuilder();
            while (true) {
                char c = peek();
                i++;
                if (c == '"') return b.toString();
                if (c < 0x20) throw new IllegalArgumentException("json");
                if (c != '\\') {
                    b.append(c);
                    continue;
                }
                char e = peek();
                i++;
                switch (e) {
                    case '"': b.append('"'); break;
                    case '\\': b.append('\\'); break;
                    case '/': b.append('/'); break;
                    case 'b': b.append('\b'); break;
                    case 'f': b.append('\f'); break;
                    case 'n': b.append('\n'); break;
                    case 'r': b.append('\r'); break;
                    case 't': b.append('\t'); break;
                    case 'u':
                        if (i + 4 > s.length()) throw new IllegalArgumentException("json");
                        b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                        i += 4;
                        break;
                    default: throw new IllegalArgumentException("json");
                }
            }
        }

        Object number() {
            int start = i;
            if (i < s.length() && s.charAt(i) == '-') i++;
            boolean whole = true;
            while (i < s.length()) {
                char c = s.charAt(i);
                if (c >= '0' && c <= '9') i++;
                else if (c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-') {
                    whole = false;
                    i++;
                } else break;
            }
            String t = s.substring(start, i);
            if (t.isEmpty() || t.equals("-")) throw new IllegalArgumentException("json");
            if (!whole) return new BigDecimal(t);
            BigInteger n = new BigInteger(t);
            return n.bitLength() < 64 ? (Object) n.longValue() : n;
        }
    }
}
