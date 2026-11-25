Tiếng Việt | [English](PERMISSIONS.md)

# Mô hình phân quyền

Ai được xem gì và làm gì trên máy chủ bảng tổng. Quy tắc nằm ở một chỗ: bảng đường dẫn cuối `server/webhook.py` (`GET_ROUTES`, `POST_ROUTES`) và cổng kiểm `Handler.gate`. Đường dẫn không có trong bảng thì trả 404. Test `test_webhook.py` giữ một bản sao của bảng và báo lỗi nếu hai bên khác nhau.

## 1. Ai đang gọi

| Bên gọi | Chứng minh bằng | Vai trên máy chủ |
|---|---|---|
| Máy nhân viên (plugin, bộ nối) | Khoá riêng của máy (`awd1.…`) trong header `Authorization`, hoặc `INGEST_KEY` khi chưa có | Không có vai: chỉ được gửi số liệu cho chính nó và tải bản cập nhật đã ký |
| Quản trị | Tên tài khoản + mã OTP 6 số, sau đó là cookie phiên (8 giờ) | `admin` |
| Quản lý | Tên tài khoản + OTP, cookie phiên (8 giờ) | `viewer` |
| Quản trị hoặc quản lý đã liên kết Telegram (tuỳ chọn) | Chữ ký của Telegram, kiểm bằng khoá bot (5 phút, một lần), cookie phiên | Vai của chính họ; thao tác quản trị vẫn hỏi OTP |
| Tài khoản màn hình treo tường | Tên tài khoản + OTP, cookie phiên (7 ngày) | `wall` |
| Màn hình TV | Khoá ghép do quản trị duyệt (30 ngày, tự gia hạn khi đang dùng) | `wall` |
| Biểu tượng thanh menu | Khoá ghép, do quản lý tự duyệt bằng tài khoản và OTP của mình, tối đa 2 máy mỗi tài khoản | Luôn là `wall` |
| Tiện ích trình duyệt | Khoá ghép trong header `Authorization`, do quản trị duyệt | Luôn là `wall` |
| Plugin Claude của quản lý (`/ai-worker:board`) | Cùng loại khoá ghép với tiện ích, do quản trị duyệt; ghi là "plugin" trong danh sách và nhật ký | Luôn là `wall`: Claude trên máy đó đọc được tên, trạng thái, chi phí và hạn mức, không bao giờ có email hay IP |
| Công cụ AI nói được MCP (Claude Code, Codex CLI, Cursor, Gemini CLI) | Khoá của riêng nó trong header `Authorization`, xin ở `/mcp/connect` và do quản trị duyệt. Khoá chỉ mở `/mcp`, và không khoá nào khác mở được `/mcp` | Luôn là `wall`, đưa dưới dạng chữ. Quản trị chọn khoá đọc từng người, hay chỉ số gộp của cả đội và từng văn phòng |
| Chat Telegram (chỉ khi `TELEGRAM_ASK=1`, khi đó bộ cài dựng tiến trình bot nói chuyện với Telegram) | Không có gì của riêng nó: tiến trình bot trên máy chủ đưa từng tin nhắn kèm số Telegram của người gửi, và chat được tính khi quản trị đã duyệt mã 8 số của nó. Con số đó không mở được gì khác | Luôn là `wall`, đưa dưới dạng vài dòng chữ. Quản trị chọn chat đọc từng người, hay chỉ số gộp của cả đội và từng văn phòng |
| Dự án hay ứng dụng AI do nhóm tự làm (chỉ khi `AI_PROJECTS=1`) | Khoá riêng (`prj_…`) trong header `Authorization`, quản trị tạo trên trang Quản trị và chỉ hiện một lần. Nó chỉ mở `/projects/ingest`, và không khoá nào khác mở được đường đó; yêu cầu có header `Origin` (trình duyệt) bị từ chối | Không có: chỉ được gửi số nó đã đo |

Máy chủ chỉ tin IP ghi trong yêu cầu khi yêu cầu đi qua proxy trên chính máy (`TRUST_PROXY`). Danh sách IP văn phòng được vào do Caddy hoặc nginx đứng trước chặn, không phải webhook.

## 2. Mỗi vai thấy gì

