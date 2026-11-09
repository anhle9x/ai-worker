[English](chrome-extension-spec.md) | Tiếng Việt

# Tiện ích Chrome cho quản lý: đặc tả

Những gì một tiện ích trình duyệt cho quản lý phải làm: thấy ai đang chờ trả lời mà không phải mở bảng. Đã làm trong `extensions/manager/` với các đường `/ext/...` của máy chủ; mã cho biết cái gì đang chạy, tài liệu này là chuẩn về những gì phải làm.

## Mục tiêu

Quản lý nhìn một cái, ở bất kỳ tab nào, là biết bao nhiêu nhân viên đang chờ Claude trả lời hoặc đang chờ chính họ trả lời, và mở bảng chỉ bằng một lần bấm. Tiện ích không bao giờ nhận nhiều dữ liệu hơn màn hình treo tường đang nhận, và không phải sửa gì trên máy nhân viên.

## Ngoài phạm vi

- **Theo dõi nhân viên trên trình duyệt của họ** (claude.ai bản web, trang khác). Việc này phải đọc trang của bên khác và theo dõi trình duyệt nhân viên: là một quyết định riêng về chính sách dữ liệu, không thuộc tiện ích này.
- **Đổi bất cứ dữ liệu nào trên máy chủ:** không làm việc quản trị, không duyệt màn hình, không sửa tên. Tiện ích chỉ đọc.
- **Email, IP nội bộ, tên tài khoản.** Tiện ích nhận đúng phần của màn hình treo tường, phần này đã bỏ các thông tin đó (`role_view`, vai `wall`). Cửa sổ nhỏ hiện đúng những gì màn hình treo tường và khung thanh menu hiện, kể cả hạn mức và chi phí hôm nay.
- **Chạy ngoài mạng công ty.** Máy chủ chỉ trả lời mạng công ty; ra ngoài thì tiện ích báo và chờ.
- **Firefox, Safari, trình duyệt điện thoại.** Chỉ Chrome và Edge, vì hai trình duyệt này chạy cùng một kiểu tiện ích (Manifest V3).
- **Đưa lên Chrome Web Store.** Cài tay từ thư mục do phòng IT phát.

## Người dùng

| Vai | Dùng | Làm được |
|---|---|---|
| Quản lý | Biểu tượng tiện ích và cửa sổ nhỏ của nó | Xem năm thẻ của khung thanh menu (Đang chờ, Đang làm, Hạn mức, Chi phí hôm nay, Cài đặt); đổi thông báo và ngôn ngữ; bỏ ghép; mở `/board` |
| Quản trị | `/admin` trên bảng | Duyệt hoặc thu hồi tiện ích đã ghép, như với màn hình treo tường |
| Máy chủ | `/ext/request-code`, `/ext/poll`, `/ext/state`, `/ext/mini`, `/ext/data`, `/ext/unpair` | Cấp mã ghép, đưa một phần số liệu của phần treo tường cho biểu tượng, trang khung thanh menu và phần treo tường cho cửa sổ nhỏ; thu hồi khoá khi tiện ích tự bỏ ghép |

## Phải làm gì

