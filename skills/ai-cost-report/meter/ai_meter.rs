//! Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
//! Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
//!
//! Copy this one file into `src/` and add `mod ai_meter;`. Standard library only, so no crate to add. Rust has no JSON reader of
//! its own: pass the token counts your client already parsed (for example `usage.input_tokens`) with `count`. FORMAT.md says
//! which field is which for each provider. The meter writes the file only; send it to a board with your own HTTP client if needed.
//! It never writes a prompt, an answer, a user id or an error message.
//! Chép đúng file này vào `src/` và thêm `mod ai_meter;`. Chỉ thư viện chuẩn, không cần thêm crate. Rust không có sẵn bộ đọc
//! JSON: đưa số token mà client của bạn đã đọc (ví dụ `usage.input_tokens`) vào `count`. FORMAT.vi.md ghi trường nào là gì
//! cho từng hãng. Bộ đo chỉ ghi file; cần gửi lên bảng thì dùng HTTP client của bạn. Không bao giờ ghi câu hỏi, câu trả lời,
//! mã người dùng hay thông báo lỗi.
//!
//! ```ignore
//! let meter = ai_meter::Meter::new("ai-meter.jsonl", "prod");
//! let mut t = meter.turn();
//! t.count("anthropic", "claude-sonnet-5-5", Some(ai_meter::Counts { input: 812, output: 95, ..Default::default() }));
//! t.end(); // or let t go out of scope
//! ```
#![allow(dead_code)]

use std::collections::hash_map::RandomState;
use std::fs::OpenOptions;
use std::hash::{BuildHasher, Hasher};
use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

static FILE_LOCK: Mutex<()> = Mutex::new(());
static COUNTER: AtomicU64 = AtomicU64::new(0);

/// Token counts of one call: input billed at the normal price (without cache reads and writes), output, cache reads, cache
/// writes, and the part of the cache writes kept longer.
/// Số token của một lần gọi: đầu vào tính giá thường (không gồm đọc và ghi cache), đầu ra, đọc cache, ghi cache, và phần
/// ghi cache giữ lâu hơn.
#[derive(Clone, Copy, Debug, Default)]
pub struct Counts {
    pub input: u64,
    pub output: u64,
    pub cache_read: u64,
    pub cache_write: u64,
    pub cache_write_long: u64,
}

#[derive(Default)]
struct Slot {
    calls: u64,
    errors: u64,
    retries: u64,
    unmeasured: u64,
    counts: Counts,
}

// A provider is a short name: lowercase letters, digits, "_", "." and "-", at most 32; anything else is written as "other"
// Hãng là một tên ngắn: chữ thường, số, "_", "." và "-", tối đa 32 ký tự; tên khác ghi thành "other"
fn clean_provider(p: &str) -> String {
    let p = p.trim().to_lowercase();
    let ok = !p.is_empty() && p.len() <= 32 && p.chars().next().map_or(false, |c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && p.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c));
    if ok { p } else { "other".to_string() }
}

fn clean_model(m: &str) -> String {
    let ok = !m.is_empty() && m.len() <= 79 && m.chars().next().map_or(false, |c| c.is_ascii_alphanumeric())
        && m.chars().all(|c| c.is_ascii_alphanumeric() || "._:/@-".contains(c));
    if ok { m.to_string() } else { "unknown".to_string() }
}

// UTC time as 2026-11-20T08:15:02.481Z, from the system clock, with no crate
// Giờ UTC dạng 2026-11-20T08:15:02.481Z, từ đồng hồ hệ thống, không cần crate
fn iso_utc(t: SystemTime) -> String {
    let d = t.duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = d.as_secs() as i64;
    let (days, rem) = (secs.div_euclid(86400), secs.rem_euclid(86400));
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}Z", year, month, day, rem / 3600, rem % 3600 / 60, rem % 60, d.subsec_millis())
}

// 16 hex characters, different for each turn; not secret, it only lets the report drop a line it has already read
// 16 ký tự hex, mỗi lượt một mã; không cần bí mật, chỉ để báo cáo bỏ dòng đã đọc
fn turn_id() -> String {
    let mut h = RandomState::new().build_hasher();
    h.write_u64(COUNTER.fetch_add(1, Ordering::Relaxed));
    h.write_u128(SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos());
    format!("{:016x}", h.finish())
}

/// One user turn: every LLM call made to answer it. Get one from `Meter::turn`; `end` (or dropping it) writes the line.
/// Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Lấy từ `Meter::turn`; `end` (hoặc bỏ nó đi) thì ghi dòng.
pub struct Turn<'a> {
    meter: &'a Meter,
    at: SystemTime,
    clock: Instant,
    ttft_ms: Option<u128>,
    models: Vec<(String, String, Slot)>,
    outcome: &'static str,
    done: bool,
}

impl<'a> Turn<'a> {
    fn slot(&mut self, provider: &str, model: &str) -> &mut Slot {
        let (p, m) = (clean_provider(provider), clean_model(model));
        let i = match self.models.iter().position(|(a, b, _)| *a == p && *b == m) {
            Some(i) => i,
            None => {
                self.models.push((p, m, Slot::default()));
                self.models.len() - 1
            }
        };
        &mut self.models[i].2
    }

