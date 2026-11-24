// The AI Worker receiver: an optional program, Go standard library only, that takes the computers' sends on an address of its own over
// TLS and hands them to the Python server in batches, and serves the boards their live numbers on /live (docs/RECEIVER.md). A small
// company does not need it.
// Bộ nhận của AI Worker: một chương trình tuỳ chọn, chỉ thư viện chuẩn của Go, nhận các lần gửi của máy trên một địa chỉ riêng qua TLS
// và trao chúng cho máy chủ Python theo lô, và phục vụ các bảng số trực tiếp ở /live (docs/RECEIVER.vi.md). Công ty nhỏ không cần nó.
//
// Settings, from the environment:
// Cấu hình, lấy từ biến môi trường:
//
//	RECEIVER_LISTEN        IP:port to listen on, required, never every address by default (example 203.0.113.2:443)
//	                       IP:cổng để nghe, bắt buộc, không bao giờ mặc định nghe mọi địa chỉ (ví dụ 203.0.113.2:443)
//	RECEIVER_TLS_CERT      the certificate file (full chain), read again when it changes
//	                       file chứng chỉ (cả chuỗi), đọc lại khi nó đổi
//	RECEIVER_TLS_KEY       the file of the certificate's private key, read again when it changes
//	                       file khoá bí mật của chứng chỉ, đọc lại khi nó đổi
//	RECEIVER_SECRETS_FILE  the file of secrets the Python server writes with RECEIVER=1 (its KEYS_DIR/receiver-secrets.json)
//	                       file bí mật máy chủ Python ghi khi có RECEIVER=1 (KEYS_DIR/receiver-secrets.json của nó)
//	RECEIVER_WEBHOOK       the Python server on this machine (default http://127.0.0.1:8788)
//	                       máy chủ Python trên máy này (mặc định http://127.0.0.1:8788)
//	RECEIVER_BATCH_MS      how often the rows go to Python, in milliseconds (default 1000; 5000 to 10000 for a large organisation)
//	                       bao lâu các dòng được gửi cho Python một lần, theo mili giây (mặc định 1000; 5000 tới 10000 cho tổ chức lớn)
//	RECEIVER_MEMORY_MB, RECEIVER_MAX_CONNECTIONS, RECEIVER_SENDS_PER_SECOND
//	                       the ceilings of memory and connections, and the pace of the sends (limits.go)
//	                       các trần bộ nhớ và kết nối, và nhịp các lần gửi (limits.go)
package main

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"aiworker/receiver/internal/devicekey"
	"aiworker/receiver/internal/feed"
	"aiworker/receiver/internal/ingest"
)

// sendTimeout bounds reading a send and writing its answer; the live feed sets its own deadlines (package feed). Tests make it short.
// sendTimeout giới hạn việc đọc một lần gửi và ghi câu trả lời của nó; luồng số trực tiếp tự đặt hạn riêng (gói feed). Bài test đặt ngắn.
var sendTimeout = 30 * time.Second

// handler sends /live and /live/... to the feed, every other path to the receiver.
// handler đưa /live và /live/... cho luồng, mọi đường khác cho bộ nhận.
func handler(r http.Handler, f http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/live" || strings.HasPrefix(req.URL.Path, "/live/") {
			f.ServeHTTP(w, req)
			return
		}
		r.ServeHTTP(w, req)
	})
}

type config struct {
	listen, cert, key, secrets, webhook string
	every                               time.Duration
}

