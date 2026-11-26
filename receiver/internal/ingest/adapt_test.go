package ingest

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"aiworker/receiver/internal/pyjson"
)

// slowPages is a Python whose pages of books fail the first fail times, then take wait each; it answers two books in pages of limit.
// slowPages là một Python có các trang sổ hỏng fail lần đầu, rồi mỗi trang mất wait; nó trả hai sổ theo các trang cỡ limit.
type slowPages struct {
	mu     sync.Mutex
	fail   int
	wait   time.Duration
	limits []int
	rows   time.Duration
	sizes  []int
}

func (f *slowPages) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	switch {
	case strings.HasPrefix(req.URL.Path, "/internal/policy"):
		_, _ = io.WriteString(w, `{"proto": 2, "seq": 1, "boot": "p", "ingestBurst": 20, "ingestPerSecond": 1, "tzHours": 7, "minGapMs": 2000}`)
	case req.URL.Path == "/internal/devices":
		limit, _ := strconv.Atoi(req.URL.Query().Get("limit"))
		f.mu.Lock()
		f.limits = append(f.limits, limit)
		failing := f.fail > 0
		f.fail--
		wait := f.wait
		f.mu.Unlock()
		if failing {
			http.Error(w, "busy", http.StatusServiceUnavailable)
			return
		}
		time.Sleep(wait)
		if req.URL.Query().Get("after") == "" {
			_, _ = io.WriteString(w, `{"devices": [{"device": "device-page001", "updatedAt": 1}], "next": "device-page001"}`)
			return
		}
		_, _ = io.WriteString(w, `{"devices": [{"device": "device-page002", "updatedAt": 1}], "next": null}`)
	case req.URL.Path == "/internal/rows":
		b, _ := io.ReadAll(req.Body)
		v, _ := pyjson.Parse(b)
		f.mu.Lock()
		f.sizes = append(f.sizes, len(get(v, "rows").([]pyjson.Value)))
		wait := f.rows
		f.mu.Unlock()
		time.Sleep(wait)
		fmt.Fprintf(w, `{"ok": true, "seq": %d, "needFull": [], "unknown": [], "incomplete": [], "bad": []}`, get(v, "seq").(pyjson.Number).I)
	default:
		http.Error(w, "away", http.StatusServiceUnavailable)
	}
}

func quick() timing {
	return timing{call: time.Second, page: time.Second, batch: time.Second, slow: 40 * time.Millisecond, loadFor: time.Second, pause: time.Millisecond}
}

// TestAFailedPageIsAskedAgain: a page of books that fails is asked again, smaller, and the load goes on instead of leaving every book
// to be read alone.
// TestAFailedPageIsAskedAgain: một trang sổ hỏng được hỏi lại, nhỏ hơn, và việc nạp tiếp tục thay vì để mọi sổ phải đọc riêng.
func TestAFailedPageIsAskedAgain(t *testing.T) {
	f := &slowPages{fail: 2}
	r, _ := receiverWith(t, f)
	r.timing = quick()
	n, err := r.LoadBooks(context.Background())
	if err != nil || n != 2 {
		t.Fatalf("loaded %d: %v", n, err)
	}
	if len(f.limits) != 4 || f.limits[0] != devicesPage || f.limits[1] != devicesPage/2 || f.limits[2] != devicesPage/4 {
		t.Fatalf("the pages asked: %v", f.limits)
	}
}

// TestPagesKeepFailingThenTheLoadStops: pages failing for timing.loadFor stop the load, so the rest are read when needed; not before.
// TestPagesKeepFailingThenTheLoadStops: các trang hỏng suốt timing.loadFor thì thôi nạp, để phần còn lại được đọc khi cần; không sớm hơn.
func TestPagesKeepFailingThenTheLoadStops(t *testing.T) {
	f := &slowPages{fail: 1 << 30}
	r, _ := receiverWith(t, f)
	r.timing = quick()
	r.timing.loadFor = 150 * time.Millisecond
	began := time.Now()
	if _, err := r.LoadBooks(context.Background()); err == nil {
		t.Fatal("no error after pages kept failing")
	}
	if took := time.Since(began); took < 150*time.Millisecond || took > 2*time.Second {
		t.Fatalf("stopped after %s", took)
	}
	if len(f.limits) < 3 || f.limits[len(f.limits)-1] != minPage {
		t.Fatalf("the pages asked: %v", f.limits)
	}
}

// TestASlowPageMakesTheNextSmaller: a page slower than timing.slow halves the next one, a quick one doubles it back.
// TestASlowPageMakesTheNextSmaller: một trang chậm hơn timing.slow làm trang sau nhỏ một nửa, trang nhanh thì gấp đôi trở lại.
func TestASlowPageMakesTheNextSmaller(t *testing.T) {
	f := &slowPages{wait: 60 * time.Millisecond}
	r, _ := receiverWith(t, f)
	r.timing = quick()
	if n, err := r.LoadBooks(context.Background()); err != nil || n != 2 {
		t.Fatalf("loaded %d: %v", n, err)
	}
	if len(f.limits) != 2 || f.limits[1] != devicesPage/2 {
		t.Fatalf("the pages asked: %v", f.limits)
	}
	s := newSizer(minPage, devicesPage)
	s.took(time.Second, 40*time.Millisecond, true)
	s.took(time.Millisecond, 40*time.Millisecond, true)
	if s.n != devicesPage {
		t.Fatalf("after a quick page: %d", s.n)
	}
}

