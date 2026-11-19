// Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
// Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
//
// Copy this one header into the project; it works from C (C99) and from C++, on Linux, macOS and Windows, with the standard
// library and the system only. C and C++ have no JSON reader of their own: pass the token counts your client already parsed
// (for example usage.input_tokens) to ai_turn_count. FORMAT.md says which field is which for each provider. The meter writes
// the file only. It never writes a prompt, an answer, a user id or an error message.
// Chép đúng header này vào dự án; dùng được từ C (C99) và C++, trên Linux, macOS và Windows, chỉ cần thư viện chuẩn và hệ điều
// hành. C và C++ không có sẵn bộ đọc JSON: đưa số token mà client của bạn đã đọc (ví dụ usage.input_tokens) vào ai_turn_count.
// FORMAT.vi.md ghi trường nào là gì cho từng hãng. Bộ đo chỉ ghi file. Không bao giờ ghi câu hỏi, câu trả lời, mã người dùng
// hay thông báo lỗi.
//
// ai_meter m;
// ai_meter_init(&m, "ai-meter.jsonl", "prod");
// ai_turn t;
// ai_turn_begin(&t, &m);
// ai_turn_count(&t, "anthropic", "claude-sonnet-5-5", 812, 95, 0, 0, 0);  // input -1 means not measured
// ai_turn_end(&t);
#ifndef AI_METER_H
#define AI_METER_H

// clock_gettime and gmtime_r are POSIX: glibc hides them under -std=c99 unless asked. This works when the header comes first;
// otherwise compile with -D_POSIX_C_SOURCE=200809L (or -std=gnu99)
// clock_gettime và gmtime_r thuộc POSIX: glibc ẩn chúng khi dùng -std=c99 nếu không bật. Cách này có tác dụng khi header đứng
// đầu; nếu không thì dịch với -D_POSIX_C_SOURCE=200809L (hoặc -std=gnu99)
#if !defined(_WIN32) && !defined(__APPLE__) && !defined(_POSIX_C_SOURCE) && !defined(_GNU_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif

#define AI_METER_MAX_MODELS 16

typedef struct {
    char path[512];
    char env[8];
    int off;
} ai_meter;

typedef struct {
    char provider[33];
    char model[80];
    long long calls, errors, retries, unmeasured, input, output, cache_read, cache_write, cache_write_long;
} ai_meter_slot;

typedef struct {
    const ai_meter *meter;
    double t0_ms, ttft_ms;
    long long at_ms;
    int has_ttft, done, count;
    char outcome[8];
    ai_meter_slot models[AI_METER_MAX_MODELS];
} ai_turn;

// a monotonic clock in milliseconds, for durations
// đồng hồ đơn điệu tính bằng mili giây, để đo khoảng thời gian
static inline double ai_meter_now_ms(void) {
#ifdef _WIN32
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)f.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
#endif
}

// wall-clock time in milliseconds since 1970, for the "at" field
// giờ thật tính bằng mili giây từ 1970, cho trường "at"
static inline long long ai_meter_epoch_ms(void) {
#ifdef _WIN32
    FILETIME ft;
    ULARGE_INTEGER u;
    GetSystemTimeAsFileTime(&ft);
    u.LowPart = ft.dwLowDateTime;
    u.HighPart = ft.dwHighDateTime;
    return (long long)((u.QuadPart - 116444736000000000ULL) / 10000ULL);
#else
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000L;
#endif
}

// a provider is a short name: lowercase letters, digits, "_", "." and "-", at most 32; anything else becomes "other"
// hãng là một tên ngắn: chữ thường, số, "_", "." và "-", tối đa 32 ký tự; tên khác thành "other"
static inline void ai_meter_clean_provider(const char *in, char out[33]) {
    size_t n = 0, i;
    int ok = in != NULL;
    while (ok && in[n] == ' ') in++;
    for (i = 0; ok && in[i] && n < 32; i++) {
        char c = (char)tolower((unsigned char)in[i]);
        if (c == ' ' && in[i + 1] == '\0') break;
        if (!(isdigit((unsigned char)c) || (c >= 'a' && c <= 'z') || ((c == '_' || c == '.' || c == '-') && n > 0))) ok = 0;
        else out[n++] = c;
    }
    if (ok && in[i] && in[i] != ' ') ok = 0;
    if (!ok || n == 0) strcpy(out, "other");
    else out[n] = '\0';
}

