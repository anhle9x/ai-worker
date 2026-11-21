package ingest

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"testing"
	"time"

	"aiworker/receiver/internal/live"
	"aiworker/receiver/internal/pyjson"
)

// judge talks to tests/contract/ingest-v2/view_judge.py, which runs the harness's Python server: ask(now) is what role_view says at that
// second, from that server's memory: the fields the live numbers carry of each person and the totals of each branch.
// judge nói chuyện với tests/contract/ingest-v2/view_judge.py, nơi chạy máy chủ Python của bộ thử: ask(now) là thứ role_view nói ở giây
// đó, từ bộ nhớ của máy chủ đó: các trường số trực tiếp mang của mỗi người và tổng của từng chi nhánh.
type judge struct {
	t   *testing.T
	in  *json.Encoder
	out *bufio.Scanner
}

type verdict struct {
	People       []map[string]any `json:"people"`
	BranchTotals []map[string]any `json:"branchTotals"`
}

// attachJudge takes the input and the output of the judge's process, before it starts.
// attachJudge lấy đầu vào và đầu ra của tiến trình trọng tài, trước khi nó khởi động.
func attachJudge(t *testing.T, cmd *exec.Cmd) *judge {
	t.Helper()
	in, err := cmd.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	out, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { in.Close() })
	scan := bufio.NewScanner(out)
	scan.Buffer(make([]byte, 1<<20), 64<<20)
	return &judge{t, json.NewEncoder(in), scan}
}

func (j *judge) ask(now float64) verdict {
	j.t.Helper()
	if err := j.in.Encode(map[string]float64{"now": now}); err != nil {
		j.t.Fatal(err)
	}
	if !j.out.Scan() {
		j.t.Fatalf("the judge said nothing: %v", j.out.Err())
	}
	var v verdict
	if err := json.Unmarshal(j.out.Bytes(), &v); err != nil {
		j.t.Fatal(err)
	}
	return v
}

// asJSON is a value as it reads back from JSON, so Go's rows and Python's compare field by field as numbers, lists and tables.
// asJSON là một giá trị như khi đọc lại từ JSON, để dòng của Go và của Python so được từng trường dưới dạng số, danh sách và bảng.
func asJSON(t *testing.T, v any) []map[string]any {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	var out []map[string]any
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatal(err)
	}
	return out
}

// compareRows checks that the receiver's rows at the second now are Python's, for the rows named (all of them when rows is nil).
// compareRows kiểm rằng các dòng của bộ nhận ở giây now đúng là của Python, với các dòng được nêu (mọi dòng khi rows là nil).
func compareRows(t *testing.T, h *harness, j *judge, now float64, rows map[string]bool, what string) verdict {
	t.Helper()
	v := j.ask(now)
	pick := func(list []map[string]any) map[string]map[string]any {
		out := map[string]map[string]any{}
		for _, p := range list {
			code, _ := p["row"].(string)
			if rows == nil || rows[code] {
				delete(p, "usdMicroToday")
				out[code] = p
			}
		}
		return out
	}
	want, got := pick(v.People), pick(asJSON(t, h.r.Rows(now)))
	if rows != nil && len(want) != len(rows) {
		t.Fatalf("%s at %.0f: Python has %d of the rows %v", what, now, len(want), rows)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%s at %.0f:\n got  %v\n want %v", what, now, got, want)
	}
	return v
}

// shifted is a copy of a send of the shared sample moved by whole days: its updatedAt and the keys of its hours.
// shifted là bản sao của một lần gửi trong bộ mẫu chung dời đi một số ngày tròn: updatedAt và khoá các giờ của nó.
func shifted(sent *pyjson.Object, days int64) *pyjson.Object {
	out := sent.Copy()
	if n, ok := field(out, "updatedAt").(pyjson.Number); ok && n.Int {
		out.Set("updatedAt", pyjson.IntN(n.I+days*86_400_000))
	}
	book := out
	if hours, ok := field(out, "hours").(*pyjson.Object); ok {
		book = hours.Copy()
		out.Set("hours", book)
	}
	for _, kind := range []string{"ledger", "tasks", "blocks"} {
		t, ok := field(book, kind).(*pyjson.Object)
		if !ok {
			continue
		}
		moved := pyjson.NewObject()
		for i, k := range t.Keys {
			n, err := strconv.ParseInt(k, 10, 64)
			if err != nil {
				moved.Set(k, t.Vals[i])
				continue
			}
			moved.Set(strconv.FormatInt(n+days*24, 10), t.Vals[i])
		}
		book.Set(kind, moved)
	}
	return out
}

