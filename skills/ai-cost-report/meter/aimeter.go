// Package aimeter measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
// Gói aimeter đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
//
// Copy this one file into a folder aimeter/ of the project. Go 1.21 or newer, standard library only. Same line format and the
// same reading of usage as ai_meter.py; it never writes a prompt, an answer, a user id or an error message.
// Chép đúng file này vào thư mục aimeter/ của dự án. Go 1.21 trở lên, chỉ thư viện chuẩn. Cùng định dạng dòng và cùng cách
// đọc usage như ai_meter.py; không bao giờ ghi câu hỏi, câu trả lời, mã người dùng hay thông báo lỗi.
//
//	m := aimeter.New("ai-meter.jsonl", "prod")
//	defer m.Close()
//	t := m.Turn()
//	defer t.End()
//	t.Record(body) // the provider's answer, as JSON bytes
//	t.Count("myprovider", "my-model", &aimeter.Counts{Input: 812, Output: 95}) // any provider, counts by hand
package aimeter

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

var (
	providerRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_.-]{0,31}$`)
	modelRe    = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$`)
	openaiRe   = regexp.MustCompile(`^(gpt-|o1|o3|o4|chatgpt)`)
	localRe    = regexp.MustCompile(`^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/`)
	fileLock   sync.Mutex
)

// Counts are the token counts of one call: input billed at the normal price, output, cache reads, cache writes, and the part of
// the cache writes kept longer.
// Counts là số token của một lần gọi: đầu vào tính giá thường, đầu ra, đọc cache, ghi cache, và phần ghi cache giữ lâu hơn.
type Counts struct {
	Input, Output, CacheRead, CacheWrite, CacheWriteLong int64
}

// Opt names the provider or the model when the answer does not, and marks a call that repeats a failed one.
// Opt cho biết hãng hay model khi câu trả lời không ghi, và đánh dấu lần gọi lặp lại một lần đã lỗi.
type Opt struct {
	Provider, Model string
	Retry           bool
}

func cleanProvider(p string) string {
	p = strings.ToLower(strings.TrimSpace(p))
	if p == "" || !providerRe.MatchString(p) {
		return "other"
	}
	return p
}

func cleanModel(m string) string {
	if !modelRe.MatchString(m) {
		return "unknown"
	}
	return m
}

// GuessProvider is used only when neither the caller nor the usage shape names the provider.
// GuessProvider chỉ dùng khi cả người gọi lẫn hình dạng usage đều không cho biết hãng.
func GuessProvider(model string) string {
	parts := strings.Split(strings.ToLower(model), "/")
	m := parts[len(parts)-1]
	switch {
	case strings.Contains(m, "claude"):
		return "anthropic"
	case openaiRe.MatchString(m):
		return "openai"
	case strings.HasPrefix(m, "gemini"), strings.HasPrefix(m, "gemma"):
		return "google"
	case strings.HasPrefix(m, "deepseek"):
		return "deepseek"
	case strings.HasPrefix(m, "mistral"), strings.HasPrefix(m, "mixtral"), strings.HasPrefix(m, "codestral"):
		return "mistral"
	case strings.HasPrefix(m, "grok"):
		return "xai"
	case strings.HasPrefix(m, "command"):
		return "cohere"
	}
	return "other"
}

type obj = map[string]any

func get(d any, keys ...string) any {
	o, ok := d.(obj)
	if !ok {
		return nil
	}
	for _, k := range keys {
		if v, ok := o[k]; ok && v != nil {
			return v
		}
	}
	return nil
}

func has(d any, key string) bool {
	o, ok := d.(obj)
	if !ok {
		return false
	}
	_, ok = o[key]
	return ok
}

// a token count is a whole number of zero or more; anything else is "not measured" (-1)
// số token là số nguyên từ 0 trở lên; thứ khác là "không đo được" (-1)
func num(v any) int64 {
	n, ok := v.(json.Number)
	if !ok {
		return -1
	}
	i, err := n.Int64()
	if err != nil || i < 0 {
		return -1
	}
	return i
}

func num0(v any) int64 {
	if v == nil {
		return 0
	}
	return num(v)
}

func str(v any) string {
	s, _ := v.(string)
	return s
}

