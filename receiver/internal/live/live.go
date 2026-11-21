// Package live keeps each computer's state as its last send left it and adds it up, with today's totals of package totals, per row of
// the board (the code Python gives in its table of people, package people) and per branch: the numbers the live feed of the board will
// carry. It copies is_fresh, status_of and the parts of group_by_person in server/board/devices.py that make the fields of role_view in
// server/board/views.py named in Row; the receiver's tests hold Python's own answer next to it. It holds no name, no email and no address.
// Package live giữ trạng thái của từng máy như lần gửi cuối để lại và cộng nó, cùng tổng hôm nay của gói totals, theo từng dòng của bảng
// (mã Python cho trong bảng người, gói people) và theo từng chi nhánh: các con số luồng trực tiếp của bảng sẽ mang. Nó chép is_fresh,
// status_of và các phần của group_by_person trong server/board/devices.py làm ra các trường của role_view trong server/board/views.py có
// tên trong Row; bài test của bộ nhận đặt chính câu trả lời của Python cạnh nó. Nó không giữ tên, email hay địa chỉ nào.
package live

import (
	"math"
	"math/big"
	"sort"
	"strconv"
	"sync"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/people"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

// The same numbers as server/board/settings.py.
// Cùng các con số như server/board/settings.py.
const (
	// OfflineSeconds: a plugin that has not sent for this long is offline (OFFLINE_SECONDS)
	// OfflineSeconds: plugin không gửi lâu chừng này thì ngoại tuyến (OFFLINE_SECONDS)
	OfflineSeconds = 12 * 60
	// ConnectorOfflineSeconds: the same for the connector, which sends only on an event (CONNECTOR_OFFLINE_SECONDS)
	// ConnectorOfflineSeconds: như trên với bộ nối, vốn chỉ gửi khi có sự kiện (CONNECTOR_OFFLINE_SECONDS)
	ConnectorOfflineSeconds = 2 * 3600
	// ConnectorWorkingSeconds: "working" from the connector is believed this long (CONNECTOR_WORKING_SECONDS)
	// ConnectorWorkingSeconds: "đang làm" từ bộ nối được tin trong chừng này (CONNECTOR_WORKING_SECONDS)
	ConnectorWorkingSeconds = 30 * 60
)

// The statuses of status_of.
// Các trạng thái của status_of.
const (
	Offline = "offline"
	Waiting = "waiting"
	Working = "working"
	Open    = "open"
)

// Counts are the session counts of a computer or of one tool on it (SESSION_COUNTS).
// Counts là số phiên của một máy hay của một công cụ trên máy đó (SESSION_COUNTS).
type Counts struct {
	OpenSessions int64 `json:"openSessions"`
	Working      int64 `json:"working"`
	Waiting      int64 `json:"waiting"`
}

func (c *Counts) add(o Counts) {
	c.OpenSessions += o.OpenSessions
	c.Working += o.Working
	c.Waiting += o.Waiting
}

// State is what counts of a computer's last send for its status: no hour, no name, no address.
// State là phần của lần gửi cuối của một máy có nghĩa cho trạng thái của nó: không giờ, không tên, không địa chỉ.
type State struct {
	// UpdatedAt is the updatedAt of the send, in milliseconds as the computer said it
	// UpdatedAt là updatedAt của lần gửi, theo mili giây như máy nói
	UpdatedAt float64
	// Connector: the send came from the connector for other coding tools (from_connector), and Tools holds its counts per tool
	// Connector: lần gửi đến từ bộ nối cho các công cụ lập trình khác (from_connector), và Tools giữ số của nó theo từng công cụ
	Connector  bool
	Tools      map[string]Counts
	Counts     Counts
	Delegating [3]int64
}

// number gives a cleaned number of a table as Python's int(v or 0): a float is cut toward zero.
// number cho một số đã làm sạch của một bảng như int(v or 0) của Python: số thực bị cắt về phía 0.
func number(o *pyjson.Object, k string) int64 {
	if o == nil {
		return 0
	}
	v, _ := o.Get(k)
	n, ok := v.(pyjson.Number)
	switch {
	case !ok:
		return 0
	case n.Int && n.Big != nil:
		return n.Big.Int64()
	case n.Int:
		return n.I
	case math.Abs(n.F) < 9e18:
		return int64(n.F)
	}
	return 0
}

func table(o *pyjson.Object, k string) *pyjson.Object {
	v, _ := o.Get(k)
	t, _ := v.(*pyjson.Object)
	return t
}

func countsOf(o *pyjson.Object) Counts {
	return Counts{number(o, "openSessions"), number(o, "working"), number(o, "waiting")}
}

// StateOf takes the state out of a cleaned send or of a record Python gave (/internal/devices); false when it has no updatedAt number,
// as group_by_person skips such a record.
// StateOf lấy trạng thái ra từ một lần gửi đã làm sạch hay một bản ghi Python cho (/internal/devices); false khi nó không có số
// updatedAt, như group_by_person bỏ qua bản ghi đó.
func StateOf(rec *pyjson.Object) (State, bool) {
	if rec == nil {
		return State{}, false
	}
	v, _ := rec.Get("updatedAt")
	n, ok := v.(pyjson.Number)
	if !ok {
		return State{}, false
	}
	s := State{UpdatedAt: n.F, Counts: countsOf(rec)}
	if n.Int {
		s.UpdatedAt, _ = new(big.Float).SetInt(n.AsBig()).Float64()
	}
	if tools := table(rec, "tools"); tools != nil {
		s.Connector, s.Tools = true, map[string]Counts{}
		for i, tool := range tools.Keys {
			if c, ok := tools.Vals[i].(*pyjson.Object); ok {
				s.Tools[tool] = countsOf(c)
			}
		}
	}
	delegating := table(rec, "delegating")
	for i, w := range clean.Workers {
		s.Delegating[i] = number(delegating, w)
	}
	return s, true
}

// Fresh is is_fresh: whether the send still says what its computer is doing at the second now.
// Fresh là is_fresh: lần gửi còn nói đúng máy đang làm gì ở giây now hay không.
func (s State) Fresh(now float64) bool {
	limit := float64(OfflineSeconds)
	if s.Connector {
		limit = ConnectorOfflineSeconds
	}
	return now-s.UpdatedAt/1000 < limit
}

// Row is one person's row of the board as the live numbers carry it: the fields of role_view of the same name, with the code of the row
// and its branch, and the cost of today in usdMicro besides its dollars.
// Row là dòng của một người trên bảng như số trực tiếp mang: các trường cùng tên của role_view, kèm mã dòng và chi nhánh của nó, và chi
// phí hôm nay theo usdMicro bên cạnh số đô la.
type Row struct {
	Row          string            `json:"row"`
	Branch       string            `json:"branch"`
	Status       string            `json:"status"`
	OpenSessions int64             `json:"openSessions"`
	Working      int64             `json:"working"`
	Waiting      int64             `json:"waiting"`
	Delegating   [3]int64          `json:"delegating"`
	Tools        map[string]Counts `json:"tools"`
	USDToday     float64           `json:"usdToday"`
	USDMicro     int64             `json:"usdMicroToday"`
	TokensIn     int64             `json:"tokensIn"`
	TokensOut    int64             `json:"tokensOut"`
	Tasks        [3]int64          `json:"tasks"`
	UpdatedAt    float64           `json:"updatedAt"`
	online       bool
}

// Round4 is Python's round(micro / 1_000_000, 4): the dollars of a whole number of usdMicro to four places, as the board shows them.
// Round4 là round(micro / 1_000_000, 4) của Python: số đô la của một số nguyên usdMicro, làm tròn bốn chữ số, như bảng hiện.
func Round4(micro int64) float64 {
	f, _ := strconv.ParseFloat(strconv.FormatFloat(float64(micro)/1_000_000, 'f', 4, 64), 64)
	return f
}

// Store holds the state of each computer; the hours are in the totals.Store it reads.
// Store giữ trạng thái của từng máy; các giờ nằm trong totals.Store mà nó đọc.
type Store struct {
	totals *totals.Store
	mu     sync.RWMutex
	states map[string]State
}

// New makes an empty store that reads today's totals from t.
// New tạo một kho rỗng đọc tổng hôm nay từ t.
func New(t *totals.Store) *Store { return &Store{totals: t, states: map[string]State{}} }

// Put replaces one computer's state.
// Put thay trạng thái của một máy.
func (s *Store) Put(device string, st State) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.states[device] = st
}