// TestLiveRowsAreRoleView plays tests/contract/ingest-v2/cases.json through this receiver, moved by whole days to a few days ago (Python
// deletes computers silent for KEEP_DAYS when the board is built), and after each step compares the live row of the case's people with
// role_view of the real Python server, which is the judge: at the moment of the send, just before and after the computer goes offline,
// and on the next day. When all the sends of a case wait as one row per computer, the rows are compared once they are written.
// TestLiveRowsAreRoleView chạy tests/contract/ingest-v2/cases.json qua bộ nhận này, dời một số ngày tròn về vài ngày trước (Python xoá
// các máy im quá KEEP_DAYS khi dựng bảng), và sau mỗi bước so dòng trực tiếp của người trong ca với role_view của máy chủ Python thật, là
// trọng tài: lúc gửi, ngay trước và ngay sau khi máy thành ngoại tuyến, và sang ngày hôm sau. Khi mọi lần gửi của một ca chờ thành mỗi
// máy một dòng, các dòng được so khi chúng đã được ghi.
func TestLiveRowsAreRoleView(t *testing.T) {
	h, j := startWith(t, true)
	ctx := context.Background()
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "tests", "contract", "ingest-v2", "cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	sample, err := pyjson.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	last := 0.0
	for _, c := range get(sample, "cases").([]pyjson.Value) {
		for _, step := range get(c, "steps").([]pyjson.Value) {
			last = max(last, atOf(get(step, "at")))
		}
	}
	days := (time.Now().Unix() - 3*86400 - int64(last)) / 86400
	runs := []struct {
		form, suffix string
		each         bool
	}{{"v2", "la", true}, {"v2", "lb", false}, {"v1", "lc", true}, {"v1", "ld", false}}
	enrolled, compared := 0, 0
	for _, c := range get(sample, "cases").([]pyjson.Value) {
		name := get(c, "name").(string)
		for _, run := range runs {
			if run.form == "v1" && get(c, "v2Only") == true {
				continue
			}
			keys := map[string]string{}
			check := func(at float64, what string) {
				t.Helper()
				h.flush()
				if err := h.r.Resync(ctx); err != nil {
					t.Fatal(err)
				}
				if _, err := h.r.RefreshPeople(ctx); err != nil {
					t.Fatal(err)
				}
				rows := map[string]bool{}
				for device := range keys {
					e, ok := h.r.People.Get(device)
					if !ok {
						t.Fatalf("%s: Python has not placed %s", what, device)
					}
					rows[e.Row] = true
				}
				for _, now := range []float64{at, at + live.OfflineSeconds - 1, at + live.OfflineSeconds + 1, at + 86400} {
					compareRows(t, h, j, now, rows, what)
					compared++
				}
			}
			at := 0.0
			for i, step := range get(c, "steps").([]pyjson.Value) {
				device := get(step, "device").(string) + run.suffix
				sent, _ := get(step, run.form).(*pyjson.Object)
				if sent == nil {
					continue
				}
				sent = shifted(sent, days)
				sent.Set("device", device)
				// a person of their own in each run: a row joins the computers of one person, and a run plays its days again
				// mỗi lượt chạy một người riêng: một dòng ghép các máy của một người, và mỗi lượt chạy lại các ngày của nó
				sent.Set("name", get(sent, "name").(string)+" "+run.suffix)
				sent.Set("account", run.suffix+"-"+get(sent, "account").(string))
				if keys[device] == "" {
					h.r.Now = func() int64 { return realNow() }
					first := map[string]any{"v": 1, "device": device, "name": get(sent, "name"), "account": get(sent, "account"), "updatedAt": realNow()}
					enrolled++
					status, ans := h.sendFrom("198.51."+strconv.Itoa(enrolled/250)+"."+strconv.Itoa(enrolled%250+1), "shared-test-key-0123456789", first)
					key, _ := ans["deviceKey"].(string)
					if status != 200 || key == "" {
						t.Fatalf("%s %s: enrol %d %v", name, device, status, ans)
					}
					keys[device] = key
					forget(h.r.entry(device))
				}
				if get(step, "dropRowFirst") == true {
					forget(h.r.entry(device))
				}
				at = atOf(get(step, "at")) + float64(days*86400)
				if get(step, "delivered") == true {
					h.r.Now = func() int64 { return int64(at * 1000) }
					if status, ans := h.send(resign(t, h.secrets, keys[device], int64(at)), json.RawMessage(pyjson.Encode(sent))); status != 200 {
						t.Fatalf("%s %s step %d: %d %v", name, run.suffix, i, status, ans)
					}
				}
				if run.each {
					check(at, name+" "+run.suffix+" step "+strconv.Itoa(i))
				}
			}
			if !run.each {
				check(at, name+" "+run.suffix+" end")
			}
		}
	}
	h.r.Now = func() int64 { return realNow() }
	if compared == 0 {
		t.Fatal("nothing compared")
	}
}

