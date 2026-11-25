package main

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"math"
	"net"
	"net/http"
	"runtime/metrics"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"

	"aiworker/receiver/internal/ingest"
)

// The receiver's own ceilings, so that too many computers make it refuse some of them instead of running the machine out of memory and
// being killed by the kernel, again and again as every computer connects at once after each start.
// Các trần của bộ nhận, để khi có quá nhiều máy thì nó từ chối bớt thay vì làm máy hết bộ nhớ rồi bị nhân giết, lặp đi lặp lại khi mọi
// máy kết nối lại cùng lúc sau mỗi lần khởi động.
//
//	RECEIVER_MEMORY_MB       memory Go aims to stay under (debug.SetMemoryLimit); default 40% of the machine's memory, 0 for none.
//	                         A GOMEMLIMIT already set wins.
//	                         bộ nhớ Go cố giữ dưới mức này (debug.SetMemoryLimit); mặc định 40% bộ nhớ của máy, 0 là không giới hạn.
//	                         GOMEMLIMIT đã đặt thì dùng nó.
//	RECEIVER_SENDS_PER_SECOND sends the machine is to answer each second; past it the computers are told to send less often, through
//	                         the minGapMs of the answer: the connections open over this, in whole seconds, at most 120. Default 2,500
//	                         a processor; 0 to keep the server's gap.
//	                         số lần gửi máy cần trả lời mỗi giây; quá mức này các máy được dặn gửi thưa hơn, qua minGapMs của câu trả
//	                         lời: số kết nối đang mở chia cho số này, làm tròn lên giây, nhiều nhất 120. Mặc định 2.500 mỗi bộ xử lý; 0
//	                         để giữ nhịp của máy chủ.
//	RECEIVER_MAX_CONNECTIONS connections kept at once; past it a send is answered 503 with Retry-After and the connection closed. Default:
//	                         the memory limit over 64 KiB a connection; 0 for no ceiling.
//	                         số kết nối giữ cùng lúc; quá mức này lần gửi được trả 503 kèm Retry-After và kết nối bị đóng. Mặc định: giới
//	                         hạn bộ nhớ chia 64 KiB mỗi kết nối; 0 là không có trần.

// connectionBytes: what one kept connection costs, measured with 40,000 computers on Linux (docs/RECEIVER.md, section 7): about 28 KiB live heap,
// 11 KiB of stack, and the garbage between two collections
// connectionBytes: chi phí của một kết nối được giữ, đo với 40.000 máy trên Linux (docs/RECEIVER.vi.md, mục 7): khoảng 28 KiB heap đang dùng,
// 11 KiB ngăn xếp, và phần rác giữa hai lần dọn
const connectionBytes = 64 << 10

// memoryShare: the part of the machine's memory the receiver takes by default; the Python server beside it needs about 3 GB at 100,000
// computers
// memoryShare: phần bộ nhớ của máy bộ nhận lấy theo mặc định; máy chủ Python bên cạnh cần khoảng 3 GB ở 100.000 máy
const memoryShare = 0.40

// sendsPerCPU: what one processor answers each second with the Python server beside it, measured on Linux (docs/RECEIVER.md, section
// 7): 40,000 computers sending every 2 seconds, 20,000 sends a second, filled 4 processors
// sendsPerCPU: số lần gửi một bộ xử lý trả lời mỗi giây khi có máy chủ Python bên cạnh, đo trên Linux (docs/RECEIVER.vi.md, mục 7):
// 40.000 máy gửi mỗi 2 giây, 20.000 lần gửi mỗi giây, làm đầy 4 bộ xử lý
const sendsPerCPU = 2500

// maxPaceMs: the longest gap asked, the most INGEST_MIN_GAP_MS allows
// maxPaceMs: khoảng cách dài nhất được dặn, mức INGEST_MIN_GAP_MS cho phép cao nhất
const maxPaceMs = 120_000

