package main

import (
	"bufio"
	"crypto/tls"
	"io"
	"math"
	"net"
	"net/http"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

// TestLimitsFromTheMachine: by default 40% of the machine's memory and 64 KiB a connection; GOMEMLIMIT wins; 0 turns each off; wrong
// values stop the start.
// TestLimitsFromTheMachine: mặc định 40% bộ nhớ của máy và 64 KiB mỗi kết nối; GOMEMLIMIT được ưu tiên; 0 tắt từng cái; giá trị sai
// thì không cho khởi động.
func readLimits4(env func(string) string, meminfo string, runtimeLimit int64) (limits, error) {
	return readLimits(env, meminfo, runtimeLimit, 4)
}

func TestLimitsFromTheMachine(t *testing.T) {
	const meminfo = "MemTotal:        7925760 kB\nMemFree:         7000000 kB\n"
	env := func(m map[string]string) func(string) string { return func(k string) string { return m[k] } }
	none := int64(math.MaxInt64)

	l, err := readLimits4(env(nil), meminfo, none)
	want := int64(float64(7925760<<10) * memoryShare)
	if err != nil || l.memory != want || l.connections != want/connectionBytes {
		t.Fatalf("default: %+v %v", l, err)
	}
	// an 8 GB machine: about 3 GB and about 48,000 connections, where the Go receiver ran out of memory at about 60,000 without them
	// máy 8 GB: khoảng 3 GB và khoảng 48.000 kết nối, trong khi bộ nhận Go hết bộ nhớ ở khoảng 60.000 khi chưa có chúng
	if l.memory>>20 < 3000 || l.memory>>20 > 3200 || l.connections < 45000 || l.connections > 50000 {
		t.Fatalf("8 GB: %d MB, %d connections", l.memory>>20, l.connections)
	}

	if l, err := readLimits4(env(nil), "", none); err != nil || l.memory != 0 || l.connections != 0 {
		t.Fatalf("no /proc/meminfo: %+v %v", l, err)
	}
	if l, err := readLimits4(env(nil), meminfo, 2<<30); err != nil || l.memory != 0 || l.from != "GOMEMLIMIT" || l.connections != (2<<30)/connectionBytes {
		t.Fatalf("GOMEMLIMIT: %+v %v", l, err)
	}
	if l, err := readLimits4(env(map[string]string{"RECEIVER_MEMORY_MB": "0"}), meminfo, none); err != nil || l.memory != 0 || l.connections != 0 {
		t.Fatalf("memory off: %+v %v", l, err)
	}
	if l, err := readLimits4(env(map[string]string{"RECEIVER_MEMORY_MB": "1024", "RECEIVER_MAX_CONNECTIONS": "0"}), meminfo, none); err != nil ||
		l.memory != 1<<30 || l.connections != 0 {
		t.Fatalf("no ceiling: %+v %v", l, err)
	}
	if l, err := readLimits4(env(map[string]string{"RECEIVER_MAX_CONNECTIONS": "20000"}), meminfo, none); err != nil || l.connections != 20000 {
		t.Fatalf("ceiling: %+v %v", l, err)
	}
	for _, bad := range []map[string]string{
		{"RECEIVER_MEMORY_MB": "100"}, {"RECEIVER_MEMORY_MB": "x"}, {"RECEIVER_MEMORY_MB": "-1"},
		{"RECEIVER_MAX_CONNECTIONS": "5"}, {"RECEIVER_MAX_CONNECTIONS": "lots"},
	} {
		if _, err := readLimits4(env(bad), meminfo, none); err == nil {
			t.Errorf("accepted %v", bad)
		}
	}
}

// TestConnectionsPastTheCeilingAreToldToComeBack: with a ceiling of 2, a third kept connection gets 503 with a Retry-After of 30 to 90
// seconds and is closed, while its /live and /health are let through; once one of the first two is gone, a new connection is served again.
// TestConnectionsPastTheCeilingAreToldToComeBack: với trần 2, kết nối giữ thứ ba nhận 503 kèm Retry-After 30 tới 90 giây và bị đóng,
// còn /live và /health trên nó vẫn được cho qua; khi một trong hai kết nối đầu đi, kết nối mới lại được phục vụ.
func TestConnectionsPastTheCeilingAreToldToComeBack(t *testing.T) {
	dir := t.TempDir()
	writeCert(t, dir, "ingest.example.com")
	cert := &certificate{certFile: filepath.Join(dir, "cert.pem"), keyFile: filepath.Join(dir, "key.pem")}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	capped := &capListener{Listener: ln, max: 2}
	srv := newServer(config{listen: ln.Addr().String()}, refuseOver(capped, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, "ok")
	})), cert)
	srv.ConnContext = connContext
	go func() { _ = srv.ServeTLS(capped, "", "") }()
	defer srv.Close()

	type kept struct {
		c  *tls.Conn
		br *bufio.Reader
	}
	open := func() kept {
		c, err := tls.Dial("tcp", ln.Addr().String(), &tls.Config{InsecureSkipVerify: true, NextProtos: []string{"http/1.1"}})
		if err != nil {
			t.Fatal(err)
		}
		return kept{c, bufio.NewReader(c)}
	}
	ask := func(k kept, path string) *http.Response {
		_ = k.c.SetDeadline(time.Now().Add(5 * time.Second))
		if _, err := io.WriteString(k.c, "POST "+path+" HTTP/1.1\r\nHost: ingest\r\nContent-Length: 2\r\n\r\n{}"); err != nil {
			t.Fatal(err)
		}
		resp, err := http.ReadResponse(k.br, nil)
		if err != nil {
			t.Fatal(err)
		}
		_, _ = io.ReadAll(resp.Body)
		resp.Body.Close()
		return resp
	}
	a, b := open(), open()
	if ask(a, "/ingest").StatusCode != 200 || ask(b, "/ingest").StatusCode != 200 {
		t.Fatal("the first two are not served")
	}
	c := open()
	for _, path := range []string{"/live/snap", "/health"} {
		if r := ask(c, path); r.StatusCode != 200 {
			t.Fatalf("%s past the ceiling: %d", path, r.StatusCode)
		}
	}
	r := ask(c, "/ingest")
	ra, _ := strconv.Atoi(r.Header.Get("Retry-After"))
	if r.StatusCode != http.StatusServiceUnavailable || ra < 30 || ra > 90 || !r.Close {
		t.Fatalf("past the ceiling: %d, Retry-After %q, close %v", r.StatusCode, r.Header.Get("Retry-After"), r.Close)
	}
	if capped.refused.Load() != 1 {
		t.Fatalf("refused %d", capped.refused.Load())
	}
	_ = c.c.Close()
	_ = a.c.Close()
	// the server sees the closes a moment later / máy chủ thấy các lần đóng sau một chút
	deadline := time.Now().Add(3 * time.Second)
	for capped.open.Load() > 1 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if capped.open.Load() != 1 {
		t.Fatalf("open %d after two closes", capped.open.Load())
	}
	if ask(open(), "/ingest").StatusCode != 200 {
		t.Fatal("a new connection under the ceiling is not served")
	}
}

