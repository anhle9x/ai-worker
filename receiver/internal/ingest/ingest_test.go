package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"aiworker/receiver/internal/devicekey"
	"aiworker/receiver/internal/pyjson"
)

// python starts the real Python server on a free port, in empty folders, with RECEIVER=1; it stops when the test ends.
// python khởi động máy chủ Python thật trên một cổng trống, trong các thư mục rỗng, với RECEIVER=1; nó dừng khi bài test kết thúc.
func python(t *testing.T) (string, string) {
	t.Helper()
	url, secrets, _ := pythonServer(t, false)
	return url, secrets
}

// pythonServer is python; with judged the server runs inside tests/contract/ingest-v2/view_judge.py, which answers on its input and
// output what role_view says at a given second (the judge, live_test.go).
// pythonServer là python; với judged máy chủ chạy bên trong tests/contract/ingest-v2/view_judge.py, nơi trả lời qua đầu vào và đầu ra
// thứ role_view nói ở một giây cho trước (trọng tài, live_test.go).
func pythonServer(t *testing.T, judged bool) (string, string, *judge) {
	t.Helper()
	py, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found: the Python server cannot run")
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	dir := t.TempDir()
	secrets := filepath.Join(dir, "keys", "receiver-secrets.json")
	server, _ := filepath.Abs(filepath.Join("..", "..", "..", "server"))
	cmd := exec.Command(py, "webhook.py")
	if judged {
		cmd = exec.Command(py, "-I", filepath.Join(server, "..", "tests", "contract", "ingest-v2", "view_judge.py"))
	}
	cmd.Dir = server
	cmd.Env = append(os.Environ(), "PORT="+strconv.Itoa(port), "BIND_ADDR=127.0.0.1", "INGEST_KEY=shared-test-key-0123456789", "RECEIVER=1",
		"DATA_DIR="+filepath.Join(dir, "data"), "KEYS_DIR="+filepath.Join(dir, "keys"), "BRANCHES_FILE="+filepath.Join(dir, "none.json"), "TZ_OFFSET=7",
		// every send of the tests also goes as it came, so Python's third check compares each one
		// mọi lần gửi trong bài test cũng được chuyển nguyên văn, để lớp đối chiếu thứ ba của Python so từng lần
		"RECEIVER_CHECK_PERCENT=100",
		// the table of people is built again at each ask, so a test sees a change at once
		// bảng người được dựng lại mỗi lần hỏi, để bài test thấy thay đổi ngay
		"RECEIVER_PEOPLE_SECONDS=0")
	var log bytes.Buffer
	cmd.Stdout, cmd.Stderr = &log, &log
	var j *judge
	if judged {
		cmd.Stdout = nil
		j = attachJudge(t, cmd)
	}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		if t.Failed() {
			t.Logf("python server:\n%s", log.String())
		}
	})
	url := "http://127.0.0.1:" + strconv.Itoa(port)
	for i := 0; i < 100; i++ {
		if r, err := http.Get(url + "/health"); err == nil {
			r.Body.Close()
			if _, err := os.Stat(secrets); err == nil {
				return url, secrets, j
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatalf("the Python server did not start:\n%s", log.String())
	return "", "", nil
}

type harness struct {
	t       *testing.T
	r       *Receiver
	front   *httptest.Server
	python  string
	secrets string
	// seq: the batches written as sends straight to Python (straight, contract_test.go)
	// seq: các lô ghi như lần gửi thẳng tới Python (straight, contract_test.go)
	seq int64
}

func start(t *testing.T) *harness {
	h, _ := startWith(t, false)
	return h
}

// startWith is start; with judged the Python server is the one inside the judge, given too.
// startWith là start; với judged máy chủ Python là máy chủ bên trong trọng tài, trọng tài cũng được trả về.
func startWith(t *testing.T, judged bool) (*harness, *judge) {
	url, secretsFile, j := pythonServer(t, judged)
	secrets, err := devicekey.Load(secretsFile)
	if err != nil {
		t.Fatal(err)
	}
	r := New(url, secrets, 0)
	if err := r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	front := httptest.NewServer(r)
	t.Cleanup(front.Close)
	return &harness{t: t, r: r, front: front, python: url, secrets: secretsFile}, j
}

func (h *harness) send(auth string, packet any) (int, map[string]any) {
	h.t.Helper()
	b, _ := json.Marshal(packet)
	req, _ := http.NewRequest(http.MethodPost, h.front.URL+"/ingest", bytes.NewReader(b))
	req.Header.Set("Authorization", "Bearer "+auth)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		h.t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	raw, _ := io.ReadAll(resp.Body)
	_ = json.Unmarshal(raw, &out)
	return resp.StatusCode, out
}

func (h *harness) pythonBook(device string, whole bool) *pyjson.Object {
	h.t.Helper()
	var page struct {
		Devices []json.RawMessage `json:"devices"`
	}
	path := "/internal/devices?device=" + device
	if whole {
		path += "&whole=1"
	}
	if err := h.r.getJSON(context.Background(), path, &page); err != nil {
		h.t.Fatal(err)
	}
	if len(page.Devices) == 0 {
		return nil
	}
	v, err := pyjson.Parse(page.Devices[0])
	if err != nil {
		h.t.Fatal(err)
	}
	return v.(*pyjson.Object)
}

func (h *harness) flush() {
	h.t.Helper()
	for {
		n, err := h.r.Flush(context.Background())
		if err != nil {
			h.t.Fatal(err)
		}
		if n == 0 {
			return
		}
	}
}

func hourNow() string { return strconv.FormatInt(time.Now().Unix()/3600, 10) }

func packet(device string, fields map[string]any) map[string]any {
	p := map[string]any{"v": 2, "device": device, "name": "Gee", "account": device + "@example.com", "updatedAt": time.Now().UnixMilli(), "openSessions": 1, "working": 1}
	for k, v := range fields {
		p[k] = v
	}
	return p
}

// TestThroughTheReceiver: a computer enrols with the shared key through the receiver (passed to Python), then sends with its own key
// (handled here); Python ends with the same book the receiver holds, the name it knows, and the computer's real address.
// TestThroughTheReceiver: một máy ghi danh bằng khoá chung qua bộ nhận (chuyển cho Python), rồi gửi bằng khoá riêng (xử lý ở đây);
// Python kết thúc với đúng sổ mà bộ nhận giữ, cái tên nó biết, và địa chỉ thật của máy.
func TestThroughTheReceiver(t *testing.T) {
	h := start(t)
	device, hour := "device-goone", hourNow()
	status, ans := h.send("shared-test-key-0123456789", packet(device, map[string]any{"full": true, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 7, "input": 3}}}}))
	if status != 200 || ans["boot"] != h.r.Boot {
		t.Fatalf("enrol: %d %v", status, ans)
	}
	key, _ := ans["deviceKey"].(string)
	if !strings.HasPrefix(key, "awd1.") {
		t.Fatalf("no key of its own: %v", ans)
	}
	// with its own key: handled here, answered with this receiver's boot, and a name the computer claims is not taken
	// với khoá riêng: xử lý ở đây, trả lời bằng boot của bộ nhận này, và tên máy tự khai không được nhận
	prev := strconv.FormatInt(time.Now().Unix()/3600-1, 10)
	p := packet(device, map[string]any{"name": "Someone Else", "waiting": 1, "hours": map[string]any{"ledger": map[string]any{prev: map[string]any{"usdMicro": 2}},
		"tasks": map[string]any{hour: map[string]any{"gemini": 1}}},
		"delegations": []any{map[string]any{"id": "0123456789abcdef01234567", "tool": "ask_gemini", "at": time.Now().UnixMilli(), "outcome": "ok"}}})
	status, ans = h.send(key, p)
	if status != 200 || ans["needFull"] != false || ans["boot"] != h.r.Boot || ans["deviceKey"] != nil {
		t.Fatalf("own key: %d %v", status, ans)
	}
	// one row for the computer, and one for the third check (RECEIVER_CHECK_PERCENT=100)
	// một dòng cho máy, và một dòng cho lớp đối chiếu thứ ba (RECEIVER_CHECK_PERCENT=100)
	if h.r.waitingCount() != 1 || h.r.queued() != 2 {
		t.Fatalf("%d computers, %d rows waiting", h.r.waitingCount(), h.r.queued())
	}
	h.flush()
	got := h.pythonBook(device, true)
	if strings.Count(string(pyjson.Encode(got)), "usdMicro") != 2 {
		t.Fatalf("python book %s", pyjson.Encode(got))
	}
	// this side keeps only the hours of today, the same as Python's book from today on
	// bên này chỉ giữ các giờ của hôm nay, đúng như sổ của Python từ hôm nay trở đi
	e := h.r.entry(device)
	theirs := heldFrom(got, h.r.today())
	if fmt.Sprint(e.rec.ledger, e.rec.tasks) != fmt.Sprint(theirs.ledger, theirs.tasks) {
		t.Fatalf("hours differ\n go     %v %v\n python %v %v", e.rec.ledger, e.rec.tasks, theirs.ledger, theirs.tasks)
	}
	// what the board shows of that computer comes from Python: the name it enrolled with, and the address the receiver saw
	// những gì bảng hiện về máy đó lấy từ Python: tên lúc ghi danh, và địa chỉ bộ nhận đã thấy
	var policy Policy
	if err := h.r.getJSON(context.Background(), "/internal/policy", &policy); err != nil {
		t.Fatal(err)
	}
	if policy.Boot == h.r.Boot {
		t.Fatal("Python's boot leaked to the computers")
	}
	if policy.Checked != 1 || policy.Mismatches != 0 {
		t.Fatalf("third check: %d compared, %d different", policy.Checked, policy.Mismatches)
	}
	// a key of another computer, a broken key, and a revoked one
	// khoá của máy khác, khoá hỏng, và khoá bị thu hồi
	if status, ans := h.send(key, packet("device-gotwo", nil)); status != 403 {
		t.Fatalf("another computer: %d %v", status, ans)
	}
	if status, ans := h.send(key[:len(key)-2]+"xx", p); status != 401 || ans["error"] != "bad signature" {
		t.Fatalf("broken key: %d %v", status, ans)
	}
	h.r.mu.Lock()
	h.r.policy.revoked = map[string]bool{device: true}
	h.r.mu.Unlock()
	if status, ans := h.send(key, p); status != 401 || ans["error"] != "device revoked" {
		t.Fatalf("revoked: %d %v", status, ans)
	}
}

