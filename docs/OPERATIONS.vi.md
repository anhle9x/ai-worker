Tiếng Việt | [English](OPERATIONS.md)

# Sổ tay vận hành

Dành cho người quản trị vận hành máy chủ bảng tổng: kiểm tra hằng ngày, xử lý sự cố, sao lưu, nâng cấp và quay về bản cũ, nhật ký. Cài đặt lần đầu xem [server/README.vi.md](../server/README.vi.md).

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
| Trang Quản trị báo *Kiểm nhật ký: một dòng … đã bị sửa hay bị xoá* | Có người sửa `board.db` bằng tay, hoặc chép đè một bản cũ lên bản mới hơn | Tìm xem ai có sudo hay quyền đọc ghi file trên máy chủ; so dấu vân tay cuối với dấu đã ghi lại; khôi phục bản sao lưu làm trước khi có chuỗi thì không gây báo này |
| Trang Quản trị liệt kê khoá cho công cụ AI *không dùng N ngày* | Một công cụ được cài một lần rồi bỏ, hoặc file cấu hình của nó bị chép đi nơi khác | Hỏi khoá đó của ai; **Thu hồi** khoá không ai cần, để khoá bỏ quên trong file cấu hình cũ không đọc được bảng |
| Mọi máy ngoại tuyến | Caddy dừng, chứng chỉ hết hạn, hoặc IP văn phòng đổi | `systemctl status caddy`; sửa danh sách IP trong file Caddy rồi `systemctl reload caddy` |
| Thiếu một máy | IP của máy nằm ngoài danh sách, hoặc máy cài gói cũ | Nhờ người đó gõ `/office`; tìm IP của máy trong nhật ký truy cập Caddy |
| Nhật ký báo `401 wrong ingest key` | Gói cài được đóng với `INGEST_KEY` khác | Đóng lại gói với khoá hiện tại và cài lại cho máy đó |
| Nhật ký báo `use this computer's own key` | Máy đã có khoá riêng nhưng lại gửi bằng khoá chung, thường do dữ liệu plugin trên máy bị xoá | `--forget-device <mã máy>` (như với máy đổi chủ); máy ghi danh lại ở lần gửi sau |
| Một máy phải ngừng gửi (mất, bị lấy, nghỉ việc) | | Trên trang Quản trị, mục **Máy nhân viên và khoá riêng**, bấm **Thu hồi** ở dòng của máy đó; hoặc bằng lệnh `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --revoke-device <mã máy>`: khoá của máy thôi hiệu lực ngay và khoá chung cũng không gửi cho nó được nữa |
| Mọi máy phải nhận khoá mới (bí mật ký khoá đã cũ, hoặc file bí mật bị lộ) | | Dừng webhook, chạy `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --rotate-device-secret`, rồi bật lại: mọi máy nhận khoá mới ở lần gửi kế tiếp, khoá cũ vẫn dùng được cho tới lúc đó. Với `--drop-old` các khoá cũ thôi hiệu lực ngay và mọi máy ghi danh lại bằng khoá chung ([RECEIVER.vi.md](RECEIVER.vi.md), mục 6) |
| Nhật ký báo `409 this device is linked to another person` | Máy đổi người dùng | `sudo systemctl stop ai-worker-webhook`, rồi `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <mã máy>`, rồi bật lại dịch vụ |
| Nhật ký báo `429 too many submissions` | Một máy gửi quá nhiều, thường do vòng lặp | Kiểm máy đó; mỗi máy được gửi dồn 20 lần, sau đó mỗi giây một lần |
| Nhật ký báo `507 device limit reached` | Đã đủ 300 máy | Chờ máy cũ tự rơi khỏi danh sách sau 30 ngày, hoặc nâng `MAX_DEVICES` trong `/etc/ai-worker.env` sau khi đo ([BENCHMARK.vi.md](BENCHMARK.vi.md)) |
| Đăng nhập báo nhập sai quá nhiều lần | Sai OTP 5 lần trong 15 phút | Chờ 15 phút; kiểm đồng hồ điện thoại đang để tự động |
| TV báo lâu chưa thấy | TV tắt hoặc mất mạng | Bật TV; nếu TV đòi mã thì ghép lại trên `/admin` |
| Nhân viên không nhận bản cập nhật | Plugin cũ hơn 0.23.0, kiểm chữ ký hỏng, hoặc thư mục plugin có `.git` | Xem mục 5 |
| Mất hết quản trị | | `sudo bash manage-otp.sh --rescue <tên>` trong thư mục `server/` |
| Dịch vụ không lên sau khi nâng cấp, nhật ký báo `Cannot back up ... before upgrading its schema` | Đĩa đầy, hoặc dịch vụ không được ghi vào thư mục dữ liệu | Chưa có gì bị đổi. Dọn bớt đĩa (`df -h /opt/ai-worker/data`), kiểm thư mục thuộc về `ai-worker`, rồi bật lại dịch vụ |
| Dịch vụ không lên, nhật ký báo `has schema version 2, newer than this program` | Cài bản cũ đè lên cơ sở dữ liệu mà bản mới đã nâng | Cài lại bản mới, hoặc quay lui bằng bản sao làm trước khi nâng: mục 5 |
| Trang Telegram báo tên miền của bot không hợp lệ | Bot chưa gắn với địa chỉ bảng tổng | Gửi `/setdomain` cho @BotFather kèm tên miền bảng tổng |
| "Tài khoản Telegram này chưa liên kết" | Người đó chưa liên kết Telegram | Đăng nhập bằng tên và mã, rồi liên kết ở `/telegram` |
| Lộ khoá bot Telegram | Ai có khoá cũng ký được lần đăng nhập | Thu hồi bằng `/revoke` trong @BotFather, ghi khoá mới vào `/etc/ai-worker.env`, khởi động lại dịch vụ |
| Trang Quản trị báo Telegram từ chối token của bot | Token dùng cho việc hỏi qua Telegram sai hoặc đã bị thu hồi | Ghi đúng token vào `/etc/ai-worker-telegram.env` (`TELEGRAM_ASK_TOKEN=`), chạy `sudo bash install.sh` |
| Trang Quản trị báo một chương trình khác đang đọc cùng bot | Token còn được dùng ở nơi khác, hoặc bot đang bị đặt webhook | Một bot chỉ có một nơi đọc: tạo một bot riêng cho việc này bằng @BotFather và dùng token của nó |
| Trang Quản trị báo máy chủ không tới được Telegram | Tường lửa, giới hạn mạng của dịch vụ bot, hoặc mạng chặn Telegram | Trên máy chủ: `curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org`. Ra một con số nghĩa là tới được Telegram: đặt `TELEGRAM_NETS` trong `/etc/ai-worker-telegram.env` rồi chạy `install.sh` (xem INSTALL) |
| Trang Quản trị báo chưa thấy tiến trình bot, hoặc bot không trả lời | Dịch vụ không chạy | `systemctl status ai-worker-telegram`, rồi `journalctl -u ai-worker-telegram -n 30`. Nhật ký nêu lý do, không bao giờ có token |
| Khung bên trong Telegram hiện chữ *Forbidden* | Caddy chặn IP mà điện thoại hay máy tính đi tới. Văn phòng có nhiều đường Internet có thể đẩy Telegram ra bằng đường chưa có trong danh sách | `sudo grep '/tg/app' /var/log/caddy/aiworker.log \| tail -3`, đọc `remote_ip`; chỉ thêm IP đó vào dòng `remote_ip` khi nó là đường Internet của chính bạn, rồi `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`. Nếu là proxy đặt trong Telegram hay VPN: tắt đi |
| Chat không có nút **AI Worker** | Chat chưa được cho mở khung, thiếu `TELEGRAM_APP_URL`, hoặc tiến trình bot không chạy | Ở `/admin` dòng của chat phải ghi *mở được khung*; `install.sh` báo khi `TELEGRAM_APP_URL` sai; `journalctl -u ai-worker-telegram -n 30` có dòng `a menu button could not be set` khi Telegram từ chối. Đóng chat trong Telegram rồi mở lại |
| Khung báo đóng rồi mở lại | Phiên đã hết: webhook khởi động lại, một giờ không dùng, hoặc chat bị bỏ quyền mở khung | Đóng khung rồi bấm **AI Worker** lại; vẫn báo vậy thì xem dòng của chat ở `/admin` |
| Chat đã bật tin báo mà không nhận được tin | Chat đó đang tắt tin báo, chưa ai chờ quá số phút của chat, đang trong 19:00 tới 07:00, hoặc chat đã chạm trần (6 tin mỗi giờ, 30 tin mỗi ngày) | Gửi `/baocho` trong chat để xem đang bật hay tắt và sau bao nhiêu phút; lần chờ quá 4 giờ, hoặc người đang ngoại tuyến, không được báo; `journalctl -u ai-worker-telegram -n 30` có dòng `an answer could not be sent` khi Telegram từ chối một tin |
| Lộ token của bot dùng để hỏi bảng | Người có token đọc được những gì mọi người gửi cho bot và nhắn cho họ dưới tên bot; họ không đọc được bảng | `/revoke` ở @BotFather, ghi token mới vào `/etc/ai-worker-telegram.env`, chạy `sudo bash install.sh` |