// TestPaceOfTheSends: the gap asked keeps the computers connected within the sends a second the machine answers, in whole seconds, never
// under the usual 2 seconds and never over 120; by default 2,500 a processor.
// TestPaceOfTheSends: khoảng cách được dặn giữ các máy đang kết nối trong số lần gửi mỗi giây máy trả lời được, theo giây tròn, không
// dưới 2 giây thường lệ và không quá 120; mặc định 2.500 mỗi bộ xử lý.
func TestPaceOfTheSends(t *testing.T) {
	for _, c := range []struct{ open, sends, want int64 }{
		{0, 10000, 0}, {20000, 10000, 0}, {20001, 10000, 3000}, {50000, 10000, 5000}, {100000, 10000, 10000}, {100000, 20000, 5000},
		{10_000_000, 10000, 120000}, {50000, 0, 0},
	} {
		if got := pace(c.open, c.sends); got != c.want {
			t.Errorf("pace(%d, %d) = %d, want %d", c.open, c.sends, got, c.want)
		}
	}
	env := func(m map[string]string) func(string) string { return func(k string) string { return m[k] } }
	if l, err := readLimits(env(nil), "", math.MaxInt64, 4); err != nil || l.sends != 4*sendsPerCPU {
		t.Fatalf("default: %+v %v", l, err)
	}
	if l, err := readLimits(env(map[string]string{"RECEIVER_SENDS_PER_SECOND": "0"}), "", math.MaxInt64, 4); err != nil || l.sends != 0 {
		t.Fatalf("off: %+v %v", l, err)
	}
	if l, err := readLimits(env(map[string]string{"RECEIVER_SENDS_PER_SECOND": "30000"}), "", math.MaxInt64, 4); err != nil || l.sends != 30000 {
		t.Fatalf("set: %+v %v", l, err)
	}
	for _, bad := range []string{"5", "x", "-3"} {
		if _, err := readLimits(env(map[string]string{"RECEIVER_SENDS_PER_SECOND": bad}), "", math.MaxInt64, 4); err == nil {
			t.Errorf("accepted %q", bad)
		}
	}
}
