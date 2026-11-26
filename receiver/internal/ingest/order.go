package ingest

// Which send of a computer an hour keeps, on this side (server/board/order.py on Python's): each hour keeps the time of the send it came
// from (clean.StampOf: seq, else updatedAt), and a send older than that does not replace it. The row waiting for Python keeps the time of
// its main send (base) and, apart, the time of each hour that came from another send, there or gone (stamps); the row brings both to
// Python (proto 3), so an hour of an older send in it never writes over a send that went straight to Python in between.
// Một giờ của một máy giữ lần gửi nào, ở bên này (server/board/order.py ở bên Python): mỗi giờ giữ thời điểm của lần gửi nó đến từ đó
// (clean.StampOf: seq, không thì updatedAt), và lần gửi cũ hơn thế không thay nó. Dòng chờ Python giữ thời điểm của lần gửi chính (base)
// và, riêng ra, thời điểm của từng giờ đến từ lần gửi khác, có mặt hay đã vắng (stamps); dòng mang cả hai tới Python (proto 3), để giờ của
// lần gửi cũ hơn trong dòng không bao giờ ghi đè một lần gửi đã đi thẳng tới Python ở giữa.

import (
	"sort"
	"strconv"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
)

// stampBytes is what one time of an hour counts in Holding: its key, its value and its share of the map.
// stampBytes là phần một thời điểm của một giờ tính vào Holding: khoá, giá trị và phần của nó trong map.
const stampBytes = 48

// hourKey names one hour of one kind of a book.
// hourKey gọi tên một giờ của một loại trong sổ.
type hourKey struct{ kind, hour string }

func isWhole(kind string) bool { return kind == "v1" || kind == "full" }

// stampOf is the time of the send the row's hour came from: its own when it has one; else the main send's when the row holds a whole book
// (an hour not there is gone as of then) or holds that hour; -1 when the row knows nothing of it, and any send takes it.
// stampOf là thời điểm của lần gửi mà giờ của dòng đến từ đó: của riêng nó nếu có; không thì của lần gửi chính khi dòng giữ một sổ đủ
// (giờ không có ở đó là đã vắng tính tới lúc ấy) hoặc giữ giờ đó; -1 khi dòng không biết gì về giờ đó, và lần gửi nào cũng nhận nó.
func (p *waiting) stampOf(row *pyjson.Object, kind, hour string) int64 {
	if s, ok := p.stamps[hourKey{kind, hour}]; ok {
		return s
	}
	if isWhole(p.kind) {
		return p.base
	}
	if t, ok := field(row, kind).(*pyjson.Object); ok {
		if _, ok := t.Get(hour); ok {
			return p.base
		}
	}
	return -1
}

// newerHours is the hour tables of d, a send stamped s, that are at least as new as what the row holds of each hour.
// newerHours là các bảng giờ của d, một lần gửi có thời điểm s, mới bằng hoặc hơn thứ dòng đang giữ của từng giờ.
func (p *waiting) newerHours(row, d *pyjson.Object, s int64) *pyjson.Object {
	out := pyjson.NewObject()
	for _, kind := range clean.HourKinds {
		t, ok := field(d, kind).(*pyjson.Object)
		if !ok {
			continue
		}
		table := pyjson.NewObject()
		for i, h := range t.Keys {
			if s >= p.stampOf(row, kind, h) {
				table.Set(h, t.Vals[i])
			}
		}
		out.Set(kind, table)
	}
	return out
}

// mark gives the hours of these tables the time s, kept apart only where it is not the main send's.
// mark đặt thời điểm s cho các giờ của các bảng này, chỉ giữ riêng khi nó khác thời điểm của lần gửi chính.
func (p *waiting) mark(hours *pyjson.Object, s int64) {
	for _, kind := range clean.HourKinds {
		t, ok := field(hours, kind).(*pyjson.Object)
		if !ok {
			continue
		}
		for _, h := range t.Keys {
			if s == p.base {
				delete(p.stamps, hourKey{kind, h})
				continue
			}
			if p.stamps == nil {
				p.stamps = map[hourKey]int64{}
			}
			p.stamps[hourKey{kind, h}] = s
		}
	}
}

