package feed

import (
	"bufio"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"aiworker/receiver/internal/devicekey"
	"aiworker/receiver/internal/live"
)

const board = "https://board.example.com"

var secret = []byte("a secret of the tests, 32 bytes!")

type keys map[string][]byte

func (k keys) TicketSecret(kid string) ([]byte, bool) {
	s, ok := k[kid]
	return s, ok
}

// source stands for the receiver: rows set by the test, a policy, and how many times the rows were added up.
// source đứng thay bộ nhận: các dòng do bài test đặt, một chính sách, và số lần các dòng được cộng.
type source struct {
	mu     sync.Mutex
	rows   []live.Row
	ended  map[string]bool
	ready  bool
	passes int
}

func (s *source) Rows(float64) []live.Row {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.passes++
	return append([]live.Row(nil), s.rows...)
}

func (s *source) LivePolicy() ([]string, map[string]bool, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	ended := map[string]bool{}
	for k, v := range s.ended {
		ended[k] = v
	}
	return []string{board}, ended, s.ready
}

func (s *source) set(rows ...live.Row) {
	s.mu.Lock()
	s.rows = rows
	s.mu.Unlock()
}

func (s *source) end(sid string) {
	s.mu.Lock()
	s.ended[sid] = true
	s.mu.Unlock()
}

// row is a person's row with a cost of cents today.
// row là dòng của một người có chi phí hôm nay là cents xu.
func row(code, branch string, cents int64) live.Row {
	return live.Row{Row: code, Branch: branch, Status: live.Open, OpenSessions: 1, USDMicro: cents * 10_000, USDToday: live.Round4(cents * 10_000), Tools: map[string]live.Counts{}}
}

// ticket makes a ticket as server/board/receiver.py make_ticket does (the shared sample holds the two together).
// ticket làm một vé như make_ticket trong server/board/receiver.py (bộ mẫu chung giữ hai bên khớp nhau).
func ticket(kid string, key []byte, role, scope, sid string, expires int64) string {
	body := strings.Join([]string{TicketPrefix, kid, role, base64.RawURLEncoding.EncodeToString([]byte(scope)), sid, strconv.FormatInt(expires, 10)}, ".")
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(body))
	return body + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func goodTicket(scope, sid string) string {
	return ticket("k1", secret, "wall", scope, sid, time.Now().Unix()+TicketSeconds)
}

func start(t *testing.T) (*source, *Feed, *httptest.Server) {
	t.Helper()
	src := &source{ended: map[string]bool{}, ready: true}
	f := New(src, keys{"k1": secret})
	f.Beat = time.Hour
	srv := httptest.NewServer(f)
	t.Cleanup(func() {
		f.Close()
		srv.Close()
	})
	return src, f, srv
}

func ask(t *testing.T, srv *httptest.Server, path, tk, scope, origin string) *http.Response {
	t.Helper()
	req, _ := http.NewRequest(http.MethodGet, srv.URL+path+"?t="+url.QueryEscape(tk)+"&scope="+url.QueryEscape(scope), nil)
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

type event struct{ name, data string }

// next reads one event of a feed; a comment comes as the event ":".
// next đọc một sự kiện của luồng; dòng chú thích đến dưới dạng sự kiện ":".
func next(t *testing.T, r *bufio.Reader) event {
	t.Helper()
	var e event
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			t.Fatalf("feed ended: %v (so far %+v)", err, e)
		}
		line = strings.TrimSuffix(line, "\n")
		switch {
		case line == "" && (e.name != "" || e.data != ""):
			return e
		case strings.HasPrefix(line, ":"):
			if _, err := r.ReadString('\n'); err != nil {
				t.Fatal(err)
			}
			return event{name: ":"}
		case strings.HasPrefix(line, "event: "):
			e.name = line[len("event: "):]
		case strings.HasPrefix(line, "data: "):
			e.data = line[len("data: "):]
		}
	}
}

type payload struct {
	Scope    string        `json:"scope"`
	Seq      int64         `json:"seq"`
	Rows     []live.Row    `json:"rows"`
	Branches []live.Branch `json:"branches"`
	Gone     []string      `json:"gone"`
	Why      string        `json:"why"`
}

func decode(t *testing.T, e event) payload {
	t.Helper()
	var p payload
	if err := json.Unmarshal([]byte(e.data), &p); err != nil {
		t.Fatalf("%s: %v", e.data, err)
	}
	return p
}

