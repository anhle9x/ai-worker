package ingest

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"testing"

	"aiworker/receiver/internal/devicekey"
	"aiworker/receiver/internal/pyjson"
)

// fakePython answers the internal paths as the Python server does, and can be away: then every batch gets 503.
// fakePython trả lời các đường nội bộ như máy chủ Python, và có thể vắng mặt: khi đó mọi lô nhận 503.
type fakePython struct {
	mu   sync.Mutex
	away bool
	// drop: the rows are not kept, for measuring this side alone
	// drop: không giữ các dòng, để đo riêng bên này
	drop bool
	seq  int64
	rows []pyjson.Value
}

func (f *fakePython) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch {
	case strings.HasPrefix(req.URL.Path, "/internal/policy"):
		_, _ = io.WriteString(w, `{"proto": 2, "seq": 1, "boot": "p", "ingestBurst": 20, "ingestPerSecond": 1, "tzHours": 7, "minGapMs": 2000}`)
	case strings.HasPrefix(req.URL.Path, "/internal/devices"):
		_, _ = io.WriteString(w, `{"devices": [], "next": null}`)
	case req.URL.Path == "/internal/rows" && !f.away:
		b, _ := io.ReadAll(req.Body)
		v, err := pyjson.Parse(b)
		if err != nil {
			http.Error(w, "bad", 400)
			return
		}
		seq := get(v, "seq").(pyjson.Number).I
		if seq > f.seq {
			f.seq = seq
			if !f.drop {
				f.rows = append(f.rows, get(v, "rows").([]pyjson.Value)...)
			}
		}
		fmt.Fprintf(w, `{"ok": true, "seq": %d, "needFull": [], "unknown": [], "incomplete": [], "bad": []}`, seq)
	default:
		http.Error(w, "away", http.StatusServiceUnavailable)
	}
}

// ownKeys writes a file of secrets and signs keys with it, as Python would.
// ownKeys ghi một file bí mật và ký khoá bằng nó, như Python sẽ làm.
type ownKeys struct {
	path   string
	secret []byte
}

func newOwnKeys(t testing.TB) *ownKeys {
	secret := []byte("0123456789abcdef0123456789abcdef")
	path := filepath.Join(t.TempDir(), "receiver-secrets.json")
	file := fmt.Sprintf(`[{"kid": "k1", "alg": "HS256", "org": "o1", "secret": %q, "since": 0}, {"kid": "internal", "alg": "internal", "secret": "inside"}]`,
		base64.RawURLEncoding.EncodeToString(secret))
	if err := os.WriteFile(path, []byte(file), 0o600); err != nil {
		t.Fatal(err)
	}
	return &ownKeys{path, secret}
}

