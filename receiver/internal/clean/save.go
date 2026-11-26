package clean

import (
	"math"

	"aiworker/receiver/internal/pyjson"
)

// What Decide did with a send, the same words as save_ingest in server/board/devices.py.
// Decide đã làm gì với một lần gửi, cùng chữ như save_ingest trong server/board/devices.py.
const (
	Saved    = "saved"
	NeedFull = "need-full"
	Stale    = "stale"
)

// Decide copies the choices of save_ingest: a send of changed hours with no book here asks for the whole book; a v: 2 send stamped a little
// older than the book (StampOf: seq, else updatedAt) arrived out of order and is dropped; a whole book again within FullBookSeconds is
// merged hour by hour. kept is the computer's record ({device, updatedAt, seq?, ledger, tasks, blocks}) or nil; lastFull is when it last
// replaced its whole book, ok false if never. It returns what was done, the kind that was applied ("v1", "full" or "hours"), and the new
// record.
// Decide chép các lựa chọn của save_ingest: gói chỉ có các giờ đã đổi mà ở đây không có sổ thì xin cả sổ; gói v: 2 có thời điểm (StampOf:
// seq, không thì updatedAt) cũ hơn sổ một chút là tới sai thứ tự và bị bỏ; lại cả sổ trong vòng FullBookSeconds thì ghép từng giờ. kept là
// bản ghi của máy ({device, updatedAt, seq?, ledger, tasks, blocks}) hoặc nil; lastFull là lần cuối nó thay cả sổ, ok false nếu chưa bao
// giờ. Trả về việc đã làm, loại đã áp ("v1", "full" hoặc "hours"), và bản ghi mới.
func Decide(kept, d *pyjson.Object, now float64, kind string, lastFull float64, everFull bool) (string, string, *pyjson.Object) {
	if kind == "hours" && kept == nil {
		return NeedFull, kind, nil
	}
	if kind != "v1" && kept != nil {
		// by the time of the sends (seq, else updatedAt): a computer whose clock went back is not out of order
		// theo thời điểm của các lần gửi (seq, không thì updatedAt): máy có đồng hồ lùi không bị coi là tới sai thứ tự
		if gap := StampOf(kept) - StampOf(d); gap > 0 && gap <= ReorderWindowMs {
			return Stale, kind, nil
		}
	}
	if kind == "full" && kept != nil {
		if !everFull {
			lastFull = -FullBookSeconds
		}
		if now-lastFull < FullBookSeconds {
			kind = "hours"
		}
	}
	rec := pyjson.NewObject()
	device, _ := d.Get("device")
	updated, _ := d.Get("updatedAt")
	rec.Set("device", device)
	rec.Set("updatedAt", updated)
	var hours *pyjson.Object
	if kind == "hours" {
		hours = MergeHours(kept, d)
	} else {
		hours = ReplaceHours(d)
	}
	for i, k := range hours.Keys {
		rec.Set(k, hours.Vals[i])
	}
	return Saved, kind, rec
}

// StampOf copies order.stamp_of: the time a cleaned send is ordered by, its seq when the plugin numbers its sends, else its updatedAt.
// StampOf chép order.stamp_of: thời điểm dùng để xếp thứ tự một lần gửi đã làm sạch, seq khi plugin đánh số các lần gửi, không thì updatedAt.
func StampOf(d *pyjson.Object) int64 {
	v, ok := d.Get("seq")
	if !ok {
		v, _ = d.Get("updatedAt")
	}
	n, ok := v.(num)
	if !ok {
		return 0
	}
	n = toInt(n)
	if n.Big != nil {
		return math.MaxInt64
	}
	return n.I
}
