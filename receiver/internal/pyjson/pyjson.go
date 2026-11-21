// Package pyjson reads and writes JSON the way Python's json module does, so the cleaning in Go gives what the cleaning in Python gives.
// Package pyjson đọc và ghi JSON theo đúng cách module json của Python làm, để bước làm sạch bằng Go cho ra đúng thứ bước làm sạch bằng Python cho ra.
//
// What matters here, and why encoding/json is not used:
// Những điểm quan trọng ở đây, và vì sao không dùng encoding/json:
//   - a table keeps its keys in the order they came; a key that comes twice keeps its first place and its last value (a Python dict);
//   - một bảng giữ các khoá theo thứ tự chúng tới; khoá tới hai lần giữ chỗ đầu và giá trị cuối (như dict của Python);
//   - a number written without a dot or an exponent is a whole number (Python int), any other is a float, and the two stay apart;
//   - số viết không có dấu chấm hay số mũ là số nguyên (int của Python), số khác là số thực, và hai loại được giữ riêng;
//   - anything this reader is not sure Python reads the same way is refused with ErrUnsure, and the receiver passes that send to Python.
//   - thứ gì bộ đọc này không chắc Python đọc giống hệt thì bị từ chối với ErrUnsure, và bộ nhận chuyển lần gửi đó cho Python.
package pyjson

import (
	"errors"
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode/utf8"
)

// ErrUnsure means Python might read these bytes another way, or refuse them: let Python answer.
// ErrUnsure nghĩa là Python có thể đọc các byte này theo cách khác, hoặc từ chối chúng: để Python trả lời.
var ErrUnsure = errors.New("pyjson: let Python read this")

// maxDepth stays far below Python's recursion limit, so a nesting Python refuses never reaches here.
// maxDepth thấp hơn nhiều so với giới hạn đệ quy của Python, để độ lồng mà Python từ chối không bao giờ tới được đây.
const maxDepth = 200

// maxIntDigits stays below the 4300 digits Python 3.11 and later refuse to turn into an int.
// maxIntDigits thấp hơn 4300 chữ số mà Python 3.11 trở lên từ chối đổi thành int.
const maxIntDigits = 4000

// Number is a JSON number as Python holds it: a whole number (Int, in I or in Big when it does not fit) or a float (F).
// Number là một số JSON như Python giữ: số nguyên (Int, nằm trong I hoặc trong Big khi không vừa) hoặc số thực (F).
type Number struct {
	Int bool
	I   int64
	Big *big.Int
	F   float64
}

// Value is nil, bool, Number, string, []Value or *Object.
// Value là nil, bool, Number, string, []Value hoặc *Object.
type Value = any

// Object is a JSON table with its keys in order.
// Object là một bảng JSON có các khoá theo thứ tự.
type Object struct {
	Keys []string
	Vals []Value
	idx  map[string]int
}

// NewObject makes an empty table.
// NewObject tạo một bảng rỗng.
func NewObject() *Object { return &Object{idx: map[string]int{}} }

// Get gives the value of a key and whether it is there.
// Get trả giá trị của một khoá và cho biết khoá có ở đó không.
func (o *Object) Get(k string) (Value, bool) {
	if o == nil {
		return nil, false
	}
	i, ok := o.idx[k]
	if !ok {
		return nil, false
	}
	return o.Vals[i], true
}

// Set puts a value: a key already there keeps its place, as in a Python dict.
// Set đặt một giá trị: khoá đã có thì giữ chỗ cũ, như trong dict của Python.
func (o *Object) Set(k string, v Value) {
	if i, ok := o.idx[k]; ok {
		o.Vals[i] = v
		return
	}
	o.idx[k] = len(o.Keys)
	o.Keys = append(o.Keys, k)
	o.Vals = append(o.Vals, v)
}

// Delete takes a key out, keeping the order of the others.
// Delete bỏ một khoá ra, giữ thứ tự các khoá còn lại.
func (o *Object) Delete(k string) {
	i, ok := o.idx[k]
	if !ok {
		return
	}
	o.Keys = append(o.Keys[:i], o.Keys[i+1:]...)
	o.Vals = append(o.Vals[:i], o.Vals[i+1:]...)
	delete(o.idx, k)
	for j := i; j < len(o.Keys); j++ {
		o.idx[o.Keys[j]] = j
	}
}

// Len is the number of keys.
// Len là số khoá.
func (o *Object) Len() int {
	if o == nil {
		return 0
	}
	return len(o.Keys)
}

