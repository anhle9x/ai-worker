package main

import (
	"bufio"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"io"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"aiworker/receiver/internal/feed"
	"aiworker/receiver/internal/live"
)

func TestSettingsMustBeSaid(t *testing.T) {
	base := map[string]string{"RECEIVER_LISTEN": "203.0.113.2:443", "RECEIVER_TLS_CERT": "c.pem", "RECEIVER_TLS_KEY": "k.pem", "RECEIVER_SECRETS_FILE": "s.json"}
	env := func(over map[string]string) func(string) string {
		return func(k string) string {
			if v, ok := over[k]; ok {
				return v
			}
			return base[k]
		}
	}
	c, err := readConfig(env(nil))
	if err != nil || c.webhook != "http://127.0.0.1:8788" || c.every != time.Second {
		t.Fatalf("%+v %v", c, err)
	}
	for _, bad := range []map[string]string{
		{"RECEIVER_LISTEN": ""}, {"RECEIVER_LISTEN": ":443"}, {"RECEIVER_LISTEN": "203.0.113.2"}, {"RECEIVER_TLS_CERT": ""}, {"RECEIVER_TLS_KEY": ""},
		{"RECEIVER_SECRETS_FILE": ""}, {"RECEIVER_WEBHOOK": "http://198.51.100.1:8788"}, {"RECEIVER_WEBHOOK": "https://127.0.0.1:8788"},
		{"RECEIVER_BATCH_MS": "5"}, {"RECEIVER_BATCH_MS": "x"},
	} {
		if _, err := readConfig(env(bad)); err == nil {
			t.Errorf("accepted %v", bad)
		}
	}
	if c, err := readConfig(env(map[string]string{"RECEIVER_BATCH_MS": "5000"})); err != nil || c.every != 5*time.Second {
		t.Errorf("batch: %+v %v", c, err)
	}
}

func writeCert(t *testing.T, dir, name string) {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: name}, DNSNames: []string{name},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour)}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	kb, _ := x509.MarshalECPrivateKey(key)
	_ = os.WriteFile(filepath.Join(dir, "cert.pem"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600)
	_ = os.WriteFile(filepath.Join(dir, "key.pem"), pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kb}), 0o600)
}

// TestTLSOnlyHTTP1AndReload: the server speaks HTTP/1.1 only, even to a client that asks for HTTP/2, and serves a renewed certificate
// without a restart.
// TestTLSOnlyHTTP1AndReload: máy chủ chỉ nói HTTP/1.1, kể cả với máy khách xin HTTP/2, và dùng chứng chỉ đã gia hạn mà không cần khởi động lại.
func TestTLSOnlyHTTP1AndReload(t *testing.T) {
	dir := t.TempDir()
	writeCert(t, dir, "ingest.example.com")
	cert := &certificate{certFile: filepath.Join(dir, "cert.pem"), keyFile: filepath.Join(dir, "key.pem")}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := newServer(config{listen: l.Addr().String()}, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = io.WriteString(w, r.Proto) }), cert)
	go func() { _ = srv.ServeTLS(l, "", "") }()
	defer srv.Close()
	ask := func() (string, string) {
		tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true, NextProtos: []string{"h2", "http/1.1"}}, ForceAttemptHTTP2: true, DisableKeepAlives: true}
		resp, err := (&http.Client{Transport: tr}).Get("https://" + l.Addr().String() + "/")
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		b, _ := io.ReadAll(resp.Body)
		return string(b), resp.TLS.PeerCertificates[0].Subject.CommonName
	}
	proto, name := ask()
	if proto != "HTTP/1.1" || name != "ingest.example.com" {
		t.Fatalf("%s %s", proto, name)
	}
	time.Sleep(20 * time.Millisecond)
	writeCert(t, dir, "renewed.example.com")
	if _, name := ask(); name != "renewed.example.com" {
		t.Fatalf("still %s", name)
	}
	// a half-written renewal keeps the certificate in use
	// lần gia hạn ghi dở thì giữ chứng chỉ đang dùng
	_ = os.WriteFile(filepath.Join(dir, "key.pem"), []byte("broken"), 0o600)
	if _, name := ask(); name != "renewed.example.com" {
		t.Fatalf("now %s", name)
	}
	if srv.ReadHeaderTimeout == 0 || !strings.Contains(srv.TLSConfig.NextProtos[0], "http/1.1") {
		t.Fatal("timeouts or protocols not set")
	}
}

type liveSource struct{}

func (liveSource) Rows(float64) []live.Row {
	return []live.Row{{Row: "r1", Branch: "a", Status: live.Open}}
}
func (liveSource) LivePolicy() ([]string, map[string]bool, bool) {
	return []string{"https://aiworker.example.com"}, map[string]bool{}, true
}