// Drop takes one computer out.
// Drop bỏ một máy ra.
func (s *Store) Drop(device string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.states, device)
}

// Len is the number of computers held.
// Len là số máy đang giữ.
func (s *Store) Len() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.states)
}

// Rows adds the computers up per row of the board at the second now (the Tools of a row are not to be changed: rows with none share one), as group_by_person and _raw_data do: place says each computer's
// row and branch (people.Table.Get); a computer Python has not placed yet is left out until it does. Today is the local day of now with
// the offset tzSeconds. The rows come in the order of their codes.
// Rows cộng các máy theo từng dòng của bảng ở giây now (không được đổi Tools của một dòng: các dòng không có công cụ nào dùng chung một), như group_by_person và _raw_data: place cho biết dòng và chi nhánh của mỗi máy
// (people.Table.Get); máy Python chưa xếp chỗ thì bị bỏ ra cho tới khi Python xếp. Hôm nay là ngày địa phương của now với độ lệch
// tzSeconds. Các dòng theo thứ tự mã của chúng.
func (s *Store) Rows(now float64, tzSeconds int64, place func(device string) (people.Entry, bool)) []Row {
	today := totals.LocalDay(totals.FirstHour(now, tzSeconds), tzSeconds)
	s.mu.RLock()
	defer s.mu.RUnlock()
	// each row once in out, found again by its code
	// mỗi dòng một lần trong out, tìm lại theo mã của nó
	byRow := make(map[string]int, len(s.states))
	out := make([]Row, 0, len(s.states))
	for device, st := range s.states {
		at, ok := place(device)
		if !ok || at.Row == "" {
			continue
		}
		i, seen := byRow[at.Row]
		if !seen {
			i = len(out)
			byRow[at.Row] = i
			out = append(out, Row{Row: at.Row, Branch: at.Scope})
		}
		r := &out[i]
		r.UpdatedAt = math.Max(r.UpdatedAt, st.UpdatedAt)
		if st.Fresh(now) {
			// the plugin sends on a beat while Claude is open, so a fresh send means the person is there; the connector's means a tool is open
			// plugin gửi theo nhịp khi Claude đang mở, nên lần gửi còn mới nghĩa là người đó đang ở đó; của bộ nối nghĩa là có công cụ đang mở
			if !st.Connector || st.Counts.OpenSessions > 0 {
				r.online = true
			}
			if st.Connector {
				for tool, c := range st.Tools {
					// a connector's send this old no longer proves that work goes on: the session stays open, not working
					// lần gửi của bộ nối cũ tới mức này không còn chứng tỏ việc vẫn đang chạy: phiên vẫn mở, không còn đang làm
					if now-st.UpdatedAt/1000 >= ConnectorWorkingSeconds {
						c.Working = 0
					}
					r.addTool(tool, c)
				}
			} else {
				r.addTool("claude", st.Counts)
			}
			for i := range r.Delegating {
				r.Delegating[i] += st.Delegating[i]
			}
		}
		if d := s.totals.Day(device, today); d != nil {
			r.USDMicro += d.USDMicro.Int64()
			r.TokensIn += d.TokensIn.Int64()
			r.TokensOut += d.TokensOut.Int64()
			for i := range r.Tasks {
				r.Tasks[i] += d.Tasks[i].Int64()
			}
		}
	}
	for i := range out {
		r := &out[i]
		if r.Tools == nil {
			r.Tools = noTools
		}
		r.USDToday = Round4(r.USDMicro)
		r.Status = statusOf(r)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Row < out[j].Row })
	return out
}