// stripOrder sorts the keys of every table, for comparing two books whatever order their hours were written in.
// stripOrder xếp khoá của mọi bảng, để so hai sổ bất kể các giờ được ghi theo thứ tự nào.
func stripOrder(v pyjson.Value) pyjson.Value {
	o, ok := v.(*pyjson.Object)
	if !ok {
		return v
	}
	keys := append([]string(nil), o.Keys...)
	for i := 1; i < len(keys); i++ {
		for j := i; j > 0 && keys[j] < keys[j-1]; j-- {
			keys[j], keys[j-1] = keys[j-1], keys[j]
		}
	}
	out := pyjson.NewObject()
	for _, k := range keys {
		x, _ := o.Get(k)
		out.Set(k, stripOrder(x))
	}
	return out
}

// TestNeedFullAndAgain: changed hours for a computer with no book ask for the whole book; the same batch sent twice is written once.
// TestNeedFullAndAgain: các giờ đã đổi cho một máy không có sổ thì xin cả sổ; cùng một lô gửi hai lần chỉ được ghi một lần.
func TestNeedFullAndAgain(t *testing.T) {
	h := start(t)
	device, hour := "device-gothree", hourNow()
	_, ans := h.send("shared-test-key-0123456789", packet(device, map[string]any{"v": 1}))
	key := ans["deviceKey"].(string)
	// Python's row for the computer is gone (as after a lost disk): the receiver learns it and asks for the whole book
	// dòng của máy ở Python đã mất (như sau khi mất đĩa): bộ nhận biết điều đó và xin cả sổ
	e := h.r.entry(device)
	e.mu.Lock()
	e.loaded, e.rec = true, nil
	e.mu.Unlock()
	if status, ans := h.send(key, packet(device, map[string]any{"hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 1}}}})); status != 200 || ans["needFull"] != true {
		t.Fatalf("need full: %d %v", status, ans)
	}
	if status, ans := h.send(key, packet(device, map[string]any{"full": true, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 4}}}})); status != 200 || ans["needFull"] != false {
		t.Fatalf("full: %d %v", status, ans)
	}
	// the two sends wait as one row
	// hai lần gửi chờ thành một dòng
	if h.r.waitingCount() != 1 {
		t.Fatalf("%d computers waiting", h.r.waitingCount())
	}
	sent := *h.r.take()
	h.flush()
	// the same batch again, under the seq already written: Python answers and writes nothing
	// cùng lô đó gửi lại, với seq đã ghi: Python trả lời và không ghi gì
	h.r.qmu.Lock()
	h.r.inflight = &sent
	h.r.qmu.Unlock()
	h.flush()
	book := h.pythonBook(device, true)
	if !strings.Contains(string(pyjson.Encode(book)), `"usdMicro": 4`) {
		t.Fatalf("python book %s", pyjson.Encode(book))
	}
}

