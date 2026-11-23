package ingest

import (
	"fmt"
	"math/rand"
	"sort"
	"strings"
	"testing"
	"time"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
)

func cleaned(t *testing.T, text string) *pyjson.Object {
	t.Helper()
	v, err := pyjson.Parse([]byte(text))
	if err != nil {
		t.Fatal(err)
	}
	d := clean.Payload(v, 1_791_165_600)
	if d == nil {
		t.Fatalf("not cleaned: %s", text)
	}
	return d
}

func ledgerOf(t *testing.T, d *pyjson.Object) string {
	t.Helper()
	x, _ := d.Get("ledger")
	return string(pyjson.Encode(stripOrder(x)))
}

// TestRowsOfOneComputerPutTogether: the sends of one computer between two batches wait as one row that Python writes as it would have
// written them one by one: the later value of an hour wins, an empty hour still removes it, hours on a whole book go on that book, and the
// records of work handed to helpers of every send are kept.
// TestRowsOfOneComputerPutTogether: các lần gửi của một máy giữa hai lô chờ thành một dòng mà Python ghi như đã ghi từng lần một: giá trị
// sau của một giờ thắng, giờ rỗng vẫn xoá giờ đó, các giờ trên một sổ đủ thì đặt lên sổ đó, và biên bản giao việc của mọi lần gửi được giữ.
func TestRowsOfOneComputerPutTogether(t *testing.T) {
	const base = `"device": "device-q1", "updatedAt": 1791165600000`
	p := &waiting{}
	p.add(cleaned(t, `{"v": 2, `+base+`, "hours": {"ledger": {"497546": {"usdMicro": 1}, "497545": {"usdMicro": 9}}}}`), "hours", "a", 1, []pyjson.Value{"r1"})
	p.add(cleaned(t, `{"v": 2, `+base+`, "working": 1, "hours": {"ledger": {"497546": {"usdMicro": 2}, "497545": {}}}}`), "hours", "b", 2, nil)
	if p.kind != "hours" || p.ip != "b" || p.at != 2 {
		t.Fatalf("kind %s, ip %s, at %d", p.kind, p.ip, p.at)
	}
	if got := ledgerOf(t, p.d); got != `{"497545": {}, "497546": {"usd": 2e-06, "usdMicro": 2}}` {
		t.Fatalf("hours put together: %s", got)
	}
	if w, _ := p.d.Get("working"); !pyjson.Equal(w, pyjson.IntN(1)) {
		t.Fatalf("the newest state: %v", w)
	}
	// a send whose numbers are not written only adds its records
	// lần gửi có số liệu không được ghi thì chỉ thêm biên bản của nó
	p.add(cleaned(t, `{"v": 2, `+base+`}`), "delegations", "c", 3, []pyjson.Value{"r2"})
	if p.kind != "hours" || len(p.delegations) != 2 {
		t.Fatalf("after delegations: %s, %d records", p.kind, len(p.delegations))
	}
	// a whole book replaces what waited; changed hours after it go on that book, the empty ones gone
	// một sổ đủ thay thứ đang chờ; các giờ đã đổi sau nó được đặt lên sổ đó, giờ rỗng thì mất
	p.add(cleaned(t, `{"v": 2, `+base+`, "full": true, "hours": {"ledger": {"497540": {"usdMicro": 5}, "497541": {"usdMicro": 6}}}}`), "full", "d", 4, nil)
	p.add(cleaned(t, `{"v": 2, `+base+`, "hours": {"ledger": {"497541": {}, "497547": {"usdMicro": 7}}}}`), "hours", "e", 5, nil)
	if p.kind != "full" {
		t.Fatalf("kind %s", p.kind)
	}
	if got := ledgerOf(t, p.d); got != `{"497540": {"usd": 5e-06, "usdMicro": 5}, "497547": {"usd": 7e-06, "usdMicro": 7}}` {
		t.Fatalf("hours on the whole book: %s", got)
	}
	// only records, with nothing waiting: a row of records alone
	// chỉ có biên bản, không có gì đang chờ: một dòng chỉ có biên bản
	q := &waiting{}
	q.add(cleaned(t, `{"v": 1, `+base+`}`), "delegations", "f", 6, []pyjson.Value{"r3"})
	q.add(cleaned(t, `{"v": 2, `+base+`, "hours": {"ledger": {"497546": {"usdMicro": 3}}}}`), "hours", "g", 7, nil)
	if q.kind != "hours" || len(q.delegations) != 1 {
		t.Fatalf("records then hours: %s, %d records", q.kind, len(q.delegations))
	}
}

