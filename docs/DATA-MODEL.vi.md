Tiếng Việt | [English](DATA-MODEL.md)

# Thiết kế dữ liệu

Máy chủ bảng tổng lưu gì, ở đâu, bao lâu và ai đọc được. Máy chủ lưu mọi thứ trong hai cơ sở dữ liệu SQLite. SQLite có sẵn trong Python nên không phải cài thêm gì.

Các thiết lập nêu ở đây (`DATA_DIR`, `KEYS_DIR`, các giới hạn) nằm trong `server/board/settings.py`. Lược đồ, các bước nâng cấp và việc chuyển từ file JSON cũ nằm trong `server/board/db.py`. Code đọc và ghi từng bảng nằm trong `server/board/stores.py`, `server/board/devices.py`, `server/board/daily.py` và `server/board/views.py`.

## 1. Các file

| File | Mặc định sau khi cài | Chủ sở hữu và quyền | Chứa |
|---|---|---|---|
| `data/board.db` (kèm `-wal`, `-shm`) | `/opt/ai-worker/data/` | `ai-worker`, `600`, thư mục `750` | Số liệu các máy, tổng theo từng người từng ngày, các lần ghép, địa điểm, gói Team, nhật ký quản trị, diễn biến tua lại |
| `data/board.db.schema-N.bak` | Nằm cạnh `board.db`, chỉ có sau một lần nâng cấp làm đổi lược đồ | `ai-worker`, `600` | Một bản sao đầy đủ của `board.db` lúc còn ở lược đồ phiên bản `N`, do máy chủ tự làm trước khi nâng. Máy chủ xoá nó sau 30 ngày |
| `keys/accounts.db` (kèm `-wal`, `-shm`) | `/opt/ai-worker/keys/` | `ai-worker`, `600`, thư mục `700` | Tài khoản và mã bí mật OTP |
| `/etc/ai-worker.env` | | `root`, `600` | Thiết lập và `INGEST_KEY` |

