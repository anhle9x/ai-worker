// Package ingest takes the sends of the computers on POST /ingest. A send with a computer's own key is checked, cleaned and put on the
// hour book held here, answered at once, and handed to the Python server in batches numbered by seq; any other send (the shared key, a
// key due for renewal, bytes this side is not sure of) is passed to Python as it came, with the real address of the computer.
// Package ingest nhận các lần gửi của máy trên POST /ingest. Lần gửi có khoá riêng của máy được kiểm, làm sạch và đặt lên sổ giờ giữ ở
// đây, trả lời ngay, rồi trao cho máy chủ Python theo lô có số thứ tự seq; mọi lần gửi khác (khoá chung, khoá tới hạn gia hạn, các byte
// bên này không chắc) được chuyển nguyên văn cho Python, kèm địa chỉ thật của máy.
package ingest

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	mrand "math/rand/v2"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/devicekey"
	"aiworker/receiver/internal/live"
	"aiworker/receiver/internal/people"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

// Limits of this side; the ones the computers are told come from Python's policy.
// Các giới hạn của bên này; những gì dặn các máy thì lấy từ chính sách của Python.
const (
	MaxBodyBytes  = 256 * 1024
	maxBatchRows  = 2000
	maxPending    = 200_000
	maxChecks     = 1000
	busyRetry     = "5"
	policyEvery   = 15 * time.Second
	peopleEvery   = 15 * time.Second
	devicesPage   = 1000
	maxRetryPause = 30 * time.Second
	// how long the oldest row may wait for Python before /health says the receiver is behind; rows keep waiting, one per computer
	// dòng chờ lâu nhất được chờ Python bao lâu trước khi /health báo bộ nhận đang chậm; các dòng vẫn chờ tiếp, mỗi máy một dòng
	behindAfter = 60 * time.Second
	forwardMax  = 16
)

// Policy is the numbered policy document of the Python server (board/receiver.py, Policy.document).
// Policy là tài liệu chính sách có số thứ tự của máy chủ Python (board/receiver.py, Policy.document).
type Policy struct {
	Proto           int64    `json:"proto"`
	Seq             int64    `json:"seq"`
	Boot            string   `json:"boot"`
	Reset           bool     `json:"reset"`
	Written         []string `json:"written"`
	Revoked         []string `json:"revoked"`
	RenewBefore     int64    `json:"renewBefore"`
	SharedKeyMode   string   `json:"sharedKeyMode"`
	MinGapMs        int64    `json:"minGapMs"`
	StateGapMs      int64    `json:"stateGapMs"`
	MaxGapMs        int64    `json:"maxGapMs"`
	IngestBurst     float64  `json:"ingestBurst"`
	IngestPerSecond float64  `json:"ingestPerSecond"`
	MaxBodyBytes    int64    `json:"maxBodyBytes"`
	CheckPercent    float64  `json:"checkPercent"`
	TzHours         float64  `json:"tzHours"`
	Checked         int64    `json:"checked"`
	Mismatches      int64    `json:"mismatches"`
	// BoardOrigins: the pages allowed to open the live feed; EndedSessions: the sids of sessions closed while their ticket lives
	// BoardOrigins: các trang được mở luồng số trực tiếp; EndedSessions: sid của các phiên đã đóng trong lúc vé của chúng còn sống
	BoardOrigins  []string `json:"boardOrigins"`
	EndedSessions []string `json:"endedSessions"`
	revoked       map[string]bool
	ended         map[string]bool
}

// entry is what is held for one computer; its lock is taken for the whole of one send, so two sends of one computer never merge on the
// same old book. rec holds the time of the last send and the hours of today and later as numbers (held): the whole book is Python's.
// entry là thứ giữ cho một máy; khoá của nó được giữ suốt một lần gửi, để hai lần gửi của một máy không bao giờ ghép trên cùng một sổ cũ.
// rec giữ thời điểm của lần gửi cuối và các giờ từ hôm nay trở đi dưới dạng số (held): cả sổ là của Python.
type entry struct {
	mu       sync.Mutex
	loaded   bool
	rec      *held
	lastFull float64
	everFull bool
	// forward: Python does not know this computer's person, so its sends go to Python until it does
	// forward: Python không biết người của máy này, nên lần gửi của nó đi tới Python cho tới khi biết
	forward bool
	// askName: Python knows this computer's person without an email or a name; a send that carries one goes to Python, which fills it in
	// askName: Python biết người của máy này mà thiếu email hay tên; lần gửi có mang chúng đi tới Python, nơi chúng được điền
	askName bool
	tokens  float64
	counted float64
}

// Receiver holds the books, the rows waiting for Python and the latest policy.
// Receiver giữ các sổ, các dòng chờ gửi cho Python và tài liệu chính sách mới nhất.
type Receiver struct {
	webhook string
	secrets *devicekey.Secrets
	client  *http.Client
	every   time.Duration
	// Boot is a new value at every start of this receiver, given to the computers in place of Python's: rows not yet written are lost
	// when it stops, and a computer that sees it change sends its latest hours again
	// Boot là giá trị mới mỗi lần bộ nhận này khởi động, đưa cho các máy thay cho giá trị của Python: các dòng chưa ghi bị mất khi nó
	// dừng, và máy thấy nó đổi thì gửi lại các giờ gần nhất
	Boot   string
	src    string
	Totals *totals.Store
	// People is each computer's row on the board and its branch, as Python last said (/internal/people), asked every 15 seconds
	// People là dòng trên bảng và chi nhánh của mỗi máy, như Python nói lần gần nhất (/internal/people), hỏi mỗi 15 giây
	People *people.Table
	// Live is each computer's state as its last send left it, added up with Totals per row of People (package live)
	// Live là trạng thái của từng máy như lần gửi cuối để lại, cộng cùng Totals theo từng dòng của People (gói live)
	Live *live.Store
	// Now gives the clock in whole milliseconds, so Python works out the same seconds from a row's "at"; tests set it
	// Now cho đồng hồ theo số nguyên mili giây, để Python tính ra đúng cùng số giây từ "at" của một dòng; bài test đặt nó
	Now func() int64

	mu      sync.Mutex
	policy  *Policy
	entries map[string]*entry
	// stale: computers Python wrote itself or holds otherwise than this side, whose state and totals are read again from Python
	// (Resync); reloadAll: another start of Python, every book is read again
	// stale: các máy Python tự ghi hay giữ khác bên này, có trạng thái và tổng được đọc lại từ Python (Resync); reloadAll: một lần
	// khởi động khác của Python, mọi sổ được đọc lại
	stale     map[string]bool
	reloadAll bool

	// forwardSlots bounds the sends passed to Python at once; a send that finds none free is told to come back at once, instead of
	// waiting in a queue for up to 30 seconds
	// forwardSlots giới hạn số lần gửi chuyển cho Python cùng lúc; lần gửi không còn chỗ thì được báo quay lại ngay, thay vì
	// chờ trong hàng tới 30 giây
	forwardSlots chan struct{}

	// one row per computer waits for the next batch, its sends since the last one put together; a batch on its way is never changed,
	// so sent again after an error it is the same batch under the same seq
	// mỗi máy một dòng chờ lô kế tiếp, các lần gửi của nó từ lô trước được gộp lại; lô đang đi thì không bao giờ bị đổi, nên gửi lại
	// sau một lỗi vẫn đúng lô đó với cùng seq
	qmu      sync.Mutex
	pending  map[string]*waiting
	order    []string
	checks   []pyjson.Value
	inflight *batch
	seq      int64
	wake     chan struct{}
	// sorted: how many computers at the head of order are in the order of their ids (see take); behind: /health says so
	// sorted: bao nhiêu máy ở đầu order đang theo thứ tự mã (xem take); behind: /health đang báo chậm
	sorted int
	behind bool
}