// TestRefusalsAnswerLikePython: what the receiver answers itself uses Python's codes and words.
// TestRefusalsAnswerLikePython: những gì bộ nhận tự trả lời dùng đúng mã và chữ của Python.
func TestRefusalsAnswerLikePython(t *testing.T) {
	h := start(t)
	for _, c := range []struct {
		path, auth, body string
		status           int
	}{
		{"/ingest", "awd1.x", "{}", 401},
		{"/ingest", "wrong", "{}", 401},
		{"/elsewhere", "wrong", "{}", 404},
		{"/ingest?x=1", "wrong", "{}", 404},
	} {
		req, _ := http.NewRequest(http.MethodPost, h.front.URL+c.path, strings.NewReader(c.body))
		req.Header.Set("Authorization", "Bearer "+c.auth)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != c.status {
			t.Errorf("%s %s: %d, expected %d", c.path, c.auth, resp.StatusCode, c.status)
		}
	}
	big := fmt.Sprintf(`{"v": 2, "pad": "%s"}`, strings.Repeat("x", MaxBodyBytes))
	req, _ := http.NewRequest(http.MethodPost, h.front.URL+"/ingest", strings.NewReader(big))
	req.Header.Set("Authorization", "Bearer wrong")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 413 {
		t.Errorf("too large: %d", resp.StatusCode)
	}
}