| Dữ liệu | `admin` | `viewer` | `wall` |
|---|---|---|---|
| Văn phòng 3D, trạng thái, chi phí, việc giao, hạn mức | Có | Có | Có |
| Email | Có | Có | Không: thay bằng mã ngắn làm từ một bí mật giữ trong cơ sở dữ liệu khoá, giữ nguyên sau khi khởi động lại |
| Tên máy là email hoặc IP | Có | Có | Không: hiện "Máy xxxxxx" |
| Mã dòng của mỗi người (`row`, chỉ khi `RECEIVER=1`), nơi luồng số trực tiếp của bộ nhận Go ghép số vào | Có | Có | Có: 12 ký tự làm từ cùng bí mật với nhãn khác, nên không cho ngược lại email hay tên, và không trùng mã ở trên |
| IP nội bộ, tài khoản nhân viên tự gõ | Có | Có | Không |
| Chi phí gói Team | Có | Có | Không |
| Mức dùng theo tuần và theo tháng, theo từng văn phòng và từng người (tổng theo ngày, giữ 13 tháng) | Có | Có | Không |
| Chi phí của cả team trong từng ngày của 7 ngày gần nhất, mỗi ngày một con số (biểu đồ của khung thanh menu) | Có | Có | Có |
| Số lần ai-worker đã chặn trên cả team trong 7 ngày qua, chỉ số đếm (`blocked7d`) | Có | Có | Không |
| Việc giao cho ChatGPT, Gemini hay Gemma: mỗi việc một biên bản, ai, trợ lý nào, độ dài, đã chặn gì, bước kiểm câu trả lời thấy gì, dấu vân tay của đề bài; không bao giờ có chữ | Có | Không | Không |
| Nhóm máy chưa đặt tên | Có | Không | Không |
| Bảng chữ `/board` | Có | Có | Không |
| Trang `/admin` và gói cài | Có | Không | Không |

Các trường mỗi vai nhận được cố định trong `server/board/views.py` (`COMMON_FIELDS_BY_ROLE`, `PERSON_FIELDS_BY_ROLE`). Trường không có trong danh sách thì không bao giờ được gửi. `/data?scope=org` và `/data?scope=branch:<mã>` ([RECEIVER.vi.md](RECEIVER.vi.md), mục 3) được cắt từ cùng khung nhìn của cùng vai, cộng tổng theo chi nhánh chỉ có số, nên một phạm vi không bao giờ cho một vai thấy hơn `/data` thường. Mức dùng theo tuần và theo tháng có danh sách riêng trong cùng file (`USAGE_FIELDS_BY_ROLE`, `USAGE_OFFICE_FIELDS_BY_ROLE`, `USAGE_PERSON_FIELDS_BY_ROLE`), để trống cho `wall`: phần này chỉ có trên `/board`, nên màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt, plugin của quản lý và cổng MCP, vốn đều đọc với vai `wall`, không nhận được gì.

## 3. Mỗi vai làm được gì

