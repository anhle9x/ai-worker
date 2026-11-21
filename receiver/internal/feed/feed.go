package feed

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"aiworker/receiver/internal/live"
)

// The pace of the feed (docs/RECEIVER.md, section 3).
// Nhịp của luồng (docs/RECEIVER.vi.md, mục 3).
const (
	// Tick: how often the numbers are built and the changed rows sent, at most
	// Tick: bao lâu các con số được dựng và các dòng đã đổi được gửi một lần, nhiều nhất
	Tick = time.Second
	// Beat: a feed that had nothing to send this long gets a comment, so proxies and browsers keep it open
	// Beat: luồng không có gì để gửi lâu chừng này thì nhận một dòng chú thích, để proxy và trình duyệt giữ nó mở
	Beat = 15 * time.Second
	// WriteWait: one write to a board may take this long; a board that reads slower is cut, and holds nothing meanwhile
	// WriteWait: một lần ghi tới bảng được lâu chừng này; bảng đọc chậm hơn bị cắt, và không giữ gì trong lúc đó
	WriteWait = 10 * time.Second
	// keepScope: a scope only asked on /live/snap is still built this long after
	// keepScope: phạm vi chỉ được hỏi ở /live/snap vẫn được dựng chừng này sau đó
	keepScope = 30 * time.Second
	// keepGone: a row gone from a scope is remembered this long; a board further behind gets the whole scope again
	// keepGone: dòng đã rời một phạm vi được nhớ chừng này; bảng chậm hơn mức đó nhận lại cả phạm vi
	keepGone = 2 * time.Minute
	// MaxFeeds: feeds open at once, at most; past that a board is told to come back
	// MaxFeeds: số luồng mở cùng lúc, nhiều nhất; quá mức đó bảng được báo quay lại sau
	MaxFeeds = 5000
)

// Source is where the numbers and the policy come from (ingest.Receiver).
// Source là nơi lấy các con số và chính sách (ingest.Receiver).
type Source interface {
	// Rows is the live numbers at the second now (ingest.Receiver.Rows)
	// Rows là số trực tiếp ở giây now (ingest.Receiver.Rows)
	Rows(now float64) []live.Row
	// LivePolicy gives the board's origins and the sessions ended, from the latest policy; ok is false until the first policy came
	// LivePolicy cho các nguồn của bảng và các phiên đã kết thúc, từ chính sách mới nhất; ok là false cho tới khi có chính sách đầu tiên
	LivePolicy() (origins []string, ended map[string]bool, ok bool)
}

// item is one row of a scope (a person's row, or a branch's totals for "org") as JSON, with the number of the change that made it; a
// nil body is a row that left, kept until keepGone.
// item là một dòng của một phạm vi (dòng của một người, hay tổng của một chi nhánh với "org") dạng JSON, kèm số của lần đổi làm ra nó;
// body nil là dòng đã rời đi, giữ tới hết keepGone.
type item struct {
	seq    int64
	body   []byte
	goneAt time.Time
}

// scope holds the numbers of one scope, shared by every board that reads it: each board keeps only the number of the change it sent last.
// scope giữ các con số của một phạm vi, dùng chung cho mọi bảng đang đọc nó: mỗi bảng chỉ giữ số của lần đổi nó gửi gần nhất.
type scope struct {
	name    string
	mu      sync.RWMutex
	items   map[string]*item
	seq     int64
	floor   int64
	built   bool
	usedAt  time.Time
	clients map[*client]struct{}
}

type client struct {
	sid  string
	wake chan struct{}
	end  chan string
	once sync.Once
}

func (c *client) stop(why string) {
	c.once.Do(func() { c.end <- why })
}