func make5(i, o, r, w, l int64) *Counts {
	if i < 0 || o < 0 || r < 0 || w < 0 || l < 0 || l > w {
		return nil
	}
	return &Counts{i, o, r, w, l}
}

// Read gives the provider, the model and the counts of a provider's answer; counts is nil when it carries no usage.
// Same shapes as ai_meter.py: Anthropic, OpenAI and every API that copies it, Gemini, Bedrock Converse, Ollama, Cohere v2, Vercel AI SDK.
// Read trả hãng, model và số đếm của câu trả lời; số đếm là nil khi không có usage. Cùng các dạng như ai_meter.py.
func Read(body []byte, provider string) (string, string, *Counts) {
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.UseNumber()
	var root any
	if dec.Decode(&root) != nil {
		return provider, "", nil
	}
	d, ok := root.(obj)
	if !ok {
		return provider, "", nil
	}
	or := func(p string) string {
		if provider != "" {
			return provider
		}
		return p
	}
	model := str(get(d, "model", "modelVersion", "model_version", "modelId"))
	// Gemini: promptTokenCount includes the cache; thinking tokens are billed as output
	// Gemini: promptTokenCount đã gồm cache; token suy nghĩ tính tiền như output
	gem := get(d, "usageMetadata", "usage_metadata")
	if gem == nil && get(d, "promptTokenCount", "prompt_token_count") != nil {
		gem = d
	}
	if g, ok := gem.(obj); ok {
		prompt := num(get(g, "promptTokenCount", "prompt_token_count"))
		cached := num0(get(g, "cachedContentTokenCount", "cached_content_token_count"))
		cand := num0(get(g, "candidatesTokenCount", "candidates_token_count"))
		think := num0(get(g, "thoughtsTokenCount", "thoughts_token_count"))
		if prompt < 0 || cached < 0 || cand < 0 || think < 0 || cached > prompt {
			return or("google"), model, nil
		}
		return or("google"), model, make5(prompt-cached, cand+think, cached, 0, 0)
	}
	// Ollama /api/chat: prompt_eval_count and eval_count on the answer itself
	// /api/chat của Ollama: prompt_eval_count và eval_count nằm ngay trên câu trả lời
	if has(d, "eval_count") || has(d, "prompt_eval_count") {
		return or("ollama"), model, make5(num(get(d, "prompt_eval_count")), num(get(d, "eval_count")), 0, 0, 0)
	}
	u := d
	if uo, ok := get(d, "usage").(obj); ok {
		u = uo
	}
	// Vercel AI SDK: inputTokens include the cache; inputTokenDetails splits them
	// Vercel AI SDK: inputTokens đã gồm cache; inputTokenDetails tách ra
	if det, ok := get(u, "inputTokenDetails").(obj); ok {
		read, write := num0(get(det, "cacheReadTokens")), num0(get(det, "cacheWriteTokens"))
		plain := num(get(det, "noCacheTokens"))
		if plain < 0 {
			if total := num(get(u, "inputTokens")); total >= 0 && read >= 0 && write >= 0 {
				plain = total - read - write
			}
		}
		return or(GuessProvider(model)), model, make5(plain, num(get(u, "outputTokens")), read, write, 0)
	}
	// Bedrock Converse: inputTokens are only the tokens not read from or written to the cache
	// Bedrock Converse: inputTokens chỉ là phần không đọc từ cache và không ghi vào cache
	if has(u, "inputTokens") || has(u, "outputTokens") {
		return or("bedrock"), model, make5(num(get(u, "inputTokens")), num(get(u, "outputTokens")),
			num0(get(u, "cacheReadInputTokens")), num0(get(u, "cacheWriteInputTokens")), 0)
	}
	// Cohere v2: the billed units are what costs money
	// Cohere v2: billed_units là phần bị tính tiền
	if b, ok := get(u, "billed_units").(obj); ok {
		return or("cohere"), model, make5(num(get(b, "input_tokens")), num(get(b, "output_tokens")), 0, 0, 0)
	}
	// Anthropic: input_tokens excludes the cache
	// Anthropic: input_tokens không gồm cache
	if has(u, "cache_read_input_tokens") || has(u, "cache_creation_input_tokens") || provider == "anthropic" {
		long := num0(get(get(u, "cache_creation"), "ephemeral_1h_input_tokens"))
		return or("anthropic"), model, make5(num(get(u, "input_tokens")), num(get(u, "output_tokens")),
			num0(get(u, "cache_read_input_tokens")), num0(get(u, "cache_creation_input_tokens")), long)
	}
	// OpenAI and every API that copies it: input or prompt tokens include cache reads and writes
	// OpenAI và mọi API chép theo nó: input hay prompt tokens đã gồm cache đọc và ghi
	total, out := num(get(u, "input_tokens", "prompt_tokens")), num(get(u, "output_tokens", "completion_tokens"))
	p := or(GuessProvider(model))
	if get(u, "input_tokens", "prompt_tokens") == nil && get(u, "output_tokens", "completion_tokens") == nil {
		return p, model, nil
	}
	det := get(u, "input_tokens_details", "prompt_tokens_details")
	readV := get(det, "cached_tokens", "prompt_cache_hit_tokens")
	if readV == nil {
		readV = get(u, "prompt_cache_hit_tokens")
	}
	read, write := num0(readV), num0(get(det, "cache_write_tokens"))
	long := num0(get(get(det, "cache_write_tokens_details"), "ttl_12h_tokens"))
	if total < 0 || out < 0 || read < 0 || write < 0 || long < 0 || read+write > total {
		return p, model, nil
	}
	// Some of these APIs (xAI's Chat Completions) leave reasoning tokens out of completion_tokens; total_tokens shows it
	// Vài API loại này (Chat Completions của xAI) không tính token suy nghĩ vào completion_tokens; total_tokens cho thấy điều đó
	if think := num0(get(get(u, "completion_tokens_details", "output_tokens_details"), "reasoning_tokens")); think > 0 && num(get(u, "total_tokens")) == total+out+think {
		out += think
	}
	return p, model, make5(total-read-write, out, read, write, long)
}

