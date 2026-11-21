package clean_test

import (
	"math/big"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

// sampleDir is the shared sample the Python server plays too (server/test_contract.py).
// sampleDir là bộ mẫu chung mà máy chủ Python cũng chạy (server/test_contract.py).
var sampleDir = filepath.Join("..", "..", "..", "tests", "contract", "ingest-v2")

func load(t *testing.T, name string) *pyjson.Object {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(sampleDir, name))
	if err != nil {
		t.Fatal(err)
	}
	v, err := pyjson.Parse(b)
	if err != nil {
		t.Fatal(err)
	}
	return v.(*pyjson.Object)
}

func field(v pyjson.Value, k string) pyjson.Value {
	x, _ := v.(*pyjson.Object).Get(k)
	return x
}

func seconds(v pyjson.Value) float64 {
	n := v.(pyjson.Number)
	if n.Int {
		return float64(n.I)
	}
	return n.F
}

// sameUnordered compares like a Python ==: tables whatever the order of their keys, but a whole number and a float kept apart.
// sameUnordered so như == của Python: bảng không kể thứ tự khoá, nhưng số nguyên và số thực vẫn tách riêng.
func sameUnordered(a, b pyjson.Value) bool {
	ao, okA := a.(*pyjson.Object)
	bo, okB := b.(*pyjson.Object)
	if okA || okB {
		if !okA || !okB || ao.Len() != bo.Len() {
			return false
		}
		for i, k := range ao.Keys {
			v, ok := bo.Get(k)
			if !ok || !sameUnordered(ao.Vals[i], v) {
				return false
			}
		}
		return true
	}
	al, okA := a.([]pyjson.Value)
	bl, okB := b.([]pyjson.Value)
	if okA || okB {
		if !okA || !okB || len(al) != len(bl) {
			return false
		}
		for i := range al {
			if !sameUnordered(al[i], bl[i]) {
				return false
			}
		}
		return true
	}
	return pyjson.Equal(a, b)
}

func daysObject(days map[string]*totals.Day) *pyjson.Object {
	keys := make([]string, 0, len(days))
	for k := range days {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := pyjson.NewObject()
	n := func(b *big.Int) pyjson.Number { return pyjson.BigN(b) }
	for _, k := range keys {
		d := days[k]
		o := pyjson.NewObject()
		o.Set("usdMicro", n(d.USDMicro))
		o.Set("tokensIn", n(d.TokensIn))
		o.Set("tokensOut", n(d.TokensOut))
		for i, w := range clean.Workers {
			o.Set(w, n(d.Tasks[i]))
		}
		out.Set(k, o)
	}
	return out
}

// TestSharedSample plays cases.json as server/test_contract.py does: each send cleaned and saved in turn, every v: 2 outcome as expected,
// and each computer ends with the book and the totals per day the sample expects, in both formats.
// TestSharedSample chạy cases.json như server/test_contract.py: từng lần gửi được làm sạch và lưu lần lượt, mọi kết quả v: 2 đúng như chờ,
// và mỗi máy kết thúc với đúng sổ và tổng theo ngày bộ mẫu chờ, ở cả hai định dạng.
func TestSharedSample(t *testing.T) {
	sample := load(t, "cases.json")
	tz := int64(seconds(field(sample, "tzHours")) * 3600)
	cases := field(sample, "cases").([]pyjson.Value)
	if len(cases) == 0 {
		t.Fatal("no cases")
	}
	for _, c := range cases {
		name := field(c, "name").(string)
		for _, form := range []string{"v2", "v1"} {
			if form == "v1" && field(c, "v2Only") == true {
				continue
			}
			kept := map[string]*pyjson.Object{}
			fullAt := map[string]float64{}
			for i, step := range field(c, "steps").([]pyjson.Value) {
				device := field(step, "device").(string)
				if field(step, "dropRowFirst") == true {
					delete(kept, device)
					delete(fullAt, device)
				}
				sent := field(step, form)
				if sent == nil || field(step, "delivered") != true {
					continue
				}
				at := seconds(field(step, "at"))
				d := clean.Payload(sent, at)
				if d == nil {
					t.Fatalf("%s step %d (%s): not cleaned", name, i, form)
				}
				last, ever := fullAt[device]
				outcome, applied, rec := clean.Decide(kept[device], d, at, clean.SendKind(sent), last, ever)
				want := clean.Saved
				if form == "v2" {
					want = field(step, "expectV2").(string)
				}
				if outcome != want {
					t.Fatalf("%s step %d (%s): %s, expected %s", name, i, form, outcome, want)
				}
				if outcome == clean.Saved {
					kept[device] = rec
					if applied == "full" {
						fullAt[device] = at
					}
				}
			}
			expect := field(c, "expect").(*pyjson.Object)
			for i, device := range expect.Keys {
				rec := kept[device]
				if rec == nil {
					t.Fatalf("%s %s %s: no book", name, form, device)
				}
				book := rec.Copy()
				book.Delete("device")
				book.Delete("updatedAt")
				if !sameUnordered(book, field(expect.Vals[i], "book")) {
					t.Errorf("%s %s %s: book\n got  %s\n want %s", name, form, device, pyjson.Encode(book), pyjson.Encode(field(expect.Vals[i], "book")))
				}
				if got := daysObject(totals.AddUp(rec, tz)); !sameUnordered(got, field(expect.Vals[i], "days")) {
					t.Errorf("%s %s %s: days\n got  %s\n want %s", name, form, device, pyjson.Encode(got), pyjson.Encode(field(expect.Vals[i], "days")))
				}
			}
		}
	}
}
