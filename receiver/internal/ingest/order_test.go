package ingest

import (
	"testing"

	"aiworker/receiver/internal/pyjson"
)

func stampsOf(t *testing.T, row pyjson.Value) string {
	t.Helper()
	return string(pyjson.Encode(stripOrder(field(row, "stamp")))) + " " + string(pyjson.Encode(stripOrder(field(row, "stamps"))))
}

// TestEachHourOfARowKeepsTheTimeOfItsSend: two sends of a computer wait as one row; each hour of it keeps the time (seq, else updatedAt)
// of the send it came from, so Python never writes an hour of the older one over a send that came straight to it in between (proto 3).
// An hour of an older send never replaces the hour of a newer one, here either.
// TestEachHourOfARowKeepsTheTimeOfItsSend: hai lần gửi của một máy chờ thành một dòng; mỗi giờ của dòng giữ thời điểm (seq, không thì
// updatedAt) của lần gửi nó đến từ đó, để Python không bao giờ ghi giờ của lần cũ hơn đè lên một lần gửi thẳng tới nó ở giữa (proto 3).
// Ở đây cũng vậy, giờ của lần gửi cũ hơn không bao giờ thay giờ của lần mới hơn.
func TestEachHourOfARowKeepsTheTimeOfItsSend(t *testing.T) {
	const device = `"device": "device-o1"`
	p := &waiting{}
	p.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165600000, "hours": {"ledger": {"497546": {"usdMicro": 1}, "497545": {"usdMicro": 9}}}}`), "hours", "a", 1, nil)
	p.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165000000, "seq": 1791165602000, "hours": {"ledger": {"497546": {"usdMicro": 2}}}}`), "hours", "a", 2, nil)
	// a send older than both, late: its hour stays out
	// một lần gửi cũ hơn cả hai, tới muộn: giờ của nó không vào
	p.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165500000, "hours": {"ledger": {"497545": {"usdMicro": 4}, "497544": {"usdMicro": 3}}}}`), "hours", "a", 3, nil)
	r := p.batchRow()
	if got := ledgerOf(t, p.row()); got != `{"497544": {"usd": 3e-06, "usdMicro": 3}, "497545": {"usd": 9e-06, "usdMicro": 9}, "497546": {"usd": 2e-06, "usdMicro": 2}}` {
		t.Fatalf("hours: %s", got)
	}
	if got := stampsOf(t, r); got != `1791165600000 {"ledger": {"497544": 1791165500000, "497546": 1791165602000}}` {
		t.Fatalf("times: %s", got)
	}
	if u, _ := p.row().Get("seq"); !pyjson.Equal(u, pyjson.IntN(1791165602000)) {
		t.Fatalf("the state of the newest send: seq %v", u)
	}
	// a whole book older than the hour waiting keeps that hour, and an hour gone after it stays gone
	// một sổ đủ cũ hơn giờ đang chờ giữ lại giờ đó, và giờ đã vắng sau nó vẫn vắng
	q := &waiting{}
	q.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165700000, "hours": {"ledger": {"497546": {"usdMicro": 8}, "497540": {}}}}`), "hours", "a", 1, nil)
	q.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165600000, "full": true, "hours": {"ledger": {"497546": {"usdMicro": 5}, "497540": {"usdMicro": 6}, "497541": {"usdMicro": 7}}}}`), "full", "a", 2, nil)
	if q.kind != "full" {
		t.Fatalf("kind %s", q.kind)
	}
	if got := ledgerOf(t, q.row()); got != `{"497541": {"usd": 7e-06, "usdMicro": 7}, "497546": {"usd": 8e-06, "usdMicro": 8}}` {
		t.Fatalf("whole book: %s", got)
	}
	if got := stampsOf(t, q.batchRow()); got != `1791165600000 {"ledger": {"497540": 1791165700000, "497546": 1791165700000}}` {
		t.Fatalf("whole book times: %s", got)
	}
	// a whole book older than the one waiting changes none of its hours
	// một sổ đủ cũ hơn sổ đang chờ không đổi giờ nào của nó
	q.add(cleaned(t, `{"v": 2, `+device+`, "updatedAt": 1791165500000, "full": true, "hours": {"ledger": {"497541": {"usdMicro": 1}, "497539": {"usdMicro": 1}}}}`), "full", "a", 3, nil)
	if got := ledgerOf(t, q.row()); got != `{"497541": {"usd": 7e-06, "usdMicro": 7}, "497546": {"usd": 8e-06, "usdMicro": 8}}` {
		t.Fatalf("older whole book: %s", got)
	}
}

// TestTheHoursHeldKeepTheTimeOfTheirSend: what this side holds for the live numbers follows the same rule as Python's book: the times
// come with the book from Python (proto 3), and an hour of an older send never replaces a newer one, in a whole book or not.
// TestTheHoursHeldKeepTheTimeOfTheirSend: thứ bên này giữ cho số trực tiếp theo cùng luật với sổ của Python: các thời điểm đến cùng sổ
// từ Python (proto 3), và giờ của lần gửi cũ hơn không bao giờ thay giờ mới hơn, trong sổ đủ hay không.
func TestTheHoursHeldKeepTheTimeOfTheirSend(t *testing.T) {
	v, _ := pyjson.Parse([]byte(`{"device": "device-o2", "updatedAt": 1791165700000, "ledger": {"497546": {"usdMicro": 8}, "497545": {"usdMicro": 3}},
		"tasks": {}, "stamps": {"ledger": {"497546": 1791165700000, "497545": 1791165100000}}}`))
	h := heldFrom(v.(*pyjson.Object), 497540)
	older := cleaned(t, `{"v": 2, "device": "device-o2", "updatedAt": 1791165200000, "hours": {"ledger": {"497546": {"usdMicro": 1}, "497545": {"usdMicro": 4}}}}`)
	next := h.next(older, "hours", 497540)
	if got := next.ledger[497546][0]; got != 8 {
		t.Fatalf("an older send replaced a newer hour: %d", got)
	}
	if got := next.ledger[497545][0]; got != 4 {
		t.Fatalf("a newer send was left out: %d", got)
	}
	whole := cleaned(t, `{"v": 2, "device": "device-o2", "updatedAt": 1791165300000, "full": true, "hours": {"ledger": {"497544": {"usdMicro": 2}}}}`)
	after := next.next(whole, "full", 497540)
	if _, ok := after.ledger[497545]; ok {
		t.Fatalf("an hour gone from a newer whole book stayed")
	}
	if after.ledger[497546][0] != 8 || after.ledger[497544][0] != 2 {
		t.Fatalf("whole book: %v", after.ledger)
	}
	// only the hour of another send than the whole book's keeps a time apart
	// chỉ giờ của lần gửi khác với sổ đủ mới giữ thời điểm riêng
	if after.base != 1791165300000 || len(after.stamps) != 1 || after.heldStamp("ledger", 497546) != 1791165700000 {
		t.Fatalf("times held: base %d, apart %v", after.base, after.stamps)
	}
}