// readingShare and holdingShare: the parts of the memory limit for the bodies being read and cleaned and for the rows waiting for
// Python (ingest.Budget); past either a send is answered busy. usedHigh and usedLow: past usedHigh of the limit in memory the process
// still uses (usedBytes), every new send is refused until it is back under usedLow, since the limit given to Go is only a target its
// collector aims at (a v: 1 book of 8 days per send ran it to 4.5 GB over a limit of 3.1 GB, docs/RECEIVER.md, section 7). The resident
// memory is not what is counted: the collector lets garbage grow up to the limit by design, so at 40,000 computers it sat at 80-95% of
// the limit with about 60% in use by the cost of a connection above, and refusing on it kept the receiver refusing after a restart.
// readingShare và holdingShare: các phần của giới hạn bộ nhớ cho các thân đang đọc và làm sạch và cho các dòng chờ Python
// (ingest.Budget); quá một trong hai thì lần gửi được trả bận. usedHigh và usedLow: quá usedHigh của giới hạn về bộ nhớ tiến trình
// còn dùng (usedBytes) thì mọi lần gửi mới bị từ chối cho tới khi về dưới usedLow, vì giới hạn trao cho Go chỉ là mức bộ dọn rác của
// nó nhắm tới (sổ v: 1 8 ngày mỗi lần gửi đã đẩy nó lên 4,5 GB trên giới hạn 3,1 GB, docs/RECEIVER.vi.md, mục 7). Không tính bộ nhớ
// thường trú: bộ dọn rác cố ý để rác lên tới giới hạn, nên ở 40.000 máy nó nằm ở 80-95% giới hạn trong khi theo chi phí một kết nối ở trên chỉ khoảng 60% còn dùng,
// và từ chối theo nó làm bộ nhận cứ từ chối mãi sau một lần khởi động lại.
const (
	readingShare = 0.25
	holdingShare = 0.35
	usedHigh     = 0.80
	usedLow      = 0.70
)

// budgets are the two budgets of a memory limit, none without one.
// budgets là hai ngân sách của một giới hạn bộ nhớ, không có khi không có giới hạn.
func budgets(memory int64) (reading, holding *ingest.Budget) {
	if memory <= 0 || memory == math.MaxInt64 {
		return nil, nil
	}
	return ingest.NewBudget(int64(float64(memory) * readingShare)), ingest.NewBudget(int64(float64(memory) * holdingShare))
}

// overloaded says, from the memory the process still uses and whether it was over already, whether it is over now: on past usedHigh of
// the limit, off again only under usedLow.
// overloaded cho biết, từ bộ nhớ tiến trình còn dùng và việc nó đã quá chưa, giờ nó có đang quá không: bật khi quá usedHigh của giới
// hạn, chỉ tắt lại khi dưới usedLow.
func overloaded(used, memory int64, was bool) bool {
	if memory <= 0 || memory == math.MaxInt64 || used <= 0 {
		return false
	}
	if was {
		return float64(used) > float64(memory)*usedLow
	}
	return float64(used) > float64(memory)*usedHigh
}

// usedBytes is the memory the process still uses, from runtime/metrics: the heap found live by the last collection and the goroutines'
// stacks, without the garbage not yet collected and the memory not yet given back.
// usedBytes là bộ nhớ tiến trình còn dùng, lấy từ runtime/metrics: phần heap lần dọn gần nhất thấy còn sống và ngăn xếp của các
// goroutine, không tính rác chưa dọn và bộ nhớ chưa trả lại.
func usedBytes() int64 {
	s := []metrics.Sample{{Name: "/gc/heap/live:bytes"}, {Name: "/memory/classes/heap/stacks:bytes"}}
	metrics.Read(s)
	var n int64
	for _, x := range s {
		if x.Value.Kind() == metrics.KindUint64 {
			n += int64(x.Value.Uint64())
		}
	}
	return n
}

