Tiếng Việt | [English](PERMISSIONS.md)

# Mô hình phân quyền

Ai được xem gì và làm gì trên máy chủ bảng tổng. Quy tắc nằm ở một chỗ: bảng đường dẫn cuối `server/webhook.py` (`GET_ROUTES`, `POST_ROUTES`) và cổng kiểm `Handler.gate`. Đường dẫn không có trong bảng thì trả 404. Test `test_webhook.py` giữ một bản sao của bảng và báo lỗi nếu hai bên khác nhau.

## 1. Ai đang gọi

| Bên gọi | Chứng minh bằng | Vai trên máy chủ |
|---|---|---|
| Máy nhân viên (plugin) | `INGEST_KEY` trong header `Authorization` | Không có vai: chỉ được gửi số liệu và tải bản cập nhật đã ký |
| Quản trị | Tên tài khoản + mã OTP 6 số, sau đó là cookie phiên (8 giờ) | `admin` |
| Quản lý | Tên tài khoản + OTP, cookie phiên (8 giờ) | `viewer` |
| Quản trị hoặc quản lý đã liên kết Telegram (tuỳ chọn) | Chữ ký của Telegram, kiểm bằng khoá bot (5 phút, một lần), cookie phiên | Vai của chính họ; thao tác quản trị vẫn hỏi OTP |
| Tài khoản màn hình treo tường | Tên tài khoản + OTP, cookie phiên (7 ngày) | `wall` |
| Màn hình TV | Khoá ghép do quản trị duyệt (30 ngày, tự gia hạn khi đang dùng) | `wall` |
| Biểu tượng thanh menu | Khoá ghép, do quản lý tự duyệt bằng tài khoản và OTP của mình, tối đa 2 máy mỗi tài khoản | Luôn là `wall` |
| Tiện ích trình duyệt | Khoá ghép trong header `Authorization`, do quản trị duyệt | Luôn là `wall` |

Máy chủ chỉ tin IP ghi trong yêu cầu khi yêu cầu đi qua proxy trên chính máy (`TRUST_PROXY`). Danh sách IP văn phòng được vào do Caddy hoặc nginx đứng trước chặn, không phải webhook.

## 2. Mỗi vai thấy gì

| Dữ liệu | `admin` | `viewer` | `wall` |
|---|---|---|---|
| Văn phòng 3D, trạng thái, chi phí, việc giao, hạn mức | Có | Có | Có |
| Email | Có | Có | Không: thay bằng mã ngắn, đổi sau mỗi lần khởi động |
| Tên máy là email hoặc IP | Có | Có | Không: hiện "Máy xxxxxx" |
| IP nội bộ, tài khoản nhân viên tự gõ | Có | Có | Không |
| Chi phí gói Team | Có | Có | Không |
| Nhóm máy chưa đặt tên | Có | Không | Không |
| Bảng chữ `/board` | Có | Có | Không |
| Trang `/admin` và gói cài | Có | Không | Không |

Các trường mỗi vai nhận được cố định trong `server/board/views.py` (`COMMON_FIELDS_BY_ROLE`, `PERSON_FIELDS_BY_ROLE`). Trường không có trong danh sách thì không bao giờ được gửi.

## 3. Mỗi vai làm được gì

| Thao tác | Đường dẫn | Ai | Kiểm thêm |
|---|---|---|---|
| Gửi số liệu | `POST /ingest` | Máy có `INGEST_KEY` | Máy bị gắn với người của lần gửi đầu |
| Tải bản cập nhật | `GET /releases/...` | Máy có `INGEST_KEY` | Máy kiểm chữ ký trước khi cài |
| Đặt tên địa điểm, đánh dấu nhóm bán hàng, nạp CSV gói Team | `POST /locations`, `/team-sale`, `/team-csv` | `admin` | Yêu cầu phải cùng nguồn trang |
| Tạo, xoá, đổi vai tài khoản; kết thúc phiên | `POST /admin/accounts`, `/admin/sessions` | `admin` | Nhập lại OTP, có hiệu lực 5 phút |
| Duyệt, đổi tên, thu hồi màn hình TV và tiện ích | `POST /admin/tv-*` | `admin` | Nhập lại OTP, có hiệu lực 5 phút |
| Tải lại một màn hình TV | `POST /admin/tv-reload` | `admin` | Yêu cầu phải cùng nguồn trang |
| Tự duyệt biểu tượng thanh menu của mình | `POST /mini/pair` | Tài khoản vai `admin` hoặc `viewer` | OTP của chính tài khoản đó |

## 4. Các lớp chặn

- **Luôn còn ít nhất một quản trị:** máy chủ từ chối xoá hoặc hạ vai quản trị cuối cùng.
- **Nhập sai OTP:** sai 5 lần từ một địa chỉ trong 15 phút thì khoá địa chỉ đó. Sai 20 lần trên một tài khoản trong 15 phút thì khoá tài khoản đó, nên người lạ không khoá được cả trang.
- **Telegram:** liên kết phải nhập mã 6 số và đi qua một bước dùng một lần gắn với phiên đó, nên lấy được phiên hay bấm đường dẫn người khác gửi cũng không thêm được Telegram. Mỗi tài khoản một Telegram; tài khoản treo tường không dùng được. Cấp lại khoá hoặc chuyển sang treo tường sẽ gỡ liên kết.
- **Giới hạn:** 200 tài khoản, 20 màn hình TV, 300 máy.
- **Mọi lần từ chối và mọi thay đổi đều ghi vào nhật ký quản trị** (bảng `audit` trong `board.db`): ai, vai gì, IP nào, đường dẫn nào. Nội dung CSV không chép vào.
- **Mất hết quản trị:** người có quyền sudo trên máy chủ chạy `sudo bash manage-otp.sh --rescue <tên>` trong thư mục `server/`. Xem [USER-GUIDE.vi.md](USER-GUIDE.vi.md).