// batch is a numbered batch of rows on its way to Python.
// batch là một lô dòng có số thứ tự đang trên đường tới Python.
type batch struct {
	seq     int64
	rows    []pyjson.Value
	devices map[string]bool
	// oldest is when the oldest of its rows began to wait, in milliseconds
	// oldest là lúc dòng chờ lâu nhất trong lô bắt đầu chờ, tính bằng mili giây
	oldest int64
}

// waiting is what waits for Python for one computer: its newest cleaned send, the kind of the row, and the records of work handed to
// helpers of every send since the last batch. Hours sent as "hours" are put together, the later one of an hour winning (an empty one
// still removes it); hours sent on a whole book are put on that book, so Python writes once what it would have written send by send.
// waiting là thứ chờ Python của một máy: lần gửi đã làm sạch mới nhất, loại của dòng, và biên bản giao việc của mọi lần gửi kể từ lô
// trước. Các giờ gửi dạng "hours" được gộp, giờ gửi sau thắng (giờ rỗng vẫn xoá giờ đó); các giờ gửi trên một sổ đủ được đặt lên sổ
// đó, để Python ghi một lần đúng thứ nó đã ghi qua từng lần gửi.
type waiting struct {
	d           *pyjson.Object
	kind, ip    string
	at          int64
	delegations []pyjson.Value
	// since is when this computer began to wait for the next batch, in milliseconds
	// since là lúc máy này bắt đầu chờ lô kế tiếp, tính bằng mili giây
	since int64
}

func (p *waiting) add(d *pyjson.Object, kind, ip string, at int64, delegations []pyjson.Value) {
	p.delegations = append(p.delegations, delegations...)
	p.ip, p.at = ip, at
	switch {
	case kind == "delegations":
		if p.d == nil {
			p.d, p.kind = d, kind
		}
	case kind == "hours" && p.kind == "hours":
		p.d = withHours(d, unionHours(p.d, d))
	case kind == "hours" && (p.kind == "v1" || p.kind == "full"):
		p.d = withHours(d, clean.MergeHours(p.d, d))
	default:
		p.d, p.kind = d, kind
	}
}

// unionHours puts the hours of b over those of a, each kind apart, empty tables kept: they remove an hour.
// unionHours đặt các giờ của b lên các giờ của a, từng loại riêng, giữ bảng rỗng: chúng xoá một giờ.
func unionHours(a, b *pyjson.Object) *pyjson.Object {
	out := pyjson.NewObject()
	for _, kind := range []string{"ledger", "tasks", "blocks"} {
		table := pyjson.NewObject()
		for _, src := range []*pyjson.Object{a, b} {
			if t, ok := field(src, kind).(*pyjson.Object); ok {
				for i, h := range t.Keys {
					table.Set(h, t.Vals[i])
				}
			}
		}
		if table.Len() > 0 || kind != "blocks" {
			out.Set(kind, table)
		}
	}
	return out
}

// withHours is a copy of d with its hour tables taken from hours.
// withHours là bản sao của d với các bảng giờ lấy từ hours.
func withHours(d, hours *pyjson.Object) *pyjson.Object {
	out := d.Copy()
	for _, kind := range []string{"ledger", "tasks", "blocks"} {
		if t, ok := hours.Get(kind); ok {
			out.Set(kind, t)
		} else {
			out.Delete(kind)
		}
	}
	return out
}

// held is what this side keeps of a computer's book: the updatedAt of its last send, and its ledger and tasks hours of today and later.
// held là thứ bên này giữ của sổ một máy: updatedAt của lần gửi cuối, và các giờ ledger và tasks từ hôm nay trở đi.
type held struct {
	updatedAt     pyjson.Value
	ledger, tasks map[int64]totals.Hour
}

// heldFrom keeps of a record ({device, updatedAt, ledger, tasks, ...}) its time and its hours from hour lo on.
// heldFrom giữ của một bản ghi ({device, updatedAt, ledger, tasks, ...}) thời điểm và các giờ từ giờ lo trở đi.
func heldFrom(rec *pyjson.Object, lo int64) *held {
	if rec == nil {
		return nil
	}
	h := &held{updatedAt: field(rec, "updatedAt"), ledger: map[int64]totals.Hour{}, tasks: map[int64]totals.Hour{}}
	h.put(rec, lo, false)
	return h
}

// put puts the ledger and tasks hours of d from hour lo on; with removing, an empty hour removes the one held.
// put đặt các giờ ledger và tasks của d từ giờ lo trở đi; với removing, giờ rỗng xoá giờ đang giữ.
func (h *held) put(d *pyjson.Object, lo int64, removing bool) {
	for kind, book := range map[string]map[int64]totals.Hour{"ledger": h.ledger, "tasks": h.tasks} {
		t, ok := field(d, kind).(*pyjson.Object)
		if !ok {
			continue
		}
		for i, hour := range t.Keys {
			n, err := strconv.ParseInt(hour, 10, 64)
			if err != nil || n < lo {
				continue
			}
			if v, ok := t.Vals[i].(*pyjson.Object); ok && v.Len() == 0 {
				if removing {
					delete(book, n)
				}
				continue
			}
			book[n] = totals.HourOf(kind, t.Vals[i])
		}
	}
}