func (k *ownKeys) key(device string, iat int64) string {
	body := strings.Join([]string{devicekey.Prefix, "k1", "o1", "pid" + device[7:], "rk1", device, strconv.FormatInt(iat, 10)}, ".")
	mac := hmac.New(sha256.New, k.secret)
	mac.Write([]byte(body))
	return body + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func receiverWith(t testing.TB, python http.Handler) (*Receiver, *ownKeys) {
	keys := newOwnKeys(t)
	secrets, err := devicekey.Load(keys.path)
	if err != nil {
		t.Fatal(err)
	}
	fake := httptest.NewServer(python)
	t.Cleanup(fake.Close)
	r := New(fake.URL, secrets, 0)
	if err := r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	return r, keys
}

func sendOwn(r *Receiver, key string, body []byte) int {
	req := httptest.NewRequest(http.MethodPost, "/ingest", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+key)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w.Code
}

// TestPythonAwayAMinute: Python does not take a batch for a minute while every computer keeps sending; every send is still answered
// 200, at most one row per computer waits (and one batch on its way), and when Python is back it writes each computer's newest hours.
// TestPythonAwayAMinute: Python không nhận lô nào trong một phút trong khi mọi máy vẫn gửi; mọi lần gửi vẫn được trả lời 200, mỗi máy
// chờ nhiều nhất một dòng (cộng một lô đang đi), và khi Python quay lại nó ghi đúng các giờ mới nhất của từng máy.
func TestPythonAwayAMinute(t *testing.T) {
	python := &fakePython{}
	r, keys := receiverWith(t, python)
	const computers = 200
	start := r.Now()
	hour := strconv.FormatInt(start/3_600_000, 10)
	send := func(i, beat int, full bool) int {
		device := fmt.Sprintf("device-away%03d", i)
		extra := ""
		if full {
			extra = `"full": true, `
		}
		body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "working": 1, %s"hours": {"ledger": {%q: {"usdMicro": %d}}}}`,
			device, r.Now(), extra, hour, beat+1)
		return sendOwn(r, keys.key(device, start/1000), []byte(body))
	}
	for i := 0; i < computers; i++ {
		e := r.entry(fmt.Sprintf("device-away%03d", i))
		e.loaded = true
		if code := send(i, 0, true); code != 200 {
			t.Fatalf("first send: %d", code)
		}
	}
	python.mu.Lock()
	python.away = true
	python.mu.Unlock()
	for beat := 1; beat <= 12; beat++ {
		now := start + int64(beat)*5000
		r.Now = func() int64 { return now }
		for i := 0; i < computers; i++ {
			if code := send(i, beat, false); code != 200 {
				t.Fatalf("beat %d computer %d: %d", beat, i, code)
			}
		}
		if _, err := r.Flush(context.Background()); err == nil {
			t.Fatal("a batch went while Python was away")
		}
		if r.waitingCount() > computers || r.queued() > 2*computers {
			t.Fatalf("beat %d: %d computers waiting, %d rows", beat, r.waitingCount(), r.queued())
		}
	}
	python.mu.Lock()
	python.away = false
	python.mu.Unlock()
	for {
		n, err := r.Flush(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if n == 0 {
			break
		}
	}
	if r.queued() != 0 {
		t.Fatalf("%d rows left", r.queued())
	}
	// the newest row of each computer holds the newest value of the hour
	// dòng mới nhất của mỗi máy mang giá trị mới nhất của giờ đó
	newest := map[string]string{}
	for _, row := range python.rows {
		device := get(row, "k").([]pyjson.Value)[1].(string)
		newest[device] = string(pyjson.Encode(get(get(get(row, "v"), "hours"), "ledger")))
	}
	if len(newest) != computers || len(python.rows) > 2*computers {
		t.Fatalf("%d computers in %d rows", len(newest), len(python.rows))
	}
	for device, ledger := range newest {
		if !strings.Contains(ledger, `"usdMicro": 13`) {
			t.Fatalf("%s: %s", device, ledger)
		}
	}
}

// TestMemoryOfManyComputers measures what this side holds for many computers, each with a busy day of hours: RECEIVER_MEASURE=100000
// go test ./internal/ingest -run TestMemoryOfManyComputers -v. Skipped without it.
// TestMemoryOfManyComputers đo thứ bên này giữ cho nhiều máy, mỗi máy một ngày giờ bận rộn: RECEIVER_MEASURE=100000
// go test ./internal/ingest -run TestMemoryOfManyComputers -v. Bỏ qua khi không đặt.
func TestMemoryOfManyComputers(t *testing.T) {
	n, _ := strconv.Atoi(os.Getenv("RECEIVER_MEASURE"))
	if n <= 0 {
		t.Skip("set RECEIVER_MEASURE to the number of computers")
	}
	r, keys := receiverWith(t, &fakePython{drop: true})
	// the last minute of the local day: every computer holds all 24 hours of it, the most this side holds
	// phút cuối của ngày địa phương: mỗi máy giữ đủ 24 giờ của ngày đó, nhiều nhất bên này giữ
	first := r.today()
	start := (first+24)*3_600_000 - 60_000
	r.Now = func() int64 { return start }
	top := first + 23
	var before runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&before)
	for i := 0; i < n; i++ {
		device := fmt.Sprintf("device-many%06d", i)
		r.entry(device).loaded = true
		var hours []string
		for h := first; h <= top; h++ {
			hours = append(hours, fmt.Sprintf(`%q: {"usdMicro": %d, "input": 1200, "output": 300, "cacheRead": 5000}`, strconv.FormatInt(h, 10), 1000+i))
		}
		body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "openSessions": 2, "working": 1, "models": {"claude-sonnet-5-5": 3},
			"quota": {"readAt": %d, "windows": [{"kind": "five_hour", "pct": 40}]}, "full": true,
			"hours": {"ledger": {%s}, "tasks": {%q: {"gemini": 1}}}}`, device, start, start, strings.Join(hours, ", "), strconv.FormatInt(top, 10))
		if code := sendOwn(r, keys.key(device, start/1000), []byte(body)); code != 200 {
			t.Fatalf("%s: %d", device, code)
		}
		if i%5000 == 4999 {
			// Python takes the rows, as it does every few seconds
			// Python nhận các dòng, như nó làm mỗi vài giây
			for m, _ := r.Flush(context.Background()); m > 0; m, _ = r.Flush(context.Background()) {
			}
		}
	}
	for m, _ := r.Flush(context.Background()); m > 0; m, _ = r.Flush(context.Background()) {
	}
	var after runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&after)
	// r is still in use here, so the collector cannot take what it holds before it is measured
	// r vẫn đang được dùng ở đây, nên bộ gom rác không lấy được thứ nó giữ trước khi đo
	runtime.KeepAlive(r)
	held := float64(after.HeapAlloc-before.HeapAlloc) / 1e6
	if r.waitingCount() != 0 || len(r.entries) != n {
		t.Fatalf("%d waiting, %d held", r.waitingCount(), len(r.entries))
	}
	b, _ := json.Marshal(map[string]any{"computers": n, "hoursEach": top - first + 1, "heapMB": int(held), "kbPerComputer": held * 1000 / float64(n),
		"sysMB": after.Sys / 1e6})
	t.Logf("%s", b)
}
