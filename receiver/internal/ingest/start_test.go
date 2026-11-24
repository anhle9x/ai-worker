package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"aiworker/receiver/internal/devicekey"
)

// enrolled gives a computer enrolled through h and its own key.
// enrolled cho một máy đã ghi danh qua h và khoá riêng của nó.
func enrolled(t *testing.T, h *harness, device string) string {
	t.Helper()
	status, ans := h.send("shared-test-key-0123456789", packet(device, map[string]any{"full": true, "hours": map[string]any{"ledger": map[string]any{hourNow(): map[string]any{"usdMicro": 7}}}}))
	key, _ := ans["deviceKey"].(string)
	if status != 200 || key == "" {
		t.Fatalf("enrol: %d %v", status, ans)
	}
	return key
}

// sendRaw posts a packet to front and gives the status, the body and the Retry-After header.
// sendRaw gửi một gói tới front và cho mã trạng thái, thân và header Retry-After.
func sendRaw(t *testing.T, front, key string, p map[string]any) (int, map[string]any, string) {
	t.Helper()
	b, _ := json.Marshal(p)
	req, _ := http.NewRequest(http.MethodPost, front+"/ingest", bytes.NewReader(b))
	req.Header.Set("Authorization", "Bearer "+key)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return resp.StatusCode, out, resp.Header.Get("Retry-After")
}

// TestComeBackWhileBooksLoad: while the books load, a computer whose book is not read yet is told to come back in 15 to 45 seconds and
// its book is not asked of Python alone; once loaded, the same send is taken.
// TestComeBackWhileBooksLoad: trong lúc nạp sổ, máy chưa có sổ được bảo quay lại sau 15 tới 45 giây và sổ của nó không bị hỏi riêng
// Python; nạp xong thì cùng lần gửi đó được nhận.
func TestComeBackWhileBooksLoad(t *testing.T) {
	h := start(t)
	device := "device-gostart"
	key := enrolled(t, h, device)
	var asked atomic.Int32
	target, _ := url.Parse(h.python)
	proxy := &httputil.ReverseProxy{Rewrite: func(pr *httputil.ProxyRequest) { pr.SetURL(target) }}
	py := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Query().Get("device") == device {
			asked.Add(1)
		}
		proxy.ServeHTTP(w, req)
	}))
	t.Cleanup(py.Close)
	secrets, err := devicekey.Load(h.secrets)
	if err != nil {
		t.Fatal(err)
	}
	r := New(py.URL, secrets, 0)
	if err := r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	front := httptest.NewServer(r)
	t.Cleanup(front.Close)
	r.loading.Store(true)
	status, ans, retry := sendRaw(t, front.URL, key, packet(device, nil))
	n, _ := strconv.Atoi(retry)
	if status != 503 || ans["error"] != "starting" || n < 15 || n > 45 {
		t.Fatalf("while loading: %d %v Retry-After %q", status, ans, retry)
	}
	if asked.Load() != 0 || r.entry(device).loaded {
		t.Fatalf("the book was read alone while the pages load: %d asks", asked.Load())
	}
	r.loading.Store(false)
	if status, ans, _ := sendRaw(t, front.URL, key, packet(device, nil)); status != 200 {
		t.Fatalf("after loading: %d %v", status, ans)
	}
}

// TestPeopleAndBatchesBeforeTheBooks: Start asks for the table of people and sends the waiting rows while the pages of books are still
// being read, so the boards have rows and Python gets the sends at once after a restart.
// TestPeopleAndBatchesBeforeTheBooks: Start hỏi bảng người và gửi các dòng đang chờ trong lúc các trang sổ vẫn đang được đọc, để các
// bảng có dòng và Python nhận các lần gửi ngay sau khi khởi động lại.
func TestPeopleAndBatchesBeforeTheBooks(t *testing.T) {
	h := start(t)
	device := "device-gofirst"
	key := enrolled(t, h, device)
	var people, rows atomic.Int32
	release := make(chan struct{})
	target, _ := url.Parse(h.python)
	proxy := &httputil.ReverseProxy{Rewrite: func(pr *httputil.ProxyRequest) { pr.SetURL(target) }}
	py := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		switch {
		case req.URL.Path == "/internal/devices" && req.URL.Query().Get("limit") != "":
			<-release
		case strings.HasPrefix(req.URL.Path, "/internal/people"):
			people.Add(1)
		case req.URL.Path == "/internal/rows":
			rows.Add(1)
		}
		proxy.ServeHTTP(w, req)
	}))
	t.Cleanup(py.Close)
	secrets, err := devicekey.Load(h.secrets)
	if err != nil {
		t.Fatal(err)
	}
	r := New(py.URL, secrets, 0)
	if err := r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	front := httptest.NewServer(r)
	t.Cleanup(front.Close)
	// a send taken before the start, its book read alone, waits to go to Python
	// một lần gửi được nhận trước khi chạy, sổ được đọc riêng, chờ đi tới Python
	if status, ans, _ := sendRaw(t, front.URL, key, packet(device, nil)); status != 200 {
		t.Fatalf("send: %d %v", status, ans)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { r.Start(ctx); close(done) }()
	t.Cleanup(func() {
		cancel()
		select {
		case <-release:
		default:
			close(release)
		}
		<-done
	})
	until := time.Now().Add(10 * time.Second)
	for (people.Load() == 0 || rows.Load() == 0 || r.waitingCount() != 0) && time.Now().Before(until) {
		time.Sleep(20 * time.Millisecond)
	}
	if people.Load() == 0 || rows.Load() == 0 || r.waitingCount() != 0 {
		t.Fatalf("while the books load: %d asks for people, %d batches, %d computers waiting", people.Load(), rows.Load(), r.waitingCount())
	}
	if !r.loading.Load() {
		t.Fatal("the books are said loaded while the page is held")
	}
	close(release)
	until = time.Now().Add(10 * time.Second)
	for r.loading.Load() && time.Now().Before(until) {
		time.Sleep(20 * time.Millisecond)
	}
	if r.loading.Load() {
		t.Fatal("still loading after the pages came")
	}
}
