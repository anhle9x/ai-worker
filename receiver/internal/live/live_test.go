package live

import (
	"testing"

	"aiworker/receiver/internal/people"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

func record(t *testing.T, s string) *pyjson.Object {
	t.Helper()
	v, err := pyjson.Parse([]byte(s))
	if err != nil {
		t.Fatal(err)
	}
	return v.(*pyjson.Object)
}

// TestRound4: the dollars are Python's round(micro / 1_000_000, 4); the values are what Python gives.
// TestRound4: số đô la là round(micro / 1_000_000, 4) của Python; các giá trị là thứ Python cho.
func TestRound4(t *testing.T) {
	for micro, want := range map[int64]float64{0: 0, 50: 0.0001, 49: 0, 150: 0.0001, 250: 0.0003, 123507: 0.1235, 999999: 1.0, 1000001: 1.0, 12345678901: 12345.6789} {
		if got := Round4(micro); got != want {
			t.Errorf("Round4(%d) = %v, %v expected", micro, got, want)
		}
	}
}

// TestRowsAndBranches: two computers of one person are one row; a computer Python has not placed is left out; a connector's tools are
// counted per tool; the branches add the rounded dollars of each person, count a person both waiting and working when both are true, and
// put the people in no branch last.
// TestRowsAndBranches: hai máy của một người là một dòng; máy Python chưa xếp chỗ bị bỏ ra; công cụ của bộ nối được đếm theo từng công
// cụ; các chi nhánh cộng số đô la đã làm tròn của từng người, đếm một người cả đang chờ lẫn đang làm khi cả hai đều đúng, và đặt người
// chưa thuộc chi nhánh nào ở cuối.
func TestRowsAndBranches(t *testing.T) {
	const now = 1_000_000.0
	tot := totals.NewStore()
	s := New(tot)
	put := func(device, rec string, micro int64) {
		st, ok := StateOf(record(t, rec))
		if !ok {
			t.Fatalf("%s: no state", device)
		}
		s.Put(device, st)
		hour := int64(now) / 3600
		tot.Put(device, totals.DaysOf(map[int64]totals.Hour{hour: {micro, 1, 2}}, nil, 0))
	}
	put("device-a1", `{"updatedAt": 999800000, "openSessions": 2, "working": 1, "waiting": 1, "delegating": {"gemma": 2.9}}`, 50)
	put("device-a2", `{"updatedAt": 999900000.5, "openSessions": 1, "working": 1}`, 100)
	put("device-b", `{"updatedAt": 999000000, "openSessions": 1, "working": 1, "tools": {"codex": {"openSessions": 1, "working": 1}, "cursor": {"openSessions": 0}}}`, 150)
	put("device-c", `{"updatedAt": 1000, "openSessions": 1}`, 0)
	put("device-x", `{"updatedAt": 999000000}`, 7)
	if _, ok := StateOf(record(t, `{"openSessions": 1}`)); ok {
		t.Fatal("a record with no updatedAt has a state")
	}
	place := map[string]people.Entry{"device-a1": {Row: "r1", Scope: "hue"}, "device-a2": {Row: "r1", Scope: "hue"}, "device-b": {Row: "r2"}, "device-c": {Row: "r3", Scope: "hue"}}
	rows := s.Rows(now, 0, func(d string) (people.Entry, bool) { e, ok := place[d]; return e, ok })
	if len(rows) != 3 || rows[0].Row != "r1" || rows[1].Row != "r2" || rows[2].Row != "r3" {
		t.Fatalf("%+v", rows)
	}
	a, b, c := rows[0], rows[1], rows[2]
	if a.Status != Waiting || a.OpenSessions != 3 || a.Delegating != [3]int64{0, 0, 2} || a.USDMicro != 150 || a.USDToday != 0.0001 || a.UpdatedAt != 999900000.5 ||
		a.Tools["claude"] != (Counts{3, 2, 1}) || a.TokensIn != 2 {
		t.Fatalf("a %+v", a)
	}
	if b.Status != Working || len(b.Tools) != 1 || b.Tools["codex"] != (Counts{1, 1, 0}) {
		t.Fatalf("b %+v", b)
	}
	if c.Status != Offline || c.OpenSessions != 0 || len(c.Tools) != 0 {
		t.Fatalf("c %+v", c)
	}
	got := Branches(rows)
	// a waits in one session while others run: counted both waiting and working
	// a đang chờ ở một phiên trong khi các phiên khác chạy: được đếm cả đang chờ lẫn đang làm
	want := []Branch{{ID: "hue", People: 2, Online: 1, Working: 1, Waiting: 1, OpenSessions: 3, USDToday: 0.0001, Tokens: 9}, {ID: "", People: 1, Online: 1, Working: 1, OpenSessions: 1, USDToday: 0.0001, Tokens: 3}}
	if len(got) != 2 || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("%+v", got)
	}
	s.Drop("device-a2")
	if s.Len() != 4 {
		t.Fatal("not dropped")
	}
}