// TestLiveStatusesAndBranches: computers of every kind sent now through this receiver (a person with two computers, one waiting and
// handing work to helpers; a person whose connector has two tools open; a person with Claude open and idle), two of them in a branch
// declared by their email; the rows and the totals of each branch are the ones the real Python server gives, now and as each kind of
// computer goes quiet: the plugin's offline after 12 minutes, the connector's "working" after 30, the connector offline after 2 hours.
// TestLiveStatusesAndBranches: các máy đủ loại gửi lúc này qua bộ nhận này (một người hai máy, một máy đang chờ và đang giao việc cho trợ
// lý; một người có bộ nối mở hai công cụ; một người mở Claude mà rảnh), hai máy trong một chi nhánh khai báo theo email; các dòng và
// tổng của từng chi nhánh đúng như máy chủ Python thật cho, lúc này và khi từng loại máy im đi: plugin ngoại tuyến sau 12 phút, "đang làm"
// của bộ nối sau 30 phút, bộ nối ngoại tuyến sau 2 giờ.
func TestLiveStatusesAndBranches(t *testing.T) {
	h, j := startWith(t, true)
	ctx := context.Background()
	branches := filepath.Join(filepath.Dir(filepath.Dir(h.secrets)), "none.json")
	if err := os.WriteFile(branches, []byte(`{"branches": [{"id": "hue", "name": "Hue", "lat": 16.46, "lon": 107.59, "people": ["live-a@example.com"]}]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	hour := hourNow()
	nowMs := time.Now().UnixMilli()
	sends := []struct {
		device, name, account string
		fields                map[string]any
	}{
		{"device-livea1", "Live A", "live-a@example.com", map[string]any{"openSessions": 2, "working": 1, "waiting": 1, "delegating": map[string]any{"gemini": 1, "gemma": 2.7},
			"full": true, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 123457, "input": 10, "output": 4}}, "tasks": map[string]any{hour: map[string]any{"gemma": 3}}}}},
		{"device-livea2", "Live A", "live-a@example.com", map[string]any{"openSessions": 1, "working": 1, "waiting": 0,
			"full": true, "hours": map[string]any{"ledger": map[string]any{hour: map[string]any{"usdMicro": 50, "cacheRead": 7}}}}},
		{"device-liveb", "Live B", "live-b@example.com", map[string]any{"v": 1, "tools": map[string]any{"codex": map[string]any{"openSessions": 1, "working": 1},
			"cursor": map[string]any{"openSessions": 1, "waiting": 0}, "gemini": map[string]any{"openSessions": 0}}, "ledger": map[string]any{hour: map[string]any{"usd": 0.00005}}}},
		{"device-livec", "Live C", "live-c@example.com", map[string]any{"openSessions": 1, "working": 0, "waiting": 0, "full": true}},
	}
	for _, s := range sends {
		first := map[string]any{"v": 1, "device": s.device, "name": s.name, "account": s.account, "updatedAt": nowMs}
		status, ans := h.send("shared-test-key-0123456789", first)
		key, _ := ans["deviceKey"].(string)
		if status != 200 || key == "" {
			t.Fatalf("enrol %s: %d %v", s.device, status, ans)
		}
		p := packet(s.device, s.fields)
		p["name"], p["account"], p["updatedAt"] = s.name, s.account, nowMs+1000
		if status, ans := h.send(key, p); status != 200 {
			t.Fatalf("%s: %d %v", s.device, status, ans)
		}
	}
	h.flush()
	if err := h.r.Resync(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := h.r.RefreshPeople(ctx); err != nil {
		t.Fatal(err)
	}
	base := float64(nowMs+1000) / 1000
	statuses := map[string][]string{}
	for _, now := range []float64{base, base + live.OfflineSeconds + 1, base + live.ConnectorWorkingSeconds + 1, base + live.ConnectorOfflineSeconds + 1} {
		v := compareRows(t, h, j, now, nil, "statuses")
		if len(v.People) != 3 {
			t.Fatalf("%d people", len(v.People))
		}
		for _, p := range v.People {
			statuses[p["status"].(string)] = append(statuses[p["status"].(string)], p["row"].(string))
		}
		got := asJSON(t, live.Branches(h.r.Rows(now)))
		byID := func(list []map[string]any) map[string]map[string]any {
			out := map[string]map[string]any{}
			for _, b := range list {
				out[b["id"].(string)] = b
			}
			return out
		}
		if !reflect.DeepEqual(byID(got), byID(v.BranchTotals)) || len(got) != 2 {
			t.Fatalf("branches at %.0f:\n got  %v\n want %v", now, got, v.BranchTotals)
		}
	}
	// every status of status_of came up, so none is copied only by chance
	// mọi trạng thái của status_of đều đã xuất hiện, nên không trạng thái nào chép đúng chỉ do may
	seen := make([]string, 0, len(statuses))
	for s := range statuses {
		seen = append(seen, s)
	}
	sort.Strings(seen)
	if !reflect.DeepEqual(seen, []string{live.Offline, live.Open, live.Waiting, live.Working}) {
		t.Fatalf("statuses seen: %v", seen)
	}
}