// TestBatchesGoInTheOrderOfTheComputers: at the start of a beat the computers waiting are sorted by id, so the batches cover ranges of
// ids; a computer that comes after that waits behind them, even with a smaller id.
// TestBatchesGoInTheOrderOfTheComputers: ở đầu một nhịp các máy đang chờ được sắp theo mã, nên các lô phủ những dải mã liền nhau; máy tới
// sau đó chờ phía sau, kể cả khi mã nhỏ hơn.
func TestBatchesGoInTheOrderOfTheComputers(t *testing.T) {
	r := &Receiver{pending: map[string]*waiting{}}
	send := func(device string) {
		r.enqueue(device, cleaned(t, `{"v": 2, "device": "`+device+`", "updatedAt": 1791165600000, "hours": {}}`), "hours", "a", 1, nil)
	}
	for _, device := range []string{"device-q5", "device-q2", "device-q9", "device-q2", "device-q1"} {
		send(device)
	}
	r.sortWaiting()
	send("device-q0")
	b := r.take()
	var got []string
	for _, one := range b.rows {
		k, _ := one.(*pyjson.Object).Get("k")
		got = append(got, k.([]pyjson.Value)[1].(string))
	}
	if want := "device-q1 device-q2 device-q5 device-q9 device-q0"; strings.Join(got, " ") != want {
		t.Fatalf("order %v, want %s", got, want)
	}
}

// TestBatchesStayInOrderWhilePythonIsBehind: with more computers waiting than one batch holds, the batches go in the order of their ids;
// the computers that come meanwhile are sorted behind the ones already sorted, never before them, even with smaller ids.
// TestBatchesStayInOrderWhilePythonIsBehind: khi số máy chờ nhiều hơn một lô, các lô đi theo thứ tự mã; các máy tới trong lúc đó được
// sắp phía sau những máy đã sắp, không bao giờ chen lên trước, kể cả khi mã nhỏ hơn.
func TestBatchesStayInOrderWhilePythonIsBehind(t *testing.T) {
	r := &Receiver{pending: map[string]*waiting{}}
	send := func(device string) {
		r.enqueue(device, cleaned(t, `{"v": 2, "device": "`+device+`", "updatedAt": 1791165600000, "hours": {}}`), "hours", "a", 1, nil)
	}
	ids := func(prefix string, n int) []string {
		out := make([]string, n)
		for i, j := range rand.New(rand.NewSource(int64(n))).Perm(n) {
			out[i] = fmt.Sprintf("device-%s%05d", prefix, j)
		}
		return out
	}
	first := ids("m", maxBatchRows+500)
	for _, d := range first {
		send(d)
	}
	devicesOf := func(b *batch) []string {
		var got []string
		for _, one := range b.rows {
			k, _ := one.(*pyjson.Object).Get("k")
			got = append(got, k.([]pyjson.Value)[1].(string))
		}
		return got
	}
	b := r.take()
	got := devicesOf(b)
	want := append([]string(nil), first...)
	sort.Strings(want)
	if strings.Join(got, " ") != strings.Join(want[:maxBatchRows], " ") {
		t.Fatalf("the first batch is not the first ids in order")
	}
	r.inflight = nil
	// Python answered; meanwhile computers with smaller ids came
	// Python đã trả lời; trong lúc đó có các máy mã nhỏ hơn tới
	later := ids("a", 300)
	for _, d := range later {
		send(d)
	}
	got = devicesOf(r.take())
	sort.Strings(later)
	if strings.Join(got, " ") != strings.Join(append(want[maxBatchRows:], later...), " ") {
		t.Fatalf("the second batch: %d rows, starting %v", len(got), got[:3])
	}
}

// TestHealthSaysWhenRowsWaitTooLong: /health gives the rows waiting and how long the oldest has waited, and says behind past a minute.
// TestHealthSaysWhenRowsWaitTooLong: /health cho số dòng đang chờ và dòng chờ lâu nhất đã chờ bao lâu, và báo chậm khi quá một phút.
func TestHealthSaysWhenRowsWaitTooLong(t *testing.T) {
	r := &Receiver{pending: map[string]*waiting{}}
	for _, d := range []string{"device-h1", "device-h2"} {
		r.enqueue(d, cleaned(t, `{"v": 2, "device": "`+d+`", "updatedAt": 1791165600000, "hours": {}}`), "hours", "a", 1, nil)
	}
	h := r.health()
	if h["queued"] != 2 || h["behind"] != false || h["waitSeconds"].(int64) > 1 {
		t.Fatalf("just queued: %v", h)
	}
	r.pending["device-h2"].since = time.Now().Add(-behindAfter - 5*time.Second).UnixMilli()
	h = r.health()
	if h["behind"] != true || h["waitSeconds"].(int64) < int64(behindAfter/time.Second) {
		t.Fatalf("waited too long: %v", h)
	}
	// the batch on its way counts until Python answers it
	// lô đang đi vẫn được tính cho tới khi Python trả lời nó
	r.take()
	if h = r.health(); h["queued"] != 2 || h["behind"] != true {
		t.Fatalf("on its way: %v", h)
	}
	r.inflight = nil
	if h = r.health(); h["queued"] != 0 || h["behind"] != false {
		t.Fatalf("written: %v", h)
	}
}
