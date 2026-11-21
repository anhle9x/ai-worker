// Package devicekey checks a computer's own key (awd1.…) as DeviceKeys.check in server/board/devicekeys.py does, with the signing secrets
// of the file the Python server writes (board/receiver.py). The file is read again when it changes and when a key names an unknown kid.
// Package devicekey kiểm khoá riêng của một máy (awd1.…) như DeviceKeys.check trong server/board/devicekeys.py, bằng các bí mật ký trong
// file máy chủ Python ghi (board/receiver.py). File được đọc lại khi nó đổi và khi một khoá nêu kid chưa biết.
package devicekey

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// The same numbers as server/board/devicekeys.py.
// Cùng các con số như server/board/devicekeys.py.
const (
	Prefix         = "awd1"
	KeyDays        = 90
	RenewAfterDays = 30
	// rereadGap: an unknown kid reads the file again at most this often, so made-up kids cannot keep the disk busy
	// rereadGap: kid lạ làm đọc lại file nhiều nhất chừng này một lần, để kid bịa không làm đĩa bận mãi
	rereadGap = 10 * time.Second
)

// Claims are the fields of a good key.
// Claims là các trường của một khoá tốt.
type Claims struct {
	Kid, Pid, Rk, Device string
	Iat                  int64
}

type entry struct {
	Kid    string `json:"kid"`
	Alg    string `json:"alg"`
	Org    string `json:"org"`
	Secret string `json:"secret"`
}

// Secrets holds the file of secrets: the signing secrets with their org, and the internal code for this machine's internal paths.
// Secrets giữ file bí mật: các bí mật ký kèm mã tổ chức, và mã nội bộ cho các đường nội bộ của máy này.
type Secrets struct {
	path     string
	mu       sync.Mutex
	modTime  time.Time
	size     int64
	readAt   time.Time
	signing  map[string][]byte
	org      string
	internal string
	// ticket: the secret of the tickets of the board's live feed, a secret of its own (package feed); none in a file of an older server
	// ticket: bí mật của vé luồng số trực tiếp của bảng, một bí mật riêng (gói feed); không có trong file của máy chủ đời cũ
	ticketKid string
	ticket    []byte
}

// Load reads the file once; a file that cannot be read or holds no signing secret is an error.
// Load đọc file một lần; file không đọc được hoặc không có bí mật ký nào là lỗi.
func Load(path string) (*Secrets, error) {
	s := &Secrets{path: path}
	if err := s.read(); err != nil {
		return nil, err
	}
	return s, nil
}

func decode(s string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(strings.TrimRight(s, "="))
}

func (s *Secrets) read() error {
	info, err := os.Stat(s.path)
	if err != nil {
		return err
	}
	b, err := os.ReadFile(s.path)
	if err != nil {
		return err
	}
	var entries []entry
	if err := json.Unmarshal(b, &entries); err != nil {
		return err
	}
	signing, org, internal, ticketKid, ticket := map[string][]byte{}, "", "", "", []byte(nil)
	for _, e := range entries {
		switch e.Alg {
		case "HS256":
			secret, err := decode(e.Secret)
			if err != nil || len(secret) < 16 {
				return errors.New("devicekey: a signing secret is not readable")
			}
			signing[e.Kid] = secret
			org = e.Org
		case "internal":
			internal = e.Secret
		case "ticket":
			secret, err := decode(e.Secret)
			if err != nil || len(secret) < 16 {
				return errors.New("devicekey: the tickets' secret is not readable")
			}
			ticketKid, ticket = e.Kid, secret
		}
	}
	if len(signing) == 0 || internal == "" {
		return errors.New("devicekey: no signing secret or no internal code in " + s.path)
	}
	s.signing, s.org, s.internal, s.modTime, s.size, s.readAt = signing, org, internal, info.ModTime(), info.Size(), time.Now()
	s.ticketKid, s.ticket = ticketKid, ticket
	return nil
}

// Refresh reads the file again if it changed on disk; a broken new file keeps the secrets already held.
// Refresh đọc lại file nếu nó đổi trên đĩa; file mới bị hỏng thì giữ các bí mật đang có.
func (s *Secrets) Refresh() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	info, err := os.Stat(s.path)
	if err != nil {
		return err
	}
	if info.ModTime().Equal(s.modTime) && info.Size() == s.size {
		return nil
	}
	return s.read()
}

