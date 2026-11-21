package feed

import (
	"fmt"
	"math/big"
	"testing"
	"time"

	"aiworker/receiver/internal/live"
	"aiworker/receiver/internal/people"
	"aiworker/receiver/internal/totals"
)

// storeSource is the live numbers of n computers, one person each, 500 people a branch, as the receiver holds them.
// storeSource là số trực tiếp của n máy, mỗi máy một người, 500 người một chi nhánh, như bộ nhận giữ chúng.
type storeSource struct {
	store  *live.Store
	places map[string]people.Entry
}

func (s *storeSource) Rows(now float64) []live.Row {
	return s.store.Rows(now, 0, func(d string) (people.Entry, bool) { e, ok := s.places[d]; return e, ok })
}

func (s *storeSource) LivePolicy() ([]string, map[string]bool, bool) {
	return []string{board}, nil, true
}

func computers(n int, now time.Time) *storeSource {
	t := totals.NewStore()
	src := &storeSource{store: live.New(t), places: map[string]people.Entry{}}
	day := totals.LocalDay(totals.FirstHour(float64(now.Unix()), 0), 0)
	for i := 0; i < n; i++ {
		device := fmt.Sprintf("device-%08d", i)
		src.places[device] = people.Entry{Row: fmt.Sprintf("r%011d", i), Scope: fmt.Sprintf("b%03d", i/500)}
		src.store.Put(device, live.State{UpdatedAt: float64(now.UnixMilli()), Counts: live.Counts{OpenSessions: 1, Working: int64(i % 2)}})
		d := &totals.Day{USDMicro: big.NewInt(int64(i) * 137), TokensIn: big.NewInt(1000), TokensOut: big.NewInt(200),
			Tasks: [3]*big.Int{big.NewInt(1), big.NewInt(0), big.NewInt(0)}}
		t.Put(device, map[string]*totals.Day{day: d})
	}
	return src
}

// BenchmarkRows100k: one pass over 100,000 computers (go test -bench Rows100k -run x ./internal/feed).
// BenchmarkRows100k: một lượt qua 100.000 máy (go test -bench Rows100k -run x ./internal/feed).
func BenchmarkRows100k(b *testing.B) {
	now := time.Now()
	src := computers(100_000, now)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		src.Rows(float64(now.Unix()))
	}
}

// BenchmarkStep100k: one tick with every branch of 100,000 computers and the whole organisation read by a board.
// BenchmarkStep100k: một nhịp khi mọi chi nhánh của 100.000 máy và cả tổ chức đều có bảng đọc.
func BenchmarkStep100k(b *testing.B) {
	now := time.Now()
	src := computers(100_000, now)
	f := New(src, keys{})
	f.Now = func() time.Time { return now }
	for i := 0; i < 200; i++ {
		f.scope(fmt.Sprintf("branch:b%03d", i))
	}
	f.scope("org")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		f.Step()
	}
}
