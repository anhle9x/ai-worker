// Package feed is the board's live feed: GET /live (server-sent events) and GET /live/snap (the same numbers once, as JSON), opened
// with a ticket the Python server gives a logged-in board (POST /sse/ticket, server/board/receiver.py Tickets). The numbers of each scope
// are built once a beat for every board that reads it, and a board that reads slowly never holds a queue (docs/RECEIVER.md, section 3).
// Package feed là luồng số trực tiếp của bảng: GET /live (sự kiện máy chủ gửi) và GET /live/snap (cùng các con số một lần, dạng JSON),
// mở bằng vé máy chủ Python cấp cho một bảng đã đăng nhập (POST /sse/ticket, Tickets trong server/board/receiver.py). Số của mỗi phạm vi
// được dựng một lần mỗi nhịp cho mọi bảng đang đọc nó, và bảng đọc chậm không bao giờ giữ một hàng chờ (docs/RECEIVER.vi.md, mục 3).
package feed

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	// TicketPrefix and TicketSeconds are the ones of server/board/receiver.py and settings.TICKET_SECONDS
	// TicketPrefix và TicketSeconds là của server/board/receiver.py và settings.TICKET_SECONDS
	TicketPrefix  = "awt1"
	TicketSeconds = 300
	// a ticket that ends later than this is not one Python makes
	// vé kết thúc muộn hơn mức này không phải vé Python làm
	ticketSlack = 60
	// scopeMax: the scope of a ticket, in base64, is at most this long (TICKET_SCOPE_MAX)
	// scopeMax: phạm vi của vé, dạng base64, dài nhiều nhất chừng này (TICKET_SCOPE_MAX)
	scopeMax = 200
)

// Keys gives the secret of the tickets for a kid (devicekey.Secrets.TicketSecret).
// Keys cho bí mật của vé ứng với một kid (devicekey.Secrets.TicketSecret).
type Keys interface {
	TicketSecret(kid string) ([]byte, bool)
}

// Ticket is what a good ticket says: the role, the scope ("org" or "branch:<id>"), the sid of the session it was given to, and when it ends.
// Ticket là điều một vé tốt nói: vai, phạm vi ("org" hay "branch:<mã>"), sid của phiên được cấp nó, và lúc nó hết hạn.
type Ticket struct {
	Kid, Role, Scope, SID string
	Expires               int64
}

func validPart(p string, most int) bool {
	if len(p) < 1 || len(p) > most {
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

// Check gives the ticket's fields when it is well formed, signed with the secret of its kid and not yet ended at now; otherwise why not.
// Check trả các trường của vé khi nó đúng dạng, được ký bằng bí mật của kid của nó và chưa hết hạn ở now; nếu không thì trả lý do.
func Check(token string, now time.Time, keys Keys) (*Ticket, string) {
	parts := strings.Split(token, ".")
	if len(parts) != 7 || parts[0] != TicketPrefix {
		return nil, "not a ticket"
	}
	for i, p := range parts[1:] {
		most := 64
		if i+1 == 3 {
			most = scopeMax
		}
		if !validPart(p, most) {
			return nil, "not a ticket"
		}
	}
	secret, ok := keys.TicketSecret(parts[1])
	if !ok {
		return nil, "unknown ticket key"
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(strings.Join(parts[:6], ".")))
	if !hmac.Equal([]byte(parts[6]), []byte(base64.RawURLEncoding.EncodeToString(mac.Sum(nil)))) {
		return nil, "bad signature"
	}
	expires, err := strconv.ParseInt(parts[5], 10, 64)
	if err != nil || strings.Trim(parts[5], "0123456789") != "" {
		return nil, "not a ticket"
	}
	if expires <= now.Unix() || expires > now.Unix()+TicketSeconds+ticketSlack {
		return nil, "ticket expired"
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[3])
	scope := string(raw)
	if err != nil || !utf8.Valid(raw) || (scope != "org" && !strings.HasPrefix(scope, "branch:")) {
		return nil, "not a ticket"
	}
	return &Ticket{Kid: parts[1], Role: parts[2], Scope: scope, SID: parts[4], Expires: expires}, ""
}
