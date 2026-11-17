[English](SECURITY.md) | Tiếng Việt

# Chính sách bảo mật

## Báo một lỗi

Đừng mở issue công khai cho lỗi bảo mật: ai cũng có thể lợi dụng trước khi lỗi được sửa.

1. Báo kín trên GitHub: tab **Security** của repo này, rồi **Report a vulnerability**.
2. Nếu không làm được, nhắn riêng qua Telegram tới [t.me/anhle9x](https://t.me/anhle9x), nói là có báo cáo bảo mật; chi tiết gửi theo cách hai bên thống nhất.

Ghi rõ phần bị ảnh hưởng (plugin, máy chủ, file cài, thanh menu), phiên bản, và các bước để thấy lỗi. Đừng gửi dữ liệu của người thật.

## Sau khi báo

- Bạn nhận trả lời trong vòng 7 ngày.
- Lỗi được xác nhận sẽ sửa trong bản phát hành kế tiếp, và tên bạn được ghi trong phần ghi chú phát hành nếu bạn muốn.
- Xin giữ kín tới khi có bản sửa, hoặc chậm nhất 90 ngày.

## Phiên bản được hỗ trợ

Chỉ bản phát hành mới nhất nhận bản sửa bảo mật.

## Dự án được thiết kế để chống những gì

AI Worker được thiết kế để chống tám rủi ro web thường gặp dưới đây, theo danh sách OWASP Top 10 năm 2013. Mã đã được rà soát cùng các trợ lý AI và các tấn công chính đã được chạy lại trên bản thử. Chưa có công ty bảo mật độc lập nào kiểm định, và không phần mềm nào cam kết được là không có lỗi.

| Rủi ro | Sản phẩm làm gì | Còn lại |
|---|---|---|
| **Giả mạo yêu cầu (CSRF)** | Cookie phiên đặt `SameSite=Strict`. Yêu cầu sai `Origin` bị từ chối, thao tác quản trị còn từ chối cả khi thiếu `Origin`. Gửi số liệu dùng mã trong header, không dùng cookie | Trình duyệt cũ không có `SameSite` chỉ còn dựa vào kiểm tra `Origin` |
| **Chèn mã vào trang (XSS)** | Trang máy chủ thoát ký tự đặc biệt, script trên trang đưa dữ liệu vào dưới dạng chữ. Trang máy chủ gửi Content-Security-Policy, chỉ cho chạy script cùng trang | Chính sách vẫn cho phép style viết trực tiếp. Trang trên máy không có chính sách này; trang chỉ hiện dữ liệu của chính máy đó |
| **Nhúng mã (Injection)** | Máy chủ không chạy lệnh shell, và các câu truy vấn SQLite chỉ nhận giá trị qua tham số, không bao giờ ghép chữ vào câu truy vấn. Yêu cầu lấy file được đối chiếu với danh sách hoặc mẫu cố định. Plugin chạy chương trình bằng danh sách tham số. Chữ cho ChatGPT đi qua đầu vào chuẩn, và Gemini bị từ chối nếu phải chạy qua file `.cmd` hoặc `.bat` trên Windows | Tài liệu vẫn có thể tìm cách điều khiển trợ lý qua đoạn chữ nó nhận. Vì vậy ChatGPT chạy trong sandbox chỉ đọc |
| **Lỗi xác thực** | Mỗi tài khoản có khoá OTP riêng, mỗi mã chỉ dùng một lần. Số lần sai bị giới hạn theo IP và theo tài khoản. Mã phiên ngẫu nhiên và có hạn; cookie đặt `HttpOnly`, và `Secure` khi dùng HTTPS. Đổi tài khoản hay màn hình TV phải nhập lại OTP | OTP là yếu tố đăng nhập duy nhất, nên hãy giữ danh sách IP. Khi bật đăng nhập Telegram, khoá bot ký được lần đăng nhập của bất kỳ ai: chỉ để trong file env của máy chủ |
| **Truy cập trực tiếp đối tượng (IDOR)** | Người xem và màn hình treo tường nhận một bản đã lọc theo vai, không có cách xin một bản ghi theo mã. Thao tác lên một tài khoản hay màn hình cụ thể chỉ dành cho quản trị | Người xem được thấy số của mọi người, đây là chủ ý. Ai có mã gửi dùng chung đều gửi được dưới một tên chưa gắn với máy nào |
| **Thiếu kiểm soát quyền theo chức năng** | Mọi đường dẫn được liệt kê kèm quyền, một cổng kiểm tất cả. Đường không có trong bảng trả 404. Có test chốt mỗi vai được gì trên từng đường. Máy chủ tự kiểm, không chỉ ẩn nút | Người viết đường dẫn mới phải tự thêm vào bảng đó |
| **Sai cấu hình bảo mật** | Không có tài khoản hay khoá mặc định, thiếu `INGEST_KEY` thì máy chủ không chạy. Sau Caddy thì chỉ nghe trong máy. Dịch vụ chạy bằng người dùng riêng với quyền hạn chế; file khoá và dữ liệu chỉ dịch vụ đọc được | Bạn phải tự đặt danh sách IP, bật HTTPS và giữ ít người có sudo |
| **Lộ dữ liệu nhạy cảm** | Không bao giờ gửi nội dung trò chuyện, tên file, tên dự án. Màn hình treo tường không nhận email, IP nội bộ. Phiên TV lưu dạng mã băm, nhật ký không chứa khoá, file trông như chứa bí mật chỉ được ghi tên. Tổng theo từng người từng ngày (chi phí, token, số việc giao) chỉ hiện cho quản trị và người xem | Không có HTTPS thì số liệu đi không mã hoá. Tổng theo ngày ở lại tối đa 13 tháng kèm tên và email tài khoản của người đó, lâu hơn nhiều so với 30 ngày của dòng riêng từng máy: hãy báo cho nhân viên, và khi cần thì xoá các dòng của một người bằng `webhook.py --forget-usage`. Bản sao cơ sở dữ liệu làm trước một lần nâng lược đồ nằm cạnh nó trong 30 ngày. Khoá OTP nằm trên máy chủ không mã hoá, dịch vụ và người có sudo đọc được. Gói cài có chứa mã gửi |

### Bộ nối cho Codex, Cursor và Gemini CLI

Bộ nối (`connectors/`) là phần tuỳ chọn, tách riêng khỏi plugin. Những điều cần biết trước khi cho phép dùng:

- **Nó chạy như một hook bên trong công cụ của hãng khác,** với quyền của chính người dùng công cụ đó. Mỗi công cụ đưa cho hook sự kiện của nó, và trong sự kiện có câu hỏi hoặc câu trả lời. Hook đọc mã phiên và việc câu cuối có kết thúc bằng dấu hỏi hay không; nó không lưu và không gửi câu hỏi lẫn câu trả lời. Toàn bộ hook là một file ngắn bạn tự đọc được: `connectors/ai-worker-hook.sh` (Windows: `ai-worker-hook.ps1`).
- **Nó giữ một bản sao thứ hai của khoá gửi,** trong `~/.local/share/ai-worker/connector/config`. Trên macOS và Linux chỉ tài khoản đó đọc được file; trên Windows file nằm trong thư mục hồ sơ của người dùng. Khoá này có đúng quyền như bản của plugin: gửi số liệu, không gì khác.
- **Nó sửa cấu hình của công cụ khác.** Bộ cài thêm hook vào `~/.codex`, `~/.cursor` và `~/.gemini`, giữ một bản sao của từng file nó sửa, và `--uninstall` gỡ các hook ra. Codex chỉ chạy hook sau khi người dùng đã xem và bấm tin cậy bằng `/hooks`; bộ cài không bao giờ bỏ qua bước đó.
- **Nó không có bản cập nhật có chữ ký.** Bộ nối không tự cập nhật; bản mới chỉ tới khi có người chạy lại bộ cài từ một gói mà họ tin.
- **Phần còn lại:** một người vẫn gửi được số đếm sai dưới tên của chính mình, giống như với plugin. Cursor, Gemini CLI và các file cho Windows chưa được thử trong công cụ thật.

### Cổng MCP

Máy chủ có một đường chỉ đọc, `/mcp`, nơi công cụ AI cầm khoá đọc số liệu của bảng. Những điều cần biết trước khi duyệt một khoá:

- **Nó đưa đúng những gì màn hình treo tường nhận, không hơn:** tên, trạng thái, chi phí và hạn mức. Email, IP và mã máy không bao giờ đi ra, dù yêu cầu xin gì.
- **Mỗi khoá do quản trị duyệt,** theo quy trình mã 8 số của màn hình TV và phải nhập lại mã OTP. Quản trị chọn khoá đọc từng người hay chỉ số gộp của cả đội và từng văn phòng. Máy chủ lưu dạng băm của khoá; trang Quản trị hiện vài ký tự đầu.
- **Khoá chỉ mở được `/mcp`, và không khoá nào khác mở được `/mcp`:** khoá của màn hình treo tường, tiện ích, plugin, mã gửi hay phiên đăng nhập đều không. Ở đường này cookie bị bỏ qua, và yêu cầu từ một trang web ở nơi khác bị từ chối.
- **Giới hạn:** mỗi khoá 120 yêu cầu trong 10 phút, tối đa 50 khoá, mỗi thông điệp tối đa 16 KB. Khoá sai bị tính là dò, nên IP cứ thử mãi sẽ bị chặn 15 phút. Khoá hết hạn sau 30 ngày không dùng và tối đa sau 1 năm; thu hồi là hết dùng được ngay, và lần dùng sau đó được ghi vào nhật ký.
- **Mỗi lần đọc được ghi nhật ký 3 tháng:** khoá nào, công cụ nào, IP nào. Câu hỏi của người dùng không bao giờ tới máy chủ.
- **Danh sách IP cho phép che luôn đường này.** Với mẫu Caddy, `/mcp` chỉ trả lời bên trong các mạng của bạn. `MCP=0` gỡ hẳn đường này.

Phần còn lại:

- **Những gì công cụ đọc sẽ tới hãng làm ra công cụ đó,** như một phần câu hỏi của người dùng: tên và chi phí của đồng nghiệp, trừ khi khoá chỉ đọc số gộp. Với số gộp, các văn phòng dưới 3 người dùng chung một dòng, nhưng một đội hay một nhóm còn lại chỉ một hai người thì vẫn lộ qua số gộp.
- **Khoá nằm trên máy của người dùng mà không được mã hoá,** trong một biến môi trường hoặc trong file cấu hình của công cụ. Ai chép được nó thì đọc được đúng các số đó từ bên trong mạng của bạn, cho tới khi khoá bị thu hồi.
- **Mã không nói lên ai đang xin.** Một người trong mạng của bạn có thể xin mã rồi tìm cách nhờ quản trị duyệt. Thẻ duyệt ghi rõ loại khoá và IP xin mã; chỉ duyệt mã do chính người xin đọc cho bạn.
- **Tên là chữ do nhân viên tự gõ.** Tên có thể được viết để lái công cụ AI của người hỏi, và vài công cụ trong số đó chạy được lệnh. Máy chủ chỉ giữ chữ, số và vài dấu trong tên, cắt còn 40 ký tự, và dặn công cụ rằng tên là dữ liệu. Việc này giảm rủi ro chứ không xoá được.
- **Không có HTTPS thì khoá đi trên mạng mà không được mã hoá,** như mọi phần khác của bảng.
- **claude.ai và tab Chat của Claude Desktop tắt mặc định.** Chúng kết nối từ máy chủ của Anthropic, nên danh sách cho phép từ chối chúng. [docs/INSTALL.vi.md](docs/INSTALL.vi.md) chỉ cách cho địa chỉ của Anthropic vào được `/mcp` và không gì khác. Khi đã mở, `/mcp` trả lời bất kỳ ai đi qua claude.ai, và khoá là thứ duy nhất chắn đường. Đã thử một lần, từ tab Chat của app Claude trên máy tính: chạy được, và Claude gọi công cụ mà không hỏi người dùng trước, nên phạm vi của khoá là thứ quyết định cái gì đi ra ngoài.
- **Mới thử ở ba nơi, đều trên macOS:** Claude Code 2.1.318, Codex CLI 0.164.0, và tab Chat của app Claude trên máy tính qua một kết nối của claude.ai. Cursor, Gemini CLI, và mọi công cụ trên Windows và Linux chưa được thử.

### Hỏi bảng qua Telegram

Tắt trừ khi chủ máy chủ đặt `TELEGRAM_ASK=1`. Khi bật, một dịch vụ thứ hai là tiến trình bot hỏi Telegram xem có tin không, và người ở trong một chat được quản trị duyệt nhận câu trả lời từ bảng. Cần biết trước khi bật:

- **Đây là phần duy nhất của máy chủ kết nối ra ngoài, và chỉ tới Telegram.** Webhook vẫn không bao giờ làm việc đó. Tiến trình bot chạy dưới người dùng riêng, chỉ tới được chính máy này, các máy chủ DNS của nó và các mạng của Telegram, và cầm hai thứ bí mật: token của bot và khoá của đúng một đường nó gọi. Nó không cầm cơ sở dữ liệu, khoá OTP hay mã gửi, và không ghi gì xuống đĩa.
- **Tiến trình bot không quyết định điều gì.** Nó đưa từng tin cho webhook trên cùng máy; webhook quyết định chat đã được duyệt chưa, được đọc gì và được hỏi bao nhiêu lần. Đường đó, `/bot/telegram`, chỉ trả lời lời gọi thẳng từ cùng máy có trình khoá: yêu cầu đi qua proxy nhận 404, còn phiên đăng nhập hay khoá khác nhận 401.
- **Mỗi chat do quản trị duyệt,** bằng quy trình mã 8 số của màn hình TV và phải nhập lại mã OTP. Thẻ hiện tên và số Telegram của người đó, cùng tài khoản bảng mà Telegram ấy đã liên kết, nếu có. Quản trị chọn chat đọc từng người hay chỉ số gộp. Chỉ chat riêng được trả lời: trong nhóm bot im lặng rồi rời nhóm.
- **Nó đưa đúng những gì màn hình treo tường nhận, không hơn,** dưới dạng vài dòng chữ. Không mô hình AI nào đọc câu hỏi. Email, IP và mã máy không bao giờ đi ra.
- **Thứ đứng thay cho một chat là số Telegram của người đó, vốn không bí mật.** Vì vậy nó chỉ được nhận ở đúng đường kia. Nó không mở được trang nào, không dùng được ở đường của tiện ích hay `/mcp`, và các đường ghép công khai không lấy hay huỷ được mã của chat.
- **Giới hạn:** 50 chat, 10 chat chờ duyệt, mỗi chat 20 tin trong 10 phút. Chat chưa được duyệt được báo điều đó mỗi giờ một lần, ngoài ra không nhận câu trả lời nào. Chat hết hạn sau 30 ngày không dùng và tối đa sau 1 năm; `/stop` trong chat hoặc Thu hồi ở trang Quản trị làm nó dừng ngay.
- **Mỗi câu trả lời có số liệu được ghi nhật ký 3 tháng:** chat nào và lệnh nào. Chữ người dùng gõ không được lưu hay ghi nhật ký, ở webhook cũng như ở tiến trình bot.

Còn lại:

- **Tên và chi phí đi qua Telegram và nằm lại trong chat.** Telegram là bên thứ ba. Chat với bot không được mã hoá đầu cuối, và hiện trên mọi thiết bị mà người đó đăng nhập Telegram. Chat chỉ đọc số gộp thì không có tên người; một đội hay một nhóm còn lại chỉ một hai người thì vẫn lộ qua số gộp.
- **Điện thoại.** Câu trả lời được gửi sao cho các app Telegram không cho chuyển tiếp hay lưu, và dòng đầu không bao giờ có tên người. Trên chiếc điện thoại đã thử, app Telegram cũng không cho chụp màn hình; đó là cách Telegram cư xử trên thiết bị ấy, không phải lời bảo đảm. Trên máy tính vẫn chụp được màn hình, màn hình nào cũng có thể bị chụp lại bằng máy khác, và điện thoại đang mở khoá rơi vào tay người khác thì chat hiện ra.
- **Token của bot.** Ai cầm nó thì đọc được những gì mọi người gửi cho bot từ lúc đó, và nhắn cho họ dưới tên bot, ví dụ để xin mã đăng nhập; bản thân bot không bao giờ hỏi mã. Họ không đọc được bảng, vì máy chủ chỉ trả lời chat đã duyệt và Telegram không cho bot đọc lại tin nó đã gửi. Trang Quản trị báo khi có chương trình khác đọc cùng bot. Hãy dùng một bot tạo riêng cho việc này, đừng dùng bot đăng nhập, vì token của bot đăng nhập ký được lần đăng nhập.
- **Ai cũng nhắn được cho bot:** tên của nó là công khai. Người lạ chỉ nhận được một mã ghép, không gì khác. Chỉ duyệt mã do chính người đó đọc cho bạn.
- **Tên là chữ do nhân viên gõ.** Trong chat nó chỉ được hiện ra, không mô hình nào đọc. Các dấu mà Telegram biến thành liên kết hay lệnh đã bị gỡ khỏi tên. Việc này làm một liên kết cài cắm khó viết hơn chứ không chặn hẳn.
- **Các mạng của Telegram có thể đổi.** Danh sách cho phép là danh sách Telegram công bố, đọc ngày 2026-11-16. Nếu Telegram chuyển mạng, bot không tới được nữa cho tới khi bạn sửa `TELEGRAM_NETS`. `any` bỏ giới hạn, và bỏ luôn lớp bảo vệ đó.
- **Mới dùng trên một máy chủ thật,** từ 2026-11-17, với một chat chỉ đọc số gộp. Chat đọc từng người đã được thử ở đó một lần, ngày 2026-11-17: câu trả lời về chi phí nêu tên người có chi phí cao nhất và cho mỗi văn phòng một dòng riêng. Câu trả lời về người đang chờ và về hạn mức có kèm tên thì chưa thấy, vì lúc đó không ai chờ và chưa ai gần hết hạn mức.

Chi tiết hơn: [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).