// next is what is held after a send of that kind: a whole book replaces the hours, changed hours go on them; hours before lo leave.
// next là thứ được giữ sau một lần gửi loại đó: sổ đủ thay các giờ, các giờ đã đổi được đặt lên chúng; giờ trước lo thì rời đi.
func (h *held) next(d *pyjson.Object, kind string, lo int64) *held {
	out := &held{updatedAt: field(d, "updatedAt"), ledger: map[int64]totals.Hour{}, tasks: map[int64]totals.Hour{}}
	if kind == "hours" && h != nil {
		keepFrom(out.ledger, h.ledger, lo)
		keepFrom(out.tasks, h.tasks, lo)
	}
	out.put(d, lo, kind == "hours")
	return out
}

func keepFrom(dst, src map[int64]totals.Hour, lo int64) {
	for n, v := range src {
		if n >= lo {
			dst[n] = v
		}
	}
}

// kept is the record Decide looks at: only the time of the last send counts there once the hours are Python's.
// kept là bản ghi Decide xem: khi các giờ là của Python thì ở đó chỉ thời điểm của lần gửi cuối là có ý nghĩa.
func (h *held) kept(device string) *pyjson.Object {
	if h == nil {
		return nil
	}
	o := pyjson.NewObject()
	o.Set("device", device)
	o.Set("updatedAt", h.updatedAt)
	return o
}

// New makes a receiver that talks to the Python server at webhook (http://127.0.0.1:port).
// New tạo một bộ nhận nói chuyện với máy chủ Python ở webhook (http://127.0.0.1:cổng).
func New(webhook string, secrets *devicekey.Secrets, every time.Duration) *Receiver {
	b := make([]byte, 8)
	_, _ = rand.Read(b)
	t := totals.NewStore()
	return &Receiver{
		Totals: t, Live: live.New(t),
		webhook: strings.TrimRight(webhook, "/"), secrets: secrets, every: every, Boot: hex.EncodeToString(b), src: "go-" + hex.EncodeToString(b[:4]),
		client: &http.Client{Timeout: 30 * time.Second, Transport: &http.Transport{MaxIdleConnsPerHost: 8, MaxConnsPerHost: 16, DisableCompression: true,
			// the Python server answers HTTP/1.0 and closes the connection after each answer
			// máy chủ Python trả lời HTTP/1.0 và đóng kết nối sau mỗi câu trả lời
			DisableKeepAlives: true, ForceAttemptHTTP2: false, Proxy: nil}},
		People: people.New(), Now: func() int64 { return time.Now().UnixMilli() }, entries: map[string]*entry{}, stale: map[string]bool{},
		wake:         make(chan struct{}, 1),
		pending:      map[string]*waiting{},
		forwardSlots: make(chan struct{}, forwardMax),
	}
}

func (r *Receiver) internal(ctx context.Context, method, path string, body []byte) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, method, r.webhook+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+r.secrets.Internal())
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return r.client.Do(req)
}

func (r *Receiver) getJSON(ctx context.Context, path string, into any) error {
	resp, err := r.internal(ctx, http.MethodGet, path, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, resp.Body)
		return fmt.Errorf("%s: %s", path, resp.Status)
	}
	return json.NewDecoder(io.LimitReader(resp.Body, 64<<20)).Decode(into)
}

// Policy gives the latest policy, nil until the first one came.
// Policy trả tài liệu chính sách mới nhất, nil cho tới khi có cái đầu tiên.
func (r *Receiver) Policy() *Policy {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.policy
}

// RefreshPolicy asks Python for the policy since the one held, and drops the books Python wrote itself since then.
// RefreshPolicy hỏi Python tài liệu chính sách kể từ bản đang giữ, và bỏ các sổ mà Python đã tự ghi từ lúc đó.
func (r *Receiver) RefreshPolicy(ctx context.Context) error {
	since, boot := int64(0), ""
	if p := r.Policy(); p != nil {
		since, boot = p.Seq, p.Boot
	}
	var p Policy
	if err := r.getJSON(ctx, "/internal/policy?since="+strconv.FormatInt(since, 10)+"&boot="+url.QueryEscape(boot), &p); err != nil {
		return err
	}
	p.revoked, p.ended = map[string]bool{}, map[string]bool{}
	for _, d := range p.Revoked {
		p.revoked[d] = true
	}
	for _, sid := range p.EndedSessions {
		p.ended[sid] = true
	}
	// the entries are changed after r.mu is let go: a send holds its entry's lock while it reads the policy, so taking the two the other
	// way round here could leave both waiting for ever
	// các entry được đổi sau khi đã nhả r.mu: một lần gửi giữ khoá entry của nó trong lúc đọc chính sách, nên ở đây lấy hai khoá theo
	// thứ tự ngược lại có thể làm cả hai chờ nhau mãi
	var drop []*entry
	r.mu.Lock()
	if p.Reset && r.policy != nil {
		// another start of Python, or this side fell behind: every book is read again from Python (Resync)
		// một lần khởi động khác của Python, hoặc bên này đã chậm: mọi sổ được đọc lại từ Python (Resync)
		for _, e := range r.entries {
			drop = append(drop, e)
		}
		r.reloadAll = true
	}
	for _, d := range p.Written {
		if e := r.entries[d]; e != nil {
			drop = append(drop, e)
		}
		// a computer Python wrote itself: its state on the board is Python's, read again
		// máy Python tự ghi: trạng thái của nó trên bảng là của Python, được đọc lại
		r.stale[d] = true
	}
	r.policy = &p
	r.mu.Unlock()
	for _, e := range drop {
		e.mu.Lock()
		e.loaded, e.rec = false, nil
		e.mu.Unlock()
	}
	return nil
}

// RefreshPeople asks Python for the changes of the table of people since the number held, and gives the computers whose row or
// branch changed.
// RefreshPeople xin Python các thay đổi của bảng người kể từ số đang giữ, và cho các máy đã đổi dòng hay chi nhánh.
func (r *Receiver) RefreshPeople(ctx context.Context) ([]string, error) {
	return r.People.Refresh(ctx, r.getJSON)
}

