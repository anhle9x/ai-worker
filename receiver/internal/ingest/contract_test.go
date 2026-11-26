package ingest

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"aiworker/receiver/internal/clean"
	"aiworker/receiver/internal/pyjson"
	"aiworker/receiver/internal/totals"
)

// resign gives a computer's key issued by Python again with another issue time, signed with the secret of the file: the shared sample
// plays days in the past, where a key issued today would not be valid yet.
// resign trả lại khoá của một máy do Python cấp với lúc cấp khác, ký bằng bí mật trong file: bộ mẫu chung chạy các ngày trong quá khứ,
// khi đó khoá cấp hôm nay chưa có hiệu lực.
func resign(t *testing.T, secretsFile, token string, iat int64) string {
	t.Helper()
	b, err := os.ReadFile(secretsFile)
	if err != nil {
		t.Fatal(err)
	}
	var entries []struct{ Kid, Alg, Secret string }
	if err := json.Unmarshal(b, &entries); err != nil {
		t.Fatal(err)
	}
	parts := strings.Split(token, ".")
	for _, e := range entries {
		if e.Alg == "HS256" && e.Kid == parts[1] {
			secret, err := base64.RawURLEncoding.DecodeString(strings.TrimRight(e.Secret, "="))
			if err != nil {
				t.Fatal(err)
			}
			parts[6] = strconv.FormatInt(iat, 10)
			mac := hmac.New(sha256.New, secret)
			mac.Write([]byte(strings.Join(parts[:7], ".")))
			parts[7] = base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
			return strings.Join(parts, ".")
		}
	}
	t.Fatalf("no secret for %s", parts[1])
	return ""
}

func get(v pyjson.Value, k string) pyjson.Value {
	x, _ := v.(*pyjson.Object).Get(k)
	return x
}

func atOf(v pyjson.Value) float64 {
	n := v.(pyjson.Number)
	if n.Int {
		return float64(n.I)
	}
	return n.F
}

// daysOf is the totals per day of a book in the sample's shape.
// daysOf là tổng theo ngày của một sổ theo dạng của bộ mẫu.
func daysOf(days map[string]*totals.Day) *pyjson.Object {
	out := pyjson.NewObject()
	n := func(b *big.Int) pyjson.Number { return pyjson.BigN(b) }
	for day, d := range days {
		o := pyjson.NewObject()
		o.Set("usdMicro", n(d.USDMicro))
		o.Set("tokensIn", n(d.TokensIn))
		o.Set("tokensOut", n(d.TokensOut))
		for i, w := range clean.Workers {
			o.Set(w, n(d.Tasks[i]))
		}
		out.Set(day, o)
	}
	return out
}