// Feed builds the numbers of each scope that is read, once a tick, and serves /live and /live/snap.
// Feed dựng các con số của mỗi phạm vi đang được đọc, mỗi nhịp một lần, và phục vụ /live và /live/snap.
type Feed struct {
	src  Source
	keys Keys
	// Now, Tick, Beat and WriteWait are set by the tests
	// Now, Tick, Beat và WriteWait do bài test đặt
	Now       func() time.Time
	Tick      time.Duration
	Beat      time.Duration
	WriteWait time.Duration

	build  sync.Mutex
	mu     sync.Mutex
	scopes map[string]*scope
	feeds  int
	closed bool
}

// New makes a feed of the numbers of src, with tickets checked against keys.
// New tạo một luồng các con số của src, kiểm vé bằng keys.
func New(src Source, keys Keys) *Feed {
	return &Feed{src: src, keys: keys, Now: time.Now, Tick: Tick, Beat: Beat, WriteWait: WriteWait, scopes: map[string]*scope{}}
}

func (f *Feed) scope(name string) *scope {
	f.mu.Lock()
	defer f.mu.Unlock()
	s := f.scopes[name]
	if s == nil {
		s = &scope{name: name, items: map[string]*item{}, clients: map[*client]struct{}{}}
		f.scopes[name] = s
	}
	s.mu.Lock()
	s.usedAt = f.Now()
	s.mu.Unlock()
	return s
}

// Feeds is the number of feeds open.
// Feeds là số luồng đang mở.
func (f *Feed) Feeds() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.feeds
}

// Run builds the numbers every tick until stop is closed.
// Run dựng các con số mỗi nhịp cho tới khi stop đóng.
func (f *Feed) Run(stop <-chan struct{}) {
	t := time.NewTicker(f.Tick)
	defer t.Stop()
	for {
		select {
		case <-stop:
			return
		case <-t.C:
			f.Step()
		}
	}
}

// Close ends every feed; the boards come back once the receiver is up again.
// Close kết thúc mọi luồng; các bảng quay lại khi bộ nhận chạy lại.
func (f *Feed) Close() {
	f.mu.Lock()
	f.closed = true
	var all []*client
	for _, s := range f.scopes {
		s.mu.RLock()
		for c := range s.clients {
			all = append(all, c)
		}
		s.mu.RUnlock()
	}
	f.mu.Unlock()
	for _, c := range all {
		c.stop("closing")
	}
}

// Step builds once the numbers of every scope read now, from one pass over the computers, wakes the boards whose scope changed, and ends
// the feeds of the sessions the policy says are closed. Scopes nobody reads are dropped.
// Step dựng một lần các con số của mọi phạm vi đang được đọc, từ một lượt qua các máy, đánh thức các bảng có phạm vi đã đổi, và kết thúc
// luồng của các phiên chính sách nói đã đóng. Phạm vi không ai đọc thì bị bỏ.
func (f *Feed) Step() {
	f.build.Lock()
	defer f.build.Unlock()
	now := f.Now()
	f.mu.Lock()
	var read []*scope
	for name, s := range f.scopes {
		s.mu.RLock()
		idle := len(s.clients) == 0 && now.Sub(s.usedAt) > keepScope
		s.mu.RUnlock()
		if idle {
			delete(f.scopes, name)
			continue
		}
		read = append(read, s)
	}
	f.mu.Unlock()
	if len(read) == 0 {
		return
	}
	f.fill(read, now)
	_, ended, _ := f.src.LivePolicy()
	for _, s := range read {
		s.mu.RLock()
		for c := range s.clients {
			if ended[c.sid] {
				c.stop("ended")
				continue
			}
			select {
			case c.wake <- struct{}{}:
			default:
			}
		}
		s.mu.RUnlock()
	}
}

