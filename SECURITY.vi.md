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
| **Lỗi xác thực** | Mỗi tài khoản có khoá OTP riêng, mỗi mã chỉ dùng một lần. Số lần sai bị giới hạn theo IP và theo tài khoản. Mã phiên ngẫu nhiên và có hạn; cookie đặt `HttpOnly`, và `Secure` khi dùng HTTPS. Mỗi máy gửi bằng khoá riêng do máy chủ ký, chỉ có hiệu lực cho đúng máy đó; quản trị thu hồi được từng khoá. Đổi tài khoản, thiết bị hay khoá đã ghép phải nhập lại OTP | OTP là yếu tố đăng nhập duy nhất, nên hãy giữ danh sách IP. Khi bật đăng nhập Telegram, khoá bot ký được lần đăng nhập của bất kỳ ai: chỉ để trong file env của máy chủ |
| **Truy cập trực tiếp đối tượng (IDOR)** | Người xem và màn hình treo tường nhận một bản đã lọc theo vai, không có cách xin một bản ghi theo mã. Thao tác lên một tài khoản hay màn hình cụ thể chỉ dành cho quản trị | Người xem được thấy số của mọi người, đây là chủ ý. Ai có mã gửi dùng chung đều gửi được dưới một tên chưa gắn với máy nào |
| **Thiếu kiểm soát quyền theo chức năng** | Mọi đường dẫn được liệt kê kèm quyền, một cổng kiểm tất cả. Đường không có trong bảng trả 404. Có test chốt mỗi vai được gì trên từng đường. Máy chủ tự kiểm, không chỉ ẩn nút | Người viết đường dẫn mới phải tự thêm vào bảng đó |
| **Sai cấu hình bảo mật** | Không có tài khoản hay khoá mặc định, thiếu `INGEST_KEY` thì máy chủ không chạy. Sau Caddy thì chỉ nghe trong máy. Dịch vụ chạy bằng người dùng riêng với quyền hạn chế; file khoá và dữ liệu chỉ dịch vụ đọc được | Bạn phải tự đặt danh sách IP, bật HTTPS và giữ ít người có sudo |
| **Lộ dữ liệu nhạy cảm** | Không bao giờ gửi nội dung trò chuyện, tên file, tên dự án. Màn hình treo tường không nhận email, IP nội bộ. Phiên TV lưu dạng mã băm, nhật ký không chứa khoá, file trông như chứa bí mật chỉ được ghi tên. Tổng theo từng người từng ngày (chi phí, token, số việc giao) chỉ hiện cho quản trị và người xem | Không có HTTPS thì số liệu đi không mã hoá. Tổng theo ngày ở lại tối đa 13 tháng kèm tên và email tài khoản của người đó, lâu hơn nhiều so với 30 ngày của dòng riêng từng máy: hãy báo cho nhân viên, và khi cần thì xoá các dòng của một người bằng `webhook.py --forget-usage`. Bản sao cơ sở dữ liệu làm trước một lần nâng lược đồ nằm cạnh nó trong 30 ngày. Khoá OTP được niêm phong trong cơ sở dữ liệu tài khoản bằng một khoá để ở `/etc`, chỉ root đọc được, nên bản chép cơ sở dữ liệu hay bản sao lưu `/opt` không cho ai đăng nhập; dịch vụ đang chạy và người có sudo vẫn mở được. Gói cài có chứa mã gửi |

### Những gì plugin chặn trên máy