func codes(rows []live.Row) string {
	var out []string
	for _, r := range rows {
		out = append(out, fmt.Sprintf("%s=%d", r.Row, r.USDMicro/10_000))
	}
	return strings.Join(out, ",")
}

// TestTheSharedSampleOfTickets: the tickets Python made in tests/contract/ticket/cases.json are good here until they end, and any change
// to one is refused.
// TestTheSharedSampleOfTickets: các vé Python làm trong tests/contract/ticket/cases.json là tốt ở đây cho tới khi hết hạn, và mọi thay
// đổi trên vé đều bị từ chối.
func TestTheSharedSampleOfTickets(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "tests", "contract", "ticket", "cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Kid, Secret string
		Cases       []struct {
			Role, Scope, Sid, Ticket string
			Expires                  int64
		}
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	key, _ := base64.RawURLEncoding.DecodeString(doc.Secret)
	k := keys{doc.Kid: key}
	for _, c := range doc.Cases {
		at := time.Unix(c.Expires-10, 0)
		got, why := Check(c.Ticket, at, k)
		if got == nil || *got != (Ticket{Kid: doc.Kid, Role: c.Role, Scope: c.Scope, SID: c.Sid, Expires: c.Expires}) {
			t.Fatalf("%s: %+v %s", c.Scope, got, why)
		}
		if ticket(doc.Kid, key, c.Role, c.Scope, c.Sid, c.Expires) != c.Ticket {
			t.Fatalf("%s: the tests make another ticket", c.Scope)
		}
		parts := strings.Split(c.Ticket, ".")
		for name, bad := range map[string]struct {
			token string
			at    time.Time
		}{
			"ended":            {c.Ticket, time.Unix(c.Expires, 0)},
			"from too far":     {c.Ticket, time.Unix(c.Expires-TicketSeconds-ticketSlack-1, 0)},
			"other scope":      {strings.Replace(c.Ticket, "."+parts[3]+".", "."+base64.RawURLEncoding.EncodeToString([]byte("branch:x"))+".", 1), at},
			"other sid":        {strings.Replace(c.Ticket, "."+parts[4]+".", ".other-sid.", 1), at},
			"other role":       {strings.Replace(c.Ticket, "."+parts[2]+".", ".admin2.", 1), at},
			"later end":        {strings.Replace(c.Ticket, "."+parts[5]+".", "."+strconv.FormatInt(c.Expires+60, 10)+".", 1), at},
			"other signature":  {c.Ticket[:len(c.Ticket)-1] + map[bool]string{true: "A", false: "B"}[!strings.HasSuffix(c.Ticket, "A")], at},
			"unknown kid":      {strings.Replace(c.Ticket, "."+doc.Kid+".", ".otherkid.", 1), at},
			"a device key":     {strings.Replace(c.Ticket, "awt1.", "awd1.", 1), at},
			"one part more":    {c.Ticket + ".x", at},
			"empty":            {"", at},
			"a dot in a scope": {strings.Replace(c.Ticket, "."+parts[3]+".", ".a.b.", 1), at},
		} {
			if got, _ := Check(bad.token, bad.at, k); got != nil {
				t.Errorf("%s, %s: accepted", c.Scope, name)
			}
		}
	}
	// a ticket signed well but for a scope that is neither org nor a branch
	// một vé ký đúng nhưng cho phạm vi không phải org cũng không phải chi nhánh
	if got, _ := Check(ticket("k1", secret, "wall", "everything", "s", time.Now().Unix()+60), time.Now(), keys{"k1": secret}); got != nil {
		t.Error("an unknown scope was accepted")
	}
}