// LoadBooks reads every book Python holds, a page at a time; a book already loaded or changed here is left as it is.
// LoadBooks đọc mọi sổ Python đang giữ, từng trang một; sổ đã nạp hoặc đã đổi ở đây thì để nguyên.
func (r *Receiver) LoadBooks(ctx context.Context) (int, error) {
	after, count := "", 0
	for {
		var page struct {
			Devices []json.RawMessage `json:"devices"`
			Next    *string           `json:"next"`
		}
		if err := r.getJSON(ctx, "/internal/devices?limit="+strconv.Itoa(devicesPage)+"&after="+url.QueryEscape(after), &page); err != nil {
			return count, err
		}
		for _, raw := range page.Devices {
			rec, err := pyjson.Parse(raw)
			o, ok := rec.(*pyjson.Object)
			if err != nil || !ok {
				continue
			}
			device, _ := o.Get("device")
			name, _ := device.(string)
			e := r.entry(name)
			e.mu.Lock()
			if !e.loaded {
				e.loaded, e.rec = true, heldFrom(o, r.today())
				r.show(name, o, e.rec)
				count++
			}
			e.mu.Unlock()
		}
		if page.Next == nil {
			return count, nil
		}
		after = *page.Next
	}
}

func (r *Receiver) entry(device string) *entry {
	r.mu.Lock()
	defer r.mu.Unlock()
	e := r.entries[device]
	if e == nil {
		e = &entry{}
		r.entries[device] = e
	}
	return e
}

// load gets one computer's book from Python when it is not held here; e.mu is held.
// load lấy sổ của một máy từ Python khi ở đây chưa giữ; e.mu đang được giữ.
func (r *Receiver) load(ctx context.Context, device string, e *entry) error {
	if e.loaded {
		return nil
	}
	o, err := r.record(ctx, device)
	if err != nil {
		return err
	}
	e.loaded, e.rec = true, heldFrom(o, r.today())
	r.show(device, o, e.rec)
	return nil
}

// record is one computer's record as Python holds it (book_for_receiver), nil if it has none.
// record là bản ghi của một máy như Python giữ (book_for_receiver), nil nếu không có.
func (r *Receiver) record(ctx context.Context, device string) (*pyjson.Object, error) {
	var page struct {
		Devices []json.RawMessage `json:"devices"`
	}
	if err := r.getJSON(ctx, "/internal/devices?device="+url.QueryEscape(device), &page); err != nil {
		return nil, err
	}
	if len(page.Devices) == 1 {
		if v, err := pyjson.Parse(page.Devices[0]); err == nil {
			o, _ := v.(*pyjson.Object)
			return o, nil
		}
	}
	return nil, nil
}

// show puts a computer's state (from a cleaned send or a record of Python) and the totals of its hours held on the live numbers; no
// record takes it off them.
// show đặt trạng thái của một máy (từ một lần gửi đã làm sạch hay một bản ghi của Python) và tổng các giờ đang giữ của nó lên số trực
// tiếp; không có bản ghi thì bỏ nó ra.
func (r *Receiver) show(device string, rec *pyjson.Object, h *held) {
	st, ok := live.StateOf(rec)
	if !ok {
		r.Live.Drop(device)
		r.Totals.Drop(device)
		return
	}
	tz := int64(0)
	if p := r.Policy(); p != nil {
		tz = int64(p.TzHours * 3600)
	}
	if h == nil {
		h = heldFrom(rec, totals.FirstHour(float64(r.Now())/1000, tz))
	}
	r.Totals.Put(device, totals.DaysOf(h.ledger, h.tasks, tz))
	r.Live.Put(device, st)
}

// Rows is the live numbers at the second now: one row per person Python placed in its table of people, in the time zone of the policy.
// Rows là số trực tiếp ở giây now: mỗi người Python đã xếp chỗ trong bảng người một dòng, theo múi giờ của chính sách.
func (r *Receiver) Rows(now float64) []live.Row {
	tz := int64(0)
	if p := r.Policy(); p != nil {
		tz = int64(p.TzHours * 3600)
	}
	return r.Live.Rows(now, tz, r.People.Get)
}

// LivePolicy gives the live feed what it needs of the latest policy (package feed): the board's origins and the sessions ended.
// LivePolicy cho luồng số trực tiếp những gì nó cần từ chính sách mới nhất (gói feed): các nguồn của bảng và các phiên đã kết thúc.
func (r *Receiver) LivePolicy() ([]string, map[string]bool, bool) {
	p := r.Policy()
	if p == nil {
		return nil, nil, false
	}
	return p.BoardOrigins, p.ended, true
}

// markStale has one computer's state and totals read again from Python at the next Resync.
// markStale cho trạng thái và tổng của một máy được đọc lại từ Python ở lần Resync kế tiếp.
func (r *Receiver) markStale(device string) {
	r.mu.Lock()
	r.stale[device] = true
	r.mu.Unlock()
}

// Resync reads again from Python the state and the totals of the computers Python wrote itself or holds otherwise than this side,
// and every book after another start of Python. A computer whose rows still wait for Python is left for the next time, so a state
// sent here is never put back to an older one.
// Resync đọc lại từ Python trạng thái và tổng của các máy Python tự ghi hay giữ khác bên này, và mọi sổ sau một lần khởi động khác của
// Python. Máy còn dòng đang chờ Python thì để lần sau, để trạng thái đã gửi tới đây không bao giờ bị đặt lại thành bản cũ hơn.
func (r *Receiver) Resync(ctx context.Context) error {
	r.mu.Lock()
	all := r.reloadAll
	r.reloadAll = false
	devices := make([]string, 0, len(r.stale))
	for d := range r.stale {
		devices = append(devices, d)
	}
	r.stale = map[string]bool{}
	r.mu.Unlock()
	if all {
		if _, err := r.LoadBooks(ctx); err != nil {
			r.mu.Lock()
			r.reloadAll = true
			r.mu.Unlock()
			return err
		}
	}
	for i, device := range devices {
		if r.isQueued(device) {
			r.markStale(device)
			continue
		}
		e := r.entry(device)
		e.mu.Lock()
		var err error
		if !e.loaded {
			err = r.load(ctx, device, e)
		} else {
			var o *pyjson.Object
			if o, err = r.record(ctx, device); err == nil {
				// the book held here stays, and its hours are the ones added up; with none held, Python's hours of today are
				// sổ đang giữ ở đây giữ nguyên, và các giờ của nó là thứ được cộng; không giữ sổ nào thì cộng các giờ hôm nay của Python
				r.show(device, o, e.rec)
			}
		}
		e.mu.Unlock()
		if err != nil {
			for _, d := range devices[i:] {
				r.markStale(d)
			}
			return err
		}
	}
	return nil
}

