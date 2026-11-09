Tiếng Việt | [English](OPERATIONS.md)

# Sổ tay vận hành

Dành cho người IT vận hành máy chủ bảng tổng: kiểm tra hằng ngày, xử lý sự cố, sao lưu, nâng cấp và quay về bản cũ, nhật ký. Cài đặt lần đầu xem [server/README.vi.md](../server/README.vi.md).

Mọi lệnh chạy trên máy chủ, trừ khi ghi khác.

## 1. Mọi thứ nằm ở đâu

| Thành phần | Vị trí |
|---|---|
| Chương trình | `/opt/ai-worker/` (`webhook.py`, `board/`, `static/`, `menubar/`, `releases/`) |
| Dữ liệu | `/opt/ai-worker/data/board.db`, xem [DATA-MODEL.vi.md](DATA-MODEL.vi.md) |
| Tài khoản | `/opt/ai-worker/keys/accounts.db` |
| Thiết lập | `/etc/ai-worker.env` (chỉ root đọc) |
| Dịch vụ | `ai-worker-webhook` (systemd), chạy bằng tài khoản `ai-worker` |
| HTTPS và danh sách IP được vào | Caddy, ví dụ `/etc/caddy/aiworker.caddy` (mẫu: `server/aiworker.caddy`) |
| Nhật ký truy cập | `/var/log/caddy/aiworker.log`, 10 file mỗi file 20 MB |

## 2. Kiểm tra hằng ngày

```bash
systemctl status ai-worker-webhook
```

Kết quả đúng: `active (running)`.

```bash
curl http://127.0.0.1:8788/health
```

Kết quả đúng: `{"ok": true}`.

```bash
journalctl -u ai-worker-webhook -n 50
```

Kết quả đúng: có các dòng đăng nhập, thỉnh thoảng một dòng từ chối, không có `Traceback`.

Trên bảng tổng, máy im 12 phút hiện ngoại tuyến, im một ngày thì bị làm mờ. Nhiều máy ngoại tuyến cùng lúc thường do mạng hoặc Caddy, không phải webhook.

## 3. Xử lý sự cố

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Dịch vụ không chạy, nhật ký báo `INGEST_KEY is required` | Thiếu hoặc rỗng file thiết lập | Kiểm `/etc/ai-worker.env`, chạy lại `sudo bash install.sh` |
| Mọi máy ngoại tuyến | Caddy dừng, chứng chỉ hết hạn, hoặc IP văn phòng đổi | `systemctl status caddy`; sửa danh sách IP trong file Caddy rồi `systemctl reload caddy` |
| Thiếu một máy | IP của máy nằm ngoài danh sách, hoặc máy cài gói cũ | Nhờ người đó gõ `/office`; tìm IP của máy trong nhật ký truy cập Caddy |
| Nhật ký báo `401 wrong ingest key` | Gói cài được đóng với `INGEST_KEY` khác | Đóng lại gói với khoá hiện tại và cài lại cho máy đó |
| Nhật ký báo `409 this device is linked to another person` | Máy đổi người dùng | `sudo systemctl stop ai-worker-webhook`, rồi `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <mã máy>`, rồi bật lại dịch vụ |
| Nhật ký báo `429 too many submissions` | Một địa chỉ gửi quá nhiều, thường do vòng lặp hoặc nhiều máy chung một IP | Kiểm địa chỉ đó; giới hạn là 300 lần mỗi 10 phút mỗi IP |
| Nhật ký báo `507 device limit reached` | Đã đủ 300 máy | Chờ máy cũ tự rơi khỏi danh sách sau 30 ngày, hoặc nâng `MAX_DEVICES` trong code |
| Đăng nhập báo nhập sai quá nhiều lần | Sai OTP 5 lần trong 15 phút | Chờ 15 phút; kiểm đồng hồ điện thoại đang để tự động |
| TV báo lâu chưa thấy | TV tắt hoặc mất mạng | Bật TV; nếu TV đòi mã thì ghép lại trên `/admin` |
| Nhân viên không nhận bản cập nhật | Plugin cũ hơn 0.23.0, kiểm chữ ký hỏng, hoặc thư mục plugin có `.git` | Xem mục 5 |
| Mất hết quản trị | | `sudo bash manage-otp.sh --rescue <tên>` trong thư mục `server/` |

## 4. Sao lưu và khôi phục

Sao lưu mỗi ngày, khi máy chủ đang chạy. Dùng lệnh sao lưu của chính SQLite: `tar` hay `cp` có thể chép phải WAL đang ghi dở.

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/data/board.db /backup/ai-worker-board-$(date +%F).db
```

Sao lưu tài khoản riêng, chỉ root đọc được, vì có mã bí mật OTP:

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/keys/accounts.db /root/ai-worker-accounts-$(date +%F).db && sudo chmod 600 /root/ai-worker-accounts-*.db
```

Kết quả đúng: không in gì, và có file mới.

Khôi phục:

```bash
sudo systemctl stop ai-worker-webhook
sudo rm -f /opt/ai-worker/data/board.db-wal /opt/ai-worker/data/board.db-shm /opt/ai-worker/keys/accounts.db-wal /opt/ai-worker/keys/accounts.db-shm
sudo cp <bản sao lưu board> /opt/ai-worker/data/board.db
sudo cp <bản sao lưu tài khoản> /opt/ai-worker/keys/accounts.db
sudo chown ai-worker: /opt/ai-worker/data/board.db /opt/ai-worker/keys/accounts.db
sudo chmod 600 /opt/ai-worker/data/board.db /opt/ai-worker/keys/accounts.db
sudo systemctl start ai-worker-webhook
```