// TestTicketsFromThePythonServer: tickets given by the server's own Tickets.issue, checked with the file of secrets it wrote.
// TestTicketsFromThePythonServer: vé do chính Tickets.issue của máy chủ cấp, kiểm bằng file bí mật nó đã ghi.
func TestTicketsFromThePythonServer(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found: the judge cannot run")
	}
	out, err := exec.Command(python, "-I", filepath.Join("..", "..", "..", "tests", "contract", "ingest-v2", "keys_judge.py"), t.TempDir()).Output()
	if err != nil {
		t.Fatalf("judge: %v", err)
	}
	var judged struct {
		Now     float64 `json:"now"`
		Secrets string  `json:"secrets"`
		Tickets []struct {
			Ticket, Scope, Role string
			ExpiresAt           int64
		} `json:"tickets"`
	}
	if err := json.Unmarshal(out, &judged); err != nil {
		t.Fatal(err)
	}
	s, err := devicekey.Load(judged.Secrets)
	if err != nil {
		t.Fatal(err)
	}
	if len(judged.Tickets) < 2 {
		t.Fatal("no tickets")
	}
	for _, tk := range judged.Tickets {
		got, why := Check(tk.Ticket, time.Unix(int64(judged.Now), 0), s)
		if got == nil || got.Scope != tk.Scope || got.Role != tk.Role || got.Expires*1000 != tk.ExpiresAt || got.Expires != int64(judged.Now)+TicketSeconds {
			t.Fatalf("%+v %s", got, why)
		}
		// the device keys' secrets cannot check a ticket, nor the ticket's secret a device key
		// bí mật của khoá máy không kiểm được vé, và bí mật của vé không kiểm được khoá máy
		if _, why := s.Check(tk.Ticket, judged.Now, nil); why != "not a device key" {
			t.Fatalf("a ticket as a key: %s", why)
		}
	}
}

// TestTheFeedIsRefused: only a page of the board's origin, with a ticket that is good now, for the scope it asks, whose session is open.
// TestTheFeedIsRefused: chỉ một trang thuộc nguồn của bảng, với vé còn tốt lúc này, cho đúng phạm vi nó xin, có phiên còn mở.
func TestTheFeedIsRefused(t *testing.T) {
	src, f, srv := start(t)
	src.set(row("r1", "a", 1))
	good := goodTicket("branch:a", "sid-1")
	src.end("sid-gone")
	for name, c := range map[string]struct {
		path, ticket, scope, origin string
		status                      int
	}{
		"expired":        {"/live", ticket("k1", secret, "wall", "branch:a", "sid-1", time.Now().Unix()-1), "branch:a", board, 401},
		"expired snap":   {"/live/snap", ticket("k1", secret, "wall", "branch:a", "sid-1", time.Now().Unix()-1), "branch:a", board, 401},
		"wrong scope":    {"/live", good, "branch:b", board, 403},
		"wrong scope 2":  {"/live/snap", good, "org", board, 403},
		"ended session":  {"/live", goodTicket("branch:a", "sid-gone"), "branch:a", board, 401},
		"ended snap":     {"/live/snap", goodTicket("branch:a", "sid-gone"), "branch:a", board, 401},
		"another site":   {"/live", good, "branch:a", "https://other.example.com", 403},
		"no origin":      {"/live", good, "branch:a", "", 403},
		"another secret": {"/live", ticket("k1", []byte("not the secret of the receiver!!"), "wall", "branch:a", "sid-1", time.Now().Unix()+60), "branch:a", board, 401},
		"no ticket":      {"/live", "", "branch:a", board, 401},
		"another path":   {"/live/other", good, "branch:a", board, 404},
	} {
		resp := ask(t, srv, c.path, c.ticket, c.scope, c.origin)
		_, _ = io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		if resp.StatusCode != c.status {
			t.Errorf("%s: %d, want %d", name, resp.StatusCode, c.status)
		}
		if c.origin != board && resp.Header.Get("Access-Control-Allow-Origin") != "" {
			t.Errorf("%s: another origin may read the answer", name)
		}
	}
	src.mu.Lock()
	src.ready = false
	src.mu.Unlock()
	if resp := ask(t, srv, "/live", good, "branch:a", board); resp.StatusCode != http.StatusServiceUnavailable {
		t.Errorf("no policy yet: %d", resp.StatusCode)
	}
	if f.Feeds() != 0 {
		t.Fatal("a refused feed was counted")
	}
}