- **Bí mật rời máy:** chữ gửi ChatGPT hay Gemini có thứ trông như khoá, token hay mật khẩu thì không được gửi, ở mọi chế độ quyền. Bộ kiểm biết hình dạng các loại khoá phổ biến và các thiết lập kiểu `.env`; bí mật không có hình dạng nhận ra được thì vẫn có thể lọt.
- **Bí mật vào git:** trước khi Claude chạy `git commit`, các dòng commit thêm vào được đọc như vậy, và commit có bí mật thì được đưa người dùng xem trước. Commit người dùng tự làm ngoài Claude thì không được kiểm.
- **Lệnh rủi ro:** xoá cả thư mục, `git reset --hard`, `git push --force`, `git clean`, chạy ngay script vừa tải, tắt Gatekeeper, ghi thẳng ra ổ đĩa và `chmod 777` được đưa người dùng xem ở mọi chế độ.
- **Trang tìm cách lái Claude:** chữ từ web, tìm kiếm hay trình duyệt mà ra lệnh cho AI thì được báo cho Claude và người dùng. Việc tìm dựa vào câu chữ, nên trang nói cùng ý theo cách khác vẫn lọt; kết quả không bao giờ bị giấu.
- **Repo tự cấu hình AI:** khi một phiên bắt đầu trong một repo, plugin đọc `.claude/settings.json` và `settings.local.json` (hook, chương trình Claude Code tự chạy, quy tắc cho mọi lệnh đi qua, chế độ không hỏi gì, biến đưa lưu lượng của Claude đi nơi khác), `.mcp.json` (server MCP và lệnh mỗi server chạy), `CLAUDE.md`, `CLAUDE.local.md` và `AGENTS.md` (chữ nhắm vào AI, lệnh tải về rồi chạy một script hay xoá một thư mục) cùng các lệnh tắt, trợ lý con và skill trong `.claude/`. Những gì mới hoặc đã đổi kể từ lần xem trước được nói với người dùng một dòng và với Claude trong suốt phiên. Không chặn gì, và hook hay server MCP của repo có thể đã chạy lúc đó: chính Claude Code chỉ hỏi một lần có tin thư mục không, không nói trong đó có gì, và với `claude -p` thì chạy chúng không hỏi. Repo thấy lần đầu mà mọi file đều cũ hơn 14 ngày thì được ghi nhớ lặng lẽ; plugin giữ dấu vân tay của từng điều thấy và của thư mục, không giữ đường dẫn hay nội dung file. Ý này mượn từ ghi chú bảo mật của Tencent LoopForge.
- **Câu trả lời của trợ lý:** những gì ChatGPT, Gemini hay Gemma gửi về được đọc tìm khoá và mật khẩu, chữ nhắm vào AI và lệnh không hoàn tác được trước khi Claude dùng; Claude được báo đã thấy gì, người dùng cũng vậy. Giới hạn như trên: tìm theo hình dạng và câu chữ, và câu trả lời không bao giờ bị giấu.
- **Gemma trên máy chủ:** Gemma chỉ giữ dữ liệu trên máy khi nó chạy ngay tại máy (`gemma4:26b`). Máy quá yếu có thể được cho một máy chủ Gemma: khi đó chữ gửi đi qua mạng tới máy chủ đó, chỉ qua HTTPS, thẳng tới Ollama đứng sau Caddy và không bao giờ qua chương trình của bảng tổng. Người dùng được báo máy chủ nào và được hỏi trước mỗi lần gửi, chữ có khoá hay mật khẩu thì không gửi, và việc dành cho Gemma của chính máy không bao giờ tự chuyển sang máy chủ. Máy tự chạy được Gemma mà có cả máy chủ thì theo quy tắc giữ dữ liệu nhạy cảm trên máy, và khi máy chủ hỏng thì nó tự trả lời, nên sự cố không bao giờ làm gửi thêm gì ra ngoài. Ai vận hành máy chủ đó đọc được thứ gửi tới nó: chỉ dựng trên máy mà tổ chức của bạn kiểm soát.
- **Biên bản mỗi lần giao việc:** mỗi việc giao cho trợ lý để lại một dòng trong nhật ký có dấu vân tay của máy chủ, gồm trợ lý nào, độ dài, đã chặn gì, bước kiểm thấy gì, và dấu vân tay của đề bài có muối trên máy. Không bao giờ có đề bài hay câu trả lời; chỉ quản trị xem được.

Trên máy chủ, trang Quản trị hiện số lần những việc này xảy ra trên cả team trong 7 ngày qua (chỉ số đếm), chỉ ra các khoá cho công cụ AI không dùng 30 ngày, và kiểm không dòng nào của nhật ký bị sửa hay bị xoá bằng tay. Mỗi dòng mang dấu vân tay của dòng trước; người viết lại được cả cơ sở dữ liệu lẫn dấu vân tay cuối thì không bị phát hiện, nên cần một bản nằm ngoài máy chủ: mỗi ngày tổng chi phí được niêm phong vào chuỗi khi không còn được đếm lại (sau một tuần), trang Quản trị liệt kê mã của các ngày đã niêm phong và báo nếu ngày đã niêm phong bị sửa, và mỗi sáng chat Telegram đã liên kết với tài khoản quản trị nhận mã mới nhất (ngày, số dòng, mã; không tên, không tiền). Một ngày vẫn sửa được trong tuần nó còn được đếm lại.

### Khoá của từng máy và việc gửi từ ngoài văn phòng

Mỗi máy gửi bằng một khoá riêng, và những máy được chọn có thể gửi từ mọi mạng. Cần biết:

