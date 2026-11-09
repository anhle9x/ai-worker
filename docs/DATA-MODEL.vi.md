Tiếng Việt | [English](DATA-MODEL.md)

# Thiết kế dữ liệu

Máy chủ bảng tổng lưu gì, ở đâu, bao lâu và ai đọc được. Máy chủ lưu mọi thứ trong hai cơ sở dữ liệu SQLite. SQLite có sẵn trong Python nên không phải cài thêm gì.

Các thiết lập nêu ở đây (`DATA_DIR`, `KEYS_DIR`, các giới hạn) nằm trong `server/board/settings.py`. Lược đồ, các bước nâng cấp và việc chuyển từ file JSON cũ nằm trong `server/board/db.py`. Code đọc và ghi từng bảng nằm trong `server/board/stores.py`, `server/board/devices.py` và `server/board/views.py`.

## 1. Các file

| File | Mặc định sau khi cài | Chủ sở hữu và quyền | Chứa |
|---|---|---|---|
| `data/board.db` (kèm `-wal`, `-shm`) | `/opt/ai-worker/data/` | `ai-worker`, `600`, thư mục `750` | Số liệu các máy, các lần ghép, địa điểm, gói Team, nhật ký quản trị, diễn biến tua lại |
| `keys/accounts.db` (kèm `-wal`, `-shm`) | `/opt/ai-worker/keys/` | `ai-worker`, `600`, thư mục `700` | Tài khoản và mã bí mật OTP |
| `/etc/ai-worker.env` | | `root`, `600` | Thiết lập và `INGEST_KEY` |

