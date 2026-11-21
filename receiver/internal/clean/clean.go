// Package clean is the Go copy of the cleaning in server/board/devices.py: clean_payload, clean_delegations, merge_hours and the money
// in usdMicro. Each function says which Python function it copies; both must give the same result for every send
// (tests/contract/ingest-v2 and the random test with Python as the judge check it).
// Package clean là bản chép bằng Go của bước làm sạch trong server/board/devices.py: clean_payload, clean_delegations, merge_hours và tiền
// theo usdMicro. Mỗi hàm ghi rõ nó chép hàm Python nào; hai bên phải cho cùng kết quả với mọi lần gửi
// (tests/contract/ingest-v2 và bài thử ngẫu nhiên có Python làm trọng tài kiểm điều đó).
package clean

import (
	"math"
	"math/big"
	"sort"
	"strconv"
	"unicode/utf8"

	"aiworker/receiver/internal/pyjson"
)

// The same numbers as server/board/settings.py and server/board/devices.py.
// Cùng các con số như server/board/settings.py và server/board/devices.py.
const (
	MaxHoursPerDevice  = 8*24 + 48
	IPHistoryMax       = 10
	MaxDelegations     = 100
	DelegationMaxAgeMs = 3 * 86_400_000
	ReorderWindowMs    = 60_000
	FullBookSeconds    = 3600
	defaultHigh        = 1e15
	hourMs             = 3_600_000
	dayMs              = 86_400_000
	maxExactInt        = 1 << 53
)

var (
	// Workers are the helpers a computer counts work for.
	// Workers là các trợ lý mà máy đếm số việc giao cho.
	Workers        = []string{"gemini", "chatgpt", "gemma"}
	BlockKinds     = []string{"secret", "commit", "risky", "page", "answer"}
	HourKinds      = []string{"ledger", "tasks", "blocks"}
	sessionCounts  = []string{"openSessions", "working", "waiting"}
	connectorTools = []string{"codex", "cursor", "gemini"}
	delegationTool = map[string]string{"ask_chatgpt": "chatgpt", "ask_gemini": "gemini", "generate_image": "gemini", "ask_local": "gemma"}
	delegationOut  = []string{"ok", "error", "refused", "declined"}
	delegationChk  = []string{"secret", "aimed", "command"}
	delegationVia  = []string{"plugin", "ai-workers"}
)

type obj = pyjson.Object
type num = pyjson.Number

