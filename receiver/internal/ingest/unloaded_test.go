package ingest

import (
	"errors"
	"strings"
	"testing"
	"time"
)

// TestBooksNotLoadedAreSaidOnceAMinute: the first failure is said at once, the next ones in one line a minute later with their count.
// TestBooksNotLoadedAreSaidOnceAMinute: lần hỏng đầu báo ngay, các lần sau gộp trong một dòng một phút sau kèm số đếm.
func TestBooksNotLoadedAreSaidOnceAMinute(t *testing.T) {
	var u unloaded
	t0 := time.Unix(1_800_000_000, 0)
	if s := u.line(t0); s != "" {
		t.Fatalf("nothing failed yet: %q", s)
	}
	u.note("device-a", errors.New("EOF"))
	if s := u.line(t0); s != "cannot load the book of device-a: EOF" {
		t.Fatalf("first: %q", s)
	}
	for i := 0; i < 1000; i++ {
		u.note("device-b", errors.New("EOF"))
		if s := u.line(t0.Add(time.Duration(i) * 50 * time.Millisecond)); s != "" {
			t.Fatalf("said again within the minute: %q", s)
		}
	}
	if s := u.line(t0.Add(time.Minute)); !strings.HasPrefix(s, "cannot load the books of 1000 computers, the last device-b") {
		t.Fatalf("a minute later: %q", s)
	}
	if s := u.line(t0.Add(3 * time.Minute)); s != "" {
		t.Fatalf("nothing new: %q", s)
	}
}