## 4. Sao lưu và khôi phục

Sao lưu mỗi ngày, khi máy chủ đang chạy. Dùng lệnh sao lưu của chính SQLite: `tar` hay `cp` có thể chép phải WAL đang ghi dở.

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/data/board.db /backup/ai-worker-board-$(date +%F).db
```

Sao lưu tài khoản riêng, chỉ root đọc được, vì có mã bí mật OTP (và người dùng Telegram đã liên kết). Giữ một bản `/etc/ai-worker.env` theo cùng cách: file này chứa `INGEST_KEY` và, khi dùng, khoá bot Telegram:

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/keys/accounts.db /root/ai-worker-accounts-$(date +%F).db && sudo chmod 600 /root/ai-worker-accounts-*.db
```

Kết quả đúng: không in gì, và có file mới.

Khoá OTP trong `accounts.db` được niêm phong bằng khoá OTP `/etc/ai-worker-otp.key`, do `install.sh` tạo một lần (chỉ root đọc được). Chỉ có bản chép `accounts.db` thì không đăng nhập được ai, và máy chủ không chạy trên file đó nếu thiếu khoá này. Giữ một bản của khoá ở nơi an toàn, tách khỏi bản sao lưu `/opt/ai-worker`, ví dụ trong trình quản lý mật khẩu của quản trị hay một USB cất trong ngăn kéo:

