// Package totals adds up the hour books into totals per local day, as add_up_hours in server/board/devices.py does, and keeps them per
// computer. It is apart from the package that takes the sends, so the live numbers (package live) read it alone.
// Package totals cộng sổ giờ thành tổng theo từng ngày địa phương, như add_up_hours trong server/board/devices.py, và giữ chúng theo
// từng máy. Nó tách khỏi gói nhận số, để số trực tiếp (gói live) đọc riêng được nó.
package totals

import (
	"math"
	"math/big"
	"sort"
	"strconv"
	"sync"
	"time"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
)

// Day is one local day of one computer or person, money in usdMicro.
// Day là một ngày địa phương của một máy hay một người, tiền theo usdMicro.
type Day struct {
	USDMicro  *big.Int
	TokensIn  *big.Int
	TokensOut *big.Int
	Tasks     [3]*big.Int
}

func newDay() *Day {
	return &Day{USDMicro: new(big.Int), TokensIn: new(big.Int), TokensOut: new(big.Int), Tasks: [3]*big.Int{new(big.Int), new(big.Int), new(big.Int)}}
}

func (d *Day) add(o *Day) {
	d.USDMicro.Add(d.USDMicro, o.USDMicro)
	d.TokensIn.Add(d.TokensIn, o.TokensIn)
	d.TokensOut.Add(d.TokensOut, o.TokensOut)
	for i := range d.Tasks {
		d.Tasks[i].Add(d.Tasks[i], o.Tasks[i])
	}
}

// LocalDay is local_day_of_hour: the local day (YYYY-MM-DD) an hour number falls in, with a fixed offset from UTC in seconds.
// LocalDay là local_day_of_hour: ngày địa phương (YYYY-MM-DD) mà một số giờ rơi vào, với độ lệch cố định so với UTC theo giây.
func LocalDay(hour int64, tzSeconds int64) string {
	s := hour*3600 + tzSeconds
	days := s / 86400
	if s%86400 < 0 {
		days--
	}
	return time.Unix(days*86400, 0).UTC().Format("2006-01-02")
}

// FirstHour is today_first_hour of server/board/devices.py: the first hour number of the local day the second now falls in, with a
// fixed offset from UTC in seconds that may be a part of an hour.
// FirstHour là today_first_hour của server/board/devices.py: số giờ đầu tiên của ngày địa phương mà giây now rơi vào, với độ lệch
// cố định so với UTC theo giây, có thể là một phần của giờ.
func FirstHour(now float64, tzSeconds int64) int64 {
	day := floorDiv(int64(math.Floor(now))+tzSeconds, 86400)
	// the first hour that starts in that day: -floor(-x / 3600) is x / 3600 rounded up, as Python's -((tz - n * 86400) // 3600)
	// giờ đầu tiên bắt đầu trong ngày đó: -floor(-x / 3600) là x / 3600 làm tròn lên, như -((tz - n * 86400) // 3600) của Python
	return -floorDiv(tzSeconds-day*86400, 3600)
}

