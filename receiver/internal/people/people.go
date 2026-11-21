// Package people holds the table Python gives of each computer: the code of its person's row on the board and the scope that row is in
// (board/receiver.py, People), so the live numbers of a computer can be put on the right row of the right branch. It holds no name,
// no email and no address. Python is the record: this table is only ever what Python said, changed by what it says next.
// Package people giữ bảng Python cho về mỗi máy: mã dòng của người của máy đó trên bảng và phạm vi dòng đó thuộc về (board/receiver.py,
// People), để số trực tiếp của một máy được đặt đúng dòng của đúng chi nhánh. Nó không giữ tên, email hay địa chỉ nào. Python là bản
// gốc: bảng này chỉ là thứ Python đã nói, đổi theo thứ Python nói tiếp.
package people

import (
	"context"
	"net/url"
	"strconv"
	"sync"
)

// PageSize is how many changes are asked for at once.
// PageSize là số thay đổi xin mỗi lần.
const PageSize = 5000

// Entry is one computer's place on the board: the code of the row and the scope, the id of a branch or "" for none.
// Entry là chỗ của một máy trên bảng: mã dòng và phạm vi, mã của một chi nhánh hoặc "" nếu chưa có.
type Entry struct {
	Row   string
	Scope string
}

// Page is one answer of /internal/people.
// Page là một câu trả lời của /internal/people.
type Page struct {
	Boot   string `json:"boot"`
	Reset  bool   `json:"reset"`
	Seq    int64  `json:"seq"`
	More   bool   `json:"more"`
	People []struct {
		Device string `json:"device"`
		Row    string `json:"row"`
		Scope  string `json:"scope"`
	} `json:"people"`
	Gone []string `json:"gone"`
}

// Table is the table of people as Python last said it, with the number and the start of Python it is good for.
// Table là bảng người như Python nói lần gần nhất, kèm số thứ tự và lần khởi động của Python mà nó đúng với.
type Table struct {
	mu   sync.RWMutex
	boot string
	seq  int64
	// loading: a reset came with more pages to follow; they are asked for as part of the whole table
	// loading: một lần reset tới kèm các trang tiếp theo; chúng được xin như một phần của cả bảng
	loading bool
	rows    map[string]Entry
}

// New gives an empty table.
// New cho một bảng rỗng.
func New() *Table { return &Table{rows: map[string]Entry{}} }

// Get gives the place of one computer, and whether Python named it.
// Get cho chỗ của một máy, và Python đã nêu nó chưa.
func (t *Table) Get(device string) (Entry, bool) {
	t.mu.RLock()
	defer t.mu.RUnlock()
	e, ok := t.rows[device]
	return e, ok
}

// Len is the number of computers in the table.
// Len là số máy trong bảng.
func (t *Table) Len() int {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return len(t.rows)
}

// Snapshot gives a copy of the whole table.
// Snapshot cho một bản sao của cả bảng.
func (t *Table) Snapshot() map[string]Entry {
	t.mu.RLock()
	defer t.mu.RUnlock()
	out := make(map[string]Entry, len(t.rows))
	for k, v := range t.rows {
		out[k] = v
	}
	return out
}

// Path is the path to ask Python for the changes after the number held.
// Path là đường để xin Python các thay đổi sau số đang giữ.
func (t *Table) Path() string {
	t.mu.RLock()
	defer t.mu.RUnlock()
	p := "/internal/people?since=" + strconv.FormatInt(t.seq, 10) + "&boot=" + url.QueryEscape(t.boot) + "&limit=" + strconv.Itoa(PageSize)
	if t.loading {
		p += "&loading=1"
	}
	return p
}

// Apply puts one page on the table and gives the computers whose place changed (gone ones included); a reset drops the table first.
// Apply đặt một trang lên bảng và cho các máy đã đổi chỗ (kể cả máy đã mất); một lần reset bỏ bảng trước.
func (t *Table) Apply(p Page) []string {
	t.mu.Lock()
	defer t.mu.Unlock()
	var changed []string
	if p.Reset {
		for d := range t.rows {
			changed = append(changed, d)
		}
		t.rows = map[string]Entry{}
		t.loading = true
	}
	for _, x := range p.People {
		e := Entry{Row: x.Row, Scope: x.Scope}
		if old, ok := t.rows[x.Device]; !ok || old != e {
			t.rows[x.Device] = e
			changed = append(changed, x.Device)
		}
	}
	for _, d := range p.Gone {
		if _, ok := t.rows[d]; ok {
			delete(t.rows, d)
			changed = append(changed, d)
		}
	}
	t.boot, t.seq = p.Boot, p.Seq
	if !p.More {
		t.loading = false
	}
	return changed
}

// Refresh asks Python for every change since the number held, a page at a time, and gives the computers whose place changed.
// get is the receiver's call to Python's internal paths.
// Refresh xin Python mọi thay đổi kể từ số đang giữ, từng trang một, và cho các máy đã đổi chỗ. get là lời gọi của bộ nhận tới các
// đường nội bộ của Python.
func (t *Table) Refresh(ctx context.Context, get func(ctx context.Context, path string, into any) error) ([]string, error) {
	var changed []string
	for {
		var p Page
		if err := get(ctx, t.Path(), &p); err != nil {
			return changed, err
		}
		changed = append(changed, t.Apply(p)...)
		if !p.More {
			return changed, nil
		}
	}
}