Tài khoản nằm ở file riêng, thư mục riêng, để bản sao lưu số liệu không bao giờ mang theo mã bí mật đăng nhập. Dịch vụ systemd chỉ được ghi vào hai thư mục này (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Các bảng

`board.db`:

| Bảng | Nội dung | Ghi khi | Giữ |
|---|---|---|---|
| `devices` | Mỗi máy một dòng: số liệu mới nhất trong `body` (mục 3), `seen_at` = lúc máy chủ nhận | Mỗi lần máy gửi, nhiều nhất 30 giây một lần | Xoá sau 30 ngày kể từ `seen_at` (`KEEP_DAYS`) |
| `identities` | `máy → tài khoản, tên` của lần gửi đầu | Máy mới gửi lần đầu | Tới khi xoá bằng `--forget-device` |
| `history` | Mỗi lần trạng thái một người đổi thì thêm một dòng: thời điểm, người, trạng thái, số việc đang giao | Trạng thái đổi | 24 giờ (nút tua lại) |
| `screens` | Màn hình TV, biểu tượng thanh menu và tiện ích trình duyệt đã ghép: bản băm của khoá, tên, chủ, loại, hạn; phần còn lại trong `body` | Ghép, dùng, đổi tên, thu hồi | 30 ngày, tự gia hạn khi đang dùng, tối đa 1 năm |
| `revoked` | Bản băm của khoá đã thu hồi, để ghi nhật ký nếu còn bị dùng | Thu hồi | 30 ngày, tối đa 500 |
| `documents` | Hai tài liệu sửa nguyên khối: `locations` (tên văn phòng, dải IP, vị trí bản đồ, nhóm bán hàng) và `team-csv` (chi phí gói Team mới nhất, đã gộp theo người) | Quản trị sửa | Tới khi sửa |
| `audit` | Ai làm gì: đăng nhập, đổi tài khoản và ghép máy, thao tác bị từ chối; cột `month` để đọc theo tháng | Mỗi thao tác quản trị | 12 tháng (`KEEP_MONTHS`) |
| `meta` | Lúc chuyển file JSON cũ vào và số dòng đã chuyển | Một lần | Luôn giữ |

`accounts.db`:

| Bảng | Nội dung |
|---|---|
| `accounts` | Tên, vai, mã bí mật OTP (base32), lúc tạo và người tạo, lần đăng nhập cuối; mã người dùng và tên @ Telegram đã liên kết khi dùng đăng nhập Telegram |
| `imported` | Tên đã nhập từ `OTP=` trong file thiết lập, để tài khoản đã xoá trên `/admin` không sống lại |

Chỉ nằm trong bộ nhớ, mất khi khởi động lại: phiên đăng nhập (8 giờ, tài khoản màn hình treo tường 7 ngày), mã ghép TV (10 phút), mã dùng một lần của thanh menu (90 giây), trạng thái TV đang bật.

## 3. Bản ghi của một máy

`devices.body`, phiên bản `v: 1`. Máy chủ làm sạch mọi trường trước khi ghi và lúc đọc ra (`clean_payload` trong `devices.py`): bỏ trường lạ, cắt chữ theo độ dài cố định, kiểm tra số.

| Trường | Ý nghĩa |
|---|---|
| `device` | Mã ngẫu nhiên `device-[a-z0-9]{1,40}` do plugin tạo |
| `name`, `account`, `enteredAccount` | Tên đã khai và email tài khoản Claude |
| `ip`, `lanIp`, `ipHistory` | IP gửi (lấy từ kết nối), IP nội bộ, 10 IP gần nhất trong 30 ngày. Lịch sử do máy chủ tự lập, máy nhân viên không gửi được |
| `hardwareMark` | Bản băm một chiều của mã phần cứng; các máy cùng dấu tính là một; không bao giờ hiện ra |
| `openSessions`, `working`, `waiting` | Số phiên đang mở, đang làm, đang chờ trả lời |
| `ledger` | Token và tiền theo giờ, 8 ngày gần nhất |
| `tasks`, `delegating` | Việc giao cho Gemini, ChatGPT và Gemma, theo giờ và lúc này |
| `models`, `subagents` | Số lượt theo từng model và từng trợ lý con |
| `assistants`, `quota` | Trợ lý phụ nào đã cài; hạn mức sử dụng theo phần trăm |
| `pluginVersion`, `updatedAt` | Phiên bản plugin và thời điểm của số liệu |

**Không bao giờ lưu:** nội dung chat, câu hỏi, tên file, tên dự án.

## 4. Cách dùng cơ sở dữ liệu

- **Mỗi file một kết nối, sau một khoá.** Máy chủ web trả lời mỗi yêu cầu trong một luồng riêng; mọi luồng dùng chung một kết nối và lần lượt dùng. Tối đa 300 máy, mỗi máy nhiều nhất 30 giây gửi một lần, tức cao nhất khoảng 10 lần ghi mỗi giây.
- **Giao dịch.** Mỗi thay đổi là một giao dịch: ghi đủ cả, hoặc không ghi gì. Mỗi kho giữ bảng của mình dạng dict trong bộ nhớ và chỉ ghi các dòng đã đổi.
- **Chế độ WAL.** Đọc không phải chờ ghi. `synchronous=NORMAL` cho số liệu, `FULL` cho tài khoản.
- **Phiên bản lược đồ.** `PRAGMA user_version` giữ số phiên bản. Khi khởi động, máy chủ chạy lần lượt các bước nâng cấp còn thiếu. Cơ sở dữ liệu mới hơn chương trình thì bị từ chối, để bản cũ không lỡ chạy trên dữ liệu mới.
- **Chỉ dùng cú pháp SQL cũ.** Không dùng `UPSERT`, `RETURNING` hay hàm JSON, để chạy được cả trên Linux đời cũ.
- **Không đặt trên ổ mạng.** WAL cần ổ đĩa trong máy; không đặt `DATA_DIR` trên NFS.

### SQLite không thay đổi điều gì

SQLite không mã hoá: ai đọc được file là đọc được dữ liệu, giống file JSON cũ. Lớp bảo vệ là quyền file, tài khoản dịch vụ riêng, vùng cách ly của systemd, việc tách riêng tài khoản và việc chỉ lưu bản băm của khoá ghép.

### Chuyển từ file JSON

Các bản trước SQLite lưu mỗi bảng một file JSON. Lần khởi động đầu, bản mới tự chuyển chúng vào:

1. Đọc từng file cũ; file hỏng thì bỏ qua và ghi tên vào nhật ký dịch vụ.
2. Ghi các dòng vào cơ sở dữ liệu trong một giao dịch. Dòng đã có thì giữ nguyên.
3. Dời file cũ sang `data/legacy-json/` và `keys/legacy-json/`. Không bao giờ xoá.
4. Nhật ký hiện `migrated JSON files into ... {"devices": ..., ...}`.

File nào được đặt lại vào `data/` sau này sẽ được chuyển vào ở lần khởi động kế tiếp theo cách đó.

## 5. Sao lưu và khôi phục

Sao lưu khi máy chủ đang chạy bằng lệnh sao lưu của chính SQLite, không dùng `tar` hay `cp`, vì có thể chép phải WAL đang ghi dở. Lệnh nằm ở [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 4.

- Sao lưu `board.db` hằng ngày. File này không chứa mã bí mật.
- Sao lưu `accounts.db` riêng, chỉ root đọc được. Mất file này thì mọi tài khoản phải quét lại mã QR.

Quay về bản trước SQLite mà không mất phần đã thay đổi từ đó: `webhook.py --export-json <thư-mục>` ghi cơ sở dữ liệu ngược ra file JSON cũ. Xem [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 5.