type limits struct {
	// sends: the sends a second the machine is to answer, 0 for no pacing
	// sends: số lần gửi mỗi giây máy cần trả lời, 0 là không giãn nhịp
	sends int64
	// memory: bytes to hand to debug.SetMemoryLimit, 0 to leave the runtime as it is
	// memory: số byte trao cho debug.SetMemoryLimit, 0 để giữ nguyên runtime
	memory int64
	// connections: the ceiling, 0 for none
	// connections: trần, 0 là không có
	connections int64
	// from: where the memory limit comes from, for the log
	// from: giới hạn bộ nhớ lấy từ đâu, để ghi nhật ký
	from string
}

// memTotal reads MemTotal of /proc/meminfo, in bytes; 0 when it is not there (not Linux).
// memTotal đọc MemTotal của /proc/meminfo, theo byte; 0 khi không có (không phải Linux).
func memTotal(meminfo string) int64 {
	for _, line := range strings.Split(meminfo, "\n") {
		f := strings.Fields(line)
		if len(f) >= 3 && f[0] == "MemTotal:" && f[2] == "kB" {
			if kb, err := strconv.ParseInt(f[1], 10, 64); err == nil && kb > 0 {
				return kb << 10
			}
		}
	}
	return 0
}

// readLimits: env gives the settings, meminfo the text of /proc/meminfo ("" if none), runtimeLimit the limit already in the runtime
// (math.MaxInt64 when GOMEMLIMIT is not set).
// readLimits: env cho cấu hình, meminfo là nội dung /proc/meminfo ("" nếu không có), runtimeLimit là giới hạn runtime đang có
// (math.MaxInt64 khi chưa đặt GOMEMLIMIT).
func readLimits(env func(string) string, meminfo string, runtimeLimit int64, cpus int) (limits, error) {
	var l limits
	switch v := env("RECEIVER_SENDS_PER_SECOND"); v {
	case "":
		l.sends = int64(cpus) * sendsPerCPU
	case "0":
	default:
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 100 || n > 10_000_000 {
			return l, errors.New("RECEIVER_SENDS_PER_SECOND must be 0, or from 100 to 10000000")
		}
		l.sends = n
	}
	switch v := env("RECEIVER_MEMORY_MB"); {
	case v == "" && runtimeLimit != math.MaxInt64:
		// GOMEMLIMIT is the runtime's own setting: it stays, and the ceiling of connections follows it
		// GOMEMLIMIT là cấu hình của chính runtime: giữ nguyên, và trần kết nối theo nó
		l.from = "GOMEMLIMIT"
		return withConnections(env, l, runtimeLimit)
	case v == "":
		if total := memTotal(meminfo); total > 0 {
			l.memory, l.from = int64(float64(total)*memoryShare), "40% of the machine"
		}
	case v == "0":
		l.from = "none"
	default:
		mb, err := strconv.ParseInt(v, 10, 64)
		if err != nil || mb < 256 || mb > 1<<20 {
			return l, errors.New("RECEIVER_MEMORY_MB must be 0, or from 256 to 1048576")
		}
		l.memory, l.from = mb<<20, "RECEIVER_MEMORY_MB"
	}
	return withConnections(env, l, l.memory)
}

func withConnections(env func(string) string, l limits, memory int64) (limits, error) {
	switch v := env("RECEIVER_MAX_CONNECTIONS"); v {
	case "":
		if memory > 0 && memory != math.MaxInt64 {
			l.connections = memory / connectionBytes
		}
	case "0":
	default:
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 100 || n > 10_000_000 {
			return l, errors.New("RECEIVER_MAX_CONNECTIONS must be 0, or from 100 to 10000000")
		}
		l.connections = n
	}
	return l, nil
}

