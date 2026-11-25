package ingest

import (
	mrand "math/rand/v2"
	"strconv"
	"sync/atomic"
)

// Budget is a ceiling of bytes that several parts of the receiver take from and give back: the bodies being read and cleaned, the rows
// waiting for Python. A nil Budget, or one with no ceiling, takes everything.
// Budget là trần số byte mà nhiều phần của bộ nhận lấy ra và trả lại: các thân đang đọc và làm sạch, các dòng chờ Python. Budget nil,
// hoặc không có trần, nhận mọi thứ.
type Budget struct {
	max  int64
	used atomic.Int64
}

// NewBudget is a budget of max bytes; 0 or less is no ceiling.
// NewBudget là một ngân sách max byte; 0 hoặc nhỏ hơn là không có trần.
func NewBudget(max int64) *Budget { return &Budget{max: max} }

// Take takes n bytes if they fit under the ceiling, and says whether it did.
// Take lấy n byte nếu còn vừa dưới trần, và cho biết đã lấy chưa.
func (b *Budget) Take(n int64) bool {
	if b == nil || b.max <= 0 {
		return true
	}
	if b.used.Add(n) > b.max {
		b.used.Add(-n)
		return false
	}
	return true
}

// Add counts n more bytes, or fewer when negative, whatever the ceiling: a row already taken that grows or shrinks.
// Add đếm thêm n byte, hoặc bớt khi âm, bất kể trần: một dòng đã nhận lớn lên hay nhỏ đi.
func (b *Budget) Add(n int64) {
	if b != nil {
		b.used.Add(n)
	}
}

// Full says whether nothing more fits.
// Full cho biết đã hết chỗ chưa.
func (b *Budget) Full() bool { return b != nil && b.max > 0 && b.used.Load() >= b.max }

// Used is the bytes counted now.
// Used là số byte đang đếm.
func (b *Budget) Used() int64 {
	if b == nil {
		return 0
	}
	return b.used.Load()
}

// RetryAfter is a Retry-After of lo to hi seconds, spread so the computers told it do not all come back in the same second.
// RetryAfter là một Retry-After từ lo tới hi giây, rải ra để các máy nhận được không cùng quay lại trong một giây.
func RetryAfter(lo, hi int) string {
	return strconv.Itoa(lo + mrand.IntN(max(1, hi-lo+1)))
}