| Mã | Yêu cầu | Ở đâu |
|---|---|---|
| F1 | Lần đầu dùng, tiện ích hỏi địa chỉ bảng và hiện mã ghép; tiện ích không giữ mật khẩu, khoá OTP hay cookie đăng nhập | `popup.js` (form), `startPairing` trong `extensions/manager/core.js`; `/ext/request-code` trong `Handler.tv_pair` |
| F2 | Tiện ích chỉ chạy sau khi quản trị duyệt mã trong `/admin`, giống cách duyệt màn hình treo tường | `TvPairing`, `Handler.tv_pair` (`/ext/request-code`, `/ext/poll`) trong `server/webhook.py` |
| F3 | Quản trị thu hồi được tiện ích trong `/admin`; trong vòng một phút tiện ích hiện "chưa ghép" và đòi ghép lại | `checkBoard` trong `extensions/manager/core.js` (401 → chưa ghép); `PERM_DEVICE_KEY` trong `Handler.gate` |
| F4 | Biểu tượng hiện số người đang chờ trả lời; không ai chờ thì không hiện số. Biểu tượng trên thanh công cụ là chữ G một màu, tối trên thanh sáng và sáng trên thanh tối; cửa hàng, trang tiện ích và thông báo dùng chữ G nền xanh | `badgeFor` trong `extensions/manager/core.js`, `setBadge` trong `background.js`, `toolbarIcon` trong `background.js`, `offscreen.js` (quyền `offscreen`, chỉ để theo dõi chế độ sáng hay tối) |
| F5 | Cửa sổ nhỏ liệt kê người đang chờ hoặc đang làm, theo tên rút gọn như trên màn hình treo tường, kèm đã chờ bao lâu. Cửa sổ nhỏ hiện `waitingSince` của máy chủ (từ `WaitTracker`, qua `/ext/data`); biểu tượng và thông báo thì tính từ lần đầu tiện ích thấy người đó chờ, vì `/ext/state` không gửi lúc bắt đầu chờ | Biểu tượng và thông báo: `trackWaits` trong `extensions/manager/core.js`, `ext_state` trong `server/webhook.py`. Cửa sổ nhỏ: khung thanh menu (năm thẻ, ô xổ xuống và thẻ xác nhận tự vẽ): `showMini` và `window.MiniApi` trong `popup.js`, các bản chép trong `extensions/manager/mini/`, `get_ext_mini` / `get_ext_data` (`page_mini(True, browser=True)`, `role_view`) trong `server/webhook.py`; `render` trong `popup.js` chỉ dùng khi bảng còn bản cũ hoặc không đưa được trang |
| F6 | Ai chờ quá thời gian đặt sẵn thì quản lý nhận một thông báo của trình duyệt cho mỗi lần chờ, không phải mỗi phút một lần | `dueNotifications` trong `extensions/manager/core.js` |
| F7 | Quản lý tắt được thông báo và đặt được thời gian chờ; lựa chọn còn nguyên sau khi mở lại trình duyệt | `cleanSettings`, `saveSettings` trong `extensions/manager/core.js` (`chrome.storage.local`); thẻ Cài đặt của cửa sổ nhỏ lưu qua `MiniApi.save` trong `popup.js` |
| F8 | Bấm "Mở bảng" thì mở `/board` ở tab mới, nơi vẫn đăng nhập như bình thường | `MiniApi.openLink` trong `popup.js` (`boardPath` trong `core.js`), `openBoard` trong `extensions/manager/background.js` cho thông báo |
| F9 | Không tới được máy chủ (ngoài mạng, máy chủ tắt) thì biểu tượng chuyển xám và cửa sổ báo rõ; không bao giờ hiện số cũ như số hiện tại | `checkBoard`, `badgeFor` trong `extensions/manager/core.js` |
| F10 | Tiện ích chỉ xin quyền truy cập địa chỉ của bảng, không xin quyền mọi trang. Bảng phải dùng https; http thường chỉ cho `localhost` hoặc `127.0.0.1`, để thử | `optional_host_permissions` trong `extensions/manager/manifest.json`, `requestAccess` trong `popup.js`, `normalizeBoardUrl` trong `core.js` |
| F13 | "Bỏ ghép trình duyệt này", và ghép lại đè lên khoá cũ, cũng thu hồi khoá trên máy chủ (cố hết sức; nếu không tới được bảng thì dòng vẫn còn trong `/admin` để quản trị thu hồi) | `forget`, `startPairing` trong `extensions/manager/core.js`; `Handler.ext_unpair` (`/ext/unpair`) trong `server/webhook.py` |
| F11 | Chữ trong tiện ích theo ngôn ngữ của trình duyệt, tiếng Anh hoặc tiếng Việt; thẻ Cài đặt của cửa sổ nhỏ chọn được ngôn ngữ khác, lưu trong trình duyệt này, và thông báo, tiêu đề biểu tượng, màn ghép mã cũng theo lựa chọn đó | `extensions/manager/_locales/en`, `_locales/vi`; `tx` trong `server/webhook.py` cho cửa sổ nhỏ (`/ext/mini?lang=`), `chosenLang` và `MiniApi.setLang` trong `popup.js`, `pickLang` trong `core.js`, `loadLang` trong `background.js` |
| F12 | Nhật ký của máy chủ ghi lúc tiện ích được ghép, bị thu hồi, hoặc gọi bằng khoá đã thu hồi, chi tiết như với màn hình | `AuditLog`, `RevokedKeys`, `Handler.note_revoked_key` trong `server/webhook.py` (trường `kind: extension`) |

## Giới hạn

| Giới hạn | Giá trị |
|---|---|
| Hỏi máy chủ | Mỗi phút một lần (mỗi 5 giây chỉ khi cửa sổ nhỏ đang hiện mã ghép) |
| Chờ bao lâu thì thông báo (mặc định) | 10 phút (chọn được 5, 10, 15, 30, 60) |
| Một lần ghép dùng được | Như màn hình: 30 ngày, tự gia hạn khi còn dùng (`TV_SESSION_SECONDS`), tới một mức trần (`TV_CEILING_SECONDS`); đổi mạng vẫn giữ và được ghi vào nhật ký (`TvStore.touch`) |
| Mã ghép còn hạn | 10 phút (`TV_CODE_SECONDS`) |
| Trình duyệt | Chrome và Edge, Manifest V3 |
| Dữ liệu đọc được | Chỉ phần treo tường (`role_view` với vai `wall`) |
| Thư viện ngoài | Không có |

## Cách ghép

Tiện ích dùng quy trình ghép của TV (`TvPairing`, `TvStore`), nhưng qua `/ext/request-code` và `/ext/poll`: khoá chờ và phiên đi trong JSON trả về và header `Authorization`, không bao giờ trong cookie. Cookie sẽ nằm trong chính trình duyệt của quản lý và đè lên phiên đăng nhập bảng của họ. Yêu cầu gửi với `credentials: "omit"`. Tiện ích đã ghép đọc `/ext/state` cho biểu tượng, chỉ trả người đang chờ hoặc đang làm, theo tên treo tường, không email, IP hay chi phí. Cửa sổ nhỏ là khung thanh menu: đọc `/ext/mini` (trang, chỉ lấy bố cục và chữ; không script nào của bảng được chạy) và `/ext/data` (đúng `/data` của màn hình treo tường), cùng một khoá, rồi chạy bản `mini.js` của chính nó. Các bản chép trong `extensions/manager/mini/` phải giống `server/static/mini.*`, còn `logo-black.png` và `logo-white.png` trong đó phải giống `server/menubar/icons/generic-black.png` và `generic-white.png`; `node tests/extension/check-extension.js` báo lỗi khi khác.

Trong `/admin`, thẻ yêu cầu ghi "tiện ích trình duyệt" và bảng Màn hình TV đánh dấu dòng đó, để quản trị phân biệt laptop với TV. Tiện ích tính vào giới hạn 20 màn hình (`TV_MAX`).

Quá 5 phút không nhận được trả lời từ máy chủ thì tiện ích đếm lại các lần chờ, vì không biết lần chờ có liên tục không.