// fill builds the given scopes from one pass of Rows; the caller holds f.build.
// fill dựng các phạm vi đã cho từ một lượt Rows; người gọi giữ f.build.
func (f *Feed) fill(scopes []*scope, now time.Time) {
	rows := f.src.Rows(float64(now.UnixMilli()) / 1000)
	// the rows of the branches read only, by their place in rows
	// chỉ các dòng của những chi nhánh đang được đọc, theo vị trí của chúng trong rows
	byBranch := map[string][]int{}
	for _, s := range scopes {
		if s.name != "org" {
			byBranch[strings.TrimPrefix(s.name, "branch:")] = nil
		}
	}
	for i := range rows {
		if list, ok := byBranch[rows[i].Branch]; ok {
			byBranch[rows[i].Branch] = append(list, i)
		}
	}
	for _, s := range scopes {
		var bodies map[string][]byte
		if s.name == "org" {
			branches := live.Branches(rows)
			bodies = make(map[string][]byte, len(branches))
			for _, b := range branches {
				bodies[b.ID], _ = json.Marshal(b)
			}
		} else {
			list := byBranch[strings.TrimPrefix(s.name, "branch:")]
			bodies = make(map[string][]byte, len(list))
			for _, i := range list {
				bodies[rows[i].Row], _ = json.Marshal(&rows[i])
			}
		}
		s.update(bodies, now)
	}
}

// update puts the new rows of the scope in place: a row whose JSON changed, or that left, gets the next number.
// update đặt các dòng mới của phạm vi vào chỗ: dòng có JSON đổi, hay đã rời đi, nhận số kế tiếp.
func (s *scope) update(bodies map[string][]byte, now time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()
	next, changed := s.seq+1, false
	for k, b := range bodies {
		if old := s.items[k]; old == nil || old.body == nil || !bytes.Equal(old.body, b) {
			s.items[k], changed = &item{seq: next, body: b}, true
		}
	}
	for k, it := range s.items {
		if _, ok := bodies[k]; ok {
			continue
		}
		if it.body != nil {
			s.items[k], changed = &item{seq: next, goneAt: now}, true
		} else if now.Sub(it.goneAt) > keepGone {
			// a board that has not seen this one leave gets the whole scope again
			// bảng chưa thấy dòng này rời đi sẽ nhận lại cả phạm vi
			delete(s.items, k)
			s.floor = max(s.floor, it.seq)
		}
	}
	if changed {
		s.seq = next
	}
	s.built = true
}