```bash
sudo cat /etc/ai-worker-otp.key
```

Kết quả đúng: một dòng gồm 64 chữ và số. Nếu mất khoá và cả bản giữ của nó, xem "Mất khoá OTP" ở mục 5.

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

Quay về bản cũ: dừng dịch vụ, chạy `install.sh` từ thư mục `server/` cũ, bật lại dịch vụ. Nếu bản mới đã đổi lược đồ thì chương trình cũ từ chối cơ sở dữ liệu và báo rõ trong nhật ký: phải đặt lại bản sao làm trước khi nâng, theo các bước dưới đây.

#### Quay lui sau khi lược đồ đã đổi

Lược đồ là cách bố trí các bảng trong file cơ sở dữ liệu. Bản đầu tiên có tổng theo ngày nâng `board.db` từ lược đồ phiên bản 1 lên 2; `accounts.db` không đổi. Ở lần chạy đầu trên một cơ sở dữ liệu đã có sẵn, bản đó:

1. chép `board.db` thành `board.db.schema-1.bak` trong cùng thư mục (quyền `600`) và kiểm rằng bản sao mở được,
2. ghi dòng `backed up ... (schema version 1) to ... before upgrading to schema version 2` vào nhật ký dịch vụ,
3. xong mới nâng. Không chép được thì không đổi gì cả và dịch vụ dừng với dòng `Cannot back up ...`.

Muốn quay về bản cũ:

```bash
sudo systemctl stop ai-worker-webhook
```

```bash
sudo ls -l /opt/ai-worker/data/board.db.schema-1.bak
```

Kết quả đúng: một dòng có tên file, kích thước lớn hơn 0. Nếu không có file thì dừng ở đây và dùng `/opt/ai-worker.prev/data/` hoặc bản sao lưu hằng ngày (mục 4).

```bash
sudo rm -f /opt/ai-worker/data/board.db-wal /opt/ai-worker/data/board.db-shm
sudo cp /opt/ai-worker/data/board.db.schema-1.bak /opt/ai-worker/data/board.db
sudo chown ai-worker: /opt/ai-worker/data/board.db
sudo chmod 600 /opt/ai-worker/data/board.db
```