func floorDiv(a, b int64) int64 {
	q := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

// intOf is int(v.get(k) or 0) of Python, for a number in a cleaned hour.
// intOf là int(v.get(k) or 0) của Python, cho một số trong một giờ đã làm sạch.
func intOf(v pyjson.Value, k string) *big.Int {
	o, ok := v.(*pyjson.Object)
	if !ok {
		return new(big.Int)
	}
	x, _ := o.Get(k)
	n, ok := x.(pyjson.Number)
	if !ok {
		return new(big.Int)
	}
	if n.Int {
		return n.AsBig()
	}
	b, _ := new(big.Float).SetFloat64(n.F).Int(nil)
	return b
}

// AddUp is the days part of add_up_hours: one computer's book added up per local day.
// AddUp là phần theo ngày của add_up_hours: sổ của một máy cộng theo từng ngày địa phương.
func AddUp(book *pyjson.Object, tzSeconds int64) map[string]*Day {
	days := map[string]*Day{}
	for _, field := range []string{"ledger", "tasks"} {
		x, _ := book.Get(field)
		table, ok := x.(*pyjson.Object)
		if !ok {
			continue
		}
		for i, hour := range table.Keys {
			v, ok := table.Vals[i].(*pyjson.Object)
			if !ok {
				continue
			}
			h, err := strconv.ParseInt(hour, 10, 64)
			if err != nil {
				continue
			}
			day := LocalDay(h, tzSeconds)
			r := days[day]
			if r == nil {
				r = newDay()
				days[day] = r
			}
			if field == "ledger" {
				r.USDMicro.Add(r.USDMicro, clean.Micro(v).AsBig())
				r.TokensIn.Add(r.TokensIn, intOf(v, "input"))
				r.TokensIn.Add(r.TokensIn, intOf(v, "cacheRead"))
				r.TokensIn.Add(r.TokensIn, intOf(v, "cacheWrite"))
				r.TokensOut.Add(r.TokensOut, intOf(v, "output"))
			} else {
				for j, w := range clean.Workers {
					r.Tasks[j].Add(r.Tasks[j], intOf(v, w))
				}
			}
		}
	}
	return days
}

// Hour is one hour of one kind as AddUp counts it: for ledger the money in usdMicro, tokens in, tokens out; for tasks the tasks given to
// Gemini, ChatGPT and Gemma. Three whole numbers instead of the hour's table, so a computer's day takes little memory.
// Hour là một giờ của một loại như AddUp đếm nó: với ledger là tiền theo usdMicro, token vào, token ra; với tasks là việc giao cho
// Gemini, ChatGPT và Gemma. Ba số nguyên thay cho bảng của giờ đó, để một ngày của một máy tốn ít bộ nhớ.
type Hour [3]int64

// HourOf is the numbers AddUp takes from one cleaned hour of a kind ("ledger" or "tasks").
// HourOf là các con số AddUp lấy từ một giờ đã làm sạch của một loại ("ledger" hoặc "tasks").
func HourOf(kind string, v pyjson.Value) Hour {
	if kind == "ledger" {
		o, _ := v.(*pyjson.Object)
		micro := new(big.Int)
		if o != nil {
			micro = clean.Micro(o).AsBig()
		}
		in := new(big.Int).Add(intOf(v, "input"), intOf(v, "cacheRead"))
		in.Add(in, intOf(v, "cacheWrite"))
		return Hour{micro.Int64(), in.Int64(), intOf(v, "output").Int64()}
	}
	var h Hour
	for j, w := range clean.Workers {
		h[j] = intOf(v, w).Int64()
	}
	return h
}

// DaysOf adds hours held as Hour up per local day, the same as AddUp on the tables they came from.
// DaysOf cộng các giờ giữ dạng Hour theo từng ngày địa phương, đúng như AddUp trên các bảng chúng đến từ.
func DaysOf(ledger, tasks map[int64]Hour, tzSeconds int64) map[string]*Day {
	days := map[string]*Day{}
	for i, book := range []map[int64]Hour{ledger, tasks} {
		for hour, v := range book {
			day := LocalDay(hour, tzSeconds)
			r := days[day]
			if r == nil {
				r = newDay()
				days[day] = r
			}
			if i == 0 {
				r.USDMicro.Add(r.USDMicro, big.NewInt(v[0]))
				r.TokensIn.Add(r.TokensIn, big.NewInt(v[1]))
				r.TokensOut.Add(r.TokensOut, big.NewInt(v[2]))
			} else {
				for j := range r.Tasks {
					r.Tasks[j].Add(r.Tasks[j], big.NewInt(v[j]))
				}
			}
		}
	}
	return days
}

// Store keeps each computer's totals per local day; the live numbers (package live) add them up per row of the board, never per pid.
// Store giữ tổng theo ngày địa phương của từng máy; số trực tiếp (gói live) cộng chúng theo dòng của bảng, không bao giờ theo pid.
type Store struct {
	mu      sync.RWMutex
	devices map[string]map[string]*Day
}

// NewStore makes an empty store.
// NewStore tạo một kho rỗng.
func NewStore() *Store { return &Store{devices: map[string]map[string]*Day{}} }

// Put replaces one computer's totals; the days given are not changed afterwards, by the store or by the caller.
// Put thay tổng của một máy; các ngày đưa vào không bị đổi về sau, bởi kho hay bởi bên gọi.
func (s *Store) Put(device string, days map[string]*Day) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.devices[device] = days
}

// Drop takes one computer out.
// Drop bỏ một máy ra.
func (s *Store) Drop(device string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.devices, device)
}

// Day is one computer's totals of one local day (YYYY-MM-DD), nil if it has none; do not change it.
// Day là tổng của một máy trong một ngày địa phương (YYYY-MM-DD), nil nếu không có; đừng sửa nó.
func (s *Store) Day(device, day string) *Day {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.devices[device][day]
}

// Days is the local days one computer has totals for, in order.
// Days là các ngày địa phương mà một máy có tổng, theo thứ tự.
func (s *Store) Days(device string) []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	keys := make([]string, 0, len(s.devices[device]))
	for k := range s.devices[device] {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
