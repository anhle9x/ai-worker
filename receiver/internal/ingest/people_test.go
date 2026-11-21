package ingest

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"testing"

	"aiworker/receiver/internal/people"
)

// TestPeopleFromPython: the receiver learns from the real Python server each computer's row on the board and its branch, then only
// what changed (two computers moved to a branch declared later); the table it put together change by change is the same as the whole
// table Python gives a receiver that starts now, which is the judge.
// TestPeopleFromPython: bộ nhận học từ máy chủ Python thật dòng trên bảng và chi nhánh của mỗi máy, rồi chỉ phần đổi (hai máy chuyển
// sang một chi nhánh khai báo sau); bảng nó ghép từng thay đổi giống hệt cả bảng Python cho một bộ nhận khởi động lúc này, là trọng tài.
func TestPeopleFromPython(t *testing.T) {
	h := start(t)
	ctx := context.Background()
	devices := []string{"device-gopeoplea", "device-gopeopleb"}
	for _, d := range devices {
		if status, ans := h.send("shared-test-key-0123456789", packet(d, map[string]any{"v": 1})); status != 200 || ans["deviceKey"] == nil {
			t.Fatalf("enrol %s: %d %v", d, status, ans)
		}
	}
	judge := func() map[string]people.Entry {
		t.Helper()
		fresh := people.New()
		if _, err := fresh.Refresh(ctx, h.r.getJSON); err != nil {
			t.Fatal(err)
		}
		return fresh.Snapshot()
	}
	changed, err := h.r.RefreshPeople(ctx)
	if err != nil || len(changed) != 2 {
		t.Fatalf("first: %v %v", changed, err)
	}
	code := regexp.MustCompile(`\A[0-9a-f]{12}\z`)
	before := h.r.People.Snapshot()
	for _, d := range devices {
		if e := before[d]; !code.MatchString(e.Row) || e.Scope != "" {
			t.Fatalf("%s: %+v", d, e)
		}
	}
	if before[devices[0]].Row == before[devices[1]].Row {
		t.Fatal("two people share a row")
	}
	if !reflect.DeepEqual(before, judge()) {
		t.Fatalf("held %v\nPython %v", before, judge())
	}
	if changed, err := h.r.RefreshPeople(ctx); err != nil || len(changed) != 0 {
		t.Fatalf("nothing changed, yet %v %v", changed, err)
	}
	// a branch declared for the address they sent from: both move to it on the next ask, on the same rows
	// một chi nhánh khai báo cho địa chỉ họ gửi từ đó: cả hai chuyển sang ở lần hỏi kế, vẫn trên cùng các dòng
	branches := filepath.Join(filepath.Dir(filepath.Dir(h.secrets)), "none.json")
	if err := os.WriteFile(branches, []byte(`{"branches": [{"id": "hue", "name": "Hue", "lat": 16.46, "lon": 107.59, "ip": ["127.0.0.0/8"]}]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	changed, err = h.r.RefreshPeople(ctx)
	if err != nil || len(changed) != 2 {
		t.Fatalf("moved: %v %v", changed, err)
	}
	after := h.r.People.Snapshot()
	for _, d := range devices {
		if after[d] != (people.Entry{Row: before[d].Row, Scope: "hue"}) {
			t.Fatalf("%s: %+v", d, after[d])
		}
	}
	if !reflect.DeepEqual(after, judge()) {
		t.Fatalf("held %v\nPython %v", after, judge())
	}
}
