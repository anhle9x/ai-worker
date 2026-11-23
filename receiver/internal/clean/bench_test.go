package clean

import (
	"fmt"
	"testing"
	"time"

	"aiworker/receiver/internal/pyjson"
)

// a send as the load test's computers make it (do-buoc-8/gen): the state and the hour of now, plus a whole 8-day book for the full form
// một lần gửi như các máy của bài đo tải tạo (do-buoc-8/gen): trạng thái và giờ hiện tại, thêm cả sổ 8 ngày cho dạng đủ
func sendOf(hours int) []byte {
	now := time.Now()
	h := now.Unix() / 3600
	led := ""
	for i := 0; i < hours; i++ {
		if i > 0 {
			led += ","
		}
		led += fmt.Sprintf(`"%d":{"usdMicro":%d,"input":%d,"output":%d,"cacheRead":0,"cacheWrite":0}`, h-int64(i), 20000+i, 2000+i, 400+i)
	}
	return []byte(fmt.Sprintf(`{"v":2,"device":"device-load000042","updatedAt":%d,"openSessions":2,"working":1,"waiting":0,"delegating":{},`+
		`"subagents":{},"models":{"claude-opus-5-5":3},"assistants":{"chatgpt":true,"gemini":true,"gemma":""},"pluginVersion":"0.50.0",`+
		`"lanIp":"10.0.0.42","quota":{"readAt":%d,"windows":[{"kind":"five_hour","pct":42,"resetsAt":%d}]},"full":false,`+
		`"hours":{"ledger":{%s},"tasks":{},"blocks":{}},"delegations":[]}`, now.UnixMilli(), now.UnixMilli(), now.Add(2*time.Hour).UnixMilli(), led))
}

// BenchmarkSend: what one usual send costs the receiver before it is queued: parse, then clean.
// BenchmarkSend: chi phí của một lần gửi thường ở bộ nhận trước khi xếp hàng: đọc, rồi làm sạch.
func BenchmarkSend(b *testing.B) {
	for _, n := range []int{1, 192} {
		body := sendOf(n)
		b.Run(fmt.Sprintf("hours=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			now := float64(time.Now().Unix())
			for i := 0; i < b.N; i++ {
				v, err := pyjson.Parse(body)
				if err != nil {
					b.Fatal(err)
				}
				if Payload(v, now) == nil {
					b.Fatal("not a report")
				}
			}
		})
	}
}