type slot struct {
	Calls, Errors, Retries, Unmeasured int64
	Counts
	order int
}

type key struct{ provider, model string }

// Turn is one user turn: every LLM call made to answer it. Get one from Meter.Turn; End writes the line.
// Turn là một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Lấy từ Meter.Turn; End ghi dòng.
type Turn struct {
	meter   *Meter
	started time.Time
	mu      sync.Mutex
	models  map[key]*slot
	ttft    time.Duration
	hasTTFT bool
	outcome string
	done    bool
}

func (t *Turn) add(provider, model string, c *Counts, retry, failed bool) {
	t.mu.Lock()
	defer t.mu.Unlock()
	k := key{cleanProvider(provider), cleanModel(model)}
	s := t.models[k]
	if s == nil {
		s = &slot{order: len(t.models)}
		t.models[k] = s
	}
	s.Calls++
	if retry {
		s.Retries++
	}
	switch {
	case failed:
		s.Errors++
	case c == nil:
		s.Unmeasured++
	default:
		s.Input += c.Input
		s.Output += c.Output
		s.CacheRead += c.CacheRead
		s.CacheWrite += c.CacheWrite
		s.CacheWriteLong += c.CacheWriteLong
	}
}

// Record counts one LLM call from the provider's answer, as JSON bytes.
// Record đếm một lần gọi LLM từ câu trả lời của hãng, dạng byte JSON.
func (t *Turn) Record(body []byte) { t.RecordWith(body, Opt{}) }

// RecordWith is Record with the provider, the model or a retry given by the caller.
// RecordWith là Record kèm hãng, model hay đánh dấu gọi lại do người gọi đưa vào.
func (t *Turn) RecordWith(body []byte, o Opt) {
	defer func() { _ = recover() }()
	p, m, c := Read(body, o.Provider)
	if o.Model != "" {
		m = o.Model
	}
	t.add(p, m, c, o.Retry, false)
}

// Count counts one LLM call from numbers read by hand; nil counts mean not measured. Input is billed at the normal price,
// without cache reads and writes.
// Count đếm một lần gọi LLM từ số tự đọc; counts nil nghĩa là không đo được. Input là đầu vào tính giá thường, không gồm đọc và ghi cache.
func (t *Turn) Count(provider, model string, c *Counts) { t.CountWith(provider, model, c, false) }