Sau đó kiểm `/health` và đăng nhập thử một lần.

## 5. Nâng cấp và quay về bản cũ

### Máy chủ

1. Trước khi nâng cấp, giữ bản đang chạy: `sudo cp -a /opt/ai-worker /opt/ai-worker.prev` (gồm cả dữ liệu và khoá).
2. Chép thư mục `server/` mới lên máy chủ và chạy `sudo bash install.sh` trong đó. Dữ liệu, khoá và file thiết lập được giữ nguyên.
3. Kiểm: `systemctl status ai-worker-webhook`, `/health`, đăng nhập, mở `/admin`.

Quay về bản cũ: dừng dịch vụ, chạy `install.sh` từ thư mục `server/` cũ, bật lại dịch vụ. Nếu bản mới đã đổi lược đồ thì chép lại `data/` và `keys/` từ `/opt/ai-worker.prev/`; cơ sở dữ liệu mới hơn chương trình sẽ không chạy và báo rõ trong nhật ký.

Quay về bản trước SQLite (0.24 trở về trước) mà không mất phần đã thay đổi từ đó:

```bash
sudo systemctl stop ai-worker-webhook
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --export-json /opt/ai-worker/data/export
```

Sau đó chạy `install.sh` từ thư mục `server/` cũ, dời `data/export/data/*` vào `data/` và `data/export/keys/accounts.json` vào `keys/`, chạy `chown -R ai-worker: /opt/ai-worker/data /opt/ai-worker/keys`, rồi bật dịch vụ. File JSON giữ lại từ lúc chuyển nằm ở `data/legacy-json/` và `keys/legacy-json/`.

### Plugin trên máy nhân viên

1. Trên máy IT, đổi `version` trong `.claude-plugin/plugin.json` rồi chạy `bash packaging/release.sh` (hỏi mật khẩu khoá ký).
2. Chép `server/` lên máy chủ và chạy `sudo bash install.sh`.
3. Các máy hỏi máy chủ nhiều nhất 4 giờ một lần, rồi hiện nút **Cập nhật**.

Quay về bản cũ: phát hành lại code cũ với số phiên bản mới, có ký. Trên riêng một máy: đổi tên thư mục `ai-worker.old` cạnh thư mục plugin về lại tên của plugin.

### Khoá

- **Khoá ký:** thêm khoá mới vào `~/.ai-worker-keys/allowed_signers`, phát hành một bản, rồi từ bản sau ký bằng khoá mới. Nếu lộ khoá chính, ký ngay bằng khoá dự phòng và bỏ khoá cũ trong bản đó.
- **`INGEST_KEY`:** đổi khoá này thì mọi máy ngừng gửi cho tới khi cài gói đóng với khoá mới. Chỉ đổi khi khoá bị lộ.

## 6. Chính sách ghi nhật ký

| Nhật ký | Nội dung | Giữ | Ai đọc |
|---|---|---|---|
| Nhật ký quản trị, bảng `audit` trong `board.db` | Đăng nhập, đổi tài khoản và vai, ghép và thu hồi màn hình, địa điểm, nạp CSV gói Team (chỉ khoảng ngày và số người), thao tác bị từ chối: ai, vai, IP, đường dẫn, thời điểm | 12 tháng, file cũ hơn máy chủ tự xoá | Quản trị, trên `/admin` theo tháng |
| Nhật ký dịch vụ (journald) | Khởi động, dòng đăng nhập, từ chối, lỗi. Không ghi từng lần máy gửi | Theo thiết lập journald của máy | Root trên máy chủ |
| Nhật ký truy cập Caddy | Mọi yêu cầu: IP, đường dẫn, mã trả về | 10 file mỗi file 20 MB | Root trên máy chủ |
| Diễn biến tua lại, bảng `history` trong `board.db` | Trạng thái từng người khi đổi | 24 giờ | Mọi người đã đăng nhập, qua nút tua lại |

Không bao giờ ghi: nội dung chat, câu hỏi, tên file, mã OTP, khoá.

## 7. Hồ sơ triển khai

Mỗi lần cài giữ một hồ sơ trong tài liệu nội bộ của công ty, **không để trong repo này**:

| Mục | Giá trị |
|---|---|
| Tên máy chủ và hệ điều hành | |
| Tên miền | |
| Các dải IP văn phòng được vào | |
| Phiên bản plugin đang dùng | |
| Tài khoản quản trị (chỉ ghi tên) | |
| Sao lưu đi đâu, bao lâu một lần | |
| Ai giữ khoá ký và khoá dự phòng | |
| Ngày nâng cấp gần nhất, ai làm | |

## 8. Gỡ bỏ

```bash
sudo systemctl disable --now ai-worker-webhook
sudo rm -rf /opt/ai-worker /etc/ai-worker.env /etc/systemd/system/ai-worker-webhook.service /etc/systemd/system/ai-worker-webhook.service.d
```

Sao lưu `data/` và `keys/` trước nếu có thể còn cần.
