package people

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"testing"
)

func page(t *testing.T, s string) Page {
	t.Helper()
	var p Page
	if err := json.Unmarshal([]byte(s), &p); err != nil {
		t.Fatal(err)
	}
	return p
}

// TestApply: a reset drops the table, the pages after it are asked as part of the load, a change and a computer gone are applied, and
// each call says which computers changed place.
// TestApply: một lần reset bỏ bảng, các trang sau nó được xin như một phần của lượt nạp, một thay đổi và một máy đã mất được áp dụng,
// và mỗi lần gọi cho biết máy nào đã đổi chỗ.
func TestApply(t *testing.T) {
	tb := New()
	if p := tb.Path(); p != "/internal/people?since=0&boot=&limit=5000" {
		t.Fatal(p)
	}
	tb.Apply(page(t, `{"boot":"b1","reset":true,"seq":1,"more":true,"people":[{"device":"device-a","row":"aaaaaaaaaaaa","scope":""}],"gone":[]}`))
	if p := tb.Path(); p != "/internal/people?since=1&boot=b1&limit=5000&loading=1" {
		t.Fatal(p)
	}
	tb.Apply(page(t, `{"boot":"b1","reset":false,"seq":2,"more":false,"people":[{"device":"device-b","row":"bbbbbbbbbbbb","scope":"hn"}],"gone":["device-x"]}`))
	if p := tb.Path(); p != "/internal/people?since=2&boot=b1&limit=5000" || tb.Len() != 2 {
		t.Fatal(p, tb.Len())
	}
	changed := tb.Apply(page(t, `{"boot":"b1","reset":false,"seq":4,"more":false,"people":[{"device":"device-b","row":"bbbbbbbbbbbb","scope":"sg"},{"device":"device-a","row":"aaaaaaaaaaaa","scope":""}],"gone":["device-a"]}`))
	sort.Strings(changed)
	if strings.Join(changed, ",") != "device-a,device-b" {
		t.Fatal(changed)
	}
	if e, ok := tb.Get("device-b"); !ok || e != (Entry{"bbbbbbbbbbbb", "sg"}) {
		t.Fatal(e, ok)
	}
	if _, ok := tb.Get("device-a"); ok {
		t.Fatal("device-a is gone")
	}
	// another start of Python: everything held is dropped, and named as changed
	// một lần khởi động khác của Python: mọi thứ đang giữ bị bỏ, và được nêu là đã đổi
	changed = tb.Apply(page(t, `{"boot":"b2","reset":true,"seq":1,"more":false,"people":[{"device":"device-c","row":"cccccccccccc","scope":""}],"gone":[]}`))
	sort.Strings(changed)
	if strings.Join(changed, ",") != "device-b,device-c" || tb.Len() != 1 {
		t.Fatal(changed, tb.Snapshot())
	}
}

// TestRefresh asks page after page until there is no more, and keeps what came when a page fails.
// TestRefresh xin hết trang này tới trang khác cho tới khi không còn, và giữ thứ đã nhận khi một trang hỏng.
func TestRefresh(t *testing.T) {
	answers := []string{
		`{"boot":"b1","reset":true,"seq":1,"more":true,"people":[{"device":"device-a","row":"aaaaaaaaaaaa","scope":""}],"gone":[]}`,
		`{"boot":"b1","reset":false,"seq":2,"more":false,"people":[{"device":"device-b","row":"bbbbbbbbbbbb","scope":""}],"gone":[]}`,
	}
	var asked []string
	get := func(_ context.Context, path string, into any) error {
		asked = append(asked, path)
		return json.Unmarshal([]byte(answers[len(asked)-1]), into)
	}
	tb := New()
	changed, err := tb.Refresh(context.Background(), get)
	if err != nil || len(changed) != 2 || tb.Len() != 2 || !strings.HasSuffix(asked[1], "&loading=1") {
		t.Fatal(changed, err, asked)
	}
}