// noTools is the Tools of every row with no session open: one empty table shared by them, never changed.
// noTools là Tools của mọi dòng không có phiên nào mở: một bảng rỗng dùng chung cho chúng, không bao giờ bị đổi.
var noTools = map[string]Counts{}

// addTool counts one tool's sessions on the row, and in Tools when one is open.
// addTool đếm số phiên của một công cụ vào dòng, và vào Tools khi có phiên đang mở.
func (r *Row) addTool(tool string, c Counts) {
	r.OpenSessions += c.OpenSessions
	r.Working += c.Working
	r.Waiting += c.Waiting
	if c.OpenSessions > 0 {
		if r.Tools == nil {
			r.Tools = map[string]Counts{}
		}
		per := r.Tools[tool]
		per.add(c)
		r.Tools[tool] = per
	}
}

// statusOf is status_of.
// statusOf là status_of.
func statusOf(r *Row) string {
	switch {
	case !r.online:
		return Offline
	case r.Waiting != 0:
		return Waiting
	case r.Working != 0:
		return Working
	}
	return Open
}

// Branch is the totals of one branch (id "" for the people in none), the fields of branch_totals in server/board/views.py.
// Branch là tổng của một chi nhánh (mã "" cho người chưa thuộc chi nhánh nào), các trường của branch_totals trong server/board/views.py.
type Branch struct {
	ID           string  `json:"id"`
	People       int64   `json:"people"`
	Online       int64   `json:"online"`
	Working      int64   `json:"working"`
	Waiting      int64   `json:"waiting"`
	OpenSessions int64   `json:"openSessions"`
	USDToday     float64 `json:"usdToday"`
	Tokens       int64   `json:"tokens"`
}

