package pyjson

import (
	"errors"
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