// TestTheFeedSendsOnlyWhatChanged: hello and the whole scope, then each tick only the rows changed and the ones gone; the organisation
// gets the totals of each branch only; each tick adds the computers up once for every board.
// TestTheFeedSendsOnlyWhatChanged: hello và cả phạm vi, rồi mỗi nhịp chỉ các dòng đã đổi và các dòng đã rời đi; cả tổ chức chỉ nhận tổng
// của từng chi nhánh; mỗi nhịp cộng các máy một lần cho mọi bảng.
func TestTheFeedSendsOnlyWhatChanged(t *testing.T) {
	src, f, srv := start(t)
	src.set(row("r1", "a", 10), row("r2", "a", 20), row("r3", "b", 30))
	open := func(scope string) (*bufio.Reader, func()) {
		resp := ask(t, srv, "/live", goodTicket(scope, "sid-"+strings.ReplaceAll(scope, ":", "-")), scope, board)
		if resp.StatusCode != 200 || resp.Header.Get("Content-Type") != "text/event-stream; charset=utf-8" || resp.Header.Get("Access-Control-Allow-Origin") != board {
			t.Fatalf("%s: %d %v", scope, resp.StatusCode, resp.Header)
		}
		return bufio.NewReader(resp.Body), func() { resp.Body.Close() }
	}
	a, closeA := open("branch:a")
	defer closeA()
	if e := next(t, a); e.name != "hello" || !strings.Contains(e.data, `"scope":"branch:a"`) || !strings.Contains(e.data, `"beatMs"`) {
		t.Fatalf("%+v", e)
	}
	snap := decode(t, next(t, a))
	if codes(snap.Rows) != "r1=10,r2=20" || snap.Gone != nil {
		t.Fatalf("snap %+v", snap)
	}
	org, closeOrg := open("org")
	defer closeOrg()
	next(t, org)
	if s := decode(t, next(t, org)); len(s.Branches) != 2 || s.Rows != nil || s.Branches[0].ID != "a" || s.Branches[0].People != 2 || s.Branches[0].USDToday != 0.3 {
		t.Fatalf("org %+v", s)
	}
	b2, closeB2 := open("branch:a")
	defer closeB2()
	next(t, b2)
	next(t, b2)

	// r2 changes, r1 does not, r3 moves to branch a and r1 leaves... one at a time
	// r2 đổi, r1 không đổi, r3 chuyển sang chi nhánh a và r1 rời đi... từng việc một
	src.set(row("r1", "a", 10), row("r2", "a", 25), row("r3", "b", 30))
	src.mu.Lock()
	before := src.passes
	src.mu.Unlock()
	f.Step()
	src.mu.Lock()
	if src.passes != before+1 {
		t.Errorf("one tick added the computers up %d times", src.passes-before)
	}
	src.mu.Unlock()
	d := decode(t, next(t, a))
	if codes(d.Rows) != "r2=25" || len(d.Gone) != 0 || d.Seq <= snap.Seq {
		t.Fatalf("d %+v", d)
	}
	if d2 := decode(t, next(t, b2)); codes(d2.Rows) != "r2=25" {
		t.Fatalf("the second board: %+v", d2)
	}
	if o := decode(t, next(t, org)); len(o.Branches) != 1 || o.Branches[0].ID != "a" || o.Branches[0].USDToday != 0.35 {
		t.Fatalf("org d %+v", o)
	}
	src.set(row("r2", "a", 25), row("r3", "a", 30))
	f.Step()
	if d := decode(t, next(t, a)); codes(d.Rows) != "r3=30" || strings.Join(d.Gone, ",") != "r1" {
		t.Fatalf("moved %+v", d)
	}
	// nothing changed: nothing is sent until the beat
	// không gì đổi: không gửi gì cho tới nhịp tim
	quiet, fq, sq := start(t)
	fq.Beat = 50 * time.Millisecond
	quiet.set(row("r1", "a", 1))
	resp := ask(t, sq, "/live", goodTicket("branch:a", "sid-quiet"), "branch:a", board)
	defer resp.Body.Close()
	c := bufio.NewReader(resp.Body)
	next(t, c)
	next(t, c)
	fq.Step()
	if e := next(t, c); e.name != ":" {
		t.Fatalf("expected the beat, got %+v", e)
	}
	// the snapshot gives the same numbers once, and keeps the scope built for a while
	// ảnh chụp cho cùng các con số một lần, và giữ phạm vi được dựng thêm một lúc
	resp = ask(t, srv, "/live/snap", goodTicket("branch:a", "s"), "branch:a", board)
	var p payload
	if err := json.NewDecoder(resp.Body).Decode(&p); err != nil || codes(p.Rows) != "r2=25,r3=30" || resp.Header.Get("Access-Control-Allow-Origin") != board {
		t.Fatalf("snap %+v %v", p, err)
	}
	resp.Body.Close()
}

