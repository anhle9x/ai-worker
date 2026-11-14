Tiếng Việt | [English](TEST-PLAN.md)

# Kế hoạch kiểm thử

Phần nào được kiểm tự động mỗi lần đẩy code, phần nào vẫn cần người kiểm, và danh sách kiểm trước khi phát hành.

## 1. Kiểm thử tự động

GitHub Actions chạy `.github/workflows/test-install.yml` mỗi lần đẩy code. Chỉ phát hành khi mọi việc đều xanh.

| Việc | Máy | Kiểm gì | File |
|---|---|---|---|
| `code-check` | Ubuntu | Soát lỗi code Python (ruff); test các hook qua Claude Code CLI; hơn 100 test máy chủ; logic tiện ích Chrome với máy chủ thật chạy trong máy | `ruff.toml`, `tests/*.test.ts(x)`, `server/test_webhook.py`, `tests/extension/check-extension.js` |
| `build` | Ubuntu | Đóng gói; kiểm dữ liệu riêng; phần đầu YAML của skill; quy tắc hai ngôn ngữ | `packaging/build.sh`, `tests/test-check-clean.sh`, `tests/check-frontmatter.py`, `tests/check-i18n.py` |
| `ubuntu` | Ubuntu | File cài trên máy sạch, từng tình huống; cài máy chủ với systemd; script thanh menu; gói `.deb` được apt cài và gỡ; ảnh huy hiệu thông báo | `tests/linux/test-install.sh`, `tests/linux/test-server.sh`, `tests/menubar/test-menubar.sh`, `tests/menubar/test-deb.sh` |
| `windows` | Windows | File cài trên máy sạch, từng tình huống; biểu tượng cạnh đồng hồ; ảnh huy hiệu thông báo | `tests/windows/test-install.ps1`, `tests/menubar/test-menubar.ps1` |
| `windows-app` | Windows | Dựng `AI Worker.exe` và `.msi`; cài cho một người dùng, không cần quyền quản trị máy; ghép; đếm người đang chờ; gỡ | `tests/menubar/test-windows-app.ps1` |

### Phạm vi các test

| Phần | Test kiểm |
|---|---|
| Quyền của mọi đường dẫn máy chủ | `test_webhook.py` giữ toàn bộ bảng đường dẫn, báo lỗi nếu thêm đường mới mà chưa khai quyền |
| Đăng nhập, OTP, khoá sau khi nhập sai, nhập lại OTP cho thao tác tài khoản | `test_webhook.py` |
| Đăng nhập Telegram: chữ ký, hết hạn, dùng lại, chỉ liên kết được khi có mã và bước dùng một lần, mỗi tài khoản một Telegram, đường sang Telegram và quay về | `test_webhook.py`, lớp `TelegramLogin` |
| Mỗi vai nhận dữ liệu gì (màn hình treo tường không có email, IP) | `test_webhook.py` |
| Ghép TV, thanh menu, tiện ích; thu hồi; hết hạn | `test_webhook.py`, `check-extension.js`, các test thanh menu |
| Một máy không gửi thay người khác được; giới hạn gửi | `test_webhook.py` |
| Nhãn và ghim văn phòng trên bản đồ: ghim chạm nhau được vẽ cạnh nhau; khi nhiều văn phòng thì nhãn không còn chỗ trống bị ẩn; không nhãn nào đè nhãn khác, đè ghim của văn phòng khác hay đè danh sách văn phòng, không nhãn nào ra khỏi khung | `tests/check-map-layout.js` |
| Bản thử với dữ liệu giả lập: bật được, vào được bằng mã nó in ra, bỏ qua cấu hình của bảng thật, xoá dữ liệu khi dừng | `test_demo.py` |
| Chi phí theo giờ, không tính trùng khi mở lại phiên | `tests/cost.test.ts` |
| Không có câu hỏi, nội dung chat hay nội dung file bí mật nào rời máy | `tests/activity.test.ts`, `tests/edits.test.ts`, `tests/team.test.ts`, `tests/office.test.tsx` |
| Trợ lý phụ: chọn model Gemma, truyền tham số an toàn cho Codex | `tests/workers.test.ts` |
| Lưu trữ SQLite: chuyển file JSON cũ vào, phiên bản lược đồ, quyền file, nhiều luồng cùng ghi, sao lưu, xuất ngược ra JSON | `test_webhook.py` (`DatabaseStorage`), `tests/linux/test-server.sh` |
| Chọn ngôn ngữ và ngôn ngữ dự phòng | `tests/lang.test.ts` |
| Gói cài không có từ riêng, địa chỉ hay khoá | `tests/test-check-clean.sh` với `packaging/check-clean.sh` |