func readConfig(env func(string) string) (config, error) {
	c := config{listen: env("RECEIVER_LISTEN"), cert: env("RECEIVER_TLS_CERT"), key: env("RECEIVER_TLS_KEY"), secrets: env("RECEIVER_SECRETS_FILE"),
		webhook: env("RECEIVER_WEBHOOK"), every: time.Second}
	host, port, err := net.SplitHostPort(c.listen)
	if err != nil || port == "" {
		return c, errors.New("RECEIVER_LISTEN must be IP:port, for example 203.0.113.2:443")
	}
	// the address is said on purpose: an empty host would listen on every address of the machine, the Python server's included
	// địa chỉ phải được nói rõ: host rỗng sẽ nghe trên mọi địa chỉ của máy, kể cả địa chỉ của máy chủ Python
	if host == "" {
		return c, errors.New("RECEIVER_LISTEN needs the IP to listen on, not only a port")
	}
	if c.cert == "" || c.key == "" {
		return c, errors.New("RECEIVER_TLS_CERT and RECEIVER_TLS_KEY are required: the receiver speaks TLS itself")
	}
	if c.secrets == "" {
		return c, errors.New("RECEIVER_SECRETS_FILE is required: the file the Python server writes with RECEIVER=1")
	}
	if c.webhook == "" {
		c.webhook = "http://127.0.0.1:8788"
	}
	u, err := url.Parse(c.webhook)
	if err != nil || u.Scheme != "http" || (u.Hostname() != "127.0.0.1" && u.Hostname() != "::1" && u.Hostname() != "localhost") || u.Path != "" {
		return c, errors.New("RECEIVER_WEBHOOK must be the Python server on this machine, for example http://127.0.0.1:8788")
	}
	if ms := env("RECEIVER_BATCH_MS"); ms != "" {
		n, err := strconv.Atoi(ms)
		if err != nil || n < 100 || n > 60000 {
			return c, errors.New("RECEIVER_BATCH_MS must be from 100 to 60000")
		}
		c.every = time.Duration(n) * time.Millisecond
	}
	return c, nil
}

// certificate reads the certificate files again when either changes on disk, so a renewal by an outside tool needs no restart.
// certificate đọc lại các file chứng chỉ khi một trong hai đổi trên đĩa, để việc gia hạn bằng công cụ ngoài không cần khởi động lại.
type certificate struct {
	certFile, keyFile string
	mu                sync.Mutex
	cert              *tls.Certificate
	stamp             string
	checked           time.Time
	// every: how often the files are looked at, at most (10 seconds; 0 in the tests)
	// every: bao lâu các file được xem lại một lần, nhiều nhất (10 giây; 0 trong bài test)
	every time.Duration
}

func stampOf(paths ...string) string {
	s := ""
	for _, p := range paths {
		if info, err := os.Stat(p); err == nil {
			s += fmt.Sprintf("%d:%d;", info.ModTime().UnixNano(), info.Size())
		}
	}
	return s
}

func (c *certificate) get(*tls.ClientHelloInfo) (*tls.Certificate, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cert != nil && time.Since(c.checked) < c.every {
		return c.cert, nil
	}
	c.checked = time.Now()
	stamp := stampOf(c.certFile, c.keyFile)
	if c.cert != nil && stamp == c.stamp {
		return c.cert, nil
	}
	cert, err := tls.LoadX509KeyPair(c.certFile, c.keyFile)
	if err != nil {
		if c.cert != nil {
			// a half-written renewal: keep the certificate already in use and try again shortly
			// lần gia hạn ghi dở: giữ chứng chỉ đang dùng và thử lại sau ít giây
			log.Printf("receiver: certificate not reloaded: %v", err)
			return c.cert, nil
		}
		return nil, err
	}
	c.cert, c.stamp = &cert, stamp
	return c.cert, nil
}

func newServer(c config, handler http.Handler, cert *certificate) *http.Server {
	return &http.Server{
		Addr:    c.listen,
		Handler: handler,
		TLSConfig: &tls.Config{
			MinVersion:     tls.VersionTLS12,
			GetCertificate: cert.get,
			// HTTP/1.1 only: HTTP/2 costs more CPU and memory here, and the plugin keeps an HTTP/1.1 connection open
			// chỉ HTTP/1.1: HTTP/2 tốn CPU và bộ nhớ hơn ở đây, và plugin giữ một kết nối HTTP/1.1 mở sẵn
			NextProtos: []string{"http/1.1"},
		},
		TLSNextProto:      map[string]func(*http.Server, *tls.Conn, http.Handler){},
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       sendTimeout,
		WriteTimeout:      sendTimeout,
		// a computer that has nothing new sends every 4 minutes; its connection is kept a little longer than that
		// máy không có gì mới gửi mỗi 4 phút; kết nối của nó được giữ lâu hơn thế một chút
		IdleTimeout:    5 * time.Minute,
		MaxHeaderBytes: 16 << 10,
		ErrorLog:       log.New(os.Stderr, "receiver: ", 0),
	}
}