    /// Counts one LLM call; `None` means its answer carried no token counts (not measured, never zero).
    /// Đếm một lần gọi LLM; `None` nghĩa là câu trả lời không kèm số token (không đo được, không bao giờ là 0).
    pub fn count(&mut self, provider: &str, model: &str, counts: Option<Counts>) {
        self.count_with(provider, model, counts, false)
    }

    /// `count` that can mark a call repeating a failed one.
    /// `count` có thể đánh dấu lần gọi lặp lại một lần đã lỗi.
    pub fn count_with(&mut self, provider: &str, model: &str, counts: Option<Counts>, retry: bool) {
        let s = self.slot(provider, model);
        s.calls += 1;
        if retry {
            s.retries += 1;
        }
        match counts {
            Some(c) if c.cache_write_long <= c.cache_write => {
                s.counts.input += c.input;
                s.counts.output += c.output;
                s.counts.cache_read += c.cache_read;
                s.counts.cache_write += c.cache_write;
                s.counts.cache_write_long += c.cache_write_long;
            }
            _ => s.unmeasured += 1,
        }
    }

    /// Counts one LLM call that failed (no answer, so no usage). Pass no error text.
    /// Đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi.
    pub fn fail(&mut self, provider: &str, model: &str, retry: bool) {
        let s = self.slot(provider, model);
        s.calls += 1;
        s.errors += 1;
        if retry {
            s.retries += 1;
        }
    }

    /// Marks the first streamed piece of the answer; only the first mark counts.
    /// Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.
    pub fn first_token(&mut self) {
        if self.ttft_ms.is_none() {
            self.ttft_ms = Some(self.clock.elapsed().as_millis());
        }
    }

    /// "error" or "timeout" when the turn did not end well.
    /// "error" hay "timeout" khi lượt không kết thúc tốt.
    pub fn set_outcome(&mut self, outcome: &str) {
        self.outcome = match outcome {
            "ok" => "ok",
            "timeout" => "timeout",
            _ => "error",
        };
    }

    /// Writes the line, once.
    /// Ghi dòng, một lần.
    pub fn end(&mut self) {
        if self.done {
            return;
        }
        self.done = true;
        let mut line = format!("{{\"v\":1,\"turnId\":\"{}\",\"at\":\"{}\",\"durationMs\":{},\"outcome\":\"{}\",\"env\":\"{}\"",
                               turn_id(), iso_utc(self.at), self.clock.elapsed().as_millis(), self.outcome, self.meter.env);
        if let Some(t) = self.ttft_ms {
            line.push_str(&format!(",\"ttftMs\":{}", t));
        }
        line.push_str(",\"models\":[");
        for (i, (p, m, s)) in self.models.iter().enumerate() {
            // every answered call lacked usage: the tokens are unknown, not zero
            // mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
            let unknown = s.unmeasured > 0 && s.calls - s.errors == s.unmeasured;
            let n = |v: u64| if unknown { "null".to_string() } else { v.to_string() };
            if i > 0 {
                line.push(',');
            }
            line.push_str(&format!("{{\"provider\":\"{}\",\"model\":\"{}\",\"calls\":{},\"errors\":{},\"retries\":{},\"unmeasured\":{},\"input\":{},\"output\":{},\"cacheRead\":{},\"cacheWrite\":{},\"cacheWriteLong\":{}}}",
                                   p, m, s.calls, s.errors, s.retries, s.unmeasured, n(s.counts.input), n(s.counts.output), n(s.counts.cache_read),
                                   n(s.counts.cache_write), n(s.counts.cache_write_long)));
        }
        line.push_str("]}\n");
        self.meter.write(&line);
    }
}

impl Drop for Turn<'_> {
    fn drop(&mut self) {
        if std::thread::panicking() {
            self.outcome = "error";
        }
        self.end();
    }
}

/// Where the lines go. env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off.
/// Nơi ghi các dòng. env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt.
pub struct Meter {
    path: String,
    env: &'static str,
    off: bool,
}

impl Meter {
    pub fn new(path: &str, env: &str) -> Meter {
        let path = std::env::var("AI_METER_FILE").ok().filter(|v| !v.is_empty()).unwrap_or_else(|| path.to_string());
        let env = std::env::var("AI_METER_ENV").ok().filter(|v| !v.is_empty()).unwrap_or_else(|| env.to_string());
        Meter { path, env: if env == "test" { "test" } else { "prod" }, off: std::env::var("AI_METER_OFF").map_or(false, |v| v == "1") }
    }

    pub fn turn(&self) -> Turn<'_> {
        Turn { meter: self, at: SystemTime::now(), clock: Instant::now(), ttft_ms: None, models: Vec::new(), outcome: "ok", done: false }
    }

    // a failure to write never reaches the project
    // ghi lỗi không bao giờ tới được dự án
    fn write(&self, line: &str) {
        if self.off {
            return;
        }
        let _guard = FILE_LOCK.lock();
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&self.path) {
            let _ = f.write_all(line.as_bytes());
        }
    }
}