- **Khoá của máy là của riêng máy đó.** Máy chủ cấp nó trong câu trả lời cho lần gửi đầu của máy (`awd1.…`, ký bằng một bí mật giữ trong `keys/`). Từ đó mã gửi chung trong gói cài không gửi thay được cho máy ấy.
- **Mã chung còn làm được gì là một tuỳ chỉnh.** `SHARED_KEY_MODE` là `allow` (máy mới ghi danh bằng nó, mặc định), `known-only` (chỉ các máy đã có trên bảng) hoặc `off`. Nếu gói cài bị lộ, đặt `known-only`: không cần gói mới.
- **Cắt một máy ở trang Quản trị** bằng nút **Thu hồi** và nhập lại mã OTP: khoá của nó dừng ngay và mã chung không đưa nó quay lại được. `webhook.py --rotate-device-secret` cấp khoá mới cho mọi máy khi bí mật ký có thể đã lộ.
- **Gửi từ ngoài văn phòng vẫn tắt cho tới khi bạn cài,** và khi đó chỉ cho những máy quản trị đặt **Mọi mạng**, từng máy một, có nhập lại mã OTP. Từ ngoài, proxy chỉ cho qua yêu cầu tới `/ingest` hay `/releases/` có mang khoá riêng của một máy; mã chung không gửi được gì từ ngoài. Trang bảng, đăng nhập và `/mcp` vẫn chỉ ở trong mạng của bạn.
- **Điều còn lại:** khi `SHARED_KEY_MODE` còn là `allow`, người cầm gói cài vẫn ghi danh được một máy mới dưới tên giả. Máy được gửi từ mọi mạng để lại trên bảng các địa chỉ nó đã gửi từ đó, kể cả địa chỉ nhà: báo cho người đó trước. Máy bị lấy cắp vẫn gửi cho tới khi quản trị bấm **Thu hồi**. Một CDN hay proxy khác đứng trước Caddy làm mọi máy trông như ở ngoài, nên cách cài này không dành cho trường hợp đó.

### Bộ nhận Go (tuỳ chọn)

Chỉ dành cho tổ chức lớn, và tắt cho tới khi `server/install-receiver.sh` cài nó ([docs/RECEIVER.vi.md](docs/RECEIVER.vi.md)). Nó là một chương trình thứ hai nghe ở một địa chỉ riêng. Cần biết trước khi bật:

- **Nó là cánh cửa thứ hai vào máy chủ,** qua TLS do chính nó xử lý, không đứng sau Caddy. Nó tự kiểm khoá riêng của máy, chuyển lần gửi bằng mã chung cho webhook kiểm như mọi khi, và chỉ trả số trực tiếp cho bảng có vé; mọi thứ khác bị từ chối.
- **Nó không quyết định gì về con người.** Đăng nhập, vai, tên và dữ liệu vẫn ở webhook. Bộ nhận không giữ tên hay email nào và không ghi file nào; số trực tiếp nó đưa cho bảng mang một mã cho mỗi dòng, không bao giờ mang tên.
- **Nó chạy bằng tài khoản của webhook, không bao giờ bằng root,** chỉ có một quyền là nghe ở cổng thấp, có trần bộ nhớ, và một tuỳ chỉnh khiến hệ điều hành dừng nó trước webhook khi hết bộ nhớ.
- **File bí mật** (`keys/receiver-secrets.json`, chỉ tài khoản đó đọc được) cho bộ nhận kiểm khoá của máy và vé. Ai cầm file này tạo được khoá cho bất kỳ máy nào và gửi số dưới danh máy đó, nhưng không đọc được dữ liệu nào. Nó ở lại trên máy chủ; `--rotate-device-secret` thay nội dung của nó.
- **Các đường bộ nhận dùng trên webhook** (`/internal/…`) chỉ trả lời lời gọi từ chính máy đó kèm một mã nội bộ. Từ nơi khác thì chúng như không tồn tại.
- **Vé đọc số trực tiếp** chỉ cấp cho phiên đã đăng nhập ở chính trang của bảng, sống 5 phút, cho một phạm vi. Bộ nhận cắt luồng trong khoảng 20 giây sau khi phiên kết thúc.
- **Nó giới hạn những gì một đợt dồn dập lấy được:** số kết nối, bộ nhớ cho các thân đang đọc và các dòng đang chờ, và nhịp gửi nó yêu cầu các máy. Quá giới hạn thì máy được bảo quay lại sau, và không mất gì đã gửi trước đó.
- **Điều còn lại:** nó không tự kiểm danh sách mạng văn phòng. Ở nơi đã đặt danh sách đó, máy để **Chỉ văn phòng** không bao giờ được báo địa chỉ của bộ nhận; chỉ máy đặt **Mọi mạng** mới tới đó, và khi ấy là từ mọi nơi. Chứng chỉ của nó do bạn gia hạn. Nó đã được đo với máy giả tới khoảng 40.000 tới 50.000 máy, và mới chạy thật ở một tổ chức với vài máy; chưa có hãng bảo mật bên ngoài nào xem xét.

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

### Dự án hay ứng dụng AI

Tắt trừ khi `AI_PROJECTS=1`. Một dự án nhóm tự làm gửi các số mà bộ đo `ai-cost-report` của nó đã đo tới `/projects/ingest`. Cần biết trước khi bật:

