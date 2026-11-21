package totals

import (
	"testing"

	"aiworker/receiver/internal/pyjson"
)

func TestDaysAndStore(t *testing.T) {
	if LocalDay(0, 7*3600) != "1970-01-01" || LocalDay(17, 7*3600) != "1970-01-02" || LocalDay(0, -3600) != "1969-12-31" {
		t.Fatal("local days")
	}
	book, err := pyjson.Parse([]byte(`{"ledger": {"17": {"usdMicro": 5, "input": 2, "cacheRead": 1.9, "output": 1}, "16": {"usd": 0.25}}, "tasks": {"17": {"gemma": 2}}}`))
	if err != nil {
		t.Fatal(err)
	}
	days := AddUp(book.(*pyjson.Object), 7*3600)
	if d := days["1970-01-02"]; d == nil || d.USDMicro.Int64() != 5 || d.TokensIn.Int64() != 3 || d.TokensOut.Int64() != 1 || d.Tasks[2].Int64() != 2 {
		t.Fatalf("%+v", days["1970-01-02"])
	}
	if days["1970-01-01"].USDMicro.Int64() != 250000 {
		t.Fatal("usd only")
	}
	s := NewStore()
	s.Put("device-a", days)
	s.Put("device-b", days)
	if keys := s.Days("device-a"); len(keys) != 2 || keys[0] != "1970-01-01" || s.Day("device-b", "1970-01-02").USDMicro.Int64() != 5 {
		t.Fatalf("%v", keys)
	}
	s.Drop("device-b")
	if s.Day("device-b", "1970-01-02") != nil || s.Day("device-a", "1970-01-03") != nil || len(s.Days("device-b")) != 0 {
		t.Fatal("not taken out")
	}
}

// TestHoursHeldAddUpTheSame: the hours held as three numbers add up to what AddUp gives on their tables; FirstHour is the first hour of
// the local day, for an offset of whole hours and of a part of one.
// TestHoursHeldAddUpTheSame: các giờ giữ dạng ba số cộng ra đúng thứ AddUp cho trên bảng của chúng; FirstHour là giờ đầu tiên của ngày
// địa phương, với độ lệch tròn giờ và lệch một phần giờ.
func TestHoursHeldAddUpTheSame(t *testing.T) {
	book, err := pyjson.Parse([]byte(`{"ledger": {"17": {"usdMicro": 5, "input": 2, "cacheRead": 1.9, "cacheWrite": 4, "output": 1}, "16": {"usd": 0.25},
		"40": {"usdMicro": 7, "output": 3}}, "tasks": {"17": {"gemma": 2, "gemini": 1}, "41": {"chatgpt": 4}}}`))
	if err != nil {
		t.Fatal(err)
	}
	o := book.(*pyjson.Object)
	ledger, tasks := map[int64]Hour{}, map[int64]Hour{}
	for kind, into := range map[string]map[int64]Hour{"ledger": ledger, "tasks": tasks} {
		table, _ := o.Get(kind)
		for i, h := range table.(*pyjson.Object).Keys {
			n := int64(0)
			for _, c := range h {
				n = n*10 + int64(c-'0')
			}
			into[n] = HourOf(kind, table.(*pyjson.Object).Vals[i])
		}
	}
	for _, tz := range []int64{7 * 3600, -3600, 19800} {
		want, got := AddUp(o, tz), DaysOf(ledger, tasks, tz)
		if len(want) != len(got) {
			t.Fatalf("tz %d: %d days, %d expected", tz, len(got), len(want))
		}
		for day, w := range want {
			g := got[day]
			if g == nil || g.USDMicro.Cmp(w.USDMicro) != 0 || g.TokensIn.Cmp(w.TokensIn) != 0 || g.TokensOut.Cmp(w.TokensOut) != 0 ||
				g.Tasks[0].Cmp(w.Tasks[0]) != 0 || g.Tasks[1].Cmp(w.Tasks[1]) != 0 || g.Tasks[2].Cmp(w.Tasks[2]) != 0 {
				t.Fatalf("tz %d %s: %+v, %+v expected", tz, day, g, w)
			}
		}
	}
	// the expected hours are what today_first_hour in server/board/devices.py gives for the same moments and offsets
	// các giờ chờ đợi là thứ today_first_hour trong server/board/devices.py cho với cùng các thời điểm và độ lệch
	for _, c := range []struct {
		now     float64
		tz, sec int64
	}{{1791165600, 7 * 3600, 497537}, {1791165600, 0, 497544}, {1791165600, 19800, 497539}, {3600 * 5, 7 * 3600, -7}} {
		if got := FirstHour(c.now, c.tz); got != c.sec || LocalDay(got, c.tz) != LocalDay(int64(c.now)/3600, c.tz) || LocalDay(got-1, c.tz) == LocalDay(got, c.tz) {
			t.Errorf("FirstHour(%v, %d) = %d, %d expected", c.now, c.tz, got, c.sec)
		}
	}
}