// today is the first hour of the local day now, in the time zone Python counts days in.
// today là giờ đầu tiên của ngày địa phương lúc này, theo múi giờ Python dùng để đếm ngày.
func (r *Receiver) today() int64 {
	tz := int64(0)
	if p := r.Policy(); p != nil {
		tz = int64(p.TzHours * 3600)
	}
	return totals.FirstHour(float64(r.Now())/1000, tz)
}

func reply(w http.ResponseWriter, status int, body any, headers ...string) {
	b, _ := json.Marshal(body)
	for i := 0; i+1 < len(headers); i += 2 {
		w.Header().Set(headers[i], headers[i+1])
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Robots-Tag", "noindex, nofollow")
	w.Header().Set("Content-Length", strconv.Itoa(len(b)))
	w.WriteHeader(status)
	_, _ = w.Write(b)
}

func refuse(w http.ResponseWriter, status int, why string) {
	reply(w, status, map[string]string{"error": why})
}

// ServeHTTP answers POST /ingest and GET /health; every other path is 404, as on the Python server.
// ServeHTTP trả lời POST /ingest và GET /health; mọi đường khác là 404, như ở máy chủ Python.
func (r *Receiver) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	switch {
	case req.URL.RequestURI() == "/health" && req.Method == http.MethodGet:
		reply(w, http.StatusOK, r.health())
	case req.URL.RequestURI() == "/ingest" && req.Method == http.MethodPost:
		r.ingest(w, req)
	default:
		refuse(w, http.StatusNotFound, "Not found")
	}
}

func clientIP(req *http.Request) string {
	host, _, err := net.SplitHostPort(req.RemoteAddr)
	if err != nil {
		return req.RemoteAddr
	}
	return host
}

func (r *Receiver) ingest(w http.ResponseWriter, req *http.Request) {
	policy := r.Policy()
	if policy == nil {
		// no policy from Python yet: nothing can be checked against revocations, so the computer tries again shortly
		// chưa có chính sách từ Python: chưa kiểm được việc thu hồi, nên máy thử lại sau ít giây
		refuse(w, http.StatusServiceUnavailable, "starting")
		return
	}
	header := req.Header.Get("Authorization")
	token := ""
	if strings.HasPrefix(header, "Bearer ") {
		token = strings.TrimSpace(header[7:])
		if len(token) > 200 {
			token = token[:200]
		}
	}
	own := strings.HasPrefix(token, devicekey.Prefix+".")
	nowMs := r.Now()
	now := float64(nowMs) / 1000
	// in Python's order: the key, then the size of the body
	// theo thứ tự của Python: khoá trước, rồi tới cỡ của thân
	var claims *devicekey.Claims
	if own {
		var why string
		if claims, why = r.secrets.Check(token, now, func(d string) bool { return policy.revoked[d] }); claims == nil {
			refuse(w, http.StatusUnauthorized, why)
			return
		}
	}
	limit := int64(MaxBodyBytes)
	if policy.MaxBodyBytes > 0 && policy.MaxBodyBytes < limit {
		limit = policy.MaxBodyBytes
	}
	if req.ContentLength <= 0 || req.ContentLength > limit {
		refuse(w, http.StatusRequestEntityTooLarge, "too large")
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, req.Body, limit))
	if err != nil {
		refuse(w, http.StatusRequestEntityTooLarge, "too large")
		return
	}
	if !own {
		r.forward(w, req, body, "")
		return
	}
	if devicekey.NeedsRenewal(claims, now, policy.RenewBefore) {
		r.forward(w, req, body, claims.Device)
		return
	}
	raw, err := pyjson.Parse(body)
	if err != nil {
		r.forward(w, req, body, claims.Device)
		return
	}
	d := clean.Payload(raw, now)
	if d == nil {
		refuse(w, http.StatusBadRequest, "invalid format")
		return
	}
	device, _ := d.Get("device")
	if device != claims.Device {
		refuse(w, http.StatusForbidden, "this key belongs to another computer")
		return
	}
	e := r.entry(claims.Device)
	e.mu.Lock()
	if e.forward || (e.askName && (field(d, "name") != nil || field(d, "account") != nil)) {
		e.mu.Unlock()
		r.forward(w, req, body, claims.Device)
		return
	}
	defer e.mu.Unlock()
	// a bucket of sends per computer, as IngestGate does in Python: INGEST_BURST sends, refilled INGEST_PER_SECOND a second
	// một xô lượt gửi cho mỗi máy, như IngestGate làm trong Python: INGEST_BURST lượt, tự đầy lại INGEST_PER_SECOND lượt mỗi giây
	if e.counted == 0 {
		e.tokens, e.counted = policy.IngestBurst, now
	}
	e.tokens = math.Min(policy.IngestBurst, e.tokens+math.Max(0, now-e.counted)*policy.IngestPerSecond)
	e.counted = now
	if e.tokens < 1 {
		refuse(w, http.StatusTooManyRequests, "too many submissions")
		return
	}
	e.tokens--
	if !r.isWaiting(claims.Device) && r.waitingCount() >= maxPending {
		// Python has not taken the rows for a long while: refuse, so the computers keep their hours instead of this side dropping them
		// Python đã lâu không nhận các dòng: từ chối, để các máy giữ giờ của chúng thay vì bên này phải bỏ đi
		reply(w, http.StatusServiceUnavailable, map[string]string{"error": "busy"}, "Retry-After", busyRetry)
		return
	}
	if err := r.load(req.Context(), claims.Device, e); err != nil {
		log.Printf("receiver: cannot load the book of %s: %v", claims.Device, err)
		reply(w, http.StatusServiceUnavailable, map[string]string{"error": "busy"}, "Retry-After", busyRetry)
		return
	}
	kind := clean.SendKind(raw)
	outcome, applied, _ := clean.Decide(e.rec.kept(claims.Device), d, now, kind, e.lastFull, e.everFull)
	delegations := clean.Delegations(field(raw, "delegations"), float64(nowMs))
	ip := clientIP(req)
	switch {
	case outcome == clean.Saved:
		e.rec = e.rec.next(d, applied, totals.FirstHour(now, int64(policy.TzHours*3600)))
		if applied == "full" {
			e.lastFull, e.everFull = now, true
		}
		r.enqueue(claims.Device, d, applied, ip, nowMs, delegations)
		if raw := sampled(policy.CheckPercent, body); raw != nil {
			r.enqueueCheck(row(d, applied, ip, nowMs, delegations, raw))
		}
		r.show(claims.Device, d, e.rec)
	case len(delegations) > 0:
		// the numbers are not written, but the records of work handed to helpers still go to the audit log, as on Python
		// số liệu không được ghi, nhưng biên bản giao việc vẫn vào nhật ký, như ở Python
		r.enqueue(claims.Device, d, "delegations", ip, nowMs, delegations)
	}
	reply(w, http.StatusOK, answer{OK: true, Accepts: []int{1, 2}, MinGapMs: policy.MinGapMs, StateGapMs: policy.StateGapMs, MaxGapMs: policy.MaxGapMs,
		NeedFull: outcome == clean.NeedFull, Boot: r.Boot})
}