// TestAPageHasALongerDeadlineThanACall: a page of books may take longer than the deadline of a call (the policy, one book); the
// batches too.
// TestAPageHasALongerDeadlineThanACall: một trang sổ được phép lâu hơn hạn của một lời gọi (chính sách, một sổ); các lô cũng vậy.
func TestAPageHasALongerDeadlineThanACall(t *testing.T) {
	f := &slowPages{wait: 150 * time.Millisecond, rows: 150 * time.Millisecond}
	r, keys := receiverWith(t, f)
	r.timing = quick()
	r.timing.call, r.timing.loadFor = 50*time.Millisecond, 0
	if n, err := r.LoadBooks(context.Background()); err != nil || n != 2 {
		t.Fatalf("loaded %d: %v", n, err)
	}
	device := "device-page003"
	r.entry(device).loaded = true
	body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "working": 1, "full": true, "hours": {"ledger": {"%d": {"usdMicro": 5}}}}`, device, r.Now(), r.Now()/3_600_000)
	if code := sendOwn(r, keys.key(device, r.Now()/1000), []byte(body)); code != 200 {
		t.Fatalf("send: %d", code)
	}
	if n, err := r.Flush(context.Background()); err != nil || n != 1 {
		t.Fatalf("batch: %d %v", n, err)
	}
	if err := r.getJSON(context.Background(), "/internal/devices?limit=1&after=", &struct{}{}); err == nil {
		t.Fatal("a call past timing.call did not fail")
	}
}

// TestASlowBatchMakesTheNextSmaller: a batch slower than timing.slow halves the rows of the next new one, down to minBatchRows; a quick
// one doubles them back. A batch sent again keeps its rows.
// TestASlowBatchMakesTheNextSmaller: một lô chậm hơn timing.slow làm lô mới sau ít dòng đi một nửa, tới minBatchRows; lô nhanh thì gấp
// đôi trở lại. Lô gửi lại giữ nguyên các dòng của nó.
func TestASlowBatchMakesTheNextSmaller(t *testing.T) {
	f := &slowPages{rows: 60 * time.Millisecond}
	r, keys := receiverWith(t, f)
	r.timing = quick()
	r.rows = newSizer(2, 8)
	for i := 0; i < 20; i++ {
		device := fmt.Sprintf("device-batch%03d", i)
		r.entry(device).loaded = true
		body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "working": 1, "full": true, "hours": {"ledger": {"%d": {"usdMicro": 5}}}}`, device, r.Now(), r.Now()/3_600_000)
		if code := sendOwn(r, keys.key(device, r.Now()/1000), []byte(body)); code != 200 {
			t.Fatalf("send %d: %d", i, code)
		}
	}
	for i := 0; i < 3; i++ {
		if _, err := r.Flush(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	f.mu.Lock()
	f.rows = 0
	f.mu.Unlock()
	if _, err := r.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := r.Flush(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := fmt.Sprint(f.sizes); got != "[8 4 2 2 4]" {
		t.Fatalf("rows a batch: %s", got)
	}
}

// TestAPageOlderThanABatchIsNotLoaded: a batch written while a page of books is on its way leaves that page's book of its computers
// older than Python's: the book is read again instead (run C48 lost money for 33 people this way).
// TestAPageOlderThanABatchIsNotLoaded: một lô được ghi trong lúc một trang sổ đang về làm sổ các máy của lô trong trang đó cũ hơn sổ
// của Python: sổ được đọc lại thay vì nạp (lượt C48 đã mất tiền của 33 người theo cách này).
func TestAPageOlderThanABatchIsNotLoaded(t *testing.T) {
	asked, release := make(chan struct{}), make(chan struct{})
	device := "device-older01"
	inner := &slowPages{}
	py := http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/internal/devices" && req.URL.Query().Get("limit") != "" {
			close(asked)
			<-release
			fmt.Fprintf(w, `{"devices": [{"device": %q, "updatedAt": 1}], "next": null}`, device)
			return
		}
		inner.ServeHTTP(w, req)
	})
	r, keys := receiverWith(t, py)
	r.timing = quick()
	e := r.entry(device)
	e.loaded = true
	body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "working": 1, "full": true, "hours": {"ledger": {"%d": {"usdMicro": 5}}}}`,
		device, r.Now(), r.Now()/3_600_000)
	if code := sendOwn(r, keys.key(device, r.Now()/1000), []byte(body)); code != 200 {
		t.Fatalf("send: %d", code)
	}
	// Python started again: every book is dropped and read from pages (RefreshPolicy with reset)
	// Python khởi động lại: mọi sổ bị bỏ và đọc lại từ các trang (RefreshPolicy khi reset)
	e.mu.Lock()
	e.loaded, e.rec = false, nil
	e.mu.Unlock()
	done := make(chan error, 1)
	go func() { _, err := r.LoadBooks(context.Background()); done <- err }()
	<-asked
	if n, err := r.Flush(context.Background()); err != nil || n != 1 {
		t.Fatalf("batch: %d %v", n, err)
	}
	close(release)
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	r.mu.Lock()
	stale := r.stale[device]
	r.mu.Unlock()
	if e.loaded || !stale {
		t.Fatalf("the book of the page older than the batch was loaded: loaded %v, stale %v", e.loaded, stale)
	}
}
