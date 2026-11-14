[English](README.md) | Tiếng Việt

# Webhook bảng tổng Văn phòng AI Worker (cho người quản trị)

Một chương trình nhỏ chạy trên máy chủ Linux trong mạng nội bộ. Máy nhân viên gửi số liệu sử dụng Claude lên đây;
máy quản lý đọc về để hiện bảng **Cả team**. Không cần thư viện ngoài, chỉ cần `python3` (3.8 trở lên) và systemd.

## Thử trước

`python3 demo.py` bật đúng máy chủ này trên `127.0.0.1` với 12 người mẫu ở 4 văn phòng, rồi in ra địa chỉ, tài khoản `demo` và mã 6 số để đăng nhập. Mọi thứ nằm trong một thư mục tạm, xoá khi bạn bấm Ctrl+C; nó bỏ qua cấu hình của bảng thật, và `install.sh` không chép nó lên máy chủ.

## Cài (một lần, khoảng 5 phút)

Chép thư mục `server/` này lên máy chủ, rồi:

```bash
sudo bash install.sh
```

Script sẽ:
- tạo người dùng hệ thống `ai-worker`, chép chương trình vào `/opt/ai-worker`;
- sinh mã gửi `INGEST_KEY` vào `/etc/ai-worker.env` (chỉ root đọc được);
- tạo dịch vụ `ai-worker-webhook` (tự chạy lại khi máy chủ khởi động hoặc chương trình lỗi), cổng mặc định **8788**;
- lần cài đầu in ra **địa chỉ webhook** và **INGEST_KEY**: gửi hai dòng này cho người đóng gói. Chạy lại để cập nhật thì
  không in mã nữa (mã nằm trong file env);
- nếu file env có `TRUST_PROXY=1` (đứng sau Caddy): đặt `BIND_ADDR=127.0.0.1` và chỉ cho localhost gọi tới
  (systemd `IPAddressAllow=localhost`), mọi truy cập đi qua HTTPS; danh sách IP được vào nằm trong `aiworker.caddy`.

Đổi cổng: `sudo PORT=9000 bash install.sh` (lần cài đầu). Tường lửa: mở cổng cho mạng nội bộ,
ví dụ `ufw allow from 192.168.0.0/16 to any port 8788`. Không cần mở ra Internet.

Tất cả cài đặt kèm giải thích: [`ai-worker.env.example`](ai-worker.env.example).

## Mã gửi và các chốt chặn

`INGEST_KEY` nằm trong gói cài của mọi nhân viên: chỉ dùng để gửi, không đọc được số liệu của ai (xem bảng phải đăng nhập OTP).
Vì ai có gói cài cũng có mã, webhook còn tự chặn:
- **mỗi máy gắn với một người**: lần gửi đầu ghi `device-... → tài khoản + tên` vào bảng `identities`; máy đó gửi
  dưới tên người khác thì bị từ chối (409, ghi vào nhật ký). Chuyển máy cho người khác: dừng dịch vụ, chạy
  `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <mã-máy>`, rồi bật lại dịch vụ;
- tối đa 300 lần gửi / 10 phút và 10 máy mới / ngày cho mỗi IP, tổng tối đa 300 máy;
- đăng nhập OTP: sai 5 lần từ một IP khoá IP đó 15 phút; sai 20 lần trên một tài khoản khoá tài khoản đó 15 phút.

Đổi mã: sửa `/etc/ai-worker.env`, `sudo systemctl restart ai-worker-webhook`, rồi đóng gói lại.

## Bảng điều khiển cả team trên trình duyệt (đăng nhập bằng OTP)

Mở `http://<IP-máy-chủ>:8788/` trên máy tính hoặc điện thoại (trong mạng được phép vào webhook), nhập mã 6 số
trong **Google Authenticator** (hoặc Microsoft Authenticator): bảng điều khiển vận hành kiểu trung tâm giám sát —
danh sách người đang hoạt động, sơ đồ người -> Claude -> Gemini/ChatGPT/Gemma (hạt sáng chạy khi đang làm/giao việc;
bấm vào thẻ để xem số liệu một người), bản đồ nhiệt chi phí 24 giờ, chỉ số, việc giao theo giờ cho từng AI,
luồng sự kiện (đổi trạng thái, giao việc), biểu đồ 24 giờ. Cập nhật 10 giây một lần. Bảng chữ riêng: `/board`.
Trang cần thư mục `static/` cạnh `webhook.py` (install.sh tự chép); thiếu thì webhook tự quay về bảng chữ. Không cần cài plugin.

