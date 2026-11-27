# AI Worker

AI Worker đo cách một nhóm dùng công cụ AI: plugin trên mỗi máy gửi số liệu lên bảng, bảng cộng lại theo người, văn phòng và ngày. Các từ dưới đây gọi tên những thứ mã và tài liệu hay nhắc tới.

## Gửi số liệu

**Send** (lần gửi):
Một lần máy gửi số liệu của nó lên bảng, qua `/ingest` hoặc qua bộ nhận Go.
_Tránh_: post, upload, report

**Hour** (giờ):
Số liệu của một máy trong một giờ đồng hồ và một loại (`ledger`, `tasks`, `blocks`), lưu thành một dòng của `device_hours`.
_Tránh_: bucket, slot

**Book** (sổ):
Mọi giờ bảng đang giữ của một máy.
_Tránh_: history, record (record là trạng thái của máy, không kèm các giờ)

**Whole book** (sổ đủ):
Lần gửi mang mọi giờ trong sổ của máy, nên giờ nào nó không mang là đã vắng.
_Tránh_: full sync, snapshot

**Changed hours** (các giờ đã đổi):
Lần gửi chỉ mang các giờ đã đổi từ lần gửi gần nhất bảng đã nhận; giờ không gửi thì giữ nguyên, giờ rỗng thì xoá giờ đó.
_Tránh_: delta, diff, patch

**Row** (dòng):
Thứ bộ nhận Go giao cho bảng về một máy trong một lô: một hay nhiều lần gửi đã gộp lại.
_Tránh_: record, entry

## Thứ tự các lần gửi

**Stamp** (mốc):
Thời điểm dùng để xếp thứ tự một lần gửi: `seq` khi plugin đánh số các lần gửi, không thì `updatedAt`. Mỗi giờ giữ mốc của lần gửi đã ghi nó (`sent_at`).
_Tránh_: timestamp, version

**Older hour** (giờ bị giữ nguyên):
Giờ của một lần gửi được để nguyên vì giờ đang giữ do một lần gửi có mốc mới hơn ghi; được đếm trên trang Quản trị.
_Tránh_: stale hour, rejected hour, conflict