Sau đó chạy `sudo bash install.sh` trong thư mục `server/` cũ (lệnh này tự bật dịch vụ), kiểm `/health` và đăng nhập một lần. Hai file bị `rm` là file phụ của chính SQLite cho cơ sở dữ liệu mới; để lại thì chúng sẽ bị áp vào file cũ.

Quay lui thì mất gì: mọi thứ đã ghi vào `board.db` sau khi nâng, như tổng theo ngày, các dòng nhật ký quản trị, màn hình hay khoá đã ghép và địa điểm đã đặt tên từ lúc đó. Bảng trực tiếp đầy lại sau vài phút, vì mỗi lần gửi máy nào cũng gửi kèm 8 ngày theo giờ gần nhất. Tài khoản không bị đụng tới.

Máy chủ xoá `board.db.schema-1.bak` 30 ngày sau khi nâng (nhật ký: `deleted the upgrade backup ...`). Đây là một bản sao đầy đủ số liệu của mọi người: giữ kín như `board.db`, và chỉ chép đi nơi khác trước khi hết 30 ngày nếu cần giữ lâu hơn.

Mọi lần đổi lược đồ sau đó cũng vậy, với số phiên bản của lần đó trong tên file. Bản giữ sổ giờ ở các dòng riêng (`device_hours`, `device_days`, xem [DATA-MODEL.vi.md](DATA-MODEL.vi.md)) nâng `board.db` từ lược đồ phiên bản 5 lên 6, nên bản sao của nó là `board.db.schema-5.bak`: dùng tên đó trong các bước trên. Lần nâng chạy trong một giao dịch, nên hỏng giữa chừng thì cơ sở dữ liệu vẫn ở phiên bản 5 và dịch vụ dừng, lỗi ghi trong nhật ký.

#### Quay lui sau khi khoá OTP đã niêm phong

Bản đầu tiên niêm phong khoá OTP nâng `accounts.db` từ lược đồ phiên bản 1 lên 2 và ghi vào nhật ký `Sealed <n> OTP secrets with the OTP key`. Bản cũ từ chối file đó, vì nó sẽ đọc khoá đã niêm phong như chính khoá và không ai đăng nhập được. Trước khi cài bản cũ, lưu lại khoá như cũ, trong lúc bản mới vẫn đang cài:

```bash
sudo bash /opt/ai-worker/manage-otp.sh --unseal
```

Kết quả đúng: `Khoá OTP đã lưu lại dạng thường, và webhook đang dừng.` Rồi chạy `sudo bash install.sh` trong thư mục `server/` cũ. Không mất gì. Bản chép `accounts.db.schema-1.bak` cũng giữ các tài khoản như trước khi nâng; máy chủ xoá nó sau 7 ngày, vì khoá trong đó chưa niêm phong.

#### Mất khoá OTP

Nhật ký dịch vụ báo `... are sealed, but the OTP key cannot be read` hoặc `... it is not the key they were sealed with`, và webhook không chạy. Trước hết chép lại file khoá từ bản giữ, bằng root, rồi chạy lại `sudo bash install.sh`:

```bash
sudo install -m 600 -o root -g root <bản giữ của khoá> /etc/ai-worker-otp.key
```

Nếu khoá mất hẳn, không ai mở được các khoá đã niêm phong. Bỏ các tài khoản đó, rồi tạo khoá mới và một quản trị mới:

```bash
sudo bash /opt/ai-worker/manage-otp.sh --forget-sealed
sudo rm -f /etc/ai-worker-otp.key
sudo bash install.sh
```

`install.sh` tạo khoá mới và, khi không còn quản trị nào, hỏi tên người quản trị đầu tiên. Những người khác được tạo lại tài khoản ở `/admin` và quét mã QR mới.

Quay về bản trước SQLite (0.24 trở về trước) mà không mất phần đã thay đổi từ đó:

```bash
sudo systemctl stop ai-worker-webhook
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --export-json /opt/ai-worker/data/export
```

Sau đó chạy `install.sh` từ thư mục `server/` cũ, dời `data/export/data/*` vào `data/` và `data/export/keys/accounts.json` vào `keys/`, chạy `chown -R ai-worker: /opt/ai-worker/data /opt/ai-worker/keys`, rồi bật dịch vụ. File JSON giữ lại từ lúc chuyển nằm ở `data/legacy-json/` và `keys/legacy-json/`.

### Plugin trên máy nhân viên