// TestTheFeedEnds: at the end of its ticket, and within a tick once the policy names its session as closed.
// TestTheFeedEnds: khi vé của nó hết hạn, và trong một nhịp khi chính sách nêu phiên của nó đã đóng.
func TestTheFeedEnds(t *testing.T) {
	src, f, srv := start(t)
	src.set(row("r1", "a", 1))
	resp := ask(t, srv, "/live", goodTicket("branch:a", "sid-out"), "branch:a", board)
	r := bufio.NewReader(resp.Body)
	next(t, r)
	next(t, r)
	src.end("sid-out")
	f.Step()
	if e := next(t, r); e.name != "bye" || decode(t, e).Why != "ended" {
		t.Fatalf("%+v", e)
	}
	if _, err := r.ReadString('\n'); err != io.EOF {
		t.Fatalf("the feed is still open: %v", err)
	}
	resp.Body.Close()
	resp = ask(t, srv, "/live", ticket("k1", secret, "wall", "branch:a", "sid-2", time.Now().Unix()+2), "branch:a", board)
	defer resp.Body.Close()
	r = bufio.NewReader(resp.Body)
	next(t, r)
	next(t, r)
	if e := next(t, r); e.name != "bye" || decode(t, e).Why != "expired" {
		t.Fatalf("%+v", e)
	}
	waitFor(t, func() bool { return f.Feeds() == 0 })
}

func waitFor(t *testing.T, ok func() bool) {
	t.Helper()
	for i := 0; i < 200; i++ {
		if ok() {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatal("waited too long")
}

// TestASlowBoardHoldsNothing: a board that never reads, while every row changes on every tick, is cut once a write waits longer than
// WriteWait, and the memory taken meanwhile stays the size of one scope, not of what it missed.
// TestASlowBoardHoldsNothing: một bảng không bao giờ đọc, trong lúc mọi dòng đổi ở mỗi nhịp, bị cắt khi một lần ghi chờ lâu hơn WriteWait,
// và bộ nhớ dùng trong lúc đó chỉ cỡ một phạm vi, không cỡ những gì nó đã bỏ lỡ.
func TestASlowBoardHoldsNothing(t *testing.T) {
	src, f, srv := start(t)
	f.WriteWait = 2 * time.Second
	many := func(usd int64) []live.Row {
		rows := make([]live.Row, 4000)
		for i := range rows {
			rows[i] = row(fmt.Sprintf("r%011d", i), "a", usd+int64(i))
			rows[i].Tools = map[string]live.Counts{"claude": {OpenSessions: 1}, "codex": {OpenSessions: 2}}
		}
		return rows
	}
	src.set(many(0)...)
	conn, err := net.Dial("tcp", strings.TrimPrefix(srv.URL, "http://"))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	q := "/live?t=" + url.QueryEscape(goodTicket("branch:a", "sid-slow")) + "&scope=branch:a"
	fmt.Fprintf(conn, "GET %s HTTP/1.1\r\nHost: x\r\nOrigin: %s\r\n\r\n", q, board)
	waitFor(t, func() bool { return f.Feeds() == 1 })
	runtime.GC()
	var before runtime.MemStats
	runtime.ReadMemStats(&before)
	peak := uint64(0)
	size := 0
	ticks := 0
	for i := 1; f.Feeds() > 0; i++ {
		ticks = i
		if i > 400 {
			t.Fatal("the slow board was never cut")
		}
		rows := many(int64(i) * 1_000_000)
		src.set(rows...)
		f.Step()
		if size == 0 {
			b, _ := json.Marshal(rows)
			size = len(b)
		}
		runtime.GC()
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		peak = max(peak, m.HeapAlloc)
		time.Sleep(20 * time.Millisecond)
	}
	t.Logf("cut after %d ticks of %d bytes each; the heap grew %d", ticks, size, int64(peak)-int64(before.HeapAlloc))
	if ticks < 10 {
		t.Fatalf("cut after %d ticks only: the test shows nothing", ticks)
	}
	// the scope itself (one copy of its rows, and the one before while a write is on its way) is all that grows
	// chỉ phạm vi (một bản các dòng của nó, và bản trước khi một lần ghi đang đi) là thứ lớn lên
	if grown := int64(peak) - int64(before.HeapAlloc); grown > int64(6*size) {
		t.Fatalf("the heap grew %d bytes for a scope of %d", grown, size)
	}
}