// CountWith is Count that can mark a retry.
// CountWith là Count có thể đánh dấu gọi lại.
func (t *Turn) CountWith(provider, model string, c *Counts, retry bool) {
	if c != nil {
		c = make5(c.Input, c.Output, c.CacheRead, c.CacheWrite, c.CacheWriteLong)
	}
	t.add(provider, model, c, retry, false)
}

// Fail counts one LLM call that failed (no answer, so no usage). Pass no error text.
// Fail đếm một lần gọi LLM bị lỗi. Không truyền chữ của lỗi.
func (t *Turn) Fail(provider, model string, retry bool) { t.add(provider, model, nil, retry, true) }

// FirstToken marks the first streamed piece of the answer; only the first mark counts.
// FirstToken đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.
func (t *Turn) FirstToken() {
	t.mu.Lock()
	defer t.mu.Unlock()
	if !t.hasTTFT {
		t.ttft, t.hasTTFT = time.Since(t.started), true
	}
}

// SetOutcome sets "error" or "timeout" when the turn did not end well.
// SetOutcome đặt "error" hay "timeout" khi lượt không kết thúc tốt.
func (t *Turn) SetOutcome(o string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.outcome = o
}

// End writes the line, once.
// End ghi dòng, một lần.
func (t *Turn) End() {
	defer func() { _ = recover() }()
	t.mu.Lock()
	if t.done {
		t.mu.Unlock()
		return
	}
	t.done = true
	elapsed := time.Since(t.started) // monotonic: time.Now keeps a monotonic reading
	outcome := t.outcome
	if outcome != "ok" && outcome != "timeout" {
		outcome = "error"
	}
	rnd := make([]byte, 8)
	_, _ = rand.Read(rnd)
	line := obj{"v": 1, "turnId": hex.EncodeToString(rnd), "at": t.started.UTC().Format("2006-01-02T15:04:05.000Z"),
		"durationMs": elapsed.Milliseconds(), "outcome": outcome, "env": t.meter.env}
	if t.hasTTFT {
		line["ttftMs"] = t.ttft.Milliseconds()
	}
	rows := make([]any, len(t.models))
	for k, s := range t.models {
		row := obj{"provider": k.provider, "model": k.model, "calls": s.Calls, "errors": s.Errors, "retries": s.Retries, "unmeasured": s.Unmeasured,
			"input": s.Input, "output": s.Output, "cacheRead": s.CacheRead, "cacheWrite": s.CacheWrite, "cacheWriteLong": s.CacheWriteLong}
		// every answered call lacked usage: the tokens are unknown, not zero
		// mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
		if s.Unmeasured > 0 && s.Calls-s.Errors == s.Unmeasured {
			for _, f := range []string{"input", "output", "cacheRead", "cacheWrite", "cacheWriteLong"} {
				row[f] = nil
			}
		}
		rows[s.order] = row
	}
	line["models"] = rows
	t.mu.Unlock()
	if b, err := json.Marshal(line); err == nil {
		t.meter.write(b)
	}
}

// Meter is where the lines go. env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off.
// AI_METER_URL and AI_METER_KEY also send each turn to an AI Worker board, in the background; call Close before the program ends.
// Meter là nơi ghi các dòng. env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt.
// AI_METER_URL và AI_METER_KEY gửi thêm từng lượt lên bảng AI Worker, ở nền; gọi Close trước khi chương trình kết thúc.
type Meter struct {
	path, env string
	off       bool
	sender    *sender
}

// New makes a meter; NewSending also sends to a board when url and key are given (the environment still wins).
// New tạo bộ đo; NewSending gửi thêm lên bảng khi có url và key (biến môi trường vẫn được ưu tiên).
func New(path, env string) *Meter { return NewSending(path, env, "", "") }

func NewSending(path, env, url, key string) *Meter {
	if v := os.Getenv("AI_METER_FILE"); v != "" {
		path = v
	}
	if v := os.Getenv("AI_METER_ENV"); v != "" {
		env = v
	}
	if env != "test" {
		env = "prod"
	}
	m := &Meter{path: path, env: env, off: os.Getenv("AI_METER_OFF") == "1"}
	if v := os.Getenv("AI_METER_URL"); v != "" {
		url = v
	}
	if v := os.Getenv("AI_METER_KEY"); v != "" {
		key = v
	}
	if url != "" && key != "" && !m.off && (strings.HasPrefix(url, "https://") || localRe.MatchString(url)) {
		m.sender = newSender(url, key)
	}
	return m
}