// Copy is a shallow copy: the values are shared.
// Copy là bản sao nông: các giá trị dùng chung.
func (o *Object) Copy() *Object {
	out := &Object{Keys: append([]string(nil), o.Keys...), Vals: append([]Value(nil), o.Vals...), idx: make(map[string]int, len(o.Keys))}
	for i, k := range out.Keys {
		out.idx[k] = i
	}
	return out
}

// IntN makes a whole number.
// IntN tạo một số nguyên.
func IntN(i int64) Number { return Number{Int: true, I: i} }

// FloatN makes a float.
// FloatN tạo một số thực.
func FloatN(f float64) Number { return Number{F: f} }

// BigN makes a whole number of any size, kept in I when it fits.
// BigN tạo một số nguyên cỡ bất kỳ, giữ trong I khi vừa.
func BigN(b *big.Int) Number {
	if b.IsInt64() {
		return IntN(b.Int64())
	}
	return Number{Int: true, Big: new(big.Int).Set(b)}
}

// AsBig is a whole number as a big.Int.
// AsBig là một số nguyên dưới dạng big.Int.
func (n Number) AsBig() *big.Int {
	if n.Big != nil {
		return new(big.Int).Set(n.Big)
	}
	return big.NewInt(n.I)
}

// Parse reads one JSON document from bytes as Python's json.loads(bytes) reads it.
// Parse đọc một tài liệu JSON từ các byte như json.loads(bytes) của Python đọc.
func Parse(b []byte) (Value, error) {
	// Python guesses UTF-16 and UTF-32 from zero bytes and byte order marks, and reads UTF-8 with surrogatepass: not here
	// Python đoán UTF-16 và UTF-32 từ byte 0 và dấu thứ tự byte, và đọc UTF-8 với surrogatepass: không làm ở đây
	if len(b) == 0 || !utf8.Valid(b) || (len(b) >= 2 && (b[0] == 0 || b[1] == 0)) || strings.HasPrefix(string(b), "\xef\xbb\xbf") {
		return nil, ErrUnsure
	}
	p := &parser{s: string(b)}
	p.space()
	v, err := p.value(0)
	if err != nil {
		return nil, err
	}
	p.space()
	if p.i != len(p.s) {
		return nil, ErrUnsure
	}
	return v, nil
}

type parser struct {
	s string
	i int
}

func (p *parser) space() {
	for p.i < len(p.s) {
		switch p.s[p.i] {
		case ' ', '\t', '\n', '\r':
			p.i++
		default:
			return
		}
	}
}

func (p *parser) value(depth int) (Value, error) {
	if depth > maxDepth || p.i >= len(p.s) {
		return nil, ErrUnsure
	}
	switch c := p.s[p.i]; {
	case c == '{':
		return p.object(depth)
	case c == '[':
		return p.array(depth)
	case c == '"':
		return p.str()
	case c == 't' && strings.HasPrefix(p.s[p.i:], "true"):
		p.i += 4
		return true, nil
	case c == 'f' && strings.HasPrefix(p.s[p.i:], "false"):
		p.i += 5
		return false, nil
	case c == 'n' && strings.HasPrefix(p.s[p.i:], "null"):
		p.i += 4
		return nil, nil
	case c == '-' || (c >= '0' && c <= '9'):
		return p.number()
	}
	// NaN, Infinity and anything else: Python's answer decides (the server refuses them)
	// NaN, Infinity và mọi thứ khác: câu trả lời của Python quyết định (máy chủ từ chối chúng)
	return nil, ErrUnsure
}

func (p *parser) object(depth int) (Value, error) {
	p.i++
	o := NewObject()
	p.space()
	if p.i < len(p.s) && p.s[p.i] == '}' {
		p.i++
		return o, nil
	}
	for {
		p.space()
		if p.i >= len(p.s) || p.s[p.i] != '"' {
			return nil, ErrUnsure
		}
		k, err := p.str()
		if err != nil {
			return nil, err
		}
		p.space()
		if p.i >= len(p.s) || p.s[p.i] != ':' {
			return nil, ErrUnsure
		}
		p.i++
		p.space()
		v, err := p.value(depth + 1)
		if err != nil {
			return nil, err
		}
		o.Set(k.(string), v)
		p.space()
		if p.i >= len(p.s) {
			return nil, ErrUnsure
		}
		if p.s[p.i] == ',' {
			p.i++
			continue
		}
		if p.s[p.i] == '}' {
			p.i++
			return o, nil
		}
		return nil, ErrUnsure
	}
}