| Thao tác | Đường dẫn | Ai | Kiểm thêm |
|---|---|---|---|
| Gửi số liệu | `POST /ingest` | Máy có khoá riêng, hoặc `INGEST_KEY` khi chưa có và `SHARED_KEY_MODE` cho phép | Khoá chỉ gửi cho đúng máy của nó; máy bị gắn với người của lần gửi đầu; máy bị thu hồi bị từ chối. Từ ngoài `OFFICE_NETS` (hoặc bị Caddy đánh dấu như vậy): chỉ khoá riêng của máy quản trị đã cho gửi từ mọi mạng, nếu không thì 403 |
| Hỏi giờ gửi tới đâu | `GET /ingest/route` | Máy có khoá riêng (khoá chung: 403) | Không ghi gì; danh sách rỗng trừ khi bộ nhận Go nhận các lần gửi của máy này. Từ ngoài văn phòng: như với `/ingest` |
| Tải bản cập nhật | `GET /releases/...` | Máy có khoá riêng hoặc `INGEST_KEY` | Máy kiểm chữ ký trước khi cài. Từ ngoài văn phòng: như với `/ingest` |
| Cho một máy gửi từ mọi mạng, hoặc thôi cho | `POST /admin/device-roam` | `admin` | Nhập lại OTP, hiệu lực 5 phút; chỉ máy đang gửi bằng khoá riêng; ghi vào nhật ký Quản trị |
| Đặt tên địa điểm, đánh dấu nhóm bán hàng, nạp CSV gói Team | `POST /locations`, `/team-sale`, `/team-csv` | `admin` | Yêu cầu phải cùng nguồn trang |
| Tạo, xoá, đổi vai tài khoản; kết thúc phiên | `POST /admin/accounts`, `/admin/sessions` | `admin` | Nhập lại OTP, có hiệu lực 5 phút |
| Duyệt, đổi tên, thu hồi màn hình TV, tiện ích, khoá cho công cụ AI và chat Telegram; chọn khoá hay chat đó được đọc gì | `POST /admin/tv-*` | `admin` | Nhập lại OTP, có hiệu lực 5 phút |
| Tải lại một màn hình TV | `POST /admin/tv-reload` | `admin` | Yêu cầu phải cùng nguồn trang |
| Tự duyệt biểu tượng thanh menu của mình | `POST /mini/pair` | Tài khoản vai `admin` hoặc `viewer` | OTP của chính tài khoản đó |
| Xin khoá cho một công cụ AI | `GET /mcp/connect`, `POST /mcp/request-code`, `/mcp/poll` | Bất kỳ ai được danh sách IP cho vào | Yêu cầu phải đi từ trang của chính bảng. Không cấp gì cho tới khi quản trị duyệt mã |
| Đọc bảng từ một công cụ AI | `POST /mcp` | Công cụ AI có khoá cho cổng MCP | Chỉ đọc. Mỗi khoá 120 yêu cầu trong 10 phút; trang web ở nơi khác bị từ chối; mỗi lần gọi công cụ được ghi nhật ký 3 tháng |
| Khung bảng bên trong Telegram: đổi các trường Telegram đã ký lấy một phiên, đọc phần treo tường (chỉ số tổng của cả team với chat chỉ đọc số gộp), đọc và đặt tin báo của chính chat, ngắt chính chat của nó | `POST /tg/session`, `GET /tg/data`, `GET /tg/state`, `POST /tg/settings`, `POST /tg/unpair` | Chat đã được quản trị duyệt và cho mở khung; phiên lấy từ `/tg/session` trong header Authorization | Tắt (404) trừ khi `TELEGRAM_APP=1`. Chữ ký của Telegram được kiểm bằng khoá suy ra từ khoá bot, các trường cũ tối đa 5 phút; phiên nằm trong bộ nhớ, sống 1 giờ sau lần dùng cuối, tối đa 12 giờ, 3 phiên mỗi chat; chat được tìm lại ở mỗi lần gọi. 10 phiên mỗi IP mỗi phút, 20 phiên mỗi chat trong 10 phút, 60 lần đọc mỗi phiên trong 10 phút |
| Đưa một tin nhắn từ chat Telegram và nhận câu trả lời để gửi | `POST /bot/telegram` | Tiến trình bot Telegram trên chính máy chủ, kèm `TELEGRAM_ASK_KEY` | Tắt (404) trừ khi `TELEGRAM_ASK=1`. Chỉ nhận lời gọi thẳng từ cùng máy: yêu cầu đi qua proxy nhận 404, phiên đăng nhập hay khoá khác nhận 401. Chỉ chat riêng; mỗi chat 20 tin trong 10 phút; mỗi câu trả lời có số liệu được ghi nhật ký 3 tháng, không bao giờ ghi chữ đã gõ |
| Bộ nhận Go tuỳ chọn: ghi một lô dòng, chuyển nguyên văn một lần gửi, đọc tài liệu chính sách có số thứ tự, các sổ giờ và bảng người (mã dòng và chi nhánh của mỗi máy, không tên, email hay địa chỉ) | `POST /internal/rows`, `POST /internal/ingest`, `GET /internal/policy`, `GET /internal/devices`, `GET /internal/people` | Bộ nhận trên chính máy chủ, kèm mã nội bộ trong file bí mật của nó | Tắt (404) trừ khi `RECEIVER=1`. Chỉ nhận lời gọi thẳng từ cùng máy có mã nội bộ: mọi thứ khác, kể cả phiên đăng nhập, nhận 404. Lần gửi được chuyển tới thì khoá riêng của nó được kiểm như ở `/ingest` ([RECEIVER.vi.md](RECEIVER.vi.md)) |
| Xin vé vào luồng số trực tiếp của bảng | `POST /sse/ticket` | Mọi tài khoản đã đăng nhập hay màn hình TV | Tắt (404) trừ khi có `RECEIVER=1` và đã đặt `RECEIVER_LIVE_URL`, `RECEIVER_BOARD_ORIGIN`. Yêu cầu phải đến từ chính trang của bảng. Mọi phạm vi của `/data?scope=`; vé sống 5 phút, mang vai, phạm vi và một mã của phiên, không có tên ([RECEIVER.vi.md](RECEIVER.vi.md), "Luồng số trực tiếp") |
| Đọc số trực tiếp của bảng | `GET /live`, `GET /live/snap` ở bộ nhận Go | Một trang thuộc `RECEIVER_BOARD_ORIGIN` có vé còn tốt, cho đúng phạm vi nó xin | Cùng các con số cho mọi vai, và chỉ có số cùng mã dòng: không tên, email hay địa chỉ. Bị cắt trong khoảng 20 giây khi phiên đã đóng |
| Gửi số mà dự án hay ứng dụng AI đã đo | `POST /projects/ingest` | Máy chủ của chính dự án, bằng khoá của nó | Tắt (404) trừ khi `AI_PROJECTS=1`. Từ chối khi gửi từ trình duyệt. Mỗi lượt được làm sạch bằng code của báo cáo (bỏ trường lạ, từ chối lượt sai, từ chối lượt cũ hơn 30 ngày) và chỉ giữ một lần theo khoá và `turnId`. Mỗi khoá 120 lần gửi trong 10 phút, mỗi lần 256 KB và 500 lượt, 100.000 lượt một ngày |
| Xem và tải báo cáo của dự án hay ứng dụng AI | `GET /projects`, `/projects/report.html`, `/projects/report.csv` | `admin`, `viewer` | Tắt (404) trừ khi `AI_PROJECTS=1`. Bản in mở trong tab riêng và không chạy script |
| Tạo khoá cho dự án hay ứng dụng AI; dán giá riêng; xoá số liệu của dự án đã thu hồi khoá | `POST /admin/project-key`, `/admin/project-prices`, `/admin/project-delete` | `admin` | Nhập lại OTP, hiệu lực 5 phút. Đổi tên và thu hồi khoá bằng `/admin/tv-*`. Khoá còn dùng được thì không cho xoá |

