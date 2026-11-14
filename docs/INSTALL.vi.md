Tiếng Việt | [English](INSTALL.md)

# Cài đặt và cấu hình

Dành cho người quản trị triển khai AI Worker: cần chuẩn bị gì, triển khai lần đầu, phát hành bản cập nhật, dữ liệu gửi đi, tuỳ chỉnh và bảo vệ. Cách dùng hằng ngày xem [USER-GUIDE.vi.md](USER-GUIDE.vi.md); vận hành máy chủ xem [OPERATIONS.vi.md](OPERATIONS.vi.md).

## Cần chuẩn bị

Muốn xem bảng trước khi triển khai, chạy `python3 server/demo.py` trên máy mình: lệnh này hiện bảng với người mẫu và không cần máy chủ (xem [README](../README.vi.md#cài-nhanh)).

- **Máy chủ Linux** có `python3` từ 3.8 và systemd. Webhook không cần thư viện ngoài.
- **Một tên miền con riêng**, ví dụ `bang.cong-ty.vn`, trỏ bản ghi DNS `A` về IP máy chủ.
- **Caddy** (hoặc nginx) trên máy chủ để có HTTPS. Webhook chỉ nghe nội bộ, Caddy nhận kết nối từ ngoài.
- **Danh sách IP được vào:** IP mạng các văn phòng. Máy ngoài danh sách không xem được bảng, không gửi được số liệu và không tải được bản cập nhật.
- **Một máy giữ khoá ký** có `ssh-keygen` để giữ khoá ký bản cập nhật.

Địa chỉ thật, `INGEST_KEY` và khoá không đưa vào git. Trong repo chỉ dùng địa chỉ mẫu như `https://bang.cong-ty.vn`.

## Triển khai lần đầu

1. **Cài webhook.** Chép `server/` lên máy chủ rồi chạy `sudo bash install.sh`. Lần đầu script in `INGEST_KEY` và tạo tài khoản quản trị đầu tiên. Chi tiết ở [`server/README.md`](../server/README.md).
2. **Bật HTTPS.** Thêm khối Caddy cho tên miền với danh sách IP được vào (mẫu: `server/aiworker.caddy`, đổi sang tên miền và IP của bạn), rồi thêm `TRUST_PROXY=1` vào `/etc/ai-worker.env` và chạy lại `install.sh`.
3. **Tạo khoá ký**, trên máy giữ khoá ký:
   ```bash
   mkdir -p ~/.ai-worker-keys && chmod 700 ~/.ai-worker-keys
   ssh-keygen -t ed25519 -C ai-worker-main -f ~/.ai-worker-keys/main
   ssh-keygen -t ed25519 -C ai-worker-backup -f ~/.ai-worker-keys/backup
   ```
   Đưa hai khoá công khai vào `~/.ai-worker-keys/allowed_signers`, mỗi dòng dạng `ai-worker ssh-ed25519 AAAA...`. `build.sh` và `release.sh` chép file đó vào gói; `keys/allowed_signers` trong git chỉ có chú thích, nên repo công khai không bao giờ mang khoá của bạn. Khoá riêng không lên máy chủ, không vào git; cất bản dự phòng ở ngoài máy.
4. **Đóng gói.** Chép `packaging/company.example.json` thành `packaging/company.json` (file này không vào git), điền `webhook` và `ingestKey`, rồi:
   ```bash
   bash packaging/build.sh packaging/company.json
   ```
   Được `dist/AI-Worker-<phiên bản>-company.zip`.
5. **Nhân viên cài.** Giải nén, bấm đúp `INSTALL-Mac.command` hoặc `INSTALL-Windows.bat`, nhập họ tên. Gói có mã gửi nên chỉ phát trong công ty.
6. **Xem bảng.** Mở địa chỉ webhook, đăng nhập bằng mã OTP. Trang `/board` có cột Plugin cho biết máy nào chưa lên bản mới nhất.

## Lệnh trên máy nhân viên

- `/office`: mở bảng điều khiển các phiên trên máy.
- `/office-pane`: mở bản 2D cạnh khung chat.
- `/update`: kiểm tra và cài bản mới.

## Biểu tượng thanh menu cho quản lý

Quản lý thấy ngay trên thanh menu có bao nhiêu người đang chờ trả lời, không cần mở bảng: app riêng trên macOS, app cạnh đồng hồ trên Windows (cài từ file .msi, không cần quyền quản trị), biểu tượng trên thanh trên cùng của Ubuntu (gói .deb). Bấm vào là mở khung nhỏ có Đang chờ, Đang làm, Hạn mức, Chi phí hôm nay và Cài đặt. Chi tiết: [docs/menu-bar-spec.vi.md](menu-bar-spec.vi.md).

- **Tải về:** trang Quản trị, mục "Biểu tượng thanh menu": "Tải cho macOS ▾" (.dmg khi máy chủ có app đã dựng, và .zip), "Tải cho Windows ▾" (.msi, và file cài PowerShell cũ "AI-Worker-windows.zip"), "Tải cho Ubuntu (.deb)". Chưa đặt `MENUBAR_MAC_APP` thì "Tải cho macOS" phát gói cài dựa trên SwiftBar, không phải app.
- **Ubuntu:** mở file .deb bằng App Center, hoặc `sudo apt install ./ai-worker-menubar.deb`; apt tự cài thư viện AppIndicator, biểu tượng tự chạy mỗi lần đăng nhập, `sudo apt remove ai-worker-menubar` là gỡ.
- **Ghép máy:** quản lý bấm biểu tượng rồi nhập tài khoản và mã 6 số của chính mình; mỗi tài khoản ghép tối đa 2 máy. Quản lý chưa có tài khoản thì đọc mã trên biểu tượng cho quản trị nhập ở mục Màn hình TV.
- **App macOS được dựng một lần cho mỗi công ty** trên một máy Mac có Command Line Tools của Apple, rồi máy chủ phát app đó:

```bash
bash server/menubar/macos-app/build.sh https://dia-chi-bang-cua-ban auto "AI Worker"
```

Chép `server/menubar/macos-app/dist/*-menu-bar-mac-app.zip` lên máy chủ và đặt `MENUBAR_MAC_APP` là đường dẫn tới nó trong file env. App dùng chữ ký tạm, nên lần mở đầu phải vào System Settings > Privacy & Security > Open Anyway một lần.

## Tiện ích trình duyệt cho quản lý

Tiện ích cho Chrome hoặc Edge hiện trên biểu tượng số người đang chờ trả lời; bấm vào là mở đúng khung nhỏ của các app thanh menu. Tiện ích chỉ đọc một phần những gì màn hình treo tường thấy, không giữ mật khẩu, OTP hay cookie đăng nhập. Chi tiết: [docs/chrome-extension-spec.vi.md](chrome-extension-spec.vi.md).

1. **Đóng gói** trên máy giữ repo: `bash packaging/build-extension.sh` tạo `server/menubar/AI-Worker-extension.zip`; chép `server/` lên máy chủ và chạy `install.sh`, trang Quản trị hiện nút **Tiện ích Chrome, Edge** ở mục "Biểu tượng thanh menu". Sửa tiện ích thì chạy lại lệnh này.
2. **Cài tay** trên máy quản lý: giải nén file đó (hoặc chép thư mục `extensions/manager/`), mở `chrome://extensions` (Edge: `edge://extensions`), bật Developer mode, bấm "Load unpacked" rồi chọn thư mục đó.
3. **Ghép:** bấm biểu tượng, nhập địa chỉ bảng, cho phép truy cập đúng trang đó khi trình duyệt hỏi, rồi đọc mã 8 số cho quản trị.
4. **Quản trị duyệt** ở trang Quản trị, mục Màn hình TV, như với màn hình; dòng đó được ghi "Tiện ích trình duyệt". Thu hồi ở đó thì trong vòng một phút tiện ích báo "chưa ghép".

Đã ghép thì cửa sổ nhỏ chính là khung nhỏ của các app thanh menu (năm thẻ, Cài đặt có thông báo, ngôn ngữ và bỏ ghép). Cửa sổ chạy bản chép của `server/static/mini.js`, `mini.css` và logo, để trong `extensions/manager/mini/`: sửa các file đó thì chép lại (`cp server/static/mini.js server/static/mini.css extensions/manager/mini/`, và chép `server/menubar/icons/generic-black.png`, `generic-white.png` thành `extensions/manager/mini/logo-black.png`, `logo-white.png`), rồi phát lại thư mục.

Thử: `node tests/extension/check-extension.js` (chạy webhook trên máy với người giả, và báo lỗi khi bản chép khác bản gốc).

## Đăng nhập bằng Telegram (tuỳ chọn)

Ai dùng Telegram hằng ngày có thể đăng nhập bảng tổng bằng nút của Telegram thay vì gõ tên và mã. Tắt cho tới khi bạn cài; tên và mã 6 số luôn dùng được, và thao tác quản trị vẫn hỏi mã.

1. **Tạo bot** (trong app Telegram, điện thoại hay máy tính đều được):
   1. Tìm **@BotFather** và mở đúng tài khoản có dấu tích xanh.
   2. Gửi `/newbot`. BotFather hỏi tên: gõ tên người dùng sẽ thấy khi xác nhận đăng nhập, ví dụ `AI Worker`.
   3. BotFather hỏi username: gõ một tên kết thúc bằng `bot` và chưa ai dùng, ví dụ `congtyban_aiworker_bot`. Nếu báo đã có người dùng thì thử tên khác.
   4. BotFather trả lời "Done! Congratulations on your new bot", trong đó có dòng **"Use this token to access the HTTP API:"** và ngay sau là **token** (khoá của bot), dạng `1234567890:AAH...`. Giữ tin nhắn này để dùng ở bước 3. Token ký được lần đăng nhập của bất kỳ ai: không dán vào chat, không chụp màn hình.
   5. Tuỳ chọn: gửi `/setuserpic`, chọn bot rồi gửi logo công ty, để người dùng nhận ra bot khi xác nhận.
2. **Gắn bot với địa chỉ bảng tổng** (vẫn trong @BotFather): gửi `/setdomain`, chọn bot, rồi gửi tên miền bảng tổng, không có `https://`, ví dụ `board.company.com`. Đúng là: "Success! Domain updated."
3. **Khai token và username cho máy chủ.** Trên máy tính của bạn, chạy lệnh sau; lệnh hỏi token mà không hiện token lên màn hình:
   ```bash
   ssh -t <tài-khoản-quản-trị>@<máy-chủ> 'read -rsp "Bot token: " T; echo; read -rp "Bot username (no @): " N; printf "TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_BOT_NAME=%s\n" "$T" "$N" | sudo tee -a /etc/ai-worker.env >/dev/null && sudo systemctl restart ai-worker-webhook && echo DONE'
   ```
   Ở dòng `Bot token:` dán token ở bước 1.4 rồi Enter (màn hình không hiện gì là đúng). Ở dòng `Bot username (no @):` gõ username ở bước 1.3, ví dụ `congtyban_aiworker_bot`. Đúng là: hiện `DONE`, và trang đăng nhập có nút **Log in with Telegram** dưới chữ "hoặc".
   Hoặc sửa file bằng tay với `sudo nano /etc/ai-worker.env`, thêm hai dòng dưới đây, lưu lại, rồi chạy `sudo systemctl restart ai-worker-webhook`:
   ```
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_BOT_NAME=<username của bot, không có @>
   ```
4. **Mỗi người liên kết một lần:** đăng nhập bằng tên và mã, mở `/telegram` (hoặc nút **Telegram** trên bảng chi tiết), nhập mã 6 số, bấm **Log in with Telegram** và xác nhận trong Telegram. Lần sau chỉ cần bấm nút đó ở trang đăng nhập.

Máy chủ không bao giờ gọi Telegram: nút đưa trình duyệt sang trang đăng nhập của Telegram rồi quay về, máy chủ chỉ kiểm chữ ký bằng token. Trang đăng nhập không nạp gì từ Telegram. Một lần đăng nhập đã ký chỉ nhận trong 5 phút và một lần. Nếu văn phòng không vào được Telegram thì đăng nhập bằng tên và mã. Quản trị xem ai đã liên kết Telegram ở `/admin` và gỡ được ở đó; cấp lại khoá hoặc chuyển tài khoản sang treo tường cũng gỡ liên kết.

## Phát hành bản cập nhật

1. Đổi `version` trong `.claude-plugin/plugin.json`.
2. Trên máy giữ khoá ký, nhập mật khẩu khoá khi được hỏi:
   ```bash
   bash packaging/release.sh
   ```
   Tạo gói, manifest và chữ ký trong `server/releases/` (ngoài git).
3. Chép `server/` lên máy chủ và chạy `sudo bash install.sh`.

Máy nhân viên hỏi máy chủ tối đa 4 giờ một lần, thất bại thì 30 phút sau hỏi lại. Có bản mới thì thanh trên ô nhập hiện nút `Cập nhật`; bấm xong phải thoát hẳn app rồi mở lại. Việc phát hành chỉ tới máy đã cài từ bản 0.23.0 trở lên.

**An toàn:** máy nhân viên chỉ cài khi đúng chữ ký và mã kiểm tra, nên máy chủ bị chiếm cũng không phát được gói độc. Máy không kiểm được chữ ký (OpenSSH quá cũ) chỉ được báo có bản mới, không tự cài. Thư mục có `.git` không bao giờ tự cập nhật.

**Lùi bản:** phát hành lại bản cũ với chữ ký mới, hoặc trên máy đó đổi tên thư mục `ai-worker.old` cạnh thư mục plugin về tên cũ.

**Đổi khoá:** thêm khoá mới vào `~/.ai-worker-keys/allowed_signers`, phát hành một bản, rồi ký bằng khoá mới từ bản sau. Khoá chính lộ thì ký ngay bằng khoá dự phòng và bỏ khoá cũ ở bản đó.

## Dữ liệu gửi lên máy chủ

Chỉ gói công ty mới gửi; gói thường không gửi gì. Số liệu lên máy chủ của công ty, không gửi cho bên ngoài.

**Có gửi:** họ tên, email tài khoản Claude và email nhập lúc cài, mã máy ngẫu nhiên, dấu máy (mã phần cứng đã băm một chiều, để nhận ra cùng máy khi cài lại plugin, không hiện trên bảng), IP nội bộ, số phiên mở, đang làm, chờ trả lời, mô hình đang dùng, hạn mức tài khoản Claude, token và chi phí theo giờ, số việc giao cho từng trợ lý, tên loại trợ lý phụ đang chạy, trợ lý có trên máy, phiên bản plugin. Máy chủ tự ghi thêm IP công cộng của máy gửi, và nhớ các IP nội bộ mỗi máy đã dùng trong 30 ngày.

**Không gửi:** nội dung chat, câu hỏi, câu trả lời, tiêu đề chat, tên file, nội dung file, tên thư mục dự án, mô tả việc giao trợ lý.

**Ai xem được:** quản trị và chỉ xem thấy tên, email, IP; màn treo tường chỉ thấy tên rút gọn. Người có sudo trên máy chủ đọc được mọi số liệu. Xem `server/README.md`.

Trên máy, lịch sử phiên và số liệu nằm ở `~/.local/share/ai-worker/`. File có dấu hiệu chứa bí mật (.env, key, token…) chỉ ghi tên, không ghi nội dung.

Tắt gửi trên một máy: thêm `"sharing": { "enabled": false }` vào `~/.local/share/ai-worker/config.js`.

## Ngôn ngữ

Sản phẩm có tiếng Anh và tiếng Việt.

- **Các trang** (trang văn phòng trên máy, bảng tổng, trang quản trị): mỗi trang có nút chuyển EN / VI ở trên cùng, lựa chọn được nhớ trong trình duyệt. Lần đầu, trang theo ngôn ngữ của trình duyệt.
- **Plugin:** file cài ghi trường `language` (`"en"` hoặc `"vi"`) vào `~/.local/share/ai-worker/user.json`, plugin đọc trường này. Có thể sửa tay trường đó. Biến môi trường `AI_WORKER_LANG` (`en` hoặc `vi`) thắng giá trị trong file.
- **File cài:** `AI_WORKER_LANG=en` hoặc `vi` để ép ngôn ngữ; không đặt thì file cài theo ngôn ngữ của máy (trên Mac hỏi macOS, trên Windows lấy ngôn ngữ Windows), không có nữa thì tiếng Anh.
- **Máy chủ:** ngôn ngữ của mỗi trang là lựa chọn của người xem trước; `DEFAULT_LANG` (`en` hoặc `vi`) trong `/etc/ai-worker.env` đặt ngôn ngữ cho người chưa chọn, không đặt thì theo ngôn ngữ trình duyệt, rồi tiếng Anh.

## Tuỳ chỉnh và chi phí

`~/.local/share/ai-worker/config.js` được tạo một lần, không bị ghi đè khi cập nhật: đổi tên hiển thị, `usdRate` (mặc định 26000), và bật tắt từng trợ lý bằng `workers`.

Chi phí là con số Claude Code tính theo bảng giá API. Dùng gói thuê bao thì đây là chi phí quy đổi để so sánh, không phải số tiền bị trừ thật.

Không có Gemini, ChatGPT hay Gemma thì plugin vẫn chạy với mình Claude. File cài hỏi cài trợ lý nào.

Không có máy chủ nhưng có ổ dùng chung: bỏ `webhook`, ghi `folders` là đường dẫn ổ đã gắn. Cách này không có trang quản trị và không tự cập nhật.

## Chống tấn công làm nghẽn (DDoS)

Máy chủ giới hạn phần một máy được dùng: tổng số kết nối và số kết nối mỗi IP, cỡ header, thời gian sống của kết nối, bộ nhớ và số luồng (`MemoryMax`, `TasksMax`, `LimitNOFILE` trong file dịch vụ). Vì vậy khi bị tấn công, dịch vụ này chậm hoặc dừng, không kéo sập cả máy chủ. Phần mềm trên máy chủ không chặn được đợt tấn công lớn, vì lưu lượng đã làm nghẽn đường mạng trước khi tới nơi.
- **Tốt nhất:** chỉ cho mạng công ty truy cập, như file mẫu `server/aiworker.caddy`.
- **Nếu buộc phải mở ra Internet:** đặt sau dịch vụ bảo vệ như Cloudflare.
- **Dùng nginx thay Caddy:** đặt `proxy_set_header X-Forwarded-For $remote_addr;` và `proxy_set_header X-Forwarded-Proto $scheme;`, nếu không người ngoài có thể giả IP và vượt giới hạn đăng nhập. Webhook tin các header này khi đến từ proxy trên máy; `TRUST_PROXY=0` để tắt.
- **Một giới hạn vẫn còn:** mọi người trong gói cài dùng chung `INGEST_KEY`, nên nhân viên vẫn có thể gửi số liệu sai dưới tên người khác. Nếu gói bị lộ thì đổi mã và cài lại.