// answer has the fields of Python's answer to /ingest, in the same order.
// answer có các trường của câu trả lời /ingest của Python, cùng thứ tự.
type answer struct {
	OK         bool   `json:"ok"`
	Accepts    []int  `json:"accepts"`
	MinGapMs   int64  `json:"minGapMs"`
	StateGapMs int64  `json:"stateGapMs"`
	MaxGapMs   int64  `json:"maxGapMs"`
	NeedFull   bool   `json:"needFull"`
	Boot       string `json:"boot"`
}

func field(v pyjson.Value, k string) pyjson.Value {
	o, ok := v.(*pyjson.Object)
	if !ok {
		return nil
	}
	x, _ := o.Get(k)
	return x
}

func sampled(percent float64, body []byte) []byte {
	if percent > 0 && mrand.Float64()*100 < percent {
		return body
	}
	return nil
}

// row builds one row of a batch (board/receiver.py): the cleaned send in the format it came in, without the name and account the
// computer claims, the address it claims or an IP history, which Python writes itself.
// row dựng một dòng của lô (board/receiver.py): lần gửi đã làm sạch theo định dạng nó tới, không có tên và tài khoản máy tự khai,
// địa chỉ nó tự khai hay lịch sử IP, những thứ Python tự ghi.
func row(d *pyjson.Object, kind, ip string, nowMs int64, delegations []pyjson.Value, raw []byte) pyjson.Value {
	v := pyjson.NewObject()
	second := kind == "hours" || kind == "full"
	if second {
		v.Set("v", pyjson.IntN(2))
	}
	hours := pyjson.NewObject()
	for i, k := range d.Keys {
		switch k {
		case "name", "account", "ip", "ipHistory":
			continue
		case "v":
			if second {
				continue
			}
		case "ledger", "tasks", "blocks":
			if second {
				hours.Set(k, d.Vals[i])
				continue
			}
		}
		v.Set(k, d.Vals[i])
	}
	if second {
		v.Set("full", kind == "full")
		v.Set("hours", hours)
	}
	v.Set("delegations", delegations)
	out := pyjson.NewObject()
	device, _ := d.Get("device")
	out.Set("k", []pyjson.Value{"m", device})
	out.Set("at", pyjson.IntN(nowMs))
	out.Set("kind", kind)
	out.Set("ip", ip)
	out.Set("v", v)
	if raw != nil {
		out.Set("raw", pyjson.Raw(raw))
	}
	return out
}

// enqueue puts one send on the row waiting for its computer, or starts that row.
// enqueue đặt một lần gửi lên dòng đang chờ của máy đó, hoặc bắt đầu dòng đó.
func (r *Receiver) enqueue(device string, d *pyjson.Object, kind, ip string, at int64, delegations []pyjson.Value) {
	r.qmu.Lock()
	p := r.pending[device]
	if p == nil {
		p = &waiting{since: time.Now().UnixMilli()}
		r.pending[device] = p
		r.order = append(r.order, device)
	}
	p.add(d, kind, ip, at, delegations)
	r.qmu.Unlock()
	r.nudge()
}

// enqueueCheck adds one send for the third check, as it came and as cleaned here; a few are enough, so past maxChecks they are dropped.
// enqueueCheck thêm một lần gửi cho lớp đối chiếu thứ ba, nguyên văn và như đã làm sạch ở đây; vài lần là đủ, nên quá maxChecks thì bỏ.
func (r *Receiver) enqueueCheck(one pyjson.Value) {
	o, _ := one.(*pyjson.Object)
	o.Set("kind", "check")
	r.qmu.Lock()
	if len(r.checks) < maxChecks {
		r.checks = append(r.checks, o)
	}
	r.qmu.Unlock()
	r.nudge()
}

func (r *Receiver) nudge() {
	if r.every <= 0 {
		select {
		case r.wake <- struct{}{}:
		default:
		}
	}
}

func (r *Receiver) isWaiting(device string) bool {
	r.qmu.Lock()
	defer r.qmu.Unlock()
	return r.pending[device] != nil
}

// isQueued: rows of this computer wait for Python, or are on their way in the batch Python has not answered yet.
// isQueued: các dòng của máy này đang chờ Python, hoặc đang trên đường trong lô Python chưa trả lời.
func (r *Receiver) isQueued(device string) bool {
	r.qmu.Lock()
	defer r.qmu.Unlock()
	return r.pending[device] != nil || (r.inflight != nil && r.inflight.devices[device])
}

func (r *Receiver) waitingCount() int {
	r.qmu.Lock()
	defer r.qmu.Unlock()
	return len(r.pending)
}

// queued is every row not yet written by Python: those waiting, the checks, and the batch on its way.
// queued là mọi dòng Python chưa ghi: các dòng đang chờ, các dòng đối chiếu, và lô đang đi.
func (r *Receiver) queued() int {
	r.qmu.Lock()
	defer r.qmu.Unlock()
	n := len(r.pending) + len(r.checks)
	if r.inflight != nil {
		n += len(r.inflight.rows)
	}
	return n
}

