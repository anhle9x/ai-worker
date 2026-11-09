[English](menu-bar-spec.md) | Tiếng Việt

# Biểu tượng trên thanh menu cho quản lý: đặc tả

Biểu tượng trên thanh menu của macOS, khay hệ thống của Windows và thanh trên cùng của Ubuntu: quản lý thấy ai đang chờ trả lời, bấm vào thì mở một khung nhỏ. Đã làm và đang chạy; mã cho biết thực tế đang chạy gì, tài liệu này được sửa theo khi hai bên khác nhau. Khung nhỏ là trang `/mini` trên máy chủ, dùng chung cho mọi hệ điều hành.

## Mục tiêu

Quản lý thấy ngay trên thanh menu, kể cả khi đã tắt trình duyệt, có bao nhiêu người đang chờ và ai chờ lâu, rồi mở bảng chỉ bằng một lần bấm. Giao diện chỉ thiết kế một lần, trên máy chủ. Biểu tượng không bao giờ nhận nhiều dữ liệu hơn màn hình treo tường, và không thêm thư viện ngoài, trừ bộ WebView2 của Microsoft cho khung Windows (xem `THIRD-PARTY.md`).

## Ngoài phạm vi

- **Email, IP nội bộ, tên đầy đủ.** Biểu tượng và khung nhận đúng phần của màn hình treo tường (`role_view`, vai `wall`).
- **Đổi dữ liệu trên máy chủ**, trừ cài đặt thông báo của chính máy này và việc bỏ ghép nó.
- **Chạy ngoài mạng công ty.** Máy chủ chỉ trả lời mạng công ty.
- **Máy nhân viên.** Biểu tượng chỉ dành cho quản lý; máy nhân viên không cài gì thêm.
- **App macOS có chữ ký Apple.** App dùng chữ ký tạm, nên lần mở đầu phải bấm "Open Anyway" một lần. Có Apple Developer ID thì hết bước này; `build.sh` đã nhận sẵn.

## Người dùng

| Vai | Dùng | Làm được |
|---|---|---|
| Quản lý | Biểu tượng và khung `/mini` | Xem số đếm và danh sách, đổi thông báo, ngôn ngữ và tự chạy khi đăng nhập, bỏ ghép, gỡ app, tự ghép máy bằng tài khoản và OTP của mình |
| Quản trị | `/admin` | Tải gói cài, ghép hộ một máy bằng mã của nó, xem ai đã ghép máy nào, thu hồi |
| Máy chủ | `/mini`, `/mini/pair`, `/mini/state`, `/mini/handoff`, `/mini/settings`, `/mini/unpair`, `/data`, các đường ghép | Trả trang khung, kiểm OTP, cấp mã dùng một lần, trả số liệu phần treo tường |

## Phải làm gì