static inline void ai_meter_clean_model(const char *in, char out[80]) {
    size_t i;
    int ok = in != NULL && in[0] && isalnum((unsigned char)in[0]);
    for (i = 0; ok && in[i]; i++) {
        if (i >= 79 || !(isalnum((unsigned char)in[i]) || strchr("._:/@-", in[i]))) ok = 0;
    }
    if (ok) strcpy(out, in);
    else strcpy(out, "unknown");
}

// env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off
// env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt
static inline void ai_meter_init(ai_meter *m, const char *path, const char *env) {
    const char *f = getenv("AI_METER_FILE"), *e = getenv("AI_METER_ENV"), *o = getenv("AI_METER_OFF");
    if (f && *f) path = f;
    if (e && *e) env = e;
    snprintf(m->path, sizeof m->path, "%s", path ? path : "ai-meter.jsonl");
    strcpy(m->env, env && strcmp(env, "test") == 0 ? "test" : "prod");
    m->off = o && strcmp(o, "1") == 0;
}

static inline void ai_turn_begin(ai_turn *t, const ai_meter *m) {
    memset(t, 0, sizeof *t);
    t->meter = m;
    t->t0_ms = ai_meter_now_ms();
    t->at_ms = ai_meter_epoch_ms();
    strcpy(t->outcome, "ok");
}

static inline ai_meter_slot *ai_turn_slot(ai_turn *t, const char *provider, const char *model) {
    char p[33], m[80];
    int i;
    ai_meter_clean_provider(provider, p);
    ai_meter_clean_model(model, m);
    for (i = 0; i < t->count; i++)
        if (strcmp(t->models[i].provider, p) == 0 && strcmp(t->models[i].model, m) == 0) return &t->models[i];
    if (t->count == AI_METER_MAX_MODELS) return NULL;
    strcpy(t->models[t->count].provider, p);
    strcpy(t->models[t->count].model, m);
    return &t->models[t->count++];
}

// Counts one LLM call. input is billed at the normal price, without cache reads and writes; input or output -1 means the
// answer carried no token counts (not measured, never zero)
// Đếm một lần gọi LLM. input là đầu vào tính giá thường, không gồm đọc và ghi cache; input hay output là -1 nghĩa là câu trả
// lời không kèm số token (không đo được, không bao giờ là 0)
static inline void ai_turn_count_retry(ai_turn *t, const char *provider, const char *model, long long input, long long output,
                                       long long cache_read, long long cache_write, long long cache_write_long, int retry) {
    ai_meter_slot *s = ai_turn_slot(t, provider, model);
    if (!s) return;
    s->calls++;
    if (retry) s->retries++;
    if (input < 0 || output < 0 || cache_read < 0 || cache_write < 0 || cache_write_long < 0 || cache_write_long > cache_write) {
        s->unmeasured++;
        return;
    }
    s->input += input;
    s->output += output;
    s->cache_read += cache_read;
    s->cache_write += cache_write;
    s->cache_write_long += cache_write_long;
}

static inline void ai_turn_count(ai_turn *t, const char *provider, const char *model, long long input, long long output,
                                 long long cache_read, long long cache_write, long long cache_write_long) {
    ai_turn_count_retry(t, provider, model, input, output, cache_read, cache_write, cache_write_long, 0);
}

// Counts one LLM call that failed (no answer, so no usage). Pass no error text.
// Đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi.
static inline void ai_turn_fail(ai_turn *t, const char *provider, const char *model, int retry) {
    ai_meter_slot *s = ai_turn_slot(t, provider, model);
    if (!s) return;
    s->calls++;
    s->errors++;
    if (retry) s->retries++;
}

// Marks the first streamed piece of the answer; only the first mark counts.
// Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.
static inline void ai_turn_first_token(ai_turn *t) {
    if (!t->has_ttft) {
        t->ttft_ms = ai_meter_now_ms() - t->t0_ms;
        t->has_ttft = 1;
    }
}

// "error" or "timeout" when the turn did not end well
// "error" hay "timeout" khi lượt không kết thúc tốt
static inline void ai_turn_set_outcome(ai_turn *t, const char *outcome) {
    strcpy(t->outcome, outcome && strcmp(outcome, "ok") == 0 ? "ok" : outcome && strcmp(outcome, "timeout") == 0 ? "timeout" : "error");
}