// Turn starts a user turn.
// Turn bắt đầu một lượt người dùng.
func (m *Meter) Turn() *Turn {
	return &Turn{meter: m, started: time.Now(), models: map[key]*slot{}, outcome: "ok"}
}

// Flush sends what is waiting now; Close also stops the background sender. Neither ever returns an error.
// Flush gửi những gì đang chờ ngay bây giờ; Close còn dừng phần gửi ở nền. Cả hai không bao giờ trả lỗi.
func (m *Meter) Flush() {
	if m.sender != nil {
		m.sender.flush()
	}
}

func (m *Meter) Close() {
	if m.sender != nil {
		m.sender.close()
	}
}

func (m *Meter) write(line []byte) {
	if m.off {
		return
	}
	if m.sender != nil {
		m.sender.add(line)
	}
	fileLock.Lock()
	defer fileLock.Unlock()
	f, err := os.OpenFile(m.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(line, '\n'))
}

// sending: batches in the background; a full queue drops the oldest turn, a failed send is tried once more, the project never waits
// gửi: các lô đi ở nền; hàng đợi đầy thì bỏ lượt cũ nhất, gửi lỗi thì thử lại một lần, dự án không bao giờ phải chờ
const (
	queueMax   = 1000
	batchTurns = 100
	batchBytes = 200 * 1024
)

type sender struct {
	url, key string
	client   http.Client
	mu, busy sync.Mutex
	queue    [][]byte
	retry    [][]byte
	stop     chan struct{}
	wake     chan struct{}
	once     sync.Once
}

func newSender(url, key string) *sender {
	// a redirect is not followed: Go keeps the key on a redirect to the same host, from https to plain http included
	// không theo chuyển hướng: Go giữ khoá khi chuyển hướng tới cùng máy, kể cả từ https sang http thường
	noRedirect := func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	s := &sender{url: url, key: key, client: http.Client{Timeout: 5 * time.Second, CheckRedirect: noRedirect}, stop: make(chan struct{}), wake: make(chan struct{}, 1)}
	go func() {
		tick := time.NewTicker(10 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-s.stop:
				return
			case <-tick.C:
			case <-s.wake:
			}
			s.flush()
		}
	}()
	return s
}

func (s *sender) add(line []byte) {
	s.mu.Lock()
	s.queue = append(s.queue, append([]byte(nil), line...))
	if len(s.queue) > queueMax {
		s.queue = s.queue[len(s.queue)-queueMax:]
	}
	full := len(s.queue) >= batchTurns
	s.mu.Unlock()
	if full {
		select {
		case s.wake <- struct{}{}:
		default:
		}
	}
}

func (s *sender) flush() {
	defer func() { _ = recover() }()
	s.busy.Lock()
	defer s.busy.Unlock()
	for {
		s.mu.Lock()
		again := len(s.retry) > 0
		batch, size := s.retry, 0
		s.retry = nil
		for len(s.queue) > 0 && len(batch) < batchTurns && size < batchBytes {
			size += len(s.queue[0])
			batch = append(batch, s.queue[0])
			s.queue = s.queue[1:]
		}
		s.mu.Unlock()
		if len(batch) == 0 {
			return
		}
		body := append([]byte(`{"turns":[`), bytes.Join(batch, []byte(","))...)
		body = append(body, ']', '}')
		req, err := http.NewRequest(http.MethodPost, s.url, bytes.NewReader(body))
		ok := err == nil
		if ok {
			req.Header.Set("Authorization", "Bearer "+s.key)
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("User-Agent", "ai-meter/1")
			res, err := s.client.Do(req)
			ok = err == nil && res.StatusCode < 500 && res.StatusCode != 429
			if res != nil {
				res.Body.Close()
			}
		}
		if !ok {
			// tried once more at the next send, then let go; the file still has every turn
			// thử lại một lần ở lần gửi sau, rồi bỏ; file vẫn còn đủ mọi lượt
			if !again {
				s.mu.Lock()
				s.retry = batch
				s.mu.Unlock()
			}
			return
		}
	}
}

func (s *sender) close() {
	s.once.Do(func() {
		close(s.stop)
		s.flush()
	})
}