func main() {
	c, err := readConfig(os.Getenv)
	if err != nil {
		log.Fatal(err)
	}
	meminfo, _ := os.ReadFile("/proc/meminfo")
	lim, err := readLimits(os.Getenv, string(meminfo), debug.SetMemoryLimit(-1), runtime.NumCPU())
	if err != nil {
		log.Fatal(err)
	}
	if lim.memory > 0 {
		debug.SetMemoryLimit(lim.memory)
	}
	secrets, err := devicekey.Load(c.secrets)
	if err != nil {
		log.Fatalf("cannot read %s: %v (start the webhook with RECEIVER=1 first)", c.secrets, err)
	}
	cert := &certificate{certFile: c.cert, keyFile: c.key, every: 10 * time.Second}
	if _, err := cert.get(nil); err != nil {
		log.Fatalf("cannot read the certificate: %v", err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	r := ingest.New(c.webhook, secrets, c.every)
	// the policy first, then the books a page at a time; sends are answered "starting" until the policy is here
	// chính sách trước, rồi các sổ từng trang một; các lần gửi được trả "starting" cho tới khi có chính sách
	for {
		if err := r.RefreshPolicy(ctx); err == nil {
			break
		} else if ctx.Err() != nil {
			return
		} else {
			log.Printf("receiver: waiting for the webhook: %v", err)
			time.Sleep(2 * time.Second)
		}
	}
	// the table of people and the batches start at once, the books load a page at a time, then the policy is asked again (Start); a
	// computer whose book is not read yet is told to come back in 15 to 45 seconds
	// bảng người và các lô chạy ngay, các sổ nạp từng trang, rồi mới hỏi lại chính sách (Start); máy chưa có sổ được bảo quay lại sau
	// 15 tới 45 giây
	go r.Start(ctx)
	go func() {
		t := time.NewTicker(5 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				if err := secrets.Refresh(); err != nil {
					log.Printf("receiver: secrets: %v", err)
				}
			}
		}
	}()
	// the live feed of the boards, built once a second for every scope that is read
	// luồng số trực tiếp của các bảng, dựng mỗi giây một lần cho mọi phạm vi đang được đọc
	live := feed.New(r, secrets)
	go live.Run(ctx.Done())
	ln, err := listen(c.listen, 10*time.Second)
	if err != nil {
		log.Fatal(err)
	}
	capped := &capListener{Listener: ln, max: lim.connections}
	r.Pace = func() int64 { return pace(capped.open.Load(), lim.sends) }
	srv := newServer(c, refuseOver(capped, handler(r, live)), cert)
	srv.ConnContext = connContext
	srv.RegisterOnShutdown(live.Close)
	// the refusals of a minute, said once a minute at most
	// các lần từ chối trong một phút, báo nhiều nhất mỗi phút một lần
	go func() {
		t := time.NewTicker(time.Minute)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				if n := capped.refused.Swap(0); n > 0 {
					log.Printf("receiver: %d sends refused in the last minute: %d connections open, the ceiling is %d", n, capped.open.Load(), capped.max)
				}
			}
		}
	}()
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	log.Printf("receiver: listening on %s (boot %s), Python at %s; %s", c.listen, r.Boot, c.webhook, lim)
	if err := srv.ServeTLS(capped, "", ""); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
	// what Python has not taken yet goes now, once
	// những gì Python chưa nhận được gửi đi ngay bây giờ, một lần
	flush, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	for {
		if n, err := r.Flush(flush); err != nil || n == 0 {
			break
		}
	}
}

// listen opens the port, trying again for up to wait while it is still held: after a kill -9 the old process may keep it for a
// moment, and a start that gave up at once had to be started again.
// listen mở cổng, thử lại tối đa wait khi cổng vẫn bị giữ: sau kill -9 tiến trình cũ có thể còn giữ nó một lúc, và một lần khởi động
// bỏ cuộc ngay thì phải được bật lại.
func listen(addr string, wait time.Duration) (net.Listener, error) {
	until := time.Now().Add(wait)
	for {
		ln, err := net.Listen("tcp", addr)
		if err == nil || !errors.Is(err, syscall.EADDRINUSE) || time.Now().After(until) {
			return ln, err
		}
		time.Sleep(200 * time.Millisecond)
	}
}