// 16 hex characters, different for each turn; not secret, it only lets the report drop a line it has already read
// 16 ký tự hex, mỗi lượt một mã; không cần bí mật, chỉ để báo cáo bỏ dòng đã đọc
static inline void ai_meter_turn_id(const ai_turn *t, char out[17]) {
    unsigned long long x = 0;
#ifndef _WIN32
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd >= 0) {
        if (read(fd, &x, sizeof x) != (ssize_t)sizeof x) x = 0;
        close(fd);
    }
#endif
    x ^= (unsigned long long)t->at_ms * 0x9E3779B97F4A7C15ULL ^ (unsigned long long)(ai_meter_now_ms() * 1000.0) ^ (unsigned long long)(size_t)t;
    snprintf(out, 17, "%016llx", x);
}

// Writes the line, once, in one write to the end of the file; a failure never reaches the project
// Ghi dòng, một lần, bằng một lệnh ghi vào cuối file; ghi lỗi không bao giờ tới được dự án
static inline void ai_turn_end(ai_turn *t) {
    char line[AI_METER_MAX_MODELS * 320 + 400], id[17], at[32];
    size_t n;
    int i, fd;
    time_t secs;
    struct tm tmv;
    if (t->done) return;
    t->done = 1;
    if (t->meter->off) return;
    ai_meter_turn_id(t, id);
    secs = (time_t)(t->at_ms / 1000);
#ifdef _WIN32
    gmtime_s(&tmv, &secs);
#else
    gmtime_r(&secs, &tmv);
#endif
    snprintf(at, sizeof at, "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ", tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday, tmv.tm_hour, tmv.tm_min,
             tmv.tm_sec, (int)(t->at_ms % 1000));
    n = (size_t)snprintf(line, sizeof line, "{\"v\":1,\"turnId\":\"%s\",\"at\":\"%s\",\"durationMs\":%lld,\"outcome\":\"%s\",\"env\":\"%s\"", id, at,
                         (long long)(ai_meter_now_ms() - t->t0_ms), t->outcome, t->meter->env);
    if (t->has_ttft) n += (size_t)snprintf(line + n, sizeof line - n, ",\"ttftMs\":%lld", (long long)t->ttft_ms);
    n += (size_t)snprintf(line + n, sizeof line - n, ",\"models\":[");
    for (i = 0; i < t->count; i++) {
        const ai_meter_slot *s = &t->models[i];
        // every answered call lacked usage: the tokens are unknown, not zero
        // mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
        int unknown = s->unmeasured > 0 && s->calls - s->errors == s->unmeasured;
        n += (size_t)snprintf(line + n, sizeof line - n, "%s{\"provider\":\"%s\",\"model\":\"%s\",\"calls\":%lld,\"errors\":%lld,\"retries\":%lld,\"unmeasured\":%lld,",
                              i ? "," : "", s->provider, s->model, s->calls, s->errors, s->retries, s->unmeasured);
        if (unknown)
            n += (size_t)snprintf(line + n, sizeof line - n, "\"input\":null,\"output\":null,\"cacheRead\":null,\"cacheWrite\":null,\"cacheWriteLong\":null}");
        else
            n += (size_t)snprintf(line + n, sizeof line - n, "\"input\":%lld,\"output\":%lld,\"cacheRead\":%lld,\"cacheWrite\":%lld,\"cacheWriteLong\":%lld}",
                                  s->input, s->output, s->cache_read, s->cache_write, s->cache_write_long);
    }
    n += (size_t)snprintf(line + n, sizeof line - n, "]}\n");
    if (n >= sizeof line) return;
#ifdef _WIN32
    fd = _open(t->meter->path, _O_WRONLY | _O_APPEND | _O_CREAT | _O_BINARY, 0644);
    if (fd >= 0) {
        _write(fd, line, (unsigned)n);
        _close(fd);
    }
#else
    fd = open(t->meter->path, O_WRONLY | O_APPEND | O_CREAT, 0644);
    if (fd >= 0) {
        if (write(fd, line, n) < 0) {
            // nothing to do: the project goes on
            // không làm gì: dự án vẫn chạy tiếp
        }
        close(fd);
    }
#endif
}

#endif  // AI_METER_H