// TestSharedSampleThroughPython plays tests/contract/ingest-v2/cases.json through this receiver with each computer's own key, and lets
// the real Python server write the batches: Python must end with the book and the totals per day the sample expects, in both formats,
// whether each send goes in a batch of its own or all the sends of a case wait as one row per computer. This receiver keeps only the
// hours of today, so the whole book is compared where it is kept; its own totals of today must be the sample's too.
// TestSharedSampleThroughPython chạy tests/contract/ingest-v2/cases.json qua bộ nhận này bằng khoá riêng của từng máy, và để máy chủ
// Python thật ghi các lô: Python phải kết thúc với đúng sổ và tổng theo ngày bộ mẫu chờ, ở cả hai định dạng, dù mỗi lần gửi đi một lô
// riêng hay mọi lần gửi của một ca chờ thành mỗi máy một dòng. Bộ nhận này chỉ giữ các giờ của hôm nay, nên cả sổ được so ở nơi giữ nó;
// tổng hôm nay của chính nó cũng phải đúng như bộ mẫu.
func TestSharedSampleThroughPython(t *testing.T) {
	h := start(t)
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "tests", "contract", "ingest-v2", "cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	sample, err := pyjson.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	tz := int64(atOf(get(sample, "tzHours")) * 3600)
	runs := []struct {
		form, suffix string
		each         bool
	}{{"v2", "a", true}, {"v2", "b", false}, {"v1", "c", true}, {"v1", "d", false}}
	enrolled := 0
	for _, c := range get(sample, "cases").([]pyjson.Value) {
		name := get(c, "name").(string)
		for _, run := range runs {
			if run.form == "v1" && get(c, "v2Only") == true {
				continue
			}
			keys := map[string]string{}
			straight := false
			for i, step := range get(c, "steps").([]pyjson.Value) {
				device := get(step, "device").(string) + run.suffix
				sent, _ := get(step, run.form).(*pyjson.Object)
				if sent == nil {
					continue
				}
				sent = sent.Copy()
				sent.Set("device", device)
				if keys[device] == "" {
					// enrolled with the shared key, at the real time; then this side forgets the book, as a computer new to it
					// ghi danh bằng khoá chung, theo giờ thật; rồi bên này quên sổ, như một máy mới với nó
					h.r.Now = func() int64 { return realNow() }
					first := map[string]any{"v": 1, "device": device, "name": get(sent, "name"), "account": get(sent, "account"), "updatedAt": realNow()}
					// each from an address of its own: Python lets only a few new computers in from one address a day
					// mỗi máy từ một địa chỉ riêng: Python chỉ cho vài máy mới vào từ một địa chỉ mỗi ngày
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
				if get(step, "delivered") != true {
					continue
				}
				at := atOf(get(step, "at"))
				if get(step, "straight") == true {
					straight = true
					h.straight(sent, at)
					continue
				}
				h.r.Now = func() int64 { return int64(at * 1000) }
				status, ans := h.send(resign(t, h.secrets, keys[device], int64(at)), json.RawMessage(pyjson.Encode(sent)))
				want := run.form == "v2" && get(step, "expectV2") == clean.NeedFull
				if status != 200 || ans["needFull"] != want {
					t.Fatalf("%s %s step %d: %d %v, needFull %v expected", name, run.suffix, i, status, ans, want)
				}
				if run.each {
					h.flush()
				}
			}
			h.flush()
			expect := get(c, "expect").(*pyjson.Object)
			for i, base := range expect.Keys {
				device := base + run.suffix
				book := h.pythonBook(device, true)
				// the record without its time and the state the live numbers read (STATE_FIELDS in server/board/receiver.py): the book
				// bản ghi bỏ thời điểm và trạng thái mà số trực tiếp đọc (STATE_FIELDS trong server/board/receiver.py): còn lại là sổ
				for _, k := range []string{"device", "updatedAt", "seq", "openSessions", "working", "waiting", "delegating", "tools", "stamps"} {
					book.Delete(k)
				}
				if !pyjson.Equal(stripOrder(book), stripOrder(get(expect.Vals[i], "book"))) {
					t.Errorf("%s %s %s: book\n got  %s\n want %s", name, run.suffix, device, pyjson.Encode(book), pyjson.Encode(get(expect.Vals[i], "book")))
				}
				wantDays := get(expect.Vals[i], "days").(*pyjson.Object)
				if got := daysOf(totals.AddUp(book, tz)); !pyjson.Equal(stripOrder(got), stripOrder(wantDays)) {
					t.Errorf("%s %s %s: days\n got  %s\n want %s", name, run.suffix, device, pyjson.Encode(got), pyjson.Encode(wantDays))
				}
				// what this side keeps: the hours of the day of the last send and later, with that day's totals
				// thứ bên này giữ: các giờ của ngày của lần gửi cuối trở đi, với tổng của ngày đó
				// a send straight to Python reaches this side through the policy, which loads the book again; the case does not wait for that
				// lần gửi thẳng tới Python đến được bên này qua chính sách, khi đó sổ được nạp lại; ca này không chờ việc đó
				e := h.r.entry(device)
				if e.rec != nil && !straight {
					mine := daysOf(totals.DaysOf(e.rec.ledger, e.rec.tasks, tz))
					for j, day := range mine.Keys {
						if w, ok := wantDays.Get(day); !ok || !pyjson.Equal(stripOrder(mine.Vals[j]), stripOrder(w)) {
							t.Errorf("%s %s %s: today %s\n got  %s\n want %s", name, run.suffix, device, day, pyjson.Encode(mine.Vals[j]), pyjson.Encode(w))
						}
					}
				}
			}
		}
	}
	h.r.Now = func() int64 { return realNow() }
	if err := h.r.RefreshPolicy(context.Background()); err != nil {
		t.Fatal(err)
	}
	if p := h.r.Policy(); p.Proto != 3 || p.Mismatches != 0 {
		t.Fatalf("proto %d, %d sends cleaned differently", p.Proto, p.Mismatches)
	}
}

// straight writes one send at Python as if it had come straight there, at the time of the case: a batch of its own from another source,
// without the times of the hours (proto 2), so Python takes the send's own; a send to /ingest would be cleaned at the real time instead.
// straight ghi một lần gửi ở Python như thể nó tới thẳng đó, theo thời điểm của ca: một lô riêng từ một nguồn khác, không kèm thời điểm của
// các giờ (proto 2), nên Python lấy thời điểm của chính lần gửi; gửi tới /ingest thì sẽ bị làm sạch theo giờ thật.
func (h *harness) straight(sent *pyjson.Object, at float64) {
	h.t.Helper()
	d := clean.Payload(sent, at)
	h.seq++
	b := pyjson.NewObject()
	b.Set("src", "straight")
	b.Set("boot", "test")
	b.Set("seq", pyjson.IntN(h.seq))
	b.Set("rows", []pyjson.Value{row(d, clean.SendKind(sent), "198.51.100.1", int64(at*1000), nil, nil)})
	resp, err := h.r.internal(context.Background(), time.Minute, http.MethodPost, "/internal/rows", pyjson.Encode(b))
	if err != nil {
		h.t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 200 {
		h.t.Fatalf("straight to Python: %d", resp.StatusCode)
	}
}

// sendFrom is a send as from a computer at that address.
// sendFrom là một lần gửi như từ một máy ở địa chỉ đó.
func (h *harness) sendFrom(ip, auth string, packet any) (int, map[string]any) {
	h.t.Helper()
	b, _ := json.Marshal(packet)
	req := httptest.NewRequest(http.MethodPost, "/ingest", bytes.NewReader(b))
	req.RemoteAddr = ip + ":40000"
	req.Header.Set("Authorization", "Bearer "+auth)
	w := httptest.NewRecorder()
	h.r.ServeHTTP(w, req)
	var out map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	return w.Code, out
}

func realNow() int64 { return time.Now().UnixMilli() }

func forget(e *entry) {
	e.mu.Lock()
	e.loaded, e.rec, e.lastFull, e.everFull, e.counted = true, nil, 0, false, 0
	e.mu.Unlock()
}