// sortWaiting puts the computers waiting in the order of their ids, once at the start of a beat: the batches of that beat then cover
// ranges of ids one after another, so Python writes neighbouring rows of its tables together and touches far fewer pages (about 14 times
// fewer bytes written, more than twice the rows a second, at 100,000 computers). Sorting each batch alone would not do it. Each computer
// waits as one row, so the two sends of one computer never change order; a computer that comes during the beat waits after the ones
// sorted, so none is pushed back for ever.
// sortWaiting xếp các máy đang chờ theo mã máy, một lần ở đầu mỗi nhịp: các lô của nhịp đó lần lượt phủ những dải mã liền nhau, nên
// Python ghi các dòng gần nhau trong bảng cùng lúc và đụng ít trang hơn nhiều (ghi ít hơn khoảng 14 lần, hơn gấp đôi số dòng mỗi giây,
// ở 100.000 máy). Chỉ sắp từng lô thì không được như vậy. Mỗi máy chờ thành một dòng, nên hai lần gửi của một máy không bao giờ đổi thứ
// tự; máy tới trong lúc nhịp đang chạy chờ sau các máy đã sắp, nên không máy nào bị đẩy lùi mãi.
func (r *Receiver) sortWaiting() {
	r.qmu.Lock()
	sort.Strings(r.order)
	r.sorted = len(r.order)
	r.qmu.Unlock()
}

// take gives the batch to send: the one on its way if an earlier try failed, else a new one of the first rows waiting, nil if none.
// The computers come in the order of their ids, a group at a time: when the batch would reach past the ones sorted, every computer
// that came since is sorted too, behind them. So while Python is behind and the beat stretches, the batches still cover ranges of ids
// (see sortWaiting), and a computer never waits behind one that came after it was sorted.
// take trả lô cần gửi: lô đang đi nếu lần thử trước hỏng, nếu không thì một lô mới gồm các dòng đứng đầu hàng chờ, nil nếu không có gì.
// Các máy đi theo thứ tự mã, từng nhóm một: khi lô sẽ vượt quá phần đã sắp, mọi máy tới từ đó cũng được sắp, phía sau chúng. Nên trong
// lúc Python chậm và nhịp giãn ra, các lô vẫn phủ những dải mã liền nhau (xem sortWaiting), và không máy nào phải chờ sau một máy tới
// sau khi nó đã được sắp.
func (r *Receiver) take() *batch {
	r.qmu.Lock()
	defer r.qmu.Unlock()
	if r.inflight != nil {
		return r.inflight
	}
	n := min(len(r.order), maxBatchRows)
	c := min(len(r.checks), maxBatchRows-n)
	if n == 0 && c == 0 {
		return nil
	}
	if r.sorted < n {
		sort.Strings(r.order[r.sorted:])
		r.sorted = len(r.order)
	}
	rows := make([]pyjson.Value, 0, n+c)
	devices := make(map[string]bool, n)
	oldest := time.Now().UnixMilli()
	for _, device := range r.order[:n] {
		p := r.pending[device]
		delete(r.pending, device)
		devices[device] = true
		rows = append(rows, row(p.d, p.kind, p.ip, p.at, p.delegations, nil))
		oldest = min(oldest, p.since)
	}
	r.order = append([]string(nil), r.order[n:]...)
	r.sorted = max(0, r.sorted-n)
	rows = append(rows, r.checks[:c]...)
	r.checks = append([]pyjson.Value(nil), r.checks[c:]...)
	r.inflight = &batch{seq: r.seq + 1, rows: rows, devices: devices, oldest: oldest}
	return r.inflight
}

// Waited is how many rows wait for Python (queued) and how long the oldest of them has waited, a batch on its way included.
// Waited là số dòng đang chờ Python (queued) và dòng chờ lâu nhất đã chờ bao lâu, kể cả lô đang đi.
func (r *Receiver) Waited() (int, time.Duration) {
	now := time.Now().UnixMilli()
	r.qmu.Lock()
	defer r.qmu.Unlock()
	n, oldest := len(r.pending)+len(r.checks), now
	if r.inflight != nil {
		n += len(r.inflight.rows)
		oldest = min(oldest, r.inflight.oldest)
	}
	for _, p := range r.pending {
		oldest = min(oldest, p.since)
	}
	return n, time.Duration(now-oldest) * time.Millisecond
}

// health is what GET /health says: the rows waiting for Python, how long the oldest has waited, and whether that is past behindAfter.
// Going past it, and coming back, is logged once.
// health là thứ GET /health nói: số dòng đang chờ Python, dòng chờ lâu nhất đã chờ bao lâu, và đã quá behindAfter chưa.
// Vượt quá mức đó, và trở lại dưới mức đó, được ghi nhật ký một lần.
func (r *Receiver) health() map[string]any {
	n, waited := r.Waited()
	behind := waited > behindAfter
	r.qmu.Lock()
	changed := behind != r.behind
	r.behind = behind
	r.qmu.Unlock()
	if changed && behind {
		log.Printf("receiver: behind: the oldest of %d rows has waited %s for Python", n, waited.Round(time.Second))
	} else if changed {
		log.Printf("receiver: caught up: %d rows wait, the oldest %s", n, waited.Round(time.Second))
	}
	return map[string]any{"ok": true, "queued": n, "waitSeconds": int64(waited / time.Second), "behind": behind}
}

