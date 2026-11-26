package ingest

import (
	"context"
	"io"
	"time"
)

// timing is how long each kind of call to Python may take, when a page of books or a batch counts as slow, and how long the pages of
// books are tried again before the rest are read when needed. A field of the Receiver, so a test can make it short.
// timing là thời gian mỗi loại lời gọi tới Python được phép kéo dài, lúc nào một trang sổ hay một lô bị coi là chậm, và các trang sổ
// được thử lại bao lâu trước khi phần còn lại được đọc khi cần. Là một trường của Receiver, để test đặt ngắn lại được.
type timing struct {
	// call: the policy, the table of people, one book, a send passed on; page and batch: a page of books and a batch of rows, longer,
	// since Python under load takes tens of seconds for them and a batch cut off at 30 seconds was written anyway and sent again
	// call: chính sách, bảng người, một sổ, một lần gửi chuyển tiếp; page và batch: một trang sổ và một lô dòng, dài hơn, vì Python lúc
	// tải nặng mất hàng chục giây cho chúng và một lô bị cắt ở 30 giây vẫn được ghi rồi lại bị gửi lại
	call, page, batch time.Duration
	// slow: a page or a batch taking longer halves the next one; one taking under a quarter of it doubles the next, up to the most
	// slow: một trang hay một lô lâu hơn mức này làm trang hay lô sau nhỏ đi một nửa; dưới một phần tư mức này thì gấp đôi, tới mức tối đa
	slow time.Duration
	// loadFor: how long a page of books keeps failing before the load stops and the rest are read when needed; pause: the first wait
	// between two tries, doubled up to maxRetryPause
	// loadFor: một trang sổ hỏng liên tục bao lâu thì thôi nạp và phần còn lại được đọc khi cần; pause: lần chờ đầu giữa hai lần thử,
	// gấp đôi dần tới maxRetryPause
	loadFor, pause time.Duration
}

func defaultTiming() timing {
	return timing{call: 30 * time.Second, page: 2 * time.Minute, batch: 2 * time.Minute, slow: 10 * time.Second,
		loadFor: 5 * time.Minute, pause: time.Second}
}

// backoff is the next wait after a failed try: twice the last, at least first, at most maxRetryPause.
// backoff là lần chờ kế tiếp sau một lần thử hỏng: gấp đôi lần trước, ít nhất first, nhiều nhất maxRetryPause.
func backoff(last, first time.Duration) time.Duration {
	return min(maxRetryPause, max(first, last*2))
}

// sleep waits d, or less when ctx ends; false when it ended.
// sleep chờ d, hoặc ít hơn khi ctx kết thúc; false khi nó đã kết thúc.
func sleep(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

// sizer is how many books a page asks, or how many rows a batch takes: halved after a slow or failed call, doubled after a quick one,
// between lo and hi.
// sizer là số sổ một trang hỏi, hay số dòng một lô lấy: giảm một nửa sau một lời gọi chậm hay hỏng, gấp đôi sau một lời gọi nhanh,
// trong khoảng lo tới hi.
type sizer struct{ n, lo, hi int }

func newSizer(lo, hi int) sizer { return sizer{n: hi, lo: lo, hi: hi} }

func (s *sizer) took(d, slow time.Duration, ok bool) {
	switch {
	case !ok || d > slow:
		s.n = max(s.lo, s.n/2)
	case d < slow/4:
		s.n = min(s.hi, s.n*2)
	}
}

// cancelOnClose ends the deadline of a call to Python once its answer is read and closed.
// cancelOnClose kết thúc hạn của một lời gọi tới Python khi câu trả lời của nó đã đọc xong và đóng lại.
type cancelOnClose struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c cancelOnClose) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}
