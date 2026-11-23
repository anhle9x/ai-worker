package pyjson

import (
	"errors"
	"fmt"
	"math"
	"testing"
)

func TestReadsAsPythonDoes(t *testing.T) {
	v, err := Parse([]byte(` {"b": 1, "a": 2.0, "b": [true, null, -0, 1e2, 12345678901234567890123]} `))
	if err != nil {
		t.Fatal(err)
	}
	o := v.(*Object)
	if o.Keys[0] != "b" || o.Keys[1] != "a" || len(o.Keys) != 2 {
		t.Fatalf("keys %v", o.Keys)
	}
	if a, _ := o.Get("a"); a.(Number).Int || a.(Number).F != 2 {
		t.Fatalf("a %v", a)
	}
	list, _ := o.Get("b")
	l := list.([]Value)
	if l[0] != true || l[1] != nil || !l[2].(Number).Int || l[3].(Number).Int || l[4].(Number).Big == nil {
		t.Fatalf("list %#v", l)
	}
	if got := string(Encode(v)); got != `{"b": [true, null, 0, 100.0, 12345678901234567890123], "a": 2.0}` {
		t.Fatalf("encoded %s", got)
	}
}

func TestLeavesToPythonWhatItIsNotSureOf(t *testing.T) {
	for _, s := range []string{"", "NaN", "[Infinity]", `"\ud800"`, "\xef\xbb\xbf{}", "{\"a\":1,}", "01", "[1] x", "\"a\x01\"", "\xff", "{\"a\" 1}", "\x00{"} {
		if _, err := Parse([]byte(s)); !errors.Is(err, ErrUnsure) {
			t.Errorf("%q: %v", s, err)
		}
	}
	if v, err := Parse([]byte(`"😀"`)); err != nil || v != "😀" {
		t.Errorf("pair: %v %v", v, err)
	}
	if v, err := Parse([]byte(`[1e400, 1e-400]`)); err != nil || !math.IsInf(v.([]Value)[0].(Number).F, 1) || v.([]Value)[1].(Number).F != 0 {
		t.Errorf("range: %v %v", v, err)
	}
}

func TestFloatTextIsPythonRepr(t *testing.T) {
	for f, want := range map[float64]string{1: "1.0", 0.1: "0.1", 1e-06: "1e-06", 1e16: "1e+16", 1e15: "1000000000000000.0", 0.0001: "0.0001",
		0.00001: "1e-05", 123456.789: "123456.789", 1.5e300: "1.5e+300", 2.5e-7: "2.5e-07"} {
		if got := FloatText(f); got != want {
			t.Errorf("%v: %s, Python %s", f, got, want)
		}
	}
	if FloatText(math.Copysign(0, -1)) != "-0.0" {
		t.Error("-0.0")
	}
}

// TestObjectSmallAndLarge: the same keys in the same order whether a table is searched in order (small) or through its map (large),
// across the step from one to the other, with keys set again, deleted and copied.
// TestObjectSmallAndLarge: cùng các khoá theo cùng thứ tự dù bảng được dò theo thứ tự (nhỏ) hay qua map (lớn), qua bước chuyển giữa hai
// dạng, với khoá được đặt lại, bị xoá và được chép.
func TestObjectSmallAndLarge(t *testing.T) {
	o := NewObject()
	var want []string
	vals := map[string]int{}
	check := func(when string) {
		t.Helper()
		if len(o.Keys) != len(want) || o.Len() != len(want) {
			t.Fatalf("%s: keys %v, want %v", when, o.Keys, want)
		}
		for i, k := range want {
			if o.Keys[i] != k {
				t.Fatalf("%s: keys %v, want %v", when, o.Keys, want)
			}
			if v, ok := o.Get(k); !ok || v != vals[k] {
				t.Fatalf("%s: %s = %v %v, want %d", when, k, v, ok, vals[k])
			}
		}
		if _, ok := o.Get("missing"); ok {
			t.Fatalf("%s: a missing key found", when)
		}
		c := o.Copy()
		for _, k := range want {
			if v, ok := c.Get(k); !ok || v != vals[k] {
				t.Fatalf("%s: the copy lost %s", when, k)
			}
		}
	}
	for i := 0; i < 3*smallObject; i++ {
		k := fmt.Sprintf("k%02d", i)
		o.Set(k, i)
		want, vals[k] = append(want, k), i
		check(fmt.Sprintf("after %d", i+1))
		// a key set again keeps its place / khoá đặt lại giữ chỗ cũ
		o.Set("k00", 100+i)
		vals["k00"] = 100 + i
		check(fmt.Sprintf("again after %d", i+1))
	}
	for _, k := range []string{"k05", "k00", fmt.Sprintf("k%02d", 3*smallObject-1)} {
		o.Delete(k)
		for i, w := range want {
			if w == k {
				want = append(want[:i], want[i+1:]...)
				break
			}
		}
		delete(vals, k)
		check("deleted " + k)
	}
	small := NewObject()
	small.Set("a", 1)
	small.Set("b", 2)
	small.Delete("a")
	if v, ok := small.Get("b"); !ok || v != 2 || small.Len() != 1 {
		t.Fatalf("small delete: %v %v", small.Keys, small.Vals)
	}
}

// TestKeysOfManyKinds: keys with escapes, keys that share a slot of the cache of keys, and a raw control character in a key, which
// Python refuses.
// TestKeysOfManyKinds: khoá có ký tự thoát, khoá dùng chung một ô của bộ nhớ khoá, và ký tự điều khiển viết thẳng trong khoá, thứ Python
// từ chối.
func TestKeysOfManyKinds(t *testing.T) {
	v, err := Parse([]byte(`{"a\"b": 1, "\u00e9": 2, "plain": 3}`))
	if err != nil {
		t.Fatal(err)
	}
	o := v.(*Object)
	if o.Keys[0] != `a"b` || o.Keys[1] != "\u00e9" || o.Keys[2] != "plain" {
		t.Fatalf("keys %q", o.Keys)
	}
	if _, err := Parse([]byte("{\"a\x01\": 1}")); err == nil {
		t.Fatal("a control character in a key was taken")
	}
	// more keys than slots, read twice: every key comes back as it was written
	// nhiều khoá hơn số ô, đọc hai lần: mọi khoá trở lại đúng như khi viết
	for round := 0; round < 2; round++ {
		for i := 0; i < 3000; i++ {
			k := fmt.Sprintf("key-%d", i)
			v, err := Parse([]byte(`{"` + k + `": true}`))
			if err != nil || v.(*Object).Keys[0] != k {
				t.Fatalf("%s: %v %v", k, v, err)
			}
		}
	}
}
