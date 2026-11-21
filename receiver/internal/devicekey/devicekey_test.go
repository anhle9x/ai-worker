package devicekey

import (
	"encoding/json"
	"os/exec"
	"path/filepath"
	"testing"
)

// TestSameAnswerAsPython: the server's own code issues keys and writes the file of secrets (tests/contract/ingest-v2/keys_judge.py);
// every key, good or bad, gets the same answer here.
// TestSameAnswerAsPython: chính mã của máy chủ cấp khoá và ghi file bí mật (tests/contract/ingest-v2/keys_judge.py);
// mọi khoá, tốt hay xấu, đều nhận cùng câu trả lời ở đây.
func TestSameAnswerAsPython(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found: the judge cannot run")
	}
	dir := t.TempDir()
	out, err := exec.Command(python, "-I", filepath.Join("..", "..", "..", "tests", "contract", "ingest-v2", "keys_judge.py"), dir).Output()
	if err != nil {
		t.Fatalf("judge: %v", err)
	}
	var judged struct {
		Now     float64 `json:"now"`
		Secrets string  `json:"secrets"`
		Cases   []struct {
			Token  string `json:"token"`
			Reason string `json:"reason"`
			Renew  *bool  `json:"renew"`
			Claims *struct {
				Kid, Pid, Rk, Device string
				Iat                  int64
			} `json:"claims"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(out, &judged); err != nil {
		t.Fatal(err)
	}
	s, err := Load(judged.Secrets)
	if err != nil {
		t.Fatal(err)
	}
	if len(s.Internal()) < 32 {
		t.Fatal("no internal code")
	}
	for i, c := range judged.Cases {
		claims, reason := s.Check(c.Token, judged.Now, nil)
		if reason != c.Reason {
			t.Errorf("case %d: %q, Python %q", i, reason, c.Reason)
			continue
		}
		if c.Claims == nil {
			continue
		}
		if claims.Kid != c.Claims.Kid || claims.Pid != c.Claims.Pid || claims.Rk != c.Claims.Rk || claims.Device != c.Claims.Device || claims.Iat != c.Claims.Iat {
			t.Errorf("case %d: claims %+v, Python %+v", i, claims, c.Claims)
		}
		if NeedsRenewal(claims, judged.Now, 0) != *c.Renew {
			t.Errorf("case %d: renewal differs", i)
		}
	}
	if claims, _ := s.Check(judged.Cases[0].Token, judged.Now, func(string) bool { return true }); claims != nil {
		t.Error("a revoked computer passed")
	}
}