func (p *parser) array(depth int) (Value, error) {
	p.i++
	out := []Value{}
	p.space()
	if p.i < len(p.s) && p.s[p.i] == ']' {
		p.i++
		return out, nil
	}
	for {
		p.space()
		v, err := p.value(depth + 1)
		if err != nil {
			return nil, err
		}
		out = append(out, v)
		p.space()
		if p.i >= len(p.s) {
			return nil, ErrUnsure
		}
		if p.s[p.i] == ',' {
			p.i++
			continue
		}
		if p.s[p.i] == ']' {
			p.i++
			return out, nil
		}
		return nil, ErrUnsure
	}
}

func hex4(s string) (rune, bool) {
	if len(s) < 4 {
		return 0, false
	}
	n, err := strconv.ParseUint(s[:4], 16, 32)
	return rune(n), err == nil && !strings.ContainsAny(s[:4], "+-")
}

func (p *parser) str() (Value, error) {
	p.i++
	var b strings.Builder
	for {
		if p.i >= len(p.s) {
			return nil, ErrUnsure
		}
		c := p.s[p.i]
		switch {
		case c == '"':
			p.i++
			return b.String(), nil
		case c < 0x20:
			// Python's json refuses a raw control character inside a string
			// json của Python từ chối ký tự điều khiển viết thẳng trong chuỗi
			return nil, ErrUnsure
		case c != '\\':
			start := p.i
			for p.i < len(p.s) && p.s[p.i] != '"' && p.s[p.i] != '\\' && p.s[p.i] >= 0x20 {
				p.i++
			}
			b.WriteString(p.s[start:p.i])
			continue
		}
		if p.i+1 >= len(p.s) {
			return nil, ErrUnsure
		}
		e := p.s[p.i+1]
		p.i += 2
		switch e {
		case '"', '\\', '/':
			b.WriteByte(e)
		case 'b':
			b.WriteByte('\b')
		case 'f':
			b.WriteByte('\f')
		case 'n':
			b.WriteByte('\n')
		case 'r':
			b.WriteByte('\r')
		case 't':
			b.WriteByte('\t')
		case 'u':
			r, ok := hex4(p.s[p.i:])
			if !ok {
				return nil, ErrUnsure
			}
			p.i += 4
			if r >= 0xd800 && r <= 0xdbff && strings.HasPrefix(p.s[p.i:], "\\u") {
				if lo, ok := hex4(p.s[p.i+2:]); ok && lo >= 0xdc00 && lo <= 0xdfff {
					p.i += 6
					b.WriteRune(0x10000 + (r-0xd800)<<10 + (lo - 0xdc00))
					continue
				}
			}
			if r >= 0xd800 && r <= 0xdfff {
				// a lone half of a pair: Python keeps it as it is, Go strings cannot
				// một nửa cặp đứng riêng: Python giữ nguyên, chuỗi Go thì không giữ được
				return nil, ErrUnsure
			}
			b.WriteRune(r)
		default:
			return nil, ErrUnsure
		}
	}
}

func digits(s string, i int) int {
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
	}
	return i
}

func (p *parser) number() (Value, error) {
	start := p.i
	i := p.i
	if s := p.s; i < len(s) && s[i] == '-' {
		i++
	}
	if i >= len(p.s) {
		return nil, ErrUnsure
	}
	if p.s[i] == '0' {
		i++
	} else if p.s[i] >= '1' && p.s[i] <= '9' {
		i = digits(p.s, i)
	} else {
		return nil, ErrUnsure
	}
	whole := true
	if i < len(p.s) && p.s[i] == '.' && i+1 < len(p.s) && p.s[i+1] >= '0' && p.s[i+1] <= '9' {
		i = digits(p.s, i+1)
		whole = false
	}
	if i < len(p.s) && (p.s[i] == 'e' || p.s[i] == 'E') {
		j := i + 1
		if j < len(p.s) && (p.s[j] == '+' || p.s[j] == '-') {
			j++
		}
		if j < len(p.s) && p.s[j] >= '0' && p.s[j] <= '9' {
			i = digits(p.s, j)
			whole = false
		}
	}
	text := p.s[start:i]
	p.i = i
	if whole {
		if len(text) > maxIntDigits {
			return nil, ErrUnsure
		}
		if n, err := strconv.ParseInt(text, 10, 64); err == nil {
			return IntN(n), nil
		}
		b, ok := new(big.Int).SetString(text, 10)
		if !ok {
			return nil, ErrUnsure
		}
		return BigN(b), nil
	}
	// out of range is what Python's float() gives too: inf for too large, 0.0 for too small
	// vượt khoảng cũng là thứ float() của Python cho ra: inf khi quá lớn, 0.0 khi quá nhỏ
	f, err := strconv.ParseFloat(text, 64)
	if err != nil && !errors.Is(err, strconv.ErrRange) {
		return nil, ErrUnsure
	}
	return FloatN(f), nil
}