## 4. Các lớp chặn

- **Luôn còn ít nhất một quản trị:** máy chủ từ chối xoá hoặc hạ vai quản trị cuối cùng.
- **Nhập sai OTP:** sai 5 lần từ một địa chỉ trong 15 phút thì khoá địa chỉ đó. Sai 20 lần trên một tài khoản trong 15 phút thì khoá tài khoản đó, nên người lạ không khoá được cả trang.
- **Telegram:** liên kết phải nhập mã 6 số và đi qua một bước dùng một lần gắn với phiên đó, nên lấy được phiên hay bấm đường dẫn người khác gửi cũng không thêm được Telegram. Mỗi tài khoản một Telegram; tài khoản treo tường không dùng được. Cấp lại khoá hoặc chuyển sang treo tường sẽ gỡ liên kết.
- **Giới hạn:** 200 tài khoản, 20 màn hình TV, 50 khoá cho công cụ AI, 20 khoá cho dự án hay ứng dụng AI, 300 máy.
- **Mọi lần từ chối và mọi thay đổi đều ghi vào nhật ký quản trị** (bảng `audit` trong `board.db`): ai, vai gì, IP nào, đường dẫn nào. Nội dung CSV không chép vào.
- **Mất hết quản trị:** người có quyền sudo trên máy chủ chạy `sudo bash manage-otp.sh --rescue <tên>` trong thư mục `server/`. Xem [USER-GUIDE.vi.md](USER-GUIDE.vi.md).