Việc hằng ngày làm ở trang `/admin` (chỉ vai quản trị): tài khoản và mã QR, đổi vai, địa điểm, gói Team, phiên đang mở, nhật ký. Tạo, cấp lại, đổi vai, xoá tài khoản cần nhập lại mã OTP, có hiệu lực 5 phút. Không xoá hay hạ được quản trị cuối, không tự xoá được.

Ba vai, máy chủ tự kiểm chứ không chỉ ẩn nút:

| | Quản trị | Chỉ xem | Treo tường |
|---|---|---|---|
| Trang `/admin` | Có | Không | Không |
| Email, IP nội bộ, `/board` | Có | Có | Không |
| Giữ đăng nhập | 8 giờ | 8 giờ | 7 ngày |

Màn hình TV: mở trang bảng trên TV (TV thông minh tự hiện mã, máy tính cắm TV thì bấm "Màn hình treo tường" ở trang đăng nhập), rồi quét mã QR trên TV bằng camera điện thoại đang dùng mạng công ty, hoặc nhập mã trong mục Màn hình TV ở `/admin`; kiểm tra thiết bị và IP, đặt tên, duyệt. TV có vai treo tường, không bị văng khi webhook khởi động lại, còn dùng thì tự gia hạn 30 ngày, tối đa một năm rồi ghép lại. Thu hồi ngay trên trang. Sau khi cài bản mới, màn hình đang mở tự tải lại trong khoảng 10 giây; trang Quản trị cho biết màn hình nào đang chạy, bản nào, và có nút tải lại từ xa. Tối đa 20 màn hình. Ghép lại một màn hình cũ thì chọn "Thay cho" để không tạo thêm dòng; màn hình không dùng quá 30 ngày tự mất khỏi danh sách. Phiên chỉ lưu dạng băm ở `data/tv.json`; xoá file này rồi khởi động lại là thu hồi tất cả.

Toàn màn hình: trình duyệt chỉ cho vào khi có người thao tác trên chính máy đó, nên màn treo tường dùng lần chạm hoặc bấm phím đầu tiên cho việc này. Máy tính cắm TV thì mở Chrome ở chế độ kiosk để khỏi phải chạm; dùng thư mục hồ sơ riêng, nếu không lệnh sẽ bị bỏ qua khi Chrome đang mở:

```bash
# Windows (cmd): đặt lối tắt này vào thư mục shell:startup để bật máy là lên
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --user-data-dir=C:\ai-worker-tv https://<địa-chỉ-bảng>/
# macOS
open -na "Google Chrome" --args --kiosk --user-data-dir="$HOME/ai-worker-tv" https://<địa-chỉ-bảng>/
# Linux
google-chrome --kiosk --user-data-dir="$HOME/ai-worker-tv" https://<địa-chỉ-bảng>/
```

Cách dễ hơn: trên chính máy đó mở `/tv`, tải file ở cuối trang rồi bấm đúp, chọn 1 để tự mở khi bật máy, chọn 2 để gỡ. Windows có thể hiện SmartScreen; macOS cần chuột phải > Open lần đầu.

Ra khỏi kiosk: Alt+F4 (macOS: Cmd+Q). Nút Thoát trên màn hình chỉ đăng xuất, không đóng cửa sổ.

Lệnh trên máy chủ chỉ để cứu, trong thư mục `server/`:

```bash
sudo bash manage-otp.sh --rescue phong-it  # mất quản trị: tạo hoặc cấp lại một quản trị, in mã QR
sudo bash manage-otp.sh --delete phong-it  # xoá khẩn cấp khi không vào được trang
sudo bash manage-otp.sh --list            # ai có tài khoản, vai gì
```

Tài khoản và khoá nằm ở `keys/accounts.db`, thư mục chỉ webhook đọc được, tách khỏi `data/board.db`. Bản sao lưu `board.db` không có khoá; muốn khôi phục không phải quét lại thì sao lưu riêng `keys/`, chỉ root đọc được. Lần đầu chạy, webhook tự nhập tài khoản từ `OTP=` trong file env, không phải quét lại; các dòng đó giữ lại để lùi về bản cũ.