// TestNameFilledInLaterAndForwardLimit: a computer enrolled without a name sends one through the receiver; Python names it incomplete in
// the answer to a batch, the next send with a name goes to Python, and the answer carries a key for the new person. With no free slot to
// pass a send on, the computer is told at once to come back.
// TestNameFilledInLaterAndForwardLimit: máy ghi danh khi chưa có tên rồi gửi tên qua bộ nhận; Python nêu nó là chưa đủ trong câu trả lời
// của một lô, lần gửi có tên kế tiếp đi tới Python, và câu trả lời mang khoá cho người mới. Khi không còn chỗ để chuyển, máy được báo
// quay lại ngay.
func TestNameFilledInLaterAndForwardLimit(t *testing.T) {
	h := start(t)
	device := "device-gofour"
	first := packet(device, map[string]any{"v": 1})
	delete(first, "name")
	_, ans := h.send("shared-test-key-0123456789", first)
	key := ans["deviceKey"].(string)
	if status, ans := h.send(key, packet(device, map[string]any{"v": 1})); status != 200 || ans["deviceKey"] != nil {
		t.Fatalf("handled here: %d %v", status, ans)
	}
	h.flush()
	if e := h.r.entry(device); !e.askName {
		t.Fatal("Python did not say the person has no name")
	}
	status, ans := h.send(key, packet(device, map[string]any{"v": 1}))
	newKey, _ := ans["deviceKey"].(string)
	if status != 200 || newKey == "" || strings.Split(newKey, ".")[3] == strings.Split(key, ".")[3] || ans["boot"] != h.r.Boot {
		t.Fatalf("filled in: %d %v", status, ans)
	}
	if e := h.r.entry(device); e.askName {
		t.Fatal("still asking for a name")
	}
	h.r.forwardSlots = make(chan struct{})
	req, _ := http.NewRequest(http.MethodPost, h.front.URL+"/ingest", strings.NewReader(`{"v": 1}`))
	req.Header.Set("Authorization", "Bearer shared-test-key-0123456789")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 503 || resp.Header.Get("Retry-After") == "" {
		t.Fatalf("no free slot: %d", resp.StatusCode)
	}
}