1. Trên máy giữ khoá ký, đổi `version` trong `.claude-plugin/plugin.json` rồi chạy `bash packaging/release.sh` (hỏi mật khẩu khoá ký).
2. Chép `server/` lên máy chủ và chạy `sudo bash install.sh`.
3. Các máy hỏi máy chủ nhiều nhất 4 giờ một lần, rồi hiện nút **Cập nhật**.

Quay về bản cũ: phát hành lại code cũ với số phiên bản mới, có ký. Trên riêng một máy: đổi tên thư mục `ai-worker.old` cạnh thư mục plugin về lại tên của plugin.

### Khoá

- **Khoá ký:** thêm khoá mới vào `~/.ai-worker-keys/allowed_signers`, phát hành một bản, rồi từ bản sau ký bằng khoá mới. Nếu lộ khoá chính, ký ngay bằng khoá dự phòng và bỏ khoá cũ trong bản đó.
- **`INGEST_KEY`:** đổi khoá này thì mọi máy ngừng gửi cho tới khi cài gói đóng với khoá mới. Chỉ đổi khi khoá bị lộ.

## 6. Chính sách ghi nhật ký

| Nhật ký | Nội dung | Giữ | Ai đọc |
|---|---|---|---|
| Nhật ký quản trị, bảng `audit` trong `board.db` | Đăng nhập, đổi tài khoản và vai, ghép và thu hồi màn hình, địa điểm, nạp CSV gói Team (chỉ khoảng ngày và số người), thao tác bị từ chối: ai, vai, IP, đường dẫn, thời điểm | 12 tháng, dòng cũ hơn máy chủ tự xoá; mỗi dòng mang dấu vân tay của dòng trước, và `/admin` báo nếu có dòng bị sửa hay bị xoá bằng tay | Quản trị, trên `/admin` theo tháng |
| Nhật ký dịch vụ (journald) | Khởi động, dòng đăng nhập, từ chối, lỗi. Không ghi từng lần máy gửi | Theo thiết lập journald của máy | Root trên máy chủ |
| Nhật ký truy cập Caddy | Mọi yêu cầu: IP, đường dẫn, mã trả về | 10 file mỗi file 20 MB | Root trên máy chủ |
| Diễn biến tua lại, bảng `history` trong `board.db` | Trạng thái từng người khi đổi | 24 giờ | Mọi người đã đăng nhập, qua nút tua lại |
| Tổng theo ngày, bảng `daily` trong `board.db` | Mỗi người mỗi ngày một dòng: chi phí, token, số việc giao, văn phòng, kèm tên và email tài khoản | Tháng hiện tại và 12 tháng trước đó, dòng cũ hơn máy chủ tự xoá | Quản trị và người xem, trên `/board` |
| Dự án hay ứng dụng AI, bảng `project_turns` và `project_daily` trong `board.db` (chỉ khi `AI_PROJECTS=1`) | Từng lượt dự án đã gửi: thời gian, kết quả, và theo từng model: số lần gọi, lỗi, token; không bao giờ có câu hỏi, câu trả lời hay người dùng. Tổng theo dự án, ngày và model | Lượt giữ 30 ngày, tổng giữ tháng hiện tại và 12 tháng trước, dòng cũ hơn máy chủ tự xoá | Quản trị và người xem, trên `/projects` |

Không bao giờ ghi: nội dung chat, câu hỏi, tên file, mã OTP, khoá.

Muốn xoá tổng theo ngày của một người trước khi chúng hết hạn, ví dụ khi người đó yêu cầu hoặc đã nghỉ việc:

```bash
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-usage <email hoặc tên>
```

Kết quả đúng: `deleted <số> daily rows of <email hoặc tên>`. Không cần dừng dịch vụ. Những ngày trong tuần vừa qua mà máy của người đó còn báo lên sẽ được ghi lại ở lần đếm kế tiếp, nên với người đã nghỉ thì chạy lệnh này sau ngày làm cuối của họ một tuần.

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
| Dấu vân tay nhật ký cuối ghi lại từ `/admin`, và lúc nào | |

## 8. Gỡ bỏ

```bash
sudo systemctl disable --now ai-worker-webhook
sudo rm -rf /opt/ai-worker /etc/ai-worker.env /etc/systemd/system/ai-worker-webhook.service /etc/systemd/system/ai-worker-webhook.service.d
```

Sao lưu `data/` và `keys/` trước nếu có thể còn cần.
