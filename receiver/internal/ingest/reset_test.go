package ingest

import (
	"context"
	"fmt"
	"strconv"
	"testing"
	"time"
)

// TestBooksDroppedWhileRowsWait: Python starts again (reset) while a row of a computer still waits here; the book this side reads back
// from Python lacks that row, and the hours this side then holds must still end equal to Python's once the row is written.
// TestBooksDroppedWhileRowsWait: Python khởi động lại (reset) trong lúc một dòng của máy còn chờ ở đây; sổ bên này đọc lại từ Python
// thiếu dòng đó, và các giờ bên này giữ sau đó vẫn phải bằng của Python khi dòng đã được ghi.
func TestBooksDroppedWhileRowsWait(t *testing.T) {
	h := start(t)
	device := "device-goreset"
	key := enrolled(t, h, device)
	now := time.Now().Unix() / 3600
	h1, h2 := strconv.FormatInt(now-1, 10), strconv.FormatInt(now, 10)
	if now-1 < h.r.today() {
		t.Skip("the hour before is yesterday here")
	}
	h.flush()
	// a send whose row waits, then Python is seen to have started again
	// một lần gửi có dòng đang chờ, rồi thấy Python đã khởi động lại
	if status, ans := h.send(key, packet(device, map[string]any{"hours": map[string]any{"ledger": map[string]any{h1: map[string]any{"usdMicro": 100}}}})); status != 200 {
		t.Fatalf("first: %d %v", status, ans)
	}
	h.r.mu.Lock()
	h.r.policy.Boot = "an-older-start"
	h.r.mu.Unlock()
	if err := h.r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	second := packet(device, map[string]any{"hours": map[string]any{"ledger": map[string]any{h2: map[string]any{"usdMicro": 50}}}})
	// while the row waits the book is not read, and the computer is told to come back
	// trong lúc dòng còn chờ thì sổ không được đọc, và máy được bảo quay lại
	if status, ans := h.send(key, second); status != 503 || ans["error"] != "busy" {
		t.Fatalf("second, row still waiting: %d %v", status, ans)
	}
	h.flush()
	if status, ans := h.send(key, second); status != 200 {
		t.Fatalf("second, once written: %d %v", status, ans)
	}
	h.flush()
	_ = h.r.Resync(context.Background())
	e := h.r.entry(device)
	theirs := heldFrom(h.pythonBook(device, true), h.r.today())
	if fmt.Sprint(e.rec.ledger) != fmt.Sprint(theirs.ledger) {
		t.Fatalf("hours differ after the reset\n go     %v\n python %v", e.rec.ledger, theirs.ledger)
	}
}

// TestPagesLeaveBooksWhoseRowsWait: after another start of Python every book is read again a page at a time; a computer whose row still
// waits is left out and read once the row is written, so its hours end equal to Python's.
// TestPagesLeaveBooksWhoseRowsWait: sau khi Python khởi động lại mọi sổ được đọc lại từng trang; máy còn dòng chờ được để lại và đọc
// sau khi dòng đã ghi, nên các giờ của nó cuối cùng bằng của Python.
func TestPagesLeaveBooksWhoseRowsWait(t *testing.T) {
	h := start(t)
	device := "device-gopages"
	key := enrolled(t, h, device)
	h.flush()
	hour := strconv.FormatInt(time.Now().Unix()/3600, 10)
	if status, ans := h.send(key, packet(device, map[string]any{"hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 300}}}})); status != 200 {
		t.Fatalf("send: %d %v", status, ans)
	}
	h.r.mu.Lock()
	h.r.policy.Boot = "an-older-start"
	h.r.mu.Unlock()
	if err := h.r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := h.r.Resync(context.Background()); err != nil {
		t.Fatal(err)
	}
	if h.r.entry(device).loaded {
		t.Fatal("the book was read from a page while its row waits")
	}
	h.flush()
	if err := h.r.Resync(context.Background()); err != nil {
		t.Fatal(err)
	}
	e := h.r.entry(device)
	theirs := heldFrom(h.pythonBook(device, true), h.r.today())
	if !e.loaded || fmt.Sprint(e.rec.ledger) != fmt.Sprint(theirs.ledger) {
		t.Fatalf("after the row was written: loaded %v\n go     %v\n python %v", e.loaded, e.rec, theirs.ledger)
	}
}
