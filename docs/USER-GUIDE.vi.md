Tiếng Việt | [English](USER-GUIDE.md)

# Văn phòng AI Worker: hướng dẫn sử dụng

Hướng dẫn này dành cho người dùng AI Worker hằng ngày, chia theo vai. Tìm vai của bạn trong bảng dưới và chỉ cần đọc phần đó.

Việc cài máy chủ và đóng gói file cài là việc của người quản trị, xem [INSTALL.vi.md](INSTALL.vi.md) và [server/README](../server/README.vi.md).

## Ai dùng phần nào

| Bạn là | Bạn dùng | Đọc phần |
|---|---|---|
| **Nhân viên** làm việc với Claude | Plugin trên máy mình: trang văn phòng, khung bên cạnh, thanh cập nhật | [1. Nhân viên](#1-nhân-viên) |
| **Quản lý** theo dõi đội | Bảng tổng trên trình duyệt, biểu tượng thanh menu hoặc tiện ích trình duyệt | [2. Quản lý](#2-quản-lý) |
| **Quản trị** bảng tổng | Trang Quản trị: tài khoản, màn hình TV, địa điểm, gói Team | [3. Quản trị](#3-quản-trị) |

Một số từ dùng trong hướng dẫn:

- **Phiên:** một cuộc trò chuyện với Claude trong thẻ Code của app Claude (hoặc lệnh `claude`).
- **Trợ lý phụ:** Gemini, ChatGPT và Gemma. Claude giao việc phụ cho các trợ lý này; có hay không đều được.
- **Bảng tổng:** trang của cả công ty, chạy trên máy chủ của công ty.
- **Mã OTP:** mã 6 số trong app Google Authenticator hoặc Microsoft Authenticator, 30 giây đổi một lần.

---

## 1. Nhân viên

### 1.1 Cài đặt

Người quản trị gửi bạn một file zip. Bên trong có `GUIDE.vi.txt`; tóm tắt:

1. Giải nén vào thư mục bất kỳ.
2. Bấm đúp `INSTALL-Mac.command` (Mac) hoặc `INSTALL-Windows.bat` (Windows). Trên Ubuntu, mở Terminal ở thư mục đó và gõ `bash INSTALL-Linux.sh`.
   - Lần đầu, máy Mac có thể chặn file: bấm chuột phải vào file, chọn **Open**, rồi **Open** lần nữa.
3. Gói của công ty sẽ hỏi họ tên. Gõ đúng tên đồng nghiệp vẫn gọi bạn.
4. Bộ cài hỏi có cài các trợ lý phụ không. Đồng ý với trợ lý công ty đang dùng; bỏ qua hết cũng được.
5. Khi cửa sổ báo **Xong**, bấm Enter, rồi thoát hẳn app Claude và mở lại. Trên Windows, đóng cửa sổ chỉ làm app ẩn đi: bấm chuột phải vào biểu tượng Claude cạnh đồng hồ rồi chọn **Exit**.

**Đúng là:** trong phiên mới, gõ `/office` thì trình duyệt mở một trang có phiên của bạn.

Cài xong có thể xoá thư mục vừa giải nén: plugin đã được chép vào thư mục người dùng.

### 1.2 Các lệnh

Gõ trong ô chat của thẻ Code:

| Lệnh | Tác dụng |
|---|---|
| `/office` | Mở trang văn phòng của máy này trên trình duyệt |
| `/office-pane` | Mở văn phòng trong khung bên cạnh ô chat |
| `/update` | Kiểm tra bản mới trên máy chủ công ty và cài |

### 1.3 Trang văn phòng (`/office`)

Trang chỉ hiện các phiên trên **máy của bạn**:

- **Sơ đồ:** mỗi phiên đang mở, nối với Claude và các trợ lý phụ. Phiên màu xanh lá là đang làm, màu vàng là đang chờ bạn trả lời.
- **Bấm vào một phiên** để xem kế hoạch, mức đầy của ngữ cảnh và chi phí.
- **Chi phí:** hôm nay, 7 ngày qua, và biểu đồ đổi được kiểu (đường, cột, nến; theo giờ hoặc theo ngày).
- **Hoạt động:** những việc đã làm trong các phiên đang mở, có ô lọc.
- **Models & quota:** đã dùng bao nhiêu hạn mức 5 giờ và 7 ngày của tài khoản Claude. Từ 80% thì chuyển đỏ, và một thanh hiện trên ô chat. Bấm **Ẩn** để ẩn thanh đó cho tới khi mức dùng tăng tiếp.

Plugin không bao giờ tự đổi mô hình. Muốn tiết kiệm hạn mức, tự gõ `/model sonnet`.

Trang mở từ một file trên máy bạn. Nội dung chat không đi đâu cả.

**Chi phí** tính theo giá API. Với gói thuê bao, đó là con số quy đổi để so sánh, không phải tiền bị trừ.

### 1.4 Trợ lý phụ

Claude giao việc phụ cho các trợ lý theo quy định của công ty:

| Trợ lý | Giỏi việc gì | Quy tắc dữ liệu |
|---|---|---|
| **Gemma** | Tóm tắt, phân loại, chạy ngay trên máy bạn | Trợ lý duy nhất được nhận dữ liệu nhạy cảm, vì dữ liệu không rời máy |
| **ChatGPT** | Xem lại code, tìm lỗi | Không bao giờ nhận tên người, tài liệu nội bộ, số liệu hay mật khẩu |
| **Gemini** | Tra cứu web, tạo ảnh | Như ChatGPT |

Trước khi gửi gì sang ChatGPT hay Gemini, Claude hỏi bạn, trừ khi quy định công ty đã cho phép sẵn. Trợ lý nào chưa cài thì bàn của trợ lý đó bị ẩn trong văn phòng.

Đăng nhập sau: mở Terminal hoặc PowerShell, gõ `codex login` (ChatGPT) hoặc `agy` (Gemini).

### 1.5 Cập nhật

Khi người quản trị phát hành bản mới, thanh trên ô chat hiện **Có bản mới** kèm nút **Cập nhật**; gõ `/update` cũng được.

1. Bấm **Cập nhật** và chờ báo đã cài xong.
2. Trong app Claude desktop (Mac, Windows, Linux), một câu hỏi hiện ra đề nghị đóng app rồi mở lại: chọn **Mở lại ngay** (các phiên đang làm dở sẽ dừng), hoặc **Để sau** rồi tự làm. Ở nơi khác thì thoát hẳn app Claude rồi mở lại.

Bản mới chỉ được cài khi có chữ ký đúng của người quản trị. Máy phải ở trong mạng công ty mới tải được. Bản trước được giữ trong thư mục `ai-worker.old` cạnh thư mục plugin.

### 1.6 Máy bạn gửi những gì

Chỉ gói của công ty mới gửi; gói thường không gửi gì.

- **Gửi lên máy chủ công ty:** họ tên, email tài khoản Claude, mã máy, địa chỉ IP, số phiên đang mở, đang làm, đang chờ, token, chi phí, hạn mức, số việc giao cho từng trợ lý, phiên bản plugin.
- **Không bao giờ gửi:** nội dung chat, câu hỏi, câu trả lời, tên file, nội dung file, tên dự án.

Muốn tắt gửi trên một máy: thêm `"sharing": { "enabled": false }` vào `config.js` (xem 1.7) và báo người quản trị.

### 1.7 Tuỳ chỉnh của bạn

Hai file trong thư mục người dùng, ở `.local/share/ai-worker/` (Windows: `%USERPROFILE%\.local\share\ai-worker\`):

| File | Sửa được gì |
|---|---|
| `user.json` | Họ tên, email, và `language` (`"en"` hoặc `"vi"`) |
| `config.js` | Tên hiển thị, `usdRate` (tỉ giá đô la ra đồng, chỉ dùng khi hiện tiếng Việt), bật tắt từng trợ lý trong `workers` |

Cập nhật không bao giờ ghi đè `config.js`. Các trang trên trình duyệt còn có nút **EN / VI** ở trên cùng.

### 1.8 Gỡ cài đặt

Trong Terminal hoặc PowerShell:

```bash
claude plugin uninstall ai-worker@ai-worker
claude plugin marketplace remove ai-worker
```

Rồi xoá thư mục `claude-plugins-ai-worker` trong thư mục người dùng.

### 1.9 Gặp lỗi

| Hiện tượng | Cách xử lý |
|---|---|
| Gõ `/office` không có gì | Thoát hẳn app Claude rồi mở lại, hoặc gõ `/reload-plugins` |
| Bộ cài báo không tới được máy chủ | Số liệu của bạn chưa lên bảng tổng. Kiểm tra máy đang ở mạng công ty và gửi ảnh chụp cho người quản trị |
| Thiếu bàn của một trợ lý phụ | Trợ lý đó chưa cài hoặc chưa đăng nhập; xem 1.4 |
| Cập nhật không được | Kiểm tra máy đang ở mạng công ty; nếu vẫn lỗi, xin người quản trị gói cài mới |

---

## 2. Quản lý

### 2.1 Đăng nhập bảng tổng

1. Xin người quản trị một tài khoản. Họ gửi bạn một mã QR.
2. Trên điện thoại, mở **Google Authenticator** (hoặc Microsoft Authenticator), bấm **+**, chọn **Quét mã QR** và quét mã đó.
3. Trên máy tính, mở địa chỉ bảng tổng người quản trị đưa (ví dụ `https://board.company.com`).
4. Gõ tên tài khoản và mã 6 số đang hiện trong app, bấm **Đăng nhập**.

**Đúng là:** bảng tổng mở ra. Một lần đăng nhập dùng được 8 giờ. Mỗi mã chỉ dùng được một lần; bị từ chối thì chờ mã kế tiếp.

**Bằng Telegram** (khi người quản trị đã bật): đăng nhập một lần bằng tên và mã, mở bảng chi tiết, bấm **Telegram**, nhập mã 6 số rồi bấm nút Telegram. Từ đó về sau, bấm **Log in with Telegram** ở trang đăng nhập và xác nhận trong Telegram. Thao tác quản trị vẫn hỏi mã 6 số.

Bảng tổng chỉ mở được từ mạng công ty.

### 2.2 Bảng tổng

Trang tự cập nhật 10 giây một lần:

- **Dải trạng thái trên cùng:** bao nhiêu người đang làm, đang chờ, đang rảnh, và các cảnh báo như có người gần hết hạn mức.
- **Sơ đồ:** mỗi người nối với Claude và các trợ lý phụ; hạt sáng chạy nghĩa là đang làm hoặc đang giao việc. **Bấm vào một người** để xem số liệu của người đó.
- **Bản đồ nhiệt:** ai dùng nhiều nhất, vào giờ nào, trong 24 giờ qua.
- **Chỉ số hôm nay, mức dùng từng trợ lý, nhật ký sự kiện** (mới nhất ở trên) **và biểu đồ 24 giờ.**
- **Chế độ xem:** chuyển giữa sơ đồ và bản đồ các chi nhánh, dạng 2D hoặc 3D.
- **Tua lại 24 giờ:** xem lại diễn biến trong ngày; **Về hiện tại** để quay về số liệu đang chạy.
- **Giải thích** cho biết mỗi màu, mỗi đường nghĩa là gì.
- **Bảng chi tiết** (`/board`): cùng số liệu dạng bảng, có cột Plugin cho biết máy nào chưa lên bản mới nhất.

Màu: xanh lá là đang làm, vàng là đang chờ trả lời, xanh nhạt là đang rảnh, xám là không kết nối.

### 2.3 Biểu tượng thanh menu

Một biểu tượng trên thanh menu (Mac), cạnh đồng hồ (Windows) hoặc thanh trên cùng (Ubuntu) cho biết bao nhiêu người đang chờ trả lời, kể cả khi đã đóng trình duyệt. Biểu tượng chuyển xanh dương khi có người chờ quá thời gian bạn đặt.

**Cài:**

1. Vào trang **Quản trị** nếu bạn có quyền, hoặc nhờ người quản trị; các file cài nằm ở mục **Biểu tượng thanh menu**.
2. Tải bản cho máy của bạn:
   - **Mac:** **Tải cho macOS ▾**, chọn **AI-Worker.dmg** (hoặc **AI-Worker-mac.zip**; máy chủ chưa có .dmg thì chỉ có một nút). Mở ra và kéo **AI Worker** vào Applications. Lần mở đầu tiên, vào **System Settings > Privacy & Security** và bấm **Open Anyway**.
   - **Windows:** **Tải cho Windows ▾ > AI-Worker.msi**. Windows sẽ cảnh báo 2–3 lần vì file chưa có chữ ký của hãng lớn; chọn **Keep**, rồi **More info > Run anyway**. Tích ô đồng ý điều khoản và bấm **Install**. Không cần mật khẩu quản trị máy.
   - **Ubuntu:** **Tải cho Ubuntu (.deb)**, mở bằng App Center, hoặc gõ `sudo apt install ./ai-worker-menubar.deb`.
3. Chỉ cài file bạn tự tải từ bảng tổng. Không mở file cài nhận qua email hay chat.

**Ghép (chỉ lần đầu):** bấm biểu tượng, chọn **Ghép bằng tài khoản của tôi**, gõ tên tài khoản và mã 6 số. Mỗi tài khoản ghép được 2 máy.

**Đúng là:** trong vòng 1 phút biểu tượng hiện số người đang chờ; bấm vào thì mở khung nhỏ có năm thẻ: **Đang chờ, Đang làm, Hạn mức, Chi phí hôm nay, Cài đặt**.

Trong **Cài đặt** có thể bật tắt thông báo và chọn chờ bao lâu thì báo (5, 10, 15, 30 hoặc 60 phút; mặc định 10), đổi ngôn ngữ, tự chạy khi đăng nhập, bỏ ghép, hoặc gỡ app. Mỗi lần có người chờ lâu chỉ báo một lần, không báo mỗi phút.

**Cập nhật:** tải file cài mới từ bảng tổng và cài đè lên bản cũ. Máy vẫn giữ ghép.

### 2.4 Tiện ích trình duyệt

Cho quản lý thích dùng trình duyệt: tiện ích Chrome hoặc Edge hiện số người đang chờ trên biểu tượng, bấm vào mở đúng khung nhỏ như trên.

1. Xin người quản trị file `AI-Worker-extension.zip` (nút **Tiện ích Chrome, Edge** ở trang Quản trị). Giải nén vào chỗ cố định, ví dụ Documents: xoá thư mục đi thì tiện ích hỏng.
2. Mở `chrome://extensions` (Edge: `edge://extensions`), bật **Developer mode**, bấm **Load unpacked**, chọn thư mục `AI-Worker-extension`.
3. Bấm biểu tượng tiện ích, gõ địa chỉ bảng tổng, cho phép truy cập đúng trang đó, rồi đọc mã 8 số cho người quản trị.

**Đúng là:** trong vòng 1 phút sau khi người quản trị duyệt, biểu tượng hiện số người đang chờ.

Tiện ích không giữ mật khẩu, mã OTP hay cookie đăng nhập nào.

---

## 3. Quản trị

Mọi việc trong phần này làm ở trang **Quản trị** (liên kết **Quản trị** trên cùng bảng tổng). Chỉ tài khoản có vai quản trị mới mở được.

### 3.1 Các vai

| | Quản trị | Chỉ xem | Treo tường |
|---|---|---|---|
| Trang Quản trị | Có | Không | Không |
| Email, IP nội bộ, bảng chi tiết | Có | Có | Không |
| Giữ đăng nhập | 8 giờ | 8 giờ | 7 ngày |

Máy chủ tự kiểm vai; không chỉ dựa vào việc ẩn nút.

### 3.2 Tài khoản

- **Tạo tài khoản:** gõ tên (chữ không dấu, số, `.`, `_`, `-`), chọn vai, nhập lại mã OTP của bạn. Mã QR hiện ra: gửi riêng cho người đó, rồi bấm **Đã quét, ẩn**.
- **Đổi vai:** có hiệu lực ngay, không ai bị đăng xuất.
- **Cấp lại khoá:** nếu nghi bị lộ, kết thúc các phiên của người đó trước, rồi cấp lại khoá và gửi mã QR mới.
- **Xoá tài khoản:** đồng thời bỏ các máy có biểu tượng thanh menu mà tài khoản đó đã ghép.

Tạo, cấp lại, đổi vai và xoá đều hỏi lại mã OTP của bạn, có hiệu lực 5 phút. Không xoá hay hạ vai được người quản trị cuối cùng, và không ai tự xoá mình được.

**Mất hết người quản trị?** Người có quyền sudo trên máy chủ chạy `sudo bash manage-otp.sh --rescue <tên>` trong thư mục `server/`.

### 3.3 Màn hình TV

1. Trên TV, mở địa chỉ bảng tổng. TV thông minh tự hiện mã 8 số; với máy tính cắm vào TV, bấm **Màn hình treo tường: ghép bằng mã** ở trang đăng nhập.
2. Quét mã QR trên TV bằng điện thoại đang ở mạng công ty, hoặc gõ mã ở mục **Màn hình TV** trên trang Quản trị.
3. Kiểm thiết bị và IP, chọn **Thêm màn hình mới** (hoặc thay màn hình cũ để không sinh thêm dòng), đặt tên như "TV phòng họp", bấm **Duyệt**.

**Đúng là:** vài giây sau TV hiện bảng treo tường. Bảng này chỉ hiện tên rút gọn, không có email hay IP.

Trong danh sách có thể **Đổi tên**, **Tải lại** màn hình từ xa, hoặc **Thu hồi**. Tối đa 20 màn hình; màn hình không dùng quá 30 ngày tự rời danh sách. Muốn máy cắm TV tự mở bảng khi khởi động: mở `/tv` trên máy đó và tải file ở cuối trang.

Biểu tượng thanh menu và tiện ích trình duyệt ghép bằng mã cũng hiện ở đây, có ghi rõ loại.

### 3.4 Địa điểm và chi nhánh

Bảng tổng gom máy theo mạng mà máy gửi số liệu từ đó.

- **Nhóm máy chưa đặt tên:** chọn một nhóm, chọn tỉnh hoặc thành phố, đặt tên (để trống thì lấy tên tỉnh).
- Máy mới ở cùng mạng tự vào đúng chi nhánh.
- Nhân viên ở nhà, dùng 4G hay đi công tác nằm trong nhóm "Di động / chưa gắn".

### 3.5 Gói Team

Chi phí ngoài plugin (Claude trên điện thoại và web) lấy từ báo cáo của gói Team:

1. Trong phần quản trị gói Claude Team, tải file CSV **Export spend report**.
2. Trên trang Quản trị, ở mục **Gói Team**, bấm **Nạp CSV** và chọn file.
3. Ở mục **Từng người**, tích **Đánh dấu sale** cho đội sale thị trường nếu muốn tính riêng.

Gói cá nhân (Pro, Max) không có trong báo cáo này.

### 3.6 Phiên đang mở và nhật ký

- **Phiên đang mở:** ai đang đăng nhập, từ đâu. Bấm **Kết thúc** một phiên, hoặc **Kết thúc các phiên khác** để đăng xuất mọi người khác.
- **Nhật ký:** đăng nhập, thay đổi và các lần bị từ chối trong tháng đã chọn. Giữ 12 tháng; trang hiện 300 dòng mới nhất.

### 3.7 File cài biểu tượng thanh menu

Mục **Biểu tượng thanh menu** có các file cài cho quản lý (xem 2.3). Máy chủ tự điền địa chỉ của mình vào từng file, nên quản lý chỉ việc cài và ghép.

---

## Câu hỏi thường gặp

- **Quản lý có đọc được nhân viên đã gõ gì cho Claude không?** Không. Nội dung chat không bao giờ được gửi; bảng tổng chỉ có số liệu.
- **Ra ngoài văn phòng có dùng được không?** Plugin dùng được ở mọi nơi. Gửi số liệu, xem bảng tổng và cập nhật thì cần mạng công ty.
- **Có bắt buộc cài Gemini, ChatGPT hay Gemma không?** Không. Mọi thứ chạy được chỉ với Claude.
- **Chi phí có phải tiền thật không?** Đó là giá theo bảng giá API. Với gói thuê bao, chỉ để so sánh.
- **Báo lỗi ở đâu?** Chụp màn hình gửi người quản trị. Với dự án mã nguồn mở, mở issue trên GitHub; lỗi bảo mật thì theo [SECURITY.vi.md](../SECURITY.vi.md).
