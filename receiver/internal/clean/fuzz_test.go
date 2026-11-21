package clean_test

import (
	"bufio"
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"testing"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

// TestRandomSendsWithPythonAsJudge: the judge (tests/contract/ingest-v2/fuzz_judge.py) makes random sends and cleans them with the server's
// own code; the same bytes cleaned here must give the same thing, keys in the same order and whole numbers kept apart from floats.
// FUZZ_SEED and FUZZ_COUNT change the seed and the number of sends. Without python3 the test is skipped, never passed in silence.
// TestRandomSendsWithPythonAsJudge: trọng tài (tests/contract/ingest-v2/fuzz_judge.py) tạo các lần gửi ngẫu nhiên và làm sạch chúng bằng
// chính mã của máy chủ; cùng các byte đó làm sạch ở đây phải ra cùng kết quả, khoá cùng thứ tự và số nguyên tách khỏi số thực.
// FUZZ_SEED và FUZZ_COUNT đổi hạt giống và số lần gửi. Không có python3 thì bài test bị bỏ qua, không bao giờ âm thầm coi là qua.
func TestRandomSendsWithPythonAsJudge(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found: the judge cannot run")
	}
	seed, count := os.Getenv("FUZZ_SEED"), os.Getenv("FUZZ_COUNT")
	if seed == "" {
		seed = "20261121"
	}
	if count == "" {
		count = "3000"
	}
	cmd := exec.Command(python, "-I", filepath.Join(sampleDir, "fuzz_judge.py"), seed, count)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("judge: %v\n%s", err, stderr.String())
	}
	lines, unsure := 0, 0
	sc := bufio.NewScanner(bytes.NewReader(out))
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for sc.Scan() {
		lines++
		v, err := pyjson.Parse(sc.Bytes())
		if err != nil {
			t.Fatalf("line %d: %v", lines, err)
		}
		line := v.(*pyjson.Object)
		now := seconds(field(line, "now"))
		rawText := field(line, "raw").(string)
		raw, err := pyjson.Parse([]byte(rawText))
		if errors.Is(err, pyjson.ErrUnsure) {
			// handed to Python as it came: nothing to compare, but not too often
			// chuyển nguyên văn cho Python: không có gì để so, nhưng không được quá thường xuyên
			unsure++
			continue
		}
		if field(line, "parsed") != true {
			t.Fatalf("line %d: Go read what Python refused: %s", lines, rawText)
		}
		got := clean.Payload(raw, now)
		want := field(line, "clean")
		if (got == nil) != (want == nil) || (got != nil && !pyjson.Equal(got, want)) {
			t.Fatalf("line %d: cleaned differently\n raw  %s\n got  %s\n want %s", lines, rawText, enc(got), pyjson.Encode(want))
		}
		if _, ok := raw.(*pyjson.Object); ok {
			if d := clean.Delegations(field(raw, "delegations"), now*1000); !pyjson.Equal(d, field(line, "delegations")) {
				t.Fatalf("line %d: delegations\n raw  %s\n got  %s\n want %s", lines, rawText, pyjson.Encode(d), pyjson.Encode(field(line, "delegations")))
			}
			if k := clean.SendKind(raw); k != field(line, "kind") {
				t.Fatalf("line %d: kind %s, Python %v", lines, k, field(line, "kind"))
			}
		}
		if s, ok := line.Get("second"); ok {
			second, err := pyjson.Parse([]byte(s.(string)))
			if err != nil {
				continue
			}
			sent := clean.Payload(second, now)
			if m := clean.MergeHours(got, sent); !pyjson.Equal(m, field(line, "merged")) {
				t.Fatalf("line %d: merged\n got  %s\n want %s", lines, pyjson.Encode(m), pyjson.Encode(field(line, "merged")))
			}
			if days := daysObject(totals.AddUp(got, 7*3600)); !sameUnordered(days, field(line, "days")) {
				t.Fatalf("line %d: days\n got  %s\n want %s", lines, pyjson.Encode(days), pyjson.Encode(field(line, "days")))
			}
		}
	}
	if want, _ := strconv.Atoi(count); lines != want {
		t.Fatalf("the judge gave %d lines, expected %s", lines, count)
	}
	if unsure*20 > lines {
		t.Fatalf("%d of %d sends left to Python: too many", unsure, lines)
	}
	t.Logf("%d sends compared, %d left to Python", lines-unsure, unsure)
}

func enc(o *pyjson.Object) string {
	if o == nil {
		return "null"
	}
	return string(pyjson.Encode(o))
}