// FloatText writes a float the way Python's repr does: shortest digits, ".0" on a whole number, an exponent below 1e-4 and from 1e16.
// FloatText viết một số thực như repr của Python: ít chữ số nhất, ".0" với số chẵn, dùng số mũ khi dưới 1e-4 và từ 1e16 trở lên.
func FloatText(f float64) string {
	switch {
	case math.IsInf(f, 1):
		return "Infinity"
	case math.IsInf(f, -1):
		return "-Infinity"
	case math.IsNaN(f):
		return "NaN"
	}
	e := strconv.FormatFloat(f, 'e', -1, 64)
	mant, exp, _ := strings.Cut(e, "e")
	x, _ := strconv.Atoi(exp)
	if f != 0 && (x < -4 || x >= 16) {
		sign := "+"
		if x < 0 {
			sign, x = "-", -x
		}
		return mant + "e" + sign + pad2(x)
	}
	s := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.Contains(s, ".") {
		s += ".0"
	}
	return s
}

func pad2(x int) string {
	if x < 10 {
		return "0" + strconv.Itoa(x)
	}
	return strconv.Itoa(x)
}

// Text writes a number as Python's json.dumps does.
// Text viết một số như json.dumps của Python.
func (n Number) Text() string {
	if n.Int {
		if n.Big != nil {
			return n.Big.String()
		}
		return strconv.FormatInt(n.I, 10)
	}
	return FloatText(n.F)
}

// Encode writes a value as JSON, keys in their order, numbers as Python writes them.
// Encode viết một giá trị thành JSON, khoá theo thứ tự của chúng, số như Python viết.
func Encode(v Value) []byte {
	var b strings.Builder
	write(&b, v)
	return []byte(b.String())
}

func write(b *strings.Builder, v Value) {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case Number:
		b.WriteString(x.Text())
	case string:
		writeString(b, x)
	case []Value:
		b.WriteByte('[')
		for i, e := range x {
			if i > 0 {
				b.WriteString(", ")
			}
			write(b, e)
		}
		b.WriteByte(']')
	case *Object:
		b.WriteByte('{')
		for i, k := range x.Keys {
			if i > 0 {
				b.WriteString(", ")
			}
			writeString(b, k)
			b.WriteString(": ")
			write(b, x.Vals[i])
		}
		b.WriteByte('}')
	case Raw:
		b.Write(x)
	default:
		b.WriteString("null")
	}
}

// Raw is JSON already written, put in as it is.
// Raw là JSON đã viết sẵn, đặt vào nguyên văn.
type Raw []byte

const hexDigits = "0123456789abcdef"

func writeString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch {
		case r == '"':
			b.WriteString(`\"`)
		case r == '\\':
			b.WriteString(`\\`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\b':
			b.WriteString(`\b`)
		case r == '\f':
			b.WriteString(`\f`)
		case r < 0x20:
			b.WriteString(`\u`)
			b.WriteByte(hexDigits[r>>12&15])
			b.WriteByte(hexDigits[r>>8&15])
			b.WriteByte(hexDigits[r>>4&15])
			b.WriteByte(hexDigits[r&15])
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('"')
}

// Equal says whether two values are the same, with a whole number and a float kept apart and the order of keys counted.
// Equal cho biết hai giá trị có như nhau không, số nguyên và số thực được tách riêng và thứ tự khoá được tính.
func Equal(a, b Value) bool {
	switch x := a.(type) {
	case nil:
		return b == nil
	case bool:
		y, ok := b.(bool)
		return ok && x == y
	case string:
		y, ok := b.(string)
		return ok && x == y
	case Number:
		y, ok := b.(Number)
		if !ok || x.Int != y.Int {
			return false
		}
		if x.Int {
			return x.AsBig().Cmp(y.AsBig()) == 0
		}
		return x.F == y.F && math.Signbit(x.F) == math.Signbit(y.F) || (math.IsNaN(x.F) && math.IsNaN(y.F))
	case []Value:
		y, ok := b.([]Value)
		if !ok || len(x) != len(y) {
			return false
		}
		for i := range x {
			if !Equal(x[i], y[i]) {
				return false
			}
		}
		return true
	case *Object:
		y, ok := b.(*Object)
		if !ok || x.Len() != y.Len() {
			return false
		}
		for i, k := range x.Keys {
			if y.Keys[i] != k || !Equal(x.Vals[i], y.Vals[i]) {
				return false
			}
		}
		return true
	}
	return false
}