// Branches adds rows up per branch as branch_totals does, in the order of the ids with "" last. The cost is added as the board's rounded
// dollars of each person, in whole ten-thousandths, so the sum is the one Python rounds whatever the order of the people.
// Branches cộng các dòng theo chi nhánh như branch_totals, theo thứ tự mã với "" ở cuối. Chi phí được cộng là số đô la đã làm tròn của
// từng người trên bảng, theo số nguyên phần mười nghìn, nên tổng là tổng Python làm tròn dù người được xếp theo thứ tự nào.
func Branches(rows []Row) []Branch {
	by := map[string]*Branch{}
	cents := map[string]int64{}
	for _, r := range rows {
		b := by[r.Branch]
		if b == nil {
			b = &Branch{ID: r.Branch}
			by[r.Branch] = b
		}
		b.People++
		cents[r.Branch] += int64(math.Round(r.USDToday * 10_000))
		b.Tokens += r.TokensIn + r.TokensOut
		if r.Status != Offline {
			b.Online++
			b.OpenSessions += r.OpenSessions
			// a person waiting in one session while another runs is counted in both, so Working + Waiting can pass Online
			// người đang chờ ở một phiên trong khi phiên khác chạy được đếm ở cả hai, nên Working + Waiting có thể vượt Online
			if r.Waiting != 0 {
				b.Waiting++
			}
			if r.Working != 0 {
				b.Working++
			}
		}
	}
	out := make([]Branch, 0, len(by))
	for id, b := range by {
		b.USDToday, _ = strconv.ParseFloat(strconv.FormatInt(cents[id], 10)+"e-4", 64)
		out = append(out, *b)
	}
	sort.Slice(out, func(i, j int) bool {
		if (out[i].ID == "") != (out[j].ID == "") {
			return out[j].ID == ""
		}
		return out[i].ID < out[j].ID
	})
	return out
}