// since gives what changed after the number last: the rows (shared, never changed once made) and the keys gone, in the order of the keys;
// whole when last is 0 or older than what the scope still remembers.
// since cho những gì đổi sau số last: các dòng (dùng chung, không bao giờ đổi khi đã làm) và các khoá đã rời đi, theo thứ tự khoá; cả
// phạm vi khi last là 0 hay cũ hơn chỗ phạm vi còn nhớ.
func (s *scope) since(last int64) (rows [][]byte, gone []string, seq int64, whole bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	whole = last <= 0 || last < s.floor
	keys := make([]string, 0, len(s.items))
	for k, it := range s.items {
		if whole && it.body != nil || !whole && it.seq > last {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	for _, k := range keys {
		if b := s.items[k].body; b != nil {
			rows = append(rows, b)
		} else {
			gone = append(gone, k)
		}
	}
	return rows, gone, s.seq, whole
}

// ensure builds a scope nobody read yet, so its first board gets its numbers at once.
// ensure dựng một phạm vi chưa ai đọc, để bảng đầu tiên của nó nhận số ngay.
func (f *Feed) ensure(s *scope) {
	s.mu.RLock()
	built := s.built
	s.mu.RUnlock()
	if built {
		return
	}
	f.build.Lock()
	defer f.build.Unlock()
	s.mu.RLock()
	built = s.built
	s.mu.RUnlock()
	if !built {
		f.fill([]*scope{s}, f.Now())
	}
}

func (s *scope) field() string {
	if s.name == "org" {
		return "branches"
	}
	return "rows"
}

// body writes {"scope", "seq", rows or branches, "gone"} to w, piece by piece, the rows as they are shared: nothing is copied for one board.
// body ghi {"scope", "seq", rows hay branches, "gone"} vào w, từng mảnh một, các dòng đúng như đang dùng chung: không chép gì riêng cho
// một bảng.
func body(w io.Writer, s *scope, seq int64, rows [][]byte, gone []string, whole bool) error {
	name, _ := json.Marshal(s.name)
	head := `{"scope":` + string(name) + `,"seq":` + strconv.FormatInt(seq, 10) + `,"` + s.field() + `":[`
	if _, err := io.WriteString(w, head); err != nil {
		return err
	}
	for i, r := range rows {
		if i > 0 {
			if _, err := io.WriteString(w, ","); err != nil {
				return err
			}
		}
		if _, err := w.Write(r); err != nil {
			return err
		}
	}
	tail := "]"
	if !whole {
		g, _ := json.Marshal(gone)
		if gone == nil {
			g = []byte("[]")
		}
		tail += `,"gone":` + string(g)
	}
	_, err := io.WriteString(w, tail+"}")
	return err
}

func refuse(w http.ResponseWriter, status int, why string) {
	b, _ := json.Marshal(map[string]string{"error": why})
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Length", strconv.Itoa(len(b)))
	w.WriteHeader(status)
	_, _ = w.Write(b)
}

// ServeHTTP answers GET /live and GET /live/snap, for a page of the board's origin with a good ticket for the scope it asks:
// ?t=<ticket>&scope=<scope>. The browser sends no cookie here, and the answer lets only the board's origin read it.
// ServeHTTP trả lời GET /live và GET /live/snap, cho một trang thuộc nguồn của bảng với một vé tốt cho phạm vi nó xin:
// ?t=<vé>&scope=<phạm vi>. Trình duyệt không gửi cookie nào ở đây, và câu trả lời chỉ cho nguồn của bảng đọc.
func (f *Feed) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodGet || (req.URL.Path != "/live" && req.URL.Path != "/live/snap") {
		refuse(w, http.StatusNotFound, "Not found")
		return
	}
	w.Header().Set("X-Robots-Tag", "noindex, nofollow")
	origins, ended, ok := f.src.LivePolicy()
	if !ok {
		w.Header().Set("Retry-After", "5")
		refuse(w, http.StatusServiceUnavailable, "starting")
		return
	}
	origin := req.Header.Get("Origin")
	allowed := false
	for _, o := range origins {
		allowed = allowed || (origin != "" && origin == o)
	}
	if !allowed {
		refuse(w, http.StatusForbidden, "wrong origin")
		return
	}
	w.Header().Set("Access-Control-Allow-Origin", origin)
	w.Header().Set("Vary", "Origin")
	q := req.URL.Query()
	t, why := Check(q.Get("t"), f.Now(), f.keys)
	switch {
	case t == nil:
		refuse(w, http.StatusUnauthorized, why)
		return
	case q.Get("scope") != t.Scope:
		refuse(w, http.StatusForbidden, "wrong scope")
		return
	case ended[t.SID]:
		refuse(w, http.StatusUnauthorized, "session ended")
		return
	}
	s := f.scope(t.Scope)
	f.ensure(s)
	if req.URL.Path == "/live/snap" {
		rows, _, seq, _ := s.since(0)
		var b bytes.Buffer
		_ = body(&b, s, seq, rows, nil, true)
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Length", strconv.Itoa(b.Len()))
		_, _ = w.Write(b.Bytes())
		return
	}
	f.stream(w, req, t, s)
}

// stream sends hello, snap, then d with the rows changed each tick, a comment when quiet for a beat, and bye when the ticket ends or its
// session closes. Each write has WriteWait of its own in place of the server's WriteTimeout, which would cut the feed.
// stream gửi hello, snap, rồi d với các dòng đã đổi mỗi nhịp, một dòng chú thích khi lặng một nhịp tim, và bye khi vé hết hạn hay phiên
// của nó đóng. Mỗi lần ghi có WriteWait riêng thay cho WriteTimeout của máy chủ, thứ sẽ cắt luồng.
func (f *Feed) stream(w http.ResponseWriter, req *http.Request, t *Ticket, s *scope) {
	c := &client{sid: t.SID, wake: make(chan struct{}, 1), end: make(chan string, 1)}
	f.mu.Lock()
	if f.closed || f.feeds >= MaxFeeds {
		f.mu.Unlock()
		w.Header().Set("Retry-After", "30")
		refuse(w, http.StatusServiceUnavailable, "busy")
		return
	}
	f.feeds++
	f.mu.Unlock()
	s.mu.Lock()
	s.clients[c] = struct{}{}
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		delete(s.clients, c)
		s.usedAt = f.Now()
		s.mu.Unlock()
		f.mu.Lock()
		f.feeds--
		f.mu.Unlock()
	}()
	rc := http.NewResponseController(w)
	// the server's ReadTimeout would end the request too: nothing more is read from a board
	// ReadTimeout của máy chủ cũng sẽ kết thúc yêu cầu: không đọc gì thêm từ bảng
	_ = rc.SetReadDeadline(time.Time{})
	h := w.Header()
	h.Set("Content-Type", "text/event-stream; charset=utf-8")
	h.Set("Cache-Control", "no-store")
	h.Set("X-Accel-Buffering", "no")
	// one event: its pieces go straight to the connection under a deadline of their own, then out at once
	// một sự kiện: các mảnh của nó đi thẳng ra kết nối với hạn riêng, rồi được đẩy đi ngay
	event := func(write func(io.Writer) error) bool {
		_ = rc.SetWriteDeadline(time.Now().Add(f.WriteWait))
		bw := bufio.NewWriterSize(w, 4096)
		err := write(bw)
		if err == nil {
			err = bw.Flush()
		}
		if err == nil {
			err = rc.Flush()
		}
		return err == nil
	}
	data := func(name string, s *scope, seq int64, rows [][]byte, gone []string, whole bool) func(io.Writer) error {
		return func(w io.Writer) error {
			if _, err := io.WriteString(w, "event: "+name+"\ndata: "); err != nil {
				return err
			}
			if err := body(w, s, seq, rows, gone, whole); err != nil {
				return err
			}
			_, err := io.WriteString(w, "\n\n")
			return err
		}
	}
	text := func(t string) func(io.Writer) error {
		return func(w io.Writer) error {
			_, err := io.WriteString(w, t)
			return err
		}
	}
	hello, _ := json.Marshal(map[string]any{"v": 1, "scope": t.Scope, "role": t.Role, "expiresAt": t.Expires * 1000, "beatMs": f.Beat.Milliseconds(),
		"tickMs": f.Tick.Milliseconds()})
	rows, _, last, _ := s.since(0)
	if !event(text("event: hello\ndata: "+string(hello)+"\n\n")) || !event(data("snap", s, last, rows, nil, true)) {
		return
	}
	rows = nil
	every := f.Beat
	beat := time.NewTimer(every)
	defer beat.Stop()
	ends := time.NewTimer(time.Until(time.Unix(t.Expires, 0)))
	defer ends.Stop()
	for {
		select {
		case <-req.Context().Done():
			return
		case why := <-c.end:
			event(text("event: bye\ndata: {\"why\":\"" + why + "\"}\n\n"))
			return
		case <-ends.C:
			event(text("event: bye\ndata: {\"why\":\"expired\"}\n\n"))
			return
		case <-beat.C:
			if !event(text(": beat\n\n")) {
				return
			}
			beat.Reset(every)
		case <-c.wake:
			rows, gone, seq, whole := s.since(last)
			if seq == last {
				continue
			}
			name := "d"
			if whole {
				name = "snap"
			}
			last = seq
			if !event(data(name, s, seq, rows, gone, whole)) {
				return
			}
			beat.Reset(every)
		}
	}
}