func has(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

// get is d.get(k) on a value that may not be a table.
// get là d.get(k) trên một giá trị có thể không phải bảng.
func get(v pyjson.Value, k string) pyjson.Value {
	o, ok := v.(*obj)
	if !ok {
		return nil
	}
	x, _ := o.Get(k)
	return x
}

// cmpFloat compares a number with a finite float exactly, as Python compares an int or a float with a float.
// cmpFloat so một số với một số thực hữu hạn một cách chính xác, như Python so int hay float với float.
func cmpFloat(n num, f float64) int {
	if !n.Int {
		switch {
		case n.F < f:
			return -1
		case n.F > f:
			return 1
		}
		return 0
	}
	if n.Big == nil && n.I <= maxExactInt && n.I >= -maxExactInt {
		x := float64(n.I)
		switch {
		case x < f:
			return -1
		case x > f:
			return 1
		}
		return 0
	}
	return new(big.Float).SetInt(n.AsBig()).Cmp(new(big.Float).SetFloat64(f))
}

// cleanNumber copies clean_number: a finite number from 0 to high, or false. true and false are not numbers here.
// cleanNumber chép clean_number: một số hữu hạn từ 0 tới high, hoặc false. true và false không tính là số.
func cleanNumber(v pyjson.Value, high float64) (num, bool) {
	n, ok := v.(num)
	if !ok {
		return num{}, false
	}
	if !n.Int && (math.IsInf(n.F, 0) || math.IsNaN(n.F)) {
		return num{}, false
	}
	return n, cmpFloat(n, 0) >= 0 && cmpFloat(n, high) <= 0
}

// toInt is Python's int(n): a float is cut toward zero.
// toInt là int(n) của Python: số thực bị cắt về phía 0.
func toInt(n num) num {
	if n.Int {
		return n
	}
	if math.Abs(n.F) < 9e18 {
		return pyjson.IntN(int64(n.F))
	}
	b, _ := new(big.Float).SetFloat64(math.Trunc(n.F)).Int(nil)
	return pyjson.BigN(b)
}

// intOrZero is int(clean_number(v, high) or 0).
// intOrZero là int(clean_number(v, high) or 0).
func intOrZero(v pyjson.Value, high float64) num {
	n, ok := cleanNumber(v, high)
	if !ok || cmpFloat(n, 0) == 0 {
		return pyjson.IntN(0)
	}
	return toInt(n)
}

func runeLen(s string) int { return utf8.RuneCountInString(s) }

func runePrefix(s string, n int) string {
	i := 0
	for j := range s {
		if i == n {
			return s[:j]
		}
		i++
	}
	return s
}

// cleanText copies clean_text: no control characters, at most limit characters; "" for anything that is not text.
// cleanText chép clean_text: không ký tự điều khiển, tối đa limit ký tự; "" với mọi thứ không phải chữ.
func cleanText(v pyjson.Value, limit int) string {
	s, ok := v.(string)
	if !ok {
		return ""
	}
	out := make([]rune, 0, len(s))
	for _, r := range s {
		if r > 0x1f && r != 0x7f {
			out = append(out, r)
		}
	}
	if len(out) > limit {
		out = out[:limit]
	}
	return string(out)
}

func allIn(s string, min, max int, ok func(byte) bool) bool {
	if len(s) < min || len(s) > max {
		return false
	}
	for i := 0; i < len(s); i++ {
		if !ok(s[i]) {
			return false
		}
	}
	return true
}

func isDigit(c byte) bool    { return c >= '0' && c <= '9' }
func isLowHex(c byte) bool   { return isDigit(c) || (c >= 'a' && c <= 'f') }
func isLowAlnum(c byte) bool { return isDigit(c) || (c >= 'a' && c <= 'z') }
func isLetter(c byte) bool   { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') }

// IsDeviceID is DEVICE_NAME_RE: device- and 1 to 40 small letters or digits.
// IsDeviceID là DEVICE_NAME_RE: device- và 1 tới 40 chữ thường hay chữ số.
func IsDeviceID(s string) bool {
	return len(s) > 7 && s[:7] == "device-" && allIn(s[7:], 1, 40, isLowAlnum)
}

// cleanCounts copies clean_counts: a small table of numbers, anything else in it dropped.
// cleanCounts chép clean_counts: một bảng số nhỏ, mọi thứ khác trong đó bị bỏ.
func cleanCounts(v pyjson.Value, keys []string, maxKeys, keyLimit int) *obj {
	out := pyjson.NewObject()
	o, ok := v.(*obj)
	if !ok {
		return out
	}
	for i, k := range o.Keys {
		n, ok := cleanNumber(o.Vals[i], defaultHigh)
		if ok && runeLen(k) <= keyLimit && (keys == nil || has(keys, k)) && out.Len() < maxKeys {
			out.Set(k, n)
		}
	}
	return out
}

// hourOf gives int(now_ms / 3_600_000), as Python works it out from a float.
// hourOf cho int(now_ms / 3_600_000), như Python tính từ một số thực.
func hourOf(nowMs float64) int64 { return int64(nowMs / hourMs) }

// cleanHours copies clean_hours: numbers per hour, the newest MaxHoursPerDevice kept; hasOldest false means no lower bound.
// cleanHours chép clean_hours: số liệu theo giờ, giữ MaxHoursPerDevice giờ mới nhất; hasOldest false nghĩa là không có cận dưới.
func cleanHours(v pyjson.Value, nowMs float64, keys []string, oldest int64, hasOldest, keepEmpty bool) *obj {
	out := pyjson.NewObject()
	o, ok := v.(*obj)
	if !ok {
		return out
	}
	top := hourOf(nowMs) + 24
	type hour struct {
		key string
		n   int64
		at  int
	}
	var hours []hour
	for i, k := range o.Keys {
		if !allIn(k, 1, 8, isDigit) {
			continue
		}
		n, _ := strconv.ParseInt(k, 10, 64)
		if n <= top && (!hasOldest || n >= oldest) {
			hours = append(hours, hour{k, n, i})
		}
	}
	sort.SliceStable(hours, func(a, b int) bool { return hours[a].n < hours[b].n })
	if len(hours) > MaxHoursPerDevice {
		hours = hours[len(hours)-MaxHoursPerDevice:]
	}
	for _, h := range hours {
		table := cleanCounts(o.Vals[h.at], keys, 16, 24)
		if table.Len() > 0 || keepEmpty {
			out.Set(h.key, table)
		}
	}
	return out
}

var million = big.NewInt(1_000_000)

// roundToInt is int(round(x)) of usdMicro, or of usd * 1_000_000, as clean_ledger_hours works it out; it may not fit in 64 bits.
// roundToInt là int(round(x)) của usdMicro, hoặc của usd * 1_000_000, như clean_ledger_hours tính; nó có thể không vừa 64 bit.
func roundToInt(f float64) num {
	r := math.RoundToEven(f)
	if math.Abs(r) < 9e18 {
		return pyjson.IntN(int64(r))
	}
	b, _ := new(big.Float).SetFloat64(r).Int(nil)
	return pyjson.BigN(b)
}

// USDOf is micro / 1_000_000 in Python: the float nearest to the exact quotient.
// USDOf là micro / 1_000_000 trong Python: số thực gần nhất với thương đúng.
func USDOf(micro num) num {
	if micro.Big == nil && micro.I <= maxExactInt && micro.I >= -maxExactInt {
		return pyjson.FloatN(float64(micro.I) / 1_000_000)
	}
	f, _ := new(big.Rat).SetFrac(micro.AsBig(), million).Float64()
	return pyjson.FloatN(f)
}

// cleanLedgerHours copies clean_ledger_hours: spend per hour, money as a whole number of millionths of a dollar (usdMicro) and usd
// worked out from it, put last in that order.
// cleanLedgerHours chép clean_ledger_hours: chi tiêu theo giờ, tiền là số nguyên phần triệu đô la (usdMicro) và usd tính từ nó,
// đặt cuối theo thứ tự đó.
func cleanLedgerHours(v pyjson.Value, nowMs float64, oldest int64, hasOldest, keepEmpty bool) *obj {
	out := cleanHours(v, nowMs, nil, oldest, hasOldest, keepEmpty)
	for i := range out.Keys {
		table := out.Vals[i].(*obj)
		var micro num
		if m, ok := table.Get("usdMicro"); ok {
			micro = m.(num)
			if !micro.Int {
				micro = roundToInt(micro.F)
			}
		} else if u, ok := table.Get("usd"); ok {
			usd := u.(num)
			if usd.Int {
				micro = pyjson.BigN(new(big.Int).Mul(usd.AsBig(), million))
			} else {
				micro = roundToInt(usd.F * 1_000_000)
			}
		} else {
			micro = pyjson.IntN(0)
		}
		table.Delete("usd")
		table.Delete("usdMicro")
		if cmpFloat(micro, 0) != 0 || table.Len() > 0 {
			table.Set("usdMicro", micro)
			table.Set("usd", USDOf(micro))
		}
	}
	if keepEmpty {
		return out
	}
	kept := pyjson.NewObject()
	for i, k := range out.Keys {
		if out.Vals[i].(*obj).Len() > 0 {
			kept.Set(k, out.Vals[i])
		}
	}
	return kept
}

// equalsInt is d.get("v") == 1 or == 2 in Python, where true equals 1.
// equalsInt là d.get("v") == 1 hay == 2 trong Python, nơi true bằng 1.
func equalsInt(v pyjson.Value, want float64) bool {
	if b, ok := v.(bool); ok {
		return b && want == 1
	}
	n, ok := v.(num)
	return ok && cmpFloat(n, want) == 0
}

// IsSecondFormat is d["v"] == 2.
// IsSecondFormat là d["v"] == 2.
func IsSecondFormat(v pyjson.Value) bool { return equalsInt(get(v, "v"), 2) }

// SendKind copies send_kind: "v1" and "full" bring the whole hour book, "hours" only the hours that changed.
// SendKind chép send_kind: "v1" và "full" mang cả sổ giờ, "hours" chỉ mang các giờ đã đổi.
func SendKind(raw pyjson.Value) string {
	if _, ok := raw.(*obj); !ok || !IsSecondFormat(raw) {
		return "v1"
	}
	if f, ok := get(raw, "full").(bool); ok && f {
		return "full"
	}
	return "hours"
}

// Payload copies clean_payload: what a computer sent, rebuilt from a fixed list of fields, types and sizes; nil if it is not a report.
// now is the server's clock in seconds. What comes out is always the v: 1 form, as in Python.
// Payload chép clean_payload: những gì một máy gửi, dựng lại từ danh sách cố định các trường, kiểu và cỡ; nil nếu không phải báo cáo.
// now là đồng hồ máy chủ theo giây. Thứ đi ra luôn ở dạng v: 1, như trong Python.
func Payload(d pyjson.Value, now float64) *obj {
	nowMs := now * 1000
	o, ok := d.(*obj)
	if !ok {
		return nil
	}
	v, _ := o.Get("v")
	device, _ := o.Get("device")
	dev, isStr := device.(string)
	updated, _ := o.Get("updatedAt")
	if !(equalsInt(v, 1) || equalsInt(v, 2)) || !isStr || !IsDeviceID(dev) {
		return nil
	}
	updatedAt, ok := cleanNumber(updated, defaultHigh)
	if !ok {
		return nil
	}
	out := pyjson.NewObject()
	out.Set("v", pyjson.IntN(1))
	out.Set("device", dev)
	if bound := nowMs + dayMs; cmpFloat(updatedAt, bound) > 0 {
		updatedAt = pyjson.FloatN(bound)
	}
	out.Set("updatedAt", updatedAt)
	for _, f := range []struct {
		name  string
		limit int
	}{{"name", 120}, {"account", 120}, {"enteredAccount", 120}, {"lanIp", 45}, {"ip", 45}, {"pluginVersion", 20}} {
		if text := cleanText(get(o, f.name), f.limit); text != "" {
			out.Set(f.name, text)
		}
	}
	for _, f := range sessionCounts {
		out.Set(f, intOrZero(get(o, f), 100000))
	}
	if tools, ok := get(o, "tools").(*obj); ok {
		cleaned := pyjson.NewObject()
		for _, tool := range connectorTools {
			if counts, ok := get(tools, tool).(*obj); ok {
				c := pyjson.NewObject()
				for _, f := range sessionCounts {
					c.Set(f, intOrZero(get(counts, f), 100000))
				}
				cleaned.Set(tool, c)
			}
		}
		out.Set("tools", cleaned)
		for _, f := range sessionCounts {
			sum := new(big.Int)
			for _, c := range cleaned.Vals {
				x, _ := c.(*obj).Get(f)
				sum.Add(sum, x.(num).AsBig())
			}
			out.Set(f, pyjson.BigN(sum))
		}
	}
	if mark, ok := get(o, "hardwareMark").(string); ok && allIn(mark, 32, 32, isLowHex) {
		out.Set("hardwareMark", mark)
	}
	if list, ok := get(o, "ipHistory").([]pyjson.Value); ok {
		var history []pyjson.Value
		for _, e := range list {
			eo, ok := e.(*obj)
			if !ok || cleanText(get(eo, "ip"), 45) == "" {
				continue
			}
			from, okFrom := cleanNumber(get(eo, "from"), defaultHigh)
			to, okTo := cleanNumber(get(eo, "to"), defaultHigh)
			if !okFrom || !okTo {
				continue
			}
			h := pyjson.NewObject()
			h.Set("ip", cleanText(get(eo, "ip"), 45))
			h.Set("from", from)
			h.Set("to", to)
			history = append(history, h)
		}
		if len(history) > 0 {
			if len(history) > IPHistoryMax {
				history = history[:IPHistoryMax]
			}
			out.Set("ipHistory", history)
		}
	}
	out.Set("delegating", cleanCounts(get(o, "delegating"), Workers, 16, 24))
	out.Set("models", cleanCounts(get(o, "models"), nil, 20, 79))
	out.Set("subagents", cleanCounts(get(o, "subagents"), nil, 10, 40))
	second := equalsInt(v, 2)
	var book pyjson.Value = o
	if second {
		book = get(o, "hours")
	}
	if _, ok := book.(*obj); !ok {
		book = pyjson.NewObject()
	}
	oldest := hourOf(nowMs) - MaxHoursPerDevice
	out.Set("ledger", cleanLedgerHours(get(book, "ledger"), nowMs, oldest, second, second))
	out.Set("tasks", cleanHours(get(book, "tasks"), nowMs, Workers, oldest, second, second))
	if blocks := cleanHours(get(book, "blocks"), nowMs, BlockKinds, oldest, second, second); blocks.Len() > 0 {
		out.Set("blocks", blocks)
	}
	if a, ok := get(o, "assistants").(*obj); ok {
		as := pyjson.NewObject()
		isTrue := func(k string) bool { b, ok := get(a, k).(bool); return ok && b }
		as.Set("chatgpt", isTrue("chatgpt"))
		as.Set("gemini", isTrue("gemini"))
		as.Set("gemma", cleanText(get(a, "gemma"), 40))
		as.Set("chatgptModel", cleanText(get(a, "chatgptModel"), 60))
		as.Set("geminiModel", cleanText(get(a, "geminiModel"), 60))
		out.Set("assistants", as)
	}
	if q, ok := get(o, "quota").(*obj); ok {
		readAt := get(q, "readAt")
		list, isList := get(q, "windows").([]pyjson.Value)
		if _, ok := cleanNumber(readAt, defaultHigh); ok && isList {
			windows := []pyjson.Value{}
			if len(list) > 5 {
				list = list[:5]
			}
			for _, w := range list {
				wo, ok := w.(*obj)
				if !ok {
					continue
				}
				kind, isKind := get(wo, "kind").(string)
				pct := get(wo, "pct")
				if _, ok := cleanNumber(pct, 999); !isKind || !ok {
					continue
				}
				e := pyjson.NewObject()
				e.Set("kind", runePrefix(kind, 30))
				e.Set("pct", pct)
				if r := get(wo, "resetsAt"); r != nil {
					if _, ok := cleanNumber(r, defaultHigh); ok {
						e.Set("resetsAt", r)
					}
				}
				windows = append(windows, e)
			}
			qo := pyjson.NewObject()
			qo.Set("readAt", readAt)
			qo.Set("windows", windows)
			out.Set("quota", qo)
		}
	}
	return out
}

// Delegations copies clean_delegations: the records of work handed to helpers, rebuilt from a fixed list; anything else, too old or from
// the future is dropped. nowMs is the server's clock in milliseconds.
// Delegations chép clean_delegations: các biên bản giao việc cho trợ lý, dựng lại từ danh sách cố định; mọi thứ khác, quá cũ hay ở
// tương lai đều bị bỏ. nowMs là đồng hồ máy chủ theo mili giây.
func Delegations(v pyjson.Value, nowMs float64) []pyjson.Value {
	out := []pyjson.Value{}
	list, ok := v.([]pyjson.Value)
	if !ok {
		return out
	}
	if len(list) > MaxDelegations {
		list = list[len(list)-MaxDelegations:]
	}
	for _, e := range list {
		d, ok := e.(*obj)
		if !ok {
			continue
		}
		rid, isID := get(d, "id").(string)
		tool, isTool := get(d, "tool").(string)
		at, isAt := cleanNumber(get(d, "at"), defaultHigh)
		if !(isID && allIn(rid, 24, 24, isLowHex) && isTool && delegationTool[tool] != "" && isAt) {
			continue
		}
		if !(cmpFloat(at, nowMs-DelegationMaxAgeMs) > 0 && cmpFloat(at, nowMs+dayMs) < 0) {
			continue
		}
		r := pyjson.NewObject()
		r.Set("id", rid)
		r.Set("at", toInt(at))
		r.Set("tool", tool)
		r.Set("worker", delegationTool[tool])
		via := "plugin"
		if s, ok := get(d, "via").(string); ok && has(delegationVia, s) {
			via = s
		}
		r.Set("via", via)
		r.Set("promptChars", intOrZero(get(d, "promptChars"), 10_000_000))
		r.Set("answerChars", intOrZero(get(d, "answerChars"), 100_000_000))
		hash := ""
		if s, ok := get(d, "promptHash").(string); ok && allIn(s, 32, 32, isLowHex) {
			hash = s
		}
		r.Set("promptHash", hash)
		outcome := "error"
		if s, ok := get(d, "outcome").(string); ok && has(delegationOut, s) {
			outcome = s
		}
		r.Set("outcome", outcome)
		checks, _ := get(d, "check").([]pyjson.Value)
		chk := []pyjson.Value{}
		for _, c := range delegationChk {
			for _, x := range checks {
				if s, ok := x.(string); ok && s == c {
					chk = append(chk, c)
					break
				}
			}
		}
		r.Set("check", chk)
		found, _ := get(d, "found").([]pyjson.Value)
		if len(found) > 8 {
			found = found[:8]
		}
		seen := map[string]bool{}
		var names []string
		for _, x := range found {
			s, ok := x.(string)
			if ok && len(s) >= 2 && len(s) <= 40 && isLetter(s[0]) && allIn(s[1:], 1, 39, func(c byte) bool { return isLetter(c) || c == ' ' || c == '.' }) && !seen[s] {
				seen[s] = true
				names = append(names, s)
			}
		}
		sort.Strings(names)
		f := []pyjson.Value{}
		for _, s := range names {
			f = append(f, s)
		}
		r.Set("found", f)
		out = append(out, r)
	}
	return out
}

func hourKey(k string) int64 {
	n, _ := strconv.ParseInt(k, 10, 64)
	return n
}

// keepNewest keeps the newest MaxHoursPerDevice hours, sorted by hour, a stable sort as Python's sorted(key=int).
// keepNewest giữ MaxHoursPerDevice giờ mới nhất, xếp theo giờ, sắp ổn định như sorted(key=int) của Python.
func keepNewest(book *obj) *obj {
	idx := make([]int, book.Len())
	for i := range idx {
		idx[i] = i
	}
	sort.SliceStable(idx, func(a, b int) bool { return hourKey(book.Keys[idx[a]]) < hourKey(book.Keys[idx[b]]) })
	if len(idx) > MaxHoursPerDevice {
		idx = idx[len(idx)-MaxHoursPerDevice:]
	}
	out := pyjson.NewObject()
	for _, i := range idx {
		out.Set(book.Keys[i], book.Vals[i])
	}
	return out
}

// MergeHours copies merge_hours: the hours of a v: 2 send put on the book kept for that computer; each hour sent replaces it, an empty
// hour removes it, an hour not sent stays. Neither argument is changed.
// MergeHours chép merge_hours: các giờ của một gói v: 2 đặt lên sổ đang giữ của máy đó; mỗi giờ gửi lên thay giờ cũ, giờ rỗng xoá giờ đó,
// giờ không gửi thì giữ. Không sửa đối số nào.
func MergeHours(kept, sent *obj) *obj {
	out := pyjson.NewObject()
	for _, kind := range HourKinds {
		book := pyjson.NewObject()
		if k, ok := get(kept, kind).(*obj); ok {
			book = k.Copy()
		}
		if s, ok := get(sent, kind).(*obj); ok {
			for i, hour := range s.Keys {
				if t, ok := s.Vals[i].(*obj); ok && t.Len() > 0 {
					book.Set(hour, t)
				} else {
					book.Delete(hour)
				}
			}
		}
		book = keepNewest(book)
		if book.Len() > 0 || kind != "blocks" {
			out.Set(kind, book)
		}
	}
	return out
}

// ReplaceHours copies replace_hours: the book a v: 1 send or a v: 2 send with full: true stands for, the empty hours left out.
// ReplaceHours chép replace_hours: sổ mà gói v: 1 hoặc gói v: 2 có full: true mang theo, bỏ các giờ rỗng.
func ReplaceHours(sent *obj) *obj {
	out := pyjson.NewObject()
	for _, kind := range HourKinds {
		book := pyjson.NewObject()
		if s, ok := get(sent, kind).(*obj); ok {
			for i, hour := range s.Keys {
				if t, ok := s.Vals[i].(*obj); ok && t.Len() > 0 {
					book.Set(hour, t)
				}
			}
		}
		if book.Len() > 0 || kind != "blocks" {
			out.Set(kind, book)
		}
	}
	return out
}

// Micro is ledger_micro: the money of one ledger hour in usdMicro, for a cleaned hour or an older one that has only usd.
// Micro là ledger_micro: tiền của một giờ trong sổ theo usdMicro, cho giờ đã làm sạch hoặc giờ cũ chỉ có usd.
func Micro(hour pyjson.Value) num {
	if m, ok := get(hour, "usdMicro").(num); ok && m.Int {
		return m
	}
	if u, ok := get(hour, "usd").(num); ok {
		if u.Int {
			return pyjson.BigN(new(big.Int).Mul(u.AsBig(), million))
		}
		return roundToInt(u.F * 1_000_000)
	}
	return pyjson.IntN(0)
}