type liveKeys []byte

func (k liveKeys) TicketSecret(kid string) ([]byte, bool) { return k, kid == "k1" }

// TestTheFeedOutlivesTheServersTimeouts: a feed stays open past the ReadTimeout and WriteTimeout a send gets, through the receiver's own
// TLS server, and a send is still answered beside it. The timeouts are made 1 second here; RECEIVER_FEED_LONG=1 keeps the real 30 seconds
// and holds the feed 35.
// TestTheFeedOutlivesTheServersTimeouts: một luồng vẫn mở quá ReadTimeout và WriteTimeout mà một lần gửi có, qua chính máy chủ TLS của
// bộ nhận, và một lần gửi vẫn được trả lời bên cạnh. Ở đây các hạn đặt 1 giây; RECEIVER_FEED_LONG=1 giữ đúng 30 giây và giữ luồng 35 giây.
func TestTheFeedOutlivesTheServersTimeouts(t *testing.T) {
	hold := 3500 * time.Millisecond
	if os.Getenv("RECEIVER_FEED_LONG") == "1" {
		hold = 35 * time.Second
	} else {
		saved := sendTimeout
		sendTimeout = time.Second
		defer func() { sendTimeout = saved }()
	}
	dir := t.TempDir()
	writeCert(t, dir, "ingest.example.com")
	cert := &certificate{certFile: filepath.Join(dir, "cert.pem"), keyFile: filepath.Join(dir, "key.pem")}
	secret := []byte("a secret of the tests, 32 bytes!")
	f := feed.New(liveSource{}, liveKeys(secret))
	f.Beat, f.Tick = 200*time.Millisecond, 100*time.Millisecond
	stop := make(chan struct{})
	defer close(stop)
	go f.Run(stop)
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	sends := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = io.WriteString(w, "sent") })
	srv := newServer(config{listen: l.Addr().String()}, handler(sends, f), cert)
	srv.RegisterOnShutdown(f.Close)
	go func() { _ = srv.ServeTLS(l, "", "") }()
	defer srv.Close()
	client := &http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}}
	body := "awt1.k1.wall." + base64.RawURLEncoding.EncodeToString([]byte("branch:a")) + ".sid-1." + strconv.FormatInt(time.Now().Unix()+300, 10)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(body))
	req, _ := http.NewRequest(http.MethodGet, "https://"+l.Addr().String()+"/live?scope=branch:a&t="+body+"."+base64.RawURLEncoding.EncodeToString(mac.Sum(nil)), nil)
	req.Header.Set("Origin", "https://aiworker.example.com")
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 {
		t.Fatalf("%v %v", resp, err)
	}
	defer resp.Body.Close()
	r := bufio.NewReader(resp.Body)
	opened, beats := time.Now(), 0
	for time.Since(opened) < hold {
		line, err := r.ReadString('\n')
		if err != nil {
			t.Fatalf("the feed was cut after %s: %v", time.Since(opened).Round(time.Millisecond), err)
		}
		if line == ": beat\n" {
			beats++
		}
	}
	if beats < 5 {
		t.Fatalf("%d beats in %s", beats, hold)
	}
	if resp, err := client.Get("https://" + l.Addr().String() + "/ingest"); err != nil {
		t.Fatal(err)
	} else if b, _ := io.ReadAll(resp.Body); string(b) != "sent" {
		t.Fatalf("a send beside the feed: %q", b)
	}
	// the receiver stopping ends the feed at once instead of waiting for it
	// bộ nhận dừng thì kết thúc luồng ngay thay vì chờ nó
	done := make(chan error, 1)
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		done <- srv.Shutdown(ctx)
	}()
	if err := <-done; err != nil {
		t.Fatalf("shutdown: %v", err)
	}
}

// TestListenWaitsForThePort: a port still held is tried again until it is free, and given up after the wait.
// TestListenWaitsForThePort: cổng còn bị giữ được thử lại tới khi trống, và bỏ cuộc sau thời gian chờ.
func TestListenWaitsForThePort(t *testing.T) {
	held, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	addr := held.Addr().String()
	if _, err := listen(addr, 300*time.Millisecond); !errors.Is(err, syscall.EADDRINUSE) {
		t.Fatalf("held all along: %v", err)
	}
	time.AfterFunc(500*time.Millisecond, func() { held.Close() })
	ln, err := listen(addr, 5*time.Second)
	if err != nil {
		t.Fatalf("freed after half a second: %v", err)
	}
	ln.Close()
}
