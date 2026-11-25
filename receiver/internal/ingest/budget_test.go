package ingest

import (
	"fmt"
	"net/http"
	"strconv"
	"testing"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
)

// TestABudgetTakesWhatFits: what fits is taken, what does not is left, a row that grows is counted whatever the ceiling, and no budget takes all.
// TestABudgetTakesWhatFits: phần vừa thì được lấy, phần không vừa thì để lại, dòng lớn lên được đếm bất kể trần, và không có ngân sách thì lấy hết.
func TestABudgetTakesWhatFits(t *testing.T) {
	b := NewBudget(100)
	if !b.Take(60) || b.Take(50) || b.Used() != 60 || b.Full() {
		t.Fatalf("take: used %d", b.Used())
	}
	b.Add(40)
	if !b.Full() || b.Take(1) {
		t.Fatalf("full at %d", b.Used())
	}
	b.Add(-100)
	if b.Used() != 0 || b.Full() {
		t.Fatalf("given back: %d", b.Used())
	}
	var none *Budget
	if !none.Take(1<<40) || none.Full() || none.Used() != 0 {
		t.Fatal("a nil budget refuses")
	}
	if !NewBudget(0).Take(1 << 40) {
		t.Fatal("no ceiling refuses")
	}
	for i := 0; i < 200; i++ {
		if n, _ := strconv.Atoi(RetryAfter(5, 15)); n < 5 || n > 15 {
			t.Fatalf("Retry-After %d", n)
		}
	}
}

// TestAWholeBookWaitsEncoded: a whole book waits encoded, not as objects, and hours sent after it are still put on it exactly as before.
// TestAWholeBookWaitsEncoded: một sổ đủ chờ ở dạng đã mã hoá, không phải đối tượng, và các giờ gửi sau vẫn được đặt lên nó đúng như trước.
func TestAWholeBookWaitsEncoded(t *testing.T) {
	parse := func(s string) *pyjson.Object {
		v, err := pyjson.Parse([]byte(s))
		if err != nil {
			t.Fatal(err)
		}
		return v.(*pyjson.Object)
	}
	book := parse(`{"device": "device-a", "updatedAt": 1, "ledger": {"100": {"usdMicro": 5}, "101": {"usdMicro": 7}}, "tasks": {}}`)
	later := parse(`{"device": "device-a", "updatedAt": 2, "ledger": {"101": {"usdMicro": 9}}, "tasks": {}}`)
	var p waiting
	p.add(book, "full", "203.0.113.9", 1, nil)
	if p.d != nil || p.enc == nil || p.size != int64(len(pyjson.Encode(book))) {
		t.Fatalf("a whole book is held as objects: d %v, %d bytes", p.d != nil, len(p.enc))
	}
	p.add(later, "hours", "203.0.113.9", 2, nil)
	want := withHours(later, clean.MergeHours(book, later))
	if p.kind != "full" || p.d != nil || string(pyjson.Encode(p.row())) != string(pyjson.Encode(want)) {
		t.Fatalf("merged %s\n want %s", pyjson.Encode(p.row()), pyjson.Encode(want))
	}
	// changed hours alone stay objects, to be put together with the next ones
	// các giờ đã đổi đứng riêng thì vẫn là đối tượng, để gộp với các lần sau
	var q waiting
	q.add(later, "hours", "203.0.113.9", 2, nil)
	if q.d == nil || q.enc != nil {
		t.Fatal("changed hours are encoded")
	}
}

// TestBusyWhenTheMemoryIsSpent: past the budget of bodies being read, or near the memory limit, a send is answered busy before its body
// is read; past the budget of waiting rows, a computer not waiting yet is answered busy and one already waiting is still taken.
// TestBusyWhenTheMemoryIsSpent: quá ngân sách thân đang đọc, hay gần chạm giới hạn bộ nhớ, lần gửi được trả bận trước khi đọc thân; quá
// ngân sách dòng chờ, máy chưa chờ được trả bận còn máy đang chờ vẫn được nhận.
func TestBusyWhenTheMemoryIsSpent(t *testing.T) {
	h := start(t)
	a, b := "device-gobudgeta", "device-gobudgetb"
	keyA, keyB := enrolled(t, h, a), enrolled(t, h, b)
	h.flush()
	busy := func(key, device, why string) {
		t.Helper()
		status, ans, retry := sendRaw(t, h.front.URL, key, packet(device, nil))
		n, _ := strconv.Atoi(retry)
		if status != http.StatusServiceUnavailable || ans["error"] != "busy" || n < 5 || n > 15 {
			t.Fatalf("%s: %d %v Retry-After %q", why, status, ans, retry)
		}
	}
	h.r.Reading = NewBudget(1)
	busy(keyA, a, "bodies being read")
	h.r.Reading = nil
	h.r.Overloaded.Store(true)
	busy(keyA, a, "near the memory limit")
	h.r.Overloaded.Store(false)
	h.r.Holding = NewBudget(1)
	if status, ans, _ := sendRaw(t, h.front.URL, keyA, packet(a, nil)); status != 200 {
		t.Fatalf("the first row: %d %v", status, ans)
	}
	busy(keyB, b, "rows waiting")
	if status, ans, _ := sendRaw(t, h.front.URL, keyA, packet(a, nil)); status != 200 {
		t.Fatalf("a computer already waiting: %d %v", status, ans)
	}
	used := h.r.Holding.Used()
	h.flush()
	if h.r.Holding.Used() != 0 || used <= 0 {
		t.Fatal(fmt.Sprintf("held %d before the batch, %d after", used, h.r.Holding.Used()))
	}
}