// Internal is the code this receiver shows on the Python server's internal paths.
// Internal là mã bộ nhận này trình ở các đường nội bộ của máy chủ Python.
func (s *Secrets) Internal() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.internal
}

// TicketSecret gives the secret of the tickets of the live feed when kid names it; a kid not known reads the file again, at most every
// 10 seconds, since Python may have turned it.
// TicketSecret trả bí mật của vé luồng số trực tiếp khi kid nêu đúng nó; kid chưa biết làm đọc lại file, nhiều nhất 10 giây một lần, vì
// có thể Python vừa xoay nó.
func (s *Secrets) TicketSecret(kid string) ([]byte, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if kid != s.ticketKid && time.Since(s.readAt) > rereadGap {
		if s.read() != nil {
			s.readAt = time.Now()
		}
	}
	if s.ticket == nil || kid != s.ticketKid {
		return nil, false
	}
	return s.ticket, true
}

func validPart(p string) bool {
	if len(p) < 1 || len(p) > 64 {
		return false
	}
	for i := 0; i < len(p); i++ {
		c := p[i]
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-') {
			return false
		}
	}
	return true
}

func validDevice(p string) bool {
	if len(p) < 8 || len(p) > 47 || p[:7] != "device-" {
		return false
	}
	for i := 7; i < len(p); i++ {
		if c := p[i]; !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9') {
			return false
		}
	}
	return true
}

// Check gives the key's fields when it is well formed, signed by a known secret, not too old and not in revoked; otherwise the reason, in
// the same words as Python. now is in seconds.
// Check trả các trường của khoá khi nó đúng dạng, được ký bằng một bí mật đã biết, chưa quá hạn và không nằm trong revoked; nếu không
// thì trả lý do, cùng chữ như Python. now tính bằng giây.
func (s *Secrets) Check(token string, now float64, revoked func(string) bool) (*Claims, string) {
	parts := strings.Split(token, ".")
	if len(parts) != 8 || parts[0] != Prefix || !validDevice(parts[5]) {
		return nil, "not a device key"
	}
	for _, p := range parts[1:] {
		if !validPart(p) {
			return nil, "not a device key"
		}
	}
	s.mu.Lock()
	secret, ok := s.signing[parts[1]]
	if !ok && time.Since(s.readAt) > rereadGap {
		// a kid made after this file was read: Python may have turned the secret since
		// kid tạo sau khi file này được đọc: có thể Python vừa xoay bí mật
		if s.read() == nil {
			secret, ok = s.signing[parts[1]]
		} else {
			s.readAt = time.Now()
		}
	}
	org := s.org
	s.mu.Unlock()
	if !ok || parts[2] != org {
		return nil, "unknown signing key"
	}
	body := strings.Join(parts[:7], ".")
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(body))
	if !hmac.Equal([]byte(parts[7]), []byte(base64.RawURLEncoding.EncodeToString(mac.Sum(nil)))) {
		return nil, "bad signature"
	}
	iat := int64(-1)
	if n, err := strconv.ParseInt(parts[6], 10, 64); err == nil && strings.Trim(parts[6], "0123456789") == "" {
		iat = n
	} else if strings.Trim(parts[6], "0123456789") == "" {
		// digits too many for 64 bits: a time far in the future
		// quá nhiều chữ số cho 64 bit: một lúc rất xa ở tương lai
		iat = 1 << 62
	}
	if iat < 0 || float64(iat) > now+300 || now-float64(iat) > KeyDays*86400 {
		return nil, "device key expired"
	}
	if revoked != nil && revoked(parts[5]) {
		return nil, "device revoked"
	}
	return &Claims{Kid: parts[1], Pid: parts[3], Rk: parts[4], Device: parts[5], Iat: iat}, ""
}

// NeedsRenewal is needs_renewal: a key older than RenewAfterDays, or issued before the moment the policy names, gets a new one from Python.
// NeedsRenewal là needs_renewal: khoá cũ hơn RenewAfterDays, hoặc cấp trước mốc chính sách nêu, được Python cấp khoá mới.
func NeedsRenewal(c *Claims, now float64, renewBefore int64) bool {
	return now-float64(c.Iat) > RenewAfterDays*86400 || c.Iat < renewBefore
}
