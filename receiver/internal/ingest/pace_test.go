package ingest

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestTheAnswerAsksForTheGapOfTheLoad: the answer's minGapMs and stateGapMs are the policy's while Pace says 0, and Pace's when it says
// more; never less than the policy's.
// TestTheAnswerAsksForTheGapOfTheLoad: minGapMs và stateGapMs của câu trả lời là của chính sách khi Pace trả 0, và là của Pace khi nó trả
// nhiều hơn; không bao giờ ít hơn của chính sách.
func TestTheAnswerAsksForTheGapOfTheLoad(t *testing.T) {
	r, keys := receiverWith(t, &fakePython{})
	device := "device-pace001"
	r.entry(device).loaded = true
	start := r.Now()
	ask := func(pace int64) (int64, int64) {
		t.Helper()
		r.Pace = func() int64 { return pace }
		body := fmt.Sprintf(`{"v": 2, "device": %q, "updatedAt": %d, "working": 1, "hours": {}}`, device, r.Now())
		req := httptest.NewRequest(http.MethodPost, "/ingest", strings.NewReader(body))
		req.Header.Set("Authorization", "Bearer "+keys.key(device, start/1000))
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		if w.Code != 200 {
			t.Fatalf("pace %d: %d %s", pace, w.Code, w.Body.String())
		}
		var a struct{ MinGapMs, StateGapMs int64 }
		if err := json.Unmarshal(w.Body.Bytes(), &a); err != nil {
			t.Fatal(err)
		}
		return a.MinGapMs, a.StateGapMs
	}
	if g, s := ask(0); g != 2000 {
		t.Fatalf("no pace: %d %d", g, s)
	}
	if g, s := ask(1000); g != 2000 || s < 1000 {
		t.Fatalf("a pace under the policy's: %d %d", g, s)
	}
	if g, s := ask(6000); g != 6000 || s != 6000 {
		t.Fatalf("pace 6 s: %d %d", g, s)
	}
}