Nhật ký thao tác: bảng `audit` trong `data/board.db`, ghi đăng nhập, thay đổi, lần bị từ chối; giữ 12 tháng, không chép khoá hay nội dung CSV.

- Ai có quyền sudo trên máy chủ cũng tự cấp được khoá (và đọc được mọi số liệu): giữ ít người có sudo. Mỗi lần cấp/thu hồi được ghi lại, xem: `journalctl -t ai-worker-otp`.
- Mỗi người một khoá riêng, thu hồi riêng.
- Khởi động lại webhook là phải nhập mã lại, kể cả màn hình treo tường. Mỗi mã chỉ dùng được một lần.
- Nhập sai 5 lần trong 15 phút thì IP đó bị chặn 15 phút. Nhật ký ghi ai đăng nhập, từ IP nào: `journalctl -u ai-worker-webhook`.
- Giờ "hôm nay" theo `TZ_OFFSET` (mặc định 7, giờ Việt Nam); tỷ giá theo `USD_RATE` (mặc định 26000), chỉ dùng cho trang tiếng Việt (trang tiếng Anh hiện đô la Mỹ, không quy đổi).
- Ngôn ngữ của trang: ưu tiên lựa chọn của người xem (nút EN / VI, ghi trong cookie `lang`), rồi `DEFAULT_LANG` trong `/etc/ai-worker.env` (`en` hoặc `vi`; để trống thì theo trình duyệt), rồi tiếng Anh. Đổi `DEFAULT_LANG` xong chạy `sudo systemctl restart ai-worker-webhook`.
- Đăng nhập bằng Telegram (tuỳ chọn): ghi `TELEGRAM_BOT_TOKEN` và `TELEGRAM_BOT_NAME` vào `/etc/ai-worker.env`, rồi khởi động lại dịch vụ. Các bước ở [docs/INSTALL.vi.md](../docs/INSTALL.vi.md), mục "Đăng nhập bằng Telegram".
- Kết nối HTTP không mã hoá: chỉ nên mở trang này trong mạng công ty. Muốn xem từ ngoài thì cần HTTPS trước.

## Vận hành

```bash
systemctl status ai-worker-webhook          # đang chạy không
journalctl -u ai-worker-webhook -n 50       # nhật ký (chỉ ghi lỗi, không ghi từng lần gửi)
curl http://127.0.0.1:8788/health       # {"ok": true}
```

Dữ liệu: `/opt/ai-worker/data/board.db` (SQLite), mỗi máy một dòng vài KB, ghi đè khi máy gửi lại. Các bảng và cách sao lưu: [docs/DATA-MODEL.vi.md](../docs/DATA-MODEL.vi.md).
Máy im lặng quá 30 ngày thì dòng tự bị xoá. Tải rất nhẹ: mỗi máy gửi tối đa một lần mỗi 30 giây khi số liệu đổi,
ít nhất một lần mỗi 5 phút khi đang mở Claude.

Cập nhật chương trình: chép bản mới đè lên rồi chạy lại `sudo bash install.sh` (giữ nguyên mã và dữ liệu).
Gỡ: `sudo systemctl disable --now ai-worker-webhook`, xoá `/opt/ai-worker`, `/etc/ai-worker.env`,
`/etc/systemd/system/ai-worker-webhook.service`.

## Lưu những gì

Tên, email tài khoản Claude, mã máy ngẫu nhiên, **IP máy gửi** (máy chủ tự ghi từ kết nối, máy nhân viên không tự khai được), IP nội bộ máy tự khai (máy chủ nhớ các IP đã dùng trong 30 ngày, tối đa 10), dấu máy (mã phần cứng đã băm một chiều; máy cùng dấu được tính là một máy, dấu không hiện trên trang), số phiên mở / đang làm / chờ trả lời, token và tiền theo từng giờ
(8 ngày gần nhất), số việc giao cho Gemini/ChatGPT/Gemma theo giờ. **Không có** nội dung chat, câu hỏi, tên file,
tên dự án. Kết nối là HTTP trong mạng nội bộ (không mã hoá); muốn HTTPS thì đặt sau nginx/Caddy sẵn có và dùng
địa chỉ `https://...` khi đóng gói; khi đó thêm `TRUST_PROXY=1` vào `/etc/ai-worker.env` để ghi đúng IP máy nhân viên thay vì IP của proxy.