// pace is the gap in milliseconds the computers are asked to keep when open connections are open: each sends once in that many
// milliseconds so that together they stay within sends a second, rounded up to whole seconds; 0 while two seconds are enough.
// pace là khoảng cách theo mili giây các máy được dặn giữ khi đang có open kết nối: mỗi máy gửi một lần trong chừng ấy mili giây để cộng
// lại vẫn trong sends lần mỗi giây, làm tròn lên giây; 0 khi hai giây là đủ.
func pace(open, sends int64) int64 {
	if sends <= 0 || open <= 0 {
		return 0
	}
	ms := (open*1000 + sends - 1) / sends
	ms = (ms + 999) / 1000 * 1000
	if ms <= 2000 {
		return 0
	}
	return min(ms, maxPaceMs)
}

func (l limits) String() string {
	mem, conns := "no memory limit", "no ceiling of connections"
	if l.memory > 0 {
		mem = fmt.Sprintf("memory limit %d MB (%s)", l.memory>>20, l.from)
	} else if l.from == "GOMEMLIMIT" {
		mem = "memory limit from GOMEMLIMIT"
	}
	if l.connections > 0 {
		conns = fmt.Sprintf("at most %d connections", l.connections)
	}
	sends := "the server's gap between sends"
	if l.sends > 0 {
		sends = fmt.Sprintf("a longer gap between sends past %d a second", l.sends)
	}
	return mem + ", " + conns + ", " + sends
}

// capListener counts the connections it gave and marks those past the ceiling; they still get their TLS handshake, so a send on them can
// be told to come back later in words the plugin understands, then they are closed.
// capListener đếm các kết nối nó đã trao và đánh dấu những kết nối quá trần; chúng vẫn được bắt tay TLS, để lần gửi trên đó được bảo quay
// lại sau bằng câu trả lời plugin hiểu, rồi bị đóng.
type capListener struct {
	net.Listener
	max     int64
	open    atomic.Int64
	refused atomic.Int64
}

func (l *capListener) Accept() (net.Conn, error) {
	c, err := l.Listener.Accept()
	if err != nil {
		return nil, err
	}
	n := l.open.Add(1)
	return &countedConn{Conn: c, l: l, over: l.max > 0 && n > l.max}, nil
}

type countedConn struct {
	net.Conn
	l    *capListener
	over bool
	once sync.Once
}

func (c *countedConn) Close() error {
	c.once.Do(func() { c.l.open.Add(-1) })
	return c.Conn.Close()
}

type overKey struct{}

// connContext marks the requests of a connection past the ceiling (http.Server.ConnContext).
// connContext đánh dấu các yêu cầu của một kết nối quá trần (http.Server.ConnContext).
func connContext(ctx context.Context, c net.Conn) context.Context {
	if tc, ok := c.(*tls.Conn); ok {
		c = tc.NetConn()
	}
	if cc, ok := c.(*countedConn); ok && cc.over {
		return context.WithValue(ctx, overKey{}, true)
	}
	return ctx
}

// refuseOver answers a send on a connection past the ceiling: 503, come back in 30 to 90 seconds (spread, so the refused do not all come
// back at once), and the connection closed. The live feed of the boards has its own ceiling and is let through, and so is /health: an
// overload is when the administrator needs to read it.
// refuseOver trả lời một lần gửi trên kết nối quá trần: 503, quay lại sau 30 tới 90 giây (rải ra, để các máy bị từ chối không quay lại
// cùng lúc), và đóng kết nối. Luồng số trực tiếp của các bảng có trần riêng nên được cho qua, và /health cũng vậy: lúc quá tải chính là
// lúc người quản trị cần đọc nó.
func refuseOver(l *capListener, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		passes := r.URL.Path == "/health" || r.URL.Path == "/live" || strings.HasPrefix(r.URL.Path, "/live/")
		if over, _ := r.Context().Value(overKey{}).(bool); over && !passes {
			l.refused.Add(1)
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Retry-After", ingest.RetryAfter(30, 90))
			w.Header().Set("Connection", "close")
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"error":"busy"}`))
			return
		}
		next.ServeHTTP(w, r)
	})
}