// above is what the row holds from sends newer than s, as a send would carry it: each such hour's table, or an empty one where it is gone;
// and the times of those hours.
// above là thứ dòng đang giữ từ các lần gửi mới hơn s, như một lần gửi sẽ mang: bảng của từng giờ như thế, hoặc bảng rỗng khi giờ đã vắng;
// cùng thời điểm của các giờ đó.
func (p *waiting) above(row *pyjson.Object, s int64) (*pyjson.Object, map[hourKey]int64) {
	out, times := pyjson.NewObject(), map[hourKey]int64{}
	for _, kind := range clean.HourKinds {
		table := pyjson.NewObject()
		t, _ := field(row, kind).(*pyjson.Object)
		if t != nil {
			for i, h := range t.Keys {
				if at := p.stampOf(row, kind, h); at > s {
					table.Set(h, t.Vals[i])
					times[hourKey{kind, h}] = at
				}
			}
		}
		var gone []string
		for k, at := range p.stamps {
			if _, there := times[k]; k.kind == kind && !there && at > s && (t == nil || !has(t, k.hour)) {
				gone = append(gone, k.hour)
			}
		}
		sort.Slice(gone, func(i, j int) bool { a, _ := strconv.Atoi(gone[i]); b, _ := strconv.Atoi(gone[j]); return a < b })
		for _, h := range gone {
			table.Set(h, pyjson.NewObject())
			times[hourKey{kind, h}] = p.stamps[hourKey{kind, h}]
		}
		out.Set(kind, table)
	}
	return out, times
}

// hourCount is the number of hours in the hour tables of d, empty ones included: an empty table removes an hour, and is an hour of the send.
// hourCount là số giờ trong các bảng giờ của d, kể cả bảng rỗng: bảng rỗng xoá một giờ, và vẫn là một giờ của lần gửi.
func hourCount(d *pyjson.Object) int {
	n := 0
	for _, kind := range clean.HourKinds {
		if t, ok := field(d, kind).(*pyjson.Object); ok {
			n += len(t.Keys)
		}
	}
	return n
}

func has(o *pyjson.Object, k string) bool {
	_, ok := o.Get(k)
	return ok
}

// newest is whichever of two cleaned sends is the newer, by their times: the state of the row comes from it.
// newest là lần gửi mới hơn trong hai lần gửi đã làm sạch, theo thời điểm của chúng: trạng thái của dòng lấy từ nó.
func newest(a, b *pyjson.Object) *pyjson.Object {
	if a == nil || clean.StampOf(b) >= clean.StampOf(a) {
		return b
	}
	return a
}

// batchRow is the row for a batch: row() with the time of the main send (stamp) and those of the hours kept apart (stamps).
// batchRow là dòng cho một lô: row() kèm thời điểm của lần gửi chính (stamp) và của các giờ giữ riêng (stamps).
func (p *waiting) batchRow() pyjson.Value {
	out := row(p.row(), p.kind, p.ip, p.at, p.delegations, nil).(*pyjson.Object)
	out.Set("stamp", pyjson.IntN(p.base))
	if p.older > 0 {
		out.Set("older", pyjson.IntN(int64(p.older)))
	}
	if len(p.stamps) > 0 {
		keys := make([]hourKey, 0, len(p.stamps))
		for k := range p.stamps {
			keys = append(keys, k)
		}
		sort.Slice(keys, func(i, j int) bool {
			if keys[i].kind != keys[j].kind {
				return keys[i].kind < keys[j].kind
			}
			a, _ := strconv.Atoi(keys[i].hour)
			b, _ := strconv.Atoi(keys[j].hour)
			return a < b
		})
		stamps := pyjson.NewObject()
		for _, k := range keys {
			t, ok := stamps.Get(k.kind)
			if !ok {
				t = pyjson.NewObject()
				stamps.Set(k.kind, t)
			}
			t.(*pyjson.Object).Set(k.hour, pyjson.IntN(p.stamps[k]))
		}
		out.Set("stamps", stamps)
	}
	return out
}

// hourStamp is the time of one hour held apart from held.base (heldKey, order.go).
// hourStamp là thời điểm của một giờ đang giữ, khác held.base (heldKey, order.go).
type hourStamp struct{ key, at int64 }