- **Chỉ có số đếm và thời gian:** mỗi lượt mất bao lâu, kết thúc ra sao, và theo từng model: hãng, tên model, số lần gọi, lỗi và token. Không bao giờ có câu hỏi, câu trả lời, người dùng hay thông báo lỗi: bộ đo không có chúng, và máy chủ chỉ giữ các trường đã biết của mỗi lượt, bỏ phần còn lại.
- **Mỗi dự án có khoá riêng,** do quản trị tạo trên trang Quản trị, nhập lại mã OTP, chỉ hiện một lần. Máy chủ lưu bản băm và vài ký tự đầu. Khoá chỉ mở `/projects/ingest`, chỉ ghi, và không khoá nào khác mở được đường đó.
- **Đặt khoá trên máy chủ của chính dự án, không bao giờ trong trang web hay app điện thoại.** Yêu cầu có header `Origin`, thứ mọi trình duyệt đều gửi, bị từ chối dù cầm khoá nào; khoá nằm trong app điện thoại vẫn có thể bị lấy ra.
- **Giới hạn:** mỗi khoá 120 lần gửi trong 10 phút, mỗi lần 256 KB và 500 lượt, 100.000 lượt một ngày, tối đa 20 khoá. Lượt gửi hai lần chỉ giữ một lần. Khoá sai bị tính là dò. Khoá hết hạn sau 30 ngày không dùng và tối đa 1 năm; thu hồi thì dừng ngay và giữ lại số đã gửi.
- **Số liệu là điều dự án tự khai.** Ai cầm khoá cũng gửi được lượt bịa cho dự án đó. Đây là báo cáo, không phải hoá đơn: đối chiếu với trang thanh toán của hãng.
- **Danh sách IP vẫn áp dụng.** Dự án chạy trên cloud nằm ngoài mạng của bạn: `aiworker.caddy` có sẵn một khối cho đúng một IP tới `/projects/ingest` và không tới đâu khác. Bộ đo chỉ gửi khoá qua HTTPS, hoặc tới chính máy đó.
- **Ai đọc được:** quản trị và người xem, ở `/projects`. Màn treo tường, cổng MCP và Telegram thì không.

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

### Khung bên trong Telegram và tin báo

Cả hai đặt lên trên việc hỏi bảng qua Telegram, và đều tắt cho tới khi bật: khung bật bằng `TELEGRAM_APP=1` và quản trị cho phép từng chat, tin báo do chính từng chat bật (`/baocho`).

- **Khung là một trang của bảng, dưới `/tg/`.** Điện thoại hay máy tính của người dùng tự tới máy chủ qua HTTPS; Telegram không chở số liệu. Với khối Caddy mẫu, chỉ mạng văn phòng vào được. Cho `/tg/` vào từ mọi nơi là một quyết định riêng mà dự án này không quyết thay bạn.
- **Phần Telegram ký được kiểm trước mọi việc khác.** Telegram đặt vài trường đã ký sau dấu `#` của địa chỉ, nên chúng không vào nhật ký nào. Webhook kiểm chúng bằng một khoá bộ cài suy ra từ khoá bot: khoá này kiểm được chữ ký nhưng không điều khiển được bot. Các trường cũ quá 5 phút bị từ chối, và chữ ký sai bị tính là dò.
- **Phiên chỉ nằm trong bộ nhớ:** một chuỗi ngẫu nhiên giữ dạng băm, sống 1 giờ sau lần dùng cuối, tối đa 12 giờ, 3 phiên mỗi chat, không có cookie. Mỗi lần gọi đều tìm lại chat, nên thu hồi chat, `/stop` hay **Thôi mở khung** đều đóng ngay mọi khung đang mở.
- **Chỉ chat được quản trị cho phép, từng cái một,** kèm nhập lại mã OTP. Chat được đọc từng người thấy đúng những gì màn hình treo tường thấy; chat chỉ đọc số gộp nhận số đếm và chi phí của cả team, cộng sẵn trên máy chủ, và không tên nào tới được nó.
- **Không có script của trang khác chạy trong khung.** Khung không nạp script của Telegram từ telegram.org, và `script-src 'self'` của trang giữ nguyên.
- **Tin báo là bot tự nhắn mà không cần được hỏi.** Tên và số phút trong đó đi qua Telegram và nằm lại trong chat, như câu trả lời. Dòng đầu không nêu tên ai, chat chỉ đọc số gộp chỉ nhận con số, và mỗi chat nhận tối đa một tin mỗi 5 phút, 6 tin mỗi giờ, 30 tin mỗi ngày, không gửi ban đêm. Mỗi tin được ghi nhật ký kèm số người, không bao giờ ghi là ai.
- **Đã thử trên một máy chủ thật** ngày 2026-11-18: khung trên Android và Telegram Desktop, ở mạng văn phòng. Chưa thử trên iPhone, và tin báo chưa thử trên chat thật.

Chi tiết hơn: [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).