// Flush sends one batch to Python and waits for its seq; on an error the same batch, with the same seq, goes again next time.
// It returns how many rows Python took.
// Flush gửi một lô cho Python và chờ seq của nó; lỗi thì đúng lô đó, cùng seq, được gửi lại lần sau. Trả về số dòng Python đã nhận.
func (r *Receiver) Flush(ctx context.Context) (int, error) {
	b := r.take()
	if b == nil {
		return 0, nil
	}
	out := pyjson.NewObject()
	out.Set("src", r.src)
	out.Set("boot", r.Boot)
	out.Set("seq", pyjson.IntN(b.seq))
	out.Set("rows", b.rows)
	// how long the oldest row of the batch has waited, so the Admin page of Python can say when the receiver is behind
	// dòng chờ lâu nhất của lô đã chờ bao lâu, để trang Quản trị của Python báo được khi bộ nhận đang chậm
	out.Set("waitMs", pyjson.IntN(max(0, time.Now().UnixMilli()-b.oldest)))
	resp, err := r.internal(ctx, http.MethodPost, "/internal/rows", pyjson.Encode(out))
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	var got struct {
		OK         bool     `json:"ok"`
		Seq        int64    `json:"seq"`
		NeedFull   []string `json:"needFull"`
		Unknown    []string `json:"unknown"`
		Incomplete []string `json:"incomplete"`
		Bad        []string `json:"bad"`
	}
	if resp.StatusCode != http.StatusOK || json.NewDecoder(io.LimitReader(resp.Body, 16<<20)).Decode(&got) != nil || got.Seq != b.seq {
		return 0, fmt.Errorf("batch %d: %s", b.seq, resp.Status)
	}
	r.qmu.Lock()
	if r.inflight == b {
		r.inflight = nil
	}
	r.seq = b.seq
	r.qmu.Unlock()
	n := len(b.rows)
	for _, d := range got.NeedFull {
		// Python holds no book for it: the computer is asked for its whole book at its next send
		// Python không giữ sổ của nó: máy được xin cả sổ ở lần gửi sau
		e := r.entry(d)
		e.mu.Lock()
		e.loaded, e.rec = true, nil
		e.mu.Unlock()
		// Python did not take this send, so the board still shows what Python held before it
		// Python không nhận lần gửi này, nên bảng vẫn hiện thứ Python giữ trước nó
		r.markStale(d)
	}
	for _, d := range got.Bad {
		// Python could not write that row and left it out: the book held here is read again from Python
		// Python không ghi được dòng đó và đã bỏ ra: sổ giữ ở đây được đọc lại từ Python
		log.Printf("receiver: Python left out the row of %s", d)
		e := r.entry(d)
		e.mu.Lock()
		e.loaded, e.rec = false, nil
		e.mu.Unlock()
		r.markStale(d)
	}
	for _, d := range got.Incomplete {
		e := r.entry(d)
		e.mu.Lock()
		e.askName = true
		e.mu.Unlock()
	}
	for _, d := range got.Unknown {
		e := r.entry(d)
		e.mu.Lock()
		e.forward, e.loaded, e.rec = true, false, nil
		e.mu.Unlock()
		r.markStale(d)
	}
	return n, nil
}

// Run sends the batches every interval (at once when the interval is 0), asks for the policy every 15 seconds and for the changes of
// the table of people at once and then every 15 seconds, and after each batch and each policy reads again from Python what Python
// wrote itself (Resync), until ctx ends.
// Run gửi các lô mỗi chu kỳ (ngay lập tức khi chu kỳ là 0), hỏi chính sách mỗi 15 giây và hỏi các thay đổi của bảng người ngay rồi
// mỗi 15 giây, và sau mỗi lô và mỗi lần hỏi chính sách thì đọc lại từ Python những gì Python tự ghi (Resync), cho tới khi ctx kết thúc.
func (r *Receiver) Run(ctx context.Context) {
	go func() {
		t := time.NewTicker(peopleEvery)
		defer t.Stop()
		for {
			if _, err := r.RefreshPeople(ctx); err != nil && ctx.Err() == nil {
				log.Printf("receiver: people: %v", err)
			}
			select {
			case <-ctx.Done():
				return
			case <-t.C:
			}
		}
	}()
	go func() {
		t := time.NewTicker(policyEvery)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				if err := r.RefreshPolicy(ctx); err != nil {
					log.Printf("receiver: policy: %v", err)
				} else if err := r.Resync(ctx); err != nil && ctx.Err() == nil {
					log.Printf("receiver: reading again from Python: %v", err)
				}
			}
		}
	}()
	every := r.every
	if every <= 0 {
		every = time.Second
	}
	pause := time.Duration(0)
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		case <-r.wake:
		}
		if pause > 0 {
			time.Sleep(pause)
		}
		for {
			n, err := r.Flush(ctx)
			if err != nil {
				if !errors.Is(err, context.Canceled) {
					log.Printf("receiver: %v", err)
				}
				pause = min(maxRetryPause, max(time.Second, pause*2))
				break
			}
			pause = 0
			if n < maxBatchRows {
				break
			}
		}
		if err := r.Resync(ctx); err != nil && ctx.Err() == nil {
			log.Printf("receiver: reading again from Python: %v", err)
		}
		// logs once when the oldest row goes past behindAfter, and once when it comes back
		// ghi nhật ký một lần khi dòng chờ lâu nhất vượt behindAfter, và một lần khi trở lại
		r.health()
	}
}

// forward passes a send to Python as it came, with the computer's address as this side saw it on the socket; Python's answer goes back
// with this receiver's boot in place of Python's. The book held for that computer is dropped, since Python wrote it.
// forward chuyển một lần gửi nguyên văn cho Python, kèm địa chỉ của máy như bên này thấy trên socket; câu trả lời của Python được trả lại
// với boot của bộ nhận này thay cho của Python. Sổ đang giữ cho máy đó bị bỏ, vì Python đã ghi nó.
func (r *Receiver) forward(w http.ResponseWriter, req *http.Request, body []byte, device string) {
	select {
	case r.forwardSlots <- struct{}{}:
		defer func() { <-r.forwardSlots }()
	default:
		reply(w, http.StatusServiceUnavailable, map[string]string{"error": "busy"}, "Retry-After", busyRetry)
		return
	}
	out, err := http.NewRequestWithContext(req.Context(), http.MethodPost, r.webhook+"/internal/ingest", bytes.NewReader(body))
	if err != nil {
		refuse(w, http.StatusBadGateway, "cannot pass on")
		return
	}
	out.Header.Set("Authorization", "Bearer "+r.secrets.Internal())
	out.Header.Set("X-Receiver-Authorization", req.Header.Get("Authorization"))
	out.Header.Set("X-Receiver-Client-Ip", clientIP(req))
	out.Header.Set("Content-Type", "application/json")
	resp, err := r.client.Do(out)
	if err != nil {
		reply(w, http.StatusServiceUnavailable, map[string]string{"error": "busy"}, "Retry-After", busyRetry)
		return
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if v, err := pyjson.Parse(b); err == nil {
		if o, ok := v.(*pyjson.Object); ok {
			if _, has := o.Get("boot"); has {
				o.Set("boot", r.Boot)
				b = pyjson.Encode(o)
			}
		}
	}
	if device == "" {
		if v, err := pyjson.Parse(body); err == nil {
			device, _ = field(v, "device").(string)
		}
	}
	if device != "" && resp.StatusCode == http.StatusOK {
		e := r.entry(device)
		e.mu.Lock()
		e.loaded, e.rec, e.forward, e.askName = false, nil, false, false
		e.mu.Unlock()
		r.markStale(device)
	}
	if ra := resp.Header.Get("Retry-After"); ra != "" {
		w.Header().Set("Retry-After", ra)
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Robots-Tag", "noindex, nofollow")
	w.Header().Set("Content-Length", strconv.Itoa(len(b)))
	w.WriteHeader(resp.StatusCode)
	_, _ = w.Write(b)
}
