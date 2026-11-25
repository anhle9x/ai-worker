package ingest

import (
	"bytes"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"aiworker/receiver/internal/pyjson"
)

// TestARowOlderThanADirectSendIsLeftOut: a computer sends a book through the receiver, its row waits for the next batch, then it sends a
// newer book straight to Python (its address of the receiver had gone, or the receiver could not be reached); the batch that comes after
// must not put Python's book back.
// TestARowOlderThanADirectSendIsLeftOut: một máy gửi sổ qua bộ nhận, dòng của nó chờ lô kế tiếp, rồi nó gửi một sổ mới hơn thẳng tới
// Python (địa chỉ bộ nhận đã hết hạn, hoặc không tới được bộ nhận); lô tới sau không được kéo sổ của Python lùi lại.
func TestARowOlderThanADirectSendIsLeftOut(t *testing.T) {
	h := start(t)
	device := "device-gostale"
	key := enrolled(t, h, device)
	h.flush()
	hour := hourNow()
	at := time.Now().UnixMilli()
	first := packet(device, map[string]any{"full": true, "updatedAt": at, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 5}}}})
	if status, ans := h.send(key, first); status != 200 {
		t.Fatalf("through the receiver: %d %v", status, ans)
	}
	second := packet(device, map[string]any{"full": true, "updatedAt": at + 1000, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 9}}}})
	b, _ := json.Marshal(second)
	req, _ := http.NewRequest(http.MethodPost, h.python+"/ingest", bytes.NewReader(b))
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("straight to Python: %d", resp.StatusCode)
	}
	h.flush()
	got := string(pyjson.Encode(h.pythonBook(device, true)))
	if !strings.Contains(got, `"usdMicro": 9`) && !strings.Contains(got, `"usdMicro":9`) {
		t.Fatalf("the older row put the book back: %s", got)
	}
}
