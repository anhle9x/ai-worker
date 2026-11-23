package ingest

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// unloaded counts the books that could not be read from Python, to say them in one line a minute: after a restart under load every
// computer that connects again may fail once, and a line each made a log of 78 MB in ten minutes (443,477 lines at 100,000 computers).
// unloaded đếm các sổ không đọc được từ Python, để báo trong một dòng mỗi phút: sau khi khởi động lại lúc đang có tải, mọi máy kết nối lại
// có thể hỏng một lần, và mỗi lần một dòng đã làm nhật ký 78 MB trong mười phút (443.477 dòng ở 100.000 máy).
type unloaded struct {
	mu   sync.Mutex
	n    int64
	last string
	said time.Time
}

func (u *unloaded) note(device string, err error) {
	u.mu.Lock()
	u.n++
	u.last = device + ": " + err.Error()
	u.mu.Unlock()
}

// line gives what to log now, "" when nothing is due: the first failure at once, then the count at most once a minute.
// line trả điều cần ghi lúc này, "" khi chưa tới lúc: lần hỏng đầu tiên báo ngay, sau đó báo số đếm nhiều nhất mỗi phút một lần.
func (u *unloaded) line(now time.Time) string {
	u.mu.Lock()
	defer u.mu.Unlock()
	if u.n == 0 || now.Sub(u.said) < time.Minute {
		return ""
	}
	s := fmt.Sprintf("cannot load the book of %s", u.last)
	if u.n > 1 {
		s = fmt.Sprintf("cannot load the books of %d computers, the last %s", u.n, u.last)
	}
	u.n, u.said = 0, now
	return s
}

func (u *unloaded) say(now time.Time) {
	if s := u.line(now); s != "" {
		log.Print("receiver: " + s)
	}
}