// heldKey is the key of one hour of the ledger (0) or tasks (1) book in held.stamps.
// heldKey là khoá của một giờ của sổ ledger (0) hoặc tasks (1) trong held.stamps.
func heldKey(kind string, hour int64) int64 {
	if kind == "tasks" {
		return hour<<1 | 1
	}
	return hour << 1
}

func (h *held) find(k int64) (int, bool) {
	i := sort.Search(len(h.stamps), func(i int) bool { return h.stamps[i].key >= k })
	return i, i < len(h.stamps) && h.stamps[i].key == k
}

// heldStamp is the time of the send an hour held came from: its own when kept apart, else base; -1 for an hour not held, or when the
// time is not known (a Python of protocol 2), and any send replaces it. Python keeps no time for an hour it removed either.
// heldStamp là thời điểm của lần gửi mà giờ đang giữ đến từ đó: của riêng nó nếu giữ riêng, không thì base; -1 cho giờ không giữ, hoặc
// khi không biết thời điểm (Python giao thức 2), và lần gửi nào cũng thay được. Python cũng không giữ thời điểm cho giờ nó đã xoá.
func (h *held) heldStamp(kind string, hour int64) int64 {
	if h == nil {
		return -1
	}
	book := h.ledger
	if kind == "tasks" {
		book = h.tasks
	}
	if _, ok := book[hour]; !ok {
		return -1
	}
	if i, ok := h.find(heldKey(kind, hour)); ok {
		return h.stamps[i].at
	}
	return h.base
}

// setStamp gives an hour held the time s, kept apart only when it is not base: after a whole book most hours share its time, so few
// are kept apart. A map of every hour cost a quarter more memory for the books held (TestMemoryOfManyComputers).
// setStamp đặt thời điểm s cho một giờ đang giữ, chỉ giữ riêng khi khác base: sau một sổ đủ phần lớn các giờ có chung thời điểm của sổ,
// nên ít giờ phải giữ riêng. Một map cho mọi giờ từng làm các sổ đang giữ tốn thêm một phần tư bộ nhớ (TestMemoryOfManyComputers).
func (h *held) setStamp(kind string, hour, s int64) {
	k := heldKey(kind, hour)
	i, there := h.find(k)
	switch {
	case s == h.base && there:
		h.stamps = append(h.stamps[:i], h.stamps[i+1:]...)
	case s == h.base:
	case there:
		h.stamps[i].at = s
	default:
		h.stamps = append(h.stamps, hourStamp{})
		copy(h.stamps[i+1:], h.stamps[i:])
		h.stamps[i] = hourStamp{k, s}
	}
}

func (h *held) dropStamp(kind string, hour int64) {
	if i, ok := h.find(heldKey(kind, hour)); ok {
		h.stamps = append(h.stamps[:i], h.stamps[i+1:]...)
	}
}

// stampsFrom puts the times of Python's book ({kind: {hour: time}}, proto 3) on the hours held from lo on: the most common one becomes
// base, the others are kept apart.
// stampsFrom đặt các thời điểm của sổ Python ({loại: {giờ: thời điểm}}, proto 3) lên các giờ đang giữ từ lo trở đi: thời điểm hay gặp
// nhất thành base, các thời điểm khác giữ riêng.
func (h *held) stampsFrom(rec *pyjson.Object, lo int64) {
	type one struct {
		kind     string
		hour, at int64
	}
	var all []one
	count := map[int64]int{}
	for _, kind := range []string{"ledger", "tasks"} {
		t, ok := field(field(rec, "stamps"), kind).(*pyjson.Object)
		if !ok {
			continue
		}
		for i, hour := range t.Keys {
			n, err := strconv.ParseInt(hour, 10, 64)
			at, isNum := t.Vals[i].(pyjson.Number)
			if err != nil || n < lo || !isNum || !at.Int || at.Big != nil {
				continue
			}
			all = append(all, one{kind, n, at.I})
			count[at.I]++
		}
	}
	for at, c := range count {
		if c > count[h.base] || c == count[h.base] && at > h.base {
			h.base = at
		}
	}
	for _, o := range all {
		h.setStamp(o.kind, o.hour, o.at)
	}
}