Tài khoản nằm ở file riêng, thư mục riêng, để bản sao lưu số liệu không bao giờ mang theo mã bí mật đăng nhập. Dịch vụ systemd chỉ được ghi vào hai thư mục này (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Các bảng

`board.db`:

| Bảng | Nội dung | Ghi khi | Giữ |
|---|---|---|---|
| `devices` | Mỗi máy một dòng cho plugin, và thêm một dòng cho bộ nối Codex, Cursor và Gemini CLI ở máy có cài: số liệu mới nhất trong `body` (mục 3), `seen_at` = lúc máy chủ nhận | Mỗi lần máy gửi, nhiều nhất 30 giây một lần | Xoá sau 30 ngày kể từ `seen_at` (`KEEP_DAYS`) |
| `identities` | `máy → tài khoản, tên` của lần gửi đầu | Máy mới gửi lần đầu | Tới khi xoá bằng `--forget-device` |
| `history` | Mỗi lần trạng thái một người đổi thì thêm một dòng: thời điểm, người, trạng thái, số việc đang giao | Trạng thái đổi | 24 giờ (nút tua lại) |
| `daily` | Mỗi người mỗi ngày một dòng (ngày tính theo `TZ_OFFSET`): tên, email tài khoản, văn phòng của người đó lúc chốt ngày, chi phí tính bằng đô la, token vào và ra, số việc giao cho Gemini, ChatGPT và Gemma. Cộng từ `ledger` và `tasks` của các máy của người đó (mục 3); không máy nào phải gửi thêm gì | Cứ 5 phút, 7 ngày gần nhất được đếm lại và ghi đè; ngày cũ hơn giữ nguyên như lần ghi cuối | Tháng hiện tại và 12 tháng trước đó (`DAILY_KEEP_MONTHS` = 13), sau đó máy chủ tự xoá. `webhook.py --forget-usage` xoá sớm các dòng của một người |
| `screens` | Màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt đã ghép, khoá cho công cụ AI (loại `mcp`) và chat Telegram đã được duyệt cho hỏi bảng (loại `telegram`): bản băm của khoá, tên, chủ, loại, hạn; phần còn lại trong `body`. Khoá cho công cụ AI còn ghi nó được đọc gì (`scope`: `people` hoặc `totals`) và 12 ký tự đầu của nó (`keyStart`), để quản trị phân biệt các dòng. Chat Telegram cũng ghi `scope`, cùng số và tên @ của người dùng Telegram (`telegramId`, `telegramUser`); con số đó là thứ đứng thay cho khoá của nó. Chat được quản trị cho mở khung bên trong Telegram có `app: true`; chat đã bật tin báo có `notify`, `notifyMinutes` và `notifyLang` | Ghép, dùng, đổi tên, thu hồi | 30 ngày, tự gia hạn khi đang dùng, tối đa 1 năm |
| `revoked` | Bản băm của khoá đã thu hồi, để ghi nhật ký nếu còn bị dùng | Thu hồi | 30 ngày, tối đa 500 |
| `documents` | Hai tài liệu sửa nguyên khối: `locations` (tên văn phòng, dải IP, vị trí bản đồ, nhóm bán hàng) và `team-csv` (chi phí gói Team mới nhất, đã gộp theo người) | Quản trị sửa | Tới khi sửa |
| `audit` | Ai làm gì: đăng nhập, đổi tài khoản và ghép máy, thao tác bị từ chối; cột `month` để đọc theo tháng. Thêm mỗi lần gọi công cụ MCP của bảng một dòng (hành động `mcp-call`): tên và id của khoá, công cụ được gọi, có chạy hay không, IP, cái tên công cụ AI tự xưng và đời giao thức; không bao giờ có khoá và không bao giờ có câu hỏi. Và mỗi câu trả lời cho một chat Telegram một dòng (hành động `telegram-ask`): tên và id của chat cùng lệnh được trả lời; không bao giờ có chữ người đó gõ. Và mỗi việc một máy giao cho trợ lý một dòng (hành động `ai-delegation`): tên và tài khoản của người đó, mã máy, và các trường của biên bản ở trên; không bao giờ có đề bài hay câu trả lời. Mỗi dòng còn có `prev` và `hash`: dấu vân tay của dòng trước và của chính nó, nên một dòng bị sửa hay bị xoá bằng tay làm đứt chuỗi, và trang Quản trị kiểm chuỗi này | Mỗi thao tác quản trị; mỗi lần gọi công cụ MCP; mỗi câu trả lời và tin báo cho chat Telegram (`telegram-ask`, `telegram-alert`, tin báo chỉ ghi số người, không ghi là ai); mỗi lần mở khung bên trong Telegram, mỗi lần bị từ chối, và mỗi lần một chat được cho phép hay thôi (`telegram-app-*`) | 12 tháng (`KEEP_MONTHS`); dòng `mcp-call`, `telegram-ask` và `ai-delegation` 3 tháng (`MCP_CALL_KEEP_MONTHS`) |
| `delegations_seen` | Mã máy và mã biên bản của mỗi dòng `ai-delegation` đã ghi, để biên bản mà một máy gửi lại ở các nhịp sau chỉ được ghi một lần | Mỗi lần gửi có biên bản mới | 4 ngày (`SEEN_DAYS`) |
| `meta` | Lúc chuyển file JSON cũ vào và số dòng đã chuyển; ngày đầu tiên mà tổng theo ngày phủ tới (`daily_since`); dấu vân tay của dòng nhật ký mới nhất (`audit_head`) | Một lần; `audit_head` ở mỗi dòng nhật ký | Luôn giữ |

`accounts.db`:

| Bảng | Nội dung |
|---|---|
| `accounts` | Tên, vai, mã bí mật OTP (base32), lúc tạo và người tạo, lần đăng nhập cuối; mã người dùng và tên @ Telegram đã liên kết khi dùng đăng nhập Telegram |
| `imported` | Tên đã nhập từ `OTP=` trong file thiết lập, để tài khoản đã xoá trên `/admin` không sống lại |

Chỉ nằm trong bộ nhớ, mất khi khởi động lại: phiên đăng nhập (8 giờ, tài khoản màn hình treo tường 7 ngày), mã ghép TV (10 phút), mã dùng một lần của thanh menu (90 giây), trạng thái TV đang bật, số lần mỗi khoá cho công cụ AI đã hỏi trong 10 phút gần nhất và cái tên công cụ của nó xưng gần nhất.

Gửi sang Telegram, chỉ khi việc hỏi qua Telegram đang bật (`TELEGRAM_ASK=1`) và chỉ tới chat đã được quản trị duyệt: chữ của từng câu trả lời, và của từng tin báo mà chat đã bật bằng `/baocho` (có bao nhiêu người chờ quá số phút của chat, và với chat đọc từng người, tên họ như màn hình treo tường hiện kèm số phút). Nó được làm từ phần treo tường: số đếm và chi phí của cả đội và từng văn phòng, và, với chat đọc từng người, tên như màn hình treo tường hiện, trạng thái, số phút chờ, chi phí và hạn mức. Telegram còn có những gì người đó viết cho bot. Máy chủ không lưu tin nào trong số này, và tiến trình bot không ghi gì xuống đĩa.

Khung bên trong Telegram (`TELEGRAM_APP=1`) không gửi gì qua máy chủ của Telegram: app Telegram mở trang của bảng trong trình duyệt riêng, và trình duyệt đó đọc phần treo tường từ bảng qua HTTPS, như tiện ích trình duyệt. Telegram chỉ biết là khung đã được mở. Phiên của khung nằm trong bộ nhớ của webhook, dạng băm, và không bao giờ được ghi xuống đĩa.

## 3. Bản ghi của một máy

`devices.body`, phiên bản `v: 1`. Máy chủ làm sạch mọi trường trước khi ghi và lúc đọc ra (`clean_payload` trong `devices.py`): bỏ trường lạ, cắt chữ theo độ dài cố định, kiểm tra số.

| Trường | Ý nghĩa |
|---|---|
| `device` | Mã ngẫu nhiên `device-[a-z0-9]{1,40}` do plugin tạo |
| `name`, `account`, `enteredAccount` | Tên đã khai và email tài khoản Claude |
| `ip`, `lanIp`, `ipHistory` | IP gửi (lấy từ kết nối), IP nội bộ, 10 IP gần nhất trong 30 ngày. Lịch sử do máy chủ tự lập, máy nhân viên không gửi được |
| `hardwareMark` | Bản băm một chiều của mã phần cứng; các máy cùng dấu tính là một; không bao giờ hiện ra |
| `openSessions`, `working`, `waiting` | Số phiên đang mở, đang làm, đang chờ trả lời |
| `ledger` | Token và tiền theo giờ, 8 ngày gần nhất |
| `tasks`, `delegating` | Việc giao cho Gemini, ChatGPT và Gemma, theo giờ và lúc này |
| `delegations` | Chỉ khi nhận, không bao giờ lưu cùng dòng của máy: các biên bản giao việc cho ChatGPT, Gemini hay Gemma trong hai ngày gần nhất (tối đa 100), mỗi biên bản có mã, giờ, công cụ, trợ lý, `plugin` hay `ai-workers`, độ dài đề bài và câu trả lời, dấu vân tay có muối của đề bài, kết quả (`ok`, `error`, `refused`, `declined`), bước kiểm câu trả lời thấy gì (`secret`, `aimed`, `command`) và loại bí mật đã chặn nó. Không bao giờ có đề bài hay câu trả lời. Mỗi biên bản mới thành một dòng `ai-delegation` của `audit` (`clean_delegations` trong `devices.py`) |
| `blocks` | Theo giờ, 8 ngày gần nhất: số lần ai-worker đã chặn hay hỏi lại, theo loại `secret`, `commit`, `risky`, `page`, `answer`; chỉ số đếm, không bao giờ có nội dung (`BLOCK_KINDS` trong `devices.py`) |
| `models`, `subagents` | Số lượt theo từng model và từng trợ lý con |
| `assistants`, `quota` | Trợ lý phụ nào đã cài; hạn mức sử dụng theo phần trăm |
| `pluginVersion`, `updatedAt` | Phiên bản plugin và thời điểm của số liệu |
| `tools` | Chỉ có trong báo cáo của bộ nối cho Codex, Cursor và Gemini CLI: với mỗi công cụ `codex`, `cursor`, `gemini` là ba số đếm phiên. Báo cáo có bảng này là báo cáo của bộ nối |

**Báo cáo của bộ nối** gồm `device`, `name`, `account`, `updatedAt`, `tools` và các trường IP do máy chủ thêm, không có gì khác trong những thứ plugin gửi. Máy chủ tự cộng `openSessions`, `working` và `waiting` từ `tools`. Báo cáo được tính trong 2 giờ kể từ `updatedAt` (`CONNECTOR_OFFLINE_SECONDS`), trong khi báo cáo của plugin được tính 12 phút, vì bộ nối chỉ gửi khi có việc xảy ra trong công cụ; báo cáo không có phiên nào đang mở thì không làm người đó hiện là trực tuyến, và số `working` của nó chỉ được tin trong 30 phút (`CONNECTOR_WORKING_SECONDS`), vì công cụ có lượt bị lỗi không gửi sự kiện nào. Nó được gộp vào người có cùng tài khoản và tên, và không tính là một máy hay một bản cài plugin. Quy cách đầy đủ: [connectors/README.vi.md](../connectors/README.vi.md).

**Không bao giờ lưu:** nội dung chat, câu hỏi, tên file, tên dự án.

### Tổng theo từng người từng ngày

Mỗi máy giữ số liệu theo giờ trong 8 ngày, và dòng của máy rời khỏi máy chủ 30 ngày sau lần gửi cuối. Để so được tuần này với tuần khác, tháng này với tháng khác, máy chủ nhớ lâu hơn đúng một thứ: con số tổng của mỗi người trong mỗi ngày, ở bảng `daily`.

- **Không thu thêm gì mới.** Các tổng là phép cộng những con số mà máy vốn đã gửi. Người được phân biệt như trên bảng: tài khoản cộng với tên.
- **Đếm lại không bao giờ cộng trùng.** Mỗi lần chạy lấy 7 ngày gần nhất từ thứ các máy đang giữ rồi ghi đè lên các dòng đang có. Là 7 ngày vì máy nào cũng còn giữ đủ những ngày đó; ngày cũ hơn sẽ bị thiếu, nên không bao giờ bị đụng lại.
- **Văn phòng là văn phòng của hôm đó.** Ngày đã qua giữ văn phòng lúc nó được chốt; người chuyển chỗ thì được tính cho văn phòng mới từ ngày chuyển.
- **Đây là việc giữ dữ liệu nhân viên lâu hơn trước.** Trước khi có bảng này, chi phí của một người mất đi 30 ngày sau lần gửi cuối của máy họ. Giờ con số tổng mỗi ngày ở lại tối đa 13 tháng, kèm tên và email tài khoản. Hãy nói rõ điều đó trong thông báo gửi nhân viên: [employee-notice.vi.md](employee-notice.vi.md).
- **Người đã nghỉ việc** vẫn nằm trong các tổng cho tới khi các dòng hết hạn. Muốn xoá sớm: `webhook.py --forget-usage <email hoặc tên>`, xem [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 6.
- **Ai đọc được:** quản trị và người xem, trên `/board`. Vai treo tường chỉ nhận một thứ: chi phí của cả team trong từng ngày của 7 ngày gần nhất, mỗi ngày một con số, không có người, không có văn phòng, cho biểu đồ nhỏ trong khung thanh menu (`teamDays` trong `/data`). Không phần nào theo từng người hay từng văn phòng tới được màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt, plugin của quản lý hay cổng MCP ([PERMISSIONS.vi.md](PERMISSIONS.vi.md)).

## 4. Cách dùng cơ sở dữ liệu

- **Mỗi file một kết nối, sau một khoá.** Máy chủ web trả lời mỗi yêu cầu trong một luồng riêng; mọi luồng dùng chung một kết nối và lần lượt dùng. Tối đa 300 máy, mỗi máy nhiều nhất 30 giây gửi một lần, tức cao nhất khoảng 10 lần ghi mỗi giây.
- **Giao dịch.** Mỗi thay đổi là một giao dịch: ghi đủ cả, hoặc không ghi gì. Mỗi kho giữ bảng của mình dạng dict trong bộ nhớ và chỉ ghi các dòng đã đổi.
- **Chế độ WAL.** Đọc không phải chờ ghi. `synchronous=NORMAL` cho số liệu, `FULL` cho tài khoản.
- **Phiên bản lược đồ.** `PRAGMA user_version` giữ số phiên bản. Khi khởi động, máy chủ chạy lần lượt các bước nâng cấp còn thiếu. Cơ sở dữ liệu mới hơn chương trình thì bị từ chối, để bản cũ không lỡ chạy trên dữ liệu mới. `board.db` ở phiên bản 3 kể từ khi có biên bản giao việc (phiên bản 2 thêm tổng theo ngày); `accounts.db` ở phiên bản 1.
- **Một bản sao trước mỗi lần nâng.** Trước khi nâng một cơ sở dữ liệu đã có sẵn, máy chủ chép nó thành `<file>.schema-<phiên bản cũ>.bak` nằm ngay cạnh (quyền `600`), kiểm rằng bản sao mở được và đúng phiên bản cũ, rồi ghi một dòng vào nhật ký dịch vụ. Không chép được thì không nâng gì cả và dừng lại kèm thông báo. Máy chủ xoá bản sao sau 30 ngày. Cách quay lui bằng bản sao này: [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 5.
- **Chỉ dùng cú pháp SQL cũ.** Không dùng `UPSERT`, `RETURNING` hay hàm JSON, để chạy được cả trên Linux đời cũ.
- **Không đặt trên ổ mạng.** WAL cần ổ đĩa trong máy; không đặt `DATA_DIR` trên NFS.

### SQLite không thay đổi điều gì

SQLite không mã hoá: ai đọc được file là đọc được dữ liệu, giống file JSON cũ. Lớp bảo vệ là quyền file, tài khoản dịch vụ riêng, vùng cách ly của systemd, việc tách riêng tài khoản và việc chỉ lưu bản băm của khoá ghép.

### Chuyển từ file JSON

Các bản trước SQLite lưu mỗi bảng một file JSON. Lần khởi động đầu, bản mới tự chuyển chúng vào:

1. Đọc từng file cũ; file hỏng thì bỏ qua và ghi tên vào nhật ký dịch vụ.
2. Ghi các dòng vào cơ sở dữ liệu trong một giao dịch. Dòng đã có thì giữ nguyên.
3. Dời file cũ sang `data/legacy-json/` và `keys/legacy-json/`. Không bao giờ xoá.
4. Nhật ký hiện `migrated JSON files into ... {"devices": ..., ...}`.

File nào được đặt lại vào `data/` sau này sẽ được chuyển vào ở lần khởi động kế tiếp theo cách đó.

## 5. Sao lưu và khôi phục

Sao lưu khi máy chủ đang chạy bằng lệnh sao lưu của chính SQLite, không dùng `tar` hay `cp`, vì có thể chép phải WAL đang ghi dở. Lệnh nằm ở [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 4.

- Sao lưu `board.db` hằng ngày. File này không chứa mã bí mật. File `.schema-N.bak` không thay cho việc sao lưu này: nó chỉ là một bản sao ở thời điểm nâng cấp.
- Sao lưu `accounts.db` riêng, chỉ root đọc được. Mất file này thì mọi tài khoản phải quét lại mã QR.

Quay về bản trước SQLite mà không mất phần đã thay đổi từ đó: `webhook.py --export-json <thư-mục>` ghi cơ sở dữ liệu ngược ra file JSON cũ. Tổng theo ngày không có chỗ trong các file đó nên không được xuất. Xem [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 5.