| Mã | Yêu cầu | Ở đâu |
|---|---|---|
| F1 | `/mini` vừa khung rộng khoảng 360: tên và giờ cập nhật, năm thẻ (Đang chờ, Đang làm, Hạn mức, Chi phí hôm nay, Cài đặt), danh sách, "Mở bảng"; theo giao diện sáng hay tối | `page_mini` trong `server/webhook.py`, `server/static/mini.js`, `mini.css` |
| F2 | Đang chờ hiện mỗi người đã chờ bao lâu; Hạn mức hiện mọi khung tài khoản báo về, gói không giới hạn 5 giờ thì không có khung đó | `WaitTracker`, `mini.js` |
| F3 | Quản lý tự ghép máy của mình: biểu tượng mở `/mini/pair` với mã sau dấu `#`, quản lý nhập tài khoản và mã 6 số, không cần ai khác duyệt | `mini_self_pair`, `TvPairing.self_approve` |
| F4 | Tự ghép kiểm OTP với cùng giới hạn như đăng nhập, chỉ nhận tài khoản vai xem hoặc quản trị, chỉ yêu cầu cùng IP, mỗi tài khoản tối đa `MENUBAR_PER_ACCOUNT` máy | `mini_self_pair`, `LoginGate.check_otp` |
| F5 | Xoá tài khoản, đổi sang vai treo tường, hay kết thúc phiên của tài khoản thì gỡ các máy nó đã tự ghép | `TvStore.revoke_owner` |
| F6 | Quản trị vẫn ghép hộ được bằng mã máy hiện ra, như ghép màn hình treo tường | `TvPairing`, `/admin` |
| F7 | Biểu tượng: chỉ logo, logo kèm số, logo xanh lam `#1A56C8` khi có người chờ quá hạn, mờ khi không tới được máy chủ, hình chìa khoá khi chưa ghép | `main.swift`, `ai-worker.1m.py`, `ai-worker-tray.ps1`, `ai-worker-indicator.py` |
| F8 | macOS: app riêng hiện khung dưới biểu tượng; khung không kéo tách ra được, nền mờ, cao theo trang | `server/menubar/macos-app/main.swift` |
| F9 | Ubuntu: biểu tượng AppIndicator trong gói .deb máy chủ tự đóng, có sẵn địa chỉ (script Argos vẫn dùng được); Windows: app `AI Worker.exe` (C#, .NET Framework 4.8) ở khay, cài cho riêng người dùng từ `AI Worker.msi` (không cần quyền quản trị; cài đè lên bản đang chạy thì tự đóng bản cũ trước, không đòi khởi động lại); mở `/mini` trong khung nhỏ không viền của riêng nó (WebView2), giống khung Mac; WebView2 lỗi thì quay về cửa sổ Edge gọn; mã hoá phiên bằng DPAPI và thay bản PowerShell cũ (`ai-worker-tray.ps1`, vẫn phát làm gói .zip dự phòng) | `ai-worker-indicator.py`, `menubar_deb`, `ai-worker.1m.py`, `windows-app/Program.cs`, `AIWorker.wxs`, `menubar-popup.cs`, `ai-worker-tray.ps1` |
| F10 | Khung nhận phiên của máy qua mã dùng một lần, sống `MINI_HANDOFF_SECONDS` và dùng được một lần | `MiniHandoff`, `get_mini` |
| F11 | Ai chờ quá thời gian đặt thì báo một lần cho mỗi lần chờ, không phải mỗi phút. Trên Windows, bấm vào thông báo thì mở khung, qua đường dẫn `ai-worker-open:` đăng ký trong `HKCU\Software\Classes` | `main.swift`, `remind`, `ToNotify`, `Notify-Long` |
| F12 | Cài đặt, trên mọi hệ điều hành: bật tắt thông báo và thời gian chờ (lưu trên máy chủ cho máy này), ngôn ngữ, tự chạy khi đăng nhập (app macOS: bật sau lần mở đầu), bỏ ghép, gỡ app (macOS: bỏ ghép, đưa vào Thùng rác, thoát; Windows và Ubuntu: bỏ ghép rồi gỡ app) | `mini.js`, `TvStore.set_mini_settings`, `main.swift`, `ai-worker-tray.ps1`, `ai-worker-indicator.py` |
| F13 | Không tới được máy chủ thì biểu tượng mờ và khung báo rõ; không bao giờ hiện số cũ như số hiện tại | `main.swift`, các script |
| F14 | Trang Quản trị có "Tải cho macOS", "Tải cho macOS (.dmg)" khi `build.sh` để file đó cạnh app, "Tải cho Windows (.msi)" khi có `server/menubar/AI-Worker.msi` (máy chủ tự điền địa chỉ của nó vào gói), "Tải cho Windows" hoặc "Windows bản cũ (.zip)" cho biểu tượng PowerShell, và "Tải cho Ubuntu (.deb)"; có đặt `MENUBAR_MAC_APP` thì macOS nhận app dựng cho máy chủ này, không thì gói cài SwiftBar | `get_menubar_installer`, `menubar_msi`, `menubar_zip`, `admin.js` |
| F15 | App macOS theo ngôn ngữ của máy Mac, trừ khi dựng cố định một ngôn ngữ. Khung dùng ngôn ngữ chọn trong Cài đặt, lưu trong cookie `lang`; biểu tượng Windows và Ubuntu mở `/mini?…&lang=`, nên khung và menu ở khay luôn khớp nhau | `main.swift`, `tx`, `get_mini`, `mini.js` |
| F16 | Danh sách màn hình của quản trị ghi máy thanh menu là "Thanh menu trên Mac/Windows/Linux", ghi ai đã tự ghép, và không kiểm phiên bản trang cho nó | `device_label`, `admin.js` |

## Giới hạn

| Giới hạn | Giá trị |
|---|---|
| Biểu tượng hỏi máy chủ | Mỗi phút một lần |
| Chờ bao lâu thì báo (mặc định) | 10 phút (5, 10, 15, 30 hoặc 60) |
| Số máy một tài khoản tự ghép | 2 (`MENUBAR_PER_ACCOUNT`) |
| Mã dùng một lần cho khung | 90 giây, dùng một lần |
| Một lần ghép dùng được | 30 ngày, tự gia hạn khi còn dùng, tối đa 1 năm |
| Dữ liệu biểu tượng đọc được | Chỉ phần treo tường |
| App macOS | macOS 13 trở lên, chip Apple và Intel, dựng bằng `swiftc` trong Command Line Tools của Apple |
| Ubuntu | Python 3 kèm python3-gi, GTK, WebKit2GTK và thư viện AppIndicator, apt tự cài từ gói .deb; nên có Chrome hoặc Chromium |
| Windows | .NET Framework 4.8 (có sẵn trong Windows 10 và 11) và WebView2 Runtime; thiếu WebView2 thì khung mở trong cửa sổ Edge gọn. Gói .zip dự phòng chỉ cần PowerShell có sẵn |

## Dựng app macOS

Trên một máy Mac có Command Line Tools của Apple (`xcode-select --install`), mỗi công ty một lần:

```bash
bash server/menubar/macos-app/build.sh https://dia-chi-bang-cua-ban auto "AI Worker"
```

Lệnh này ghi địa chỉ bảng vào app trước khi ký, và tạo `server/menubar/macos-app/dist/AI-Worker-menu-bar-mac-app.zip`. Chép file zip lên máy chủ và đặt `MENUBAR_MAC_APP` là đường dẫn tới nó. Người chỉ dùng app không phải cài gì.