## 2. Chạy trên máy mình

```bash
python3 -m unittest test_webhook
```

Chạy trong `server/`. Kết quả đúng: `OK`.

```bash
npx -y @anthropic-ai/claude-code plugin test .
```

Chạy ở thư mục gốc repo. Kết quả đúng: mọi test đạt.

```bash
node tests/extension/check-extension.js
```

```bash
python3 tests/check-i18n.py
```

```bash
bash packaging/check-clean.sh
```

Kết quả đúng của lệnh cuối: `Clean.`

## 3. Phần vẫn cần người kiểm

Test tự động dùng máy chủ giả và trình duyệt giả. Trước khi phát hành bản có đụng tới các phần này, kiểm tay:

| Phần | Máy | Kiểm | Kết quả đúng |
|---|---|---|---|
| Cài plugin | Một máy Mac thật và một máy Windows thật | Chạy file cài, mở Claude Code, gõ `/office` | Trang văn phòng mở; máy hiện trên bảng tổng trong vòng 5 phút |
| Cập nhật | Máy đang ở bản trước | Chờ hoặc ép kiểm bản mới, bấm **Cập nhật**, mở lại app | Số phiên bản mới hiện trong `/office` |
| Đăng nhập OTP | Điện thoại thật có Google hoặc Microsoft Authenticator | Quét mã QR trên `/admin`, đăng nhập | Vào được; nhập sai 5 lần thì bị khoá 15 phút |
| Đăng nhập Telegram | Tài khoản Telegram thật và bot của máy chủ | Ở `/telegram` nhập mã rồi bấm nút, đăng xuất, bấm **Log in with Telegram** ở trang đăng nhập | Vào thẳng bảng điều khiển, không gõ tên hay mã |
| Màn hình TV | TV thật hoặc trình duyệt toàn màn hình | Mở `/tv`, duyệt mã trên `/admin` | Bảng hiện ra, không có email hay IP |
| Thanh menu macOS | Máy Mac thật | Cài `.dmg` hoặc `.zip`, ghép | Biểu tượng hiện số người chờ, có thông báo |
| Thanh menu Ubuntu | Ubuntu chạy X11 **và** Ubuntu chạy Wayland | Cài `.deb`, ghép | Biểu tượng hiện trên thanh trên cùng ở cả hai |
| Tiện ích Chrome | Chrome thật | Nạp tiện ích, ghép, mở khung bật lên | Khung và huy hiệu hiện số người chờ |
| Khổ điện thoại | Điện thoại hoặc cửa sổ 375 px | Mở bảng tổng | Không tràn ngang; bấm được các nút |

## 4. Trước khi phát hành

1. Mọi việc trên GitHub Actions đều xanh.
2. Đã kiểm tay mục 3 cho mọi phần mà bản này thay đổi.
3. Đã tăng `version` trong `.claude-plugin/plugin.json`, và `CHANGELOG.md` đã ghi các thay đổi.
   Nếu giao diện bảng tổng đổi, chụp lại `assets/dashboard.png` và `assets/dashboard.vi.png` từ máy chủ thử với người giả, không bao giờ từ máy chủ thật.
4. `bash packaging/release.sh` chạy thành công, và đã thử kiểm chữ ký trên một máy trước khi phát cho mọi người.
5. Ghi vào hồ sơ triển khai: bản nào, khi nào, ai phát hành ([OPERATIONS.vi.md](OPERATIONS.vi.md), mục 7).

## 5. Chỗ còn thiếu

- `hooks/register.tsx` và `web/ops.js` (chép sang `server/static/ops.js`) chưa có test riêng.
- Chưa có test tự động trên máy Mac thật.
- Chưa có test tự động trên Ubuntu Wayland; đang kiểm tay.
