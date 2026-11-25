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
| `keys/receiver-secrets.json` | `/opt/ai-worker/keys/`, chỉ khi có `RECEIVER=1` | `ai-worker`, `600` | Thứ bộ nhận Go tuỳ chọn đọc: các bí mật ký khoá máy và mã của các đường nội bộ. Được ghi lại ở mỗi lần khởi động ([RECEIVER.vi.md](RECEIVER.vi.md)) |

Tài khoản nằm ở file riêng, thư mục riêng, để bản sao lưu số liệu không bao giờ mang theo mã bí mật đăng nhập. Dịch vụ systemd chỉ được ghi vào hai thư mục này (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Các bảng

`board.db`:

| Bảng | Nội dung | Ghi khi | Giữ |
|---|---|---|---|
| `devices` | Mỗi máy một dòng cho plugin, và thêm một dòng cho bộ nối Codex, Cursor và Gemini CLI ở máy có cài: số liệu mới nhất trong `body` (mục 3), không kèm sổ giờ, `seen_at` = lúc máy chủ nhận | Khi một lần gửi đổi nhiều hơn thời điểm, và ít nhất mỗi phút một lần khi máy đang gửi (`STATE_REWRITE_SECONDS`) | Xoá sau 30 ngày kể từ `seen_at` (`KEEP_DAYS`), cùng các dòng của nó trong `device_hours` và `device_days` |
| `device_hours` | Sổ giờ của từng máy, mỗi giờ mỗi loại (`ledger`, `tasks`, `blocks`) một dòng: giờ (số giờ từ 1970, giờ UTC), loại, máy, và số liệu của giờ đó dạng JSON trong `body`. Khoá bắt đầu bằng giờ, nên các giờ mới nhất của mọi máy nằm cạnh nhau ở cuối bảng; một chỉ mục thứ hai đọc các giờ của một máy. Có từ lược đồ phiên bản 6 | Mỗi lần gửi chỉ ghi các giờ đã đổi | 240 giờ mới nhất của mỗi loại (`MAX_HOURS_PER_DEVICE`), và khi máy còn trong `devices` |
| `device_days` | Mỗi máy mỗi ngày địa phương một dòng (ngày tính theo `TZ_OFFSET`): tiền theo phần triệu đô la, token vào và ra, việc giao cho Gemini, ChatGPT và Gemma, cộng từ các dòng `device_hours` của ngày đó. Bảng và tổng theo ngày đọc các dòng này thay vì cộng lại các giờ. Có từ lược đồ phiên bản 6 | Cùng lúc với các giờ của ngày đó | Khi ngày đó còn giờ trong `device_hours` |
| `identities` | `máy → tài khoản, tên` của lần gửi đầu | Máy mới gửi lần đầu | Tới khi xoá bằng `--forget-device` |
| `device_keys` | `máy → lúc cấp khoá riêng mới nhất mà máy đã dùng để gửi, lúc bị thu hồi`. Không bao giờ lưu bản thân khoá: khoá được kiểm bằng chữ ký (`server/board/devicekeys.py`). Khoá mới chỉ được cấp thì chưa ghi gì | Lần đầu máy gửi bằng một khoá riêng mới hơn, hoặc khi thu hồi | Tới khi xoá bằng `--forget-device` |
| `device_roaming` | `máy → từ lúc nào, do quản trị nào` cho các máy quản trị đã cho gửi số liệu và tải bản cập nhật từ mọi mạng (`OFFICE_NETS`). Chỉ có mã máy, không có địa chỉ. Từ lược đồ phiên bản 7 | **Mọi mạng** hoặc **Chỉ văn phòng** trên trang Quản trị | Tới khi thôi cho, hoặc máy bị thu hồi hay bị quên |
| `history` | Mỗi lần trạng thái một người đổi thì thêm một dòng: thời điểm, người, trạng thái, số việc đang giao | Trạng thái đổi | 24 giờ (nút tua lại) |
| `daily` | Mỗi người mỗi ngày một dòng (ngày tính theo `TZ_OFFSET`): tên, email tài khoản, văn phòng của người đó lúc chốt ngày, chi phí tính bằng đô la, token vào và ra, số việc giao cho Gemini, ChatGPT và Gemma. Cộng từ `ledger` và `tasks` của các máy của người đó (mục 3); không máy nào phải gửi thêm gì | Cứ 5 phút, 7 ngày gần nhất được đếm lại và ghi đè; ngày cũ hơn giữ nguyên như lần ghi cuối | Tháng hiện tại và 12 tháng trước đó (`DAILY_KEEP_MONTHS` = 13), sau đó máy chủ tự xoá. `webhook.py --forget-usage` xoá sớm các dòng của một người |
| `screens` | Màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt đã ghép, khoá cho công cụ AI (loại `mcp`), khoá cho dự án hay ứng dụng AI (loại `project`, cũng có `keyStart`) và chat Telegram đã được duyệt cho hỏi bảng (loại `telegram`): bản băm của khoá, tên, chủ, loại, hạn; phần còn lại trong `body`. Khoá cho công cụ AI còn ghi nó được đọc gì (`scope`: `people` hoặc `totals`) và 12 ký tự đầu của nó (`keyStart`), để quản trị phân biệt các dòng. Chat Telegram cũng ghi `scope`, cùng số và tên @ của người dùng Telegram (`telegramId`, `telegramUser`); con số đó là thứ đứng thay cho khoá của nó. Chat được quản trị cho mở khung bên trong Telegram có `app: true`; chat đã bật tin báo có `notify`, `notifyMinutes` và `notifyLang` | Ghép, dùng, đổi tên, thu hồi | 30 ngày, tự gia hạn khi đang dùng, tối đa 1 năm |
| `revoked` | Bản băm của khoá đã thu hồi, để ghi nhật ký nếu còn bị dùng | Thu hồi | 30 ngày, tối đa 500 |
| `documents` | Các tài liệu sửa nguyên khối: `locations` (tên văn phòng, dải IP, vị trí bản đồ, nhóm bán hàng), `team-csv` (chi phí gói Team mới nhất, đã gộp theo người) và `project-prices` (giá quản trị dán cho dự án hay ứng dụng AI) | Quản trị sửa | Tới khi sửa |
| `audit` | Ai làm gì: đăng nhập, đổi tài khoản và ghép máy, thao tác bị từ chối; cột `month` để đọc theo tháng. Thêm mỗi lần gọi công cụ MCP của bảng một dòng (hành động `mcp-call`): tên và id của khoá, công cụ được gọi, có chạy hay không, IP, cái tên công cụ AI tự xưng và đời giao thức; không bao giờ có khoá và không bao giờ có câu hỏi. Và mỗi câu trả lời cho một chat Telegram một dòng (hành động `telegram-ask`): tên và id của chat cùng lệnh được trả lời; không bao giờ có chữ người đó gõ. Và mỗi việc một máy giao cho trợ lý một dòng (hành động `ai-delegation`): tên và tài khoản của người đó, mã máy, và các trường của biên bản ở trên; không bao giờ có đề bài hay câu trả lời. Mỗi dòng còn có `prev` và `hash`: dấu vân tay của dòng trước và của chính nó, nên một dòng bị sửa hay bị xoá bằng tay làm đứt chuỗi, và trang Quản trị kiểm chuỗi này | Mỗi thao tác quản trị; mỗi lần gọi công cụ MCP; mỗi câu trả lời và tin báo cho chat Telegram (`telegram-ask`, `telegram-alert`, tin báo chỉ ghi số người, không ghi là ai); mỗi lần mở khung bên trong Telegram, mỗi lần bị từ chối, và mỗi lần một chat được cho phép hay thôi (`telegram-app-*`) | 12 tháng (`KEEP_MONTHS`); dòng `mcp-call`, `telegram-ask` và `ai-delegation` 3 tháng (`MCP_CALL_KEEP_MONTHS`) |
| `delegations_seen` | Mã máy và mã biên bản của mỗi dòng `ai-delegation` đã ghi, để biên bản mà một máy gửi lại ở các nhịp sau chỉ được ghi một lần | Mỗi lần gửi có biên bản mới | 4 ngày (`SEEN_DAYS`) |
| `project_turns` | Từng lượt mà một dự án hay ứng dụng AI đã gửi (chỉ khi `AI_PROJECTS=1`): dự án (id của khoá), `turn_id`, thời điểm, ngày UTC, môi trường, và lượt đó theo định dạng dòng của bộ đo, đã làm sạch chỉ còn trường đã biết: thời gian, kết quả, và theo từng model: hãng, tên model, số lần gọi, lỗi, gọi lại và số token. Không bao giờ có câu hỏi, câu trả lời, người dùng hay thông báo lỗi; bộ đo không có chúng | Mỗi lần gửi tới `/projects/ingest`; lượt gửi lại bị bỏ qua | 30 ngày (`PROJECT_TURN_KEEP_DAYS`), hoặc tới khi quản trị xoá số liệu của một dự án đã thu hồi khoá |
| `project_daily` | Mỗi dự án, ngày UTC, môi trường và model một dòng: tên dự án, số lượt, lần gọi, lỗi, gọi lại, lượt không đo được và số token; dòng không hãng, không model đếm mỗi lượt một lần. Không bao giờ lưu tiền: tiền được tính từ token và bảng giá lúc có người xem | Với mỗi lượt mới | Tháng hiện tại và 12 tháng trước, như `daily`, hoặc tới khi quản trị xoá số liệu của một dự án đã thu hồi khoá |
| `meta` | Lúc chuyển file JSON cũ vào và số dòng đã chuyển; ngày đầu tiên mà tổng theo ngày phủ tới (`daily_since`); dấu vân tay của dòng nhật ký mới nhất (`audit_head`); độ lệch so với UTC, tính bằng giây, mà `device_days` đã đếm ngày theo (`device_days_tz`: khi `TZ_OFFSET` đổi, máy chủ đếm lại `device_days` ở lần khởi động sau) | Một lần; `audit_head` ở mỗi dòng nhật ký | Luôn giữ |

`accounts.db`:

| Bảng | Nội dung |
|---|---|
| `accounts` | Tên, vai, mã bí mật OTP (base32), lúc tạo và người tạo, lần đăng nhập cuối; mã người dùng và tên @ Telegram đã liên kết khi dùng đăng nhập Telegram |
| `imported` | Tên đã nhập từ `OTP=` trong file thiết lập, để tài khoản đã xoá trên `/admin` không sống lại |

Chỉ nằm trong bộ nhớ, mất khi khởi động lại: phiên đăng nhập (8 giờ, tài khoản màn hình treo tường 7 ngày), mã ghép TV (10 phút), mã dùng một lần của thanh menu (90 giây), trạng thái TV đang bật, số lần mỗi khoá cho công cụ AI đã hỏi trong 10 phút gần nhất và cái tên công cụ của nó xưng gần nhất.

Gửi sang Telegram, chỉ khi việc hỏi qua Telegram đang bật (`TELEGRAM_ASK=1`) và chỉ tới chat đã được quản trị duyệt: chữ của từng câu trả lời, và của từng tin báo mà chat đã bật bằng `/baocho` (có bao nhiêu người chờ quá số phút của chat, và với chat đọc từng người, tên họ như màn hình treo tường hiện kèm số phút). Nó được làm từ phần treo tường: số đếm và chi phí của cả đội và từng văn phòng, và, với chat đọc từng người, tên như màn hình treo tường hiện, trạng thái, số phút chờ, chi phí và hạn mức. Telegram còn có những gì người đó viết cho bot. Máy chủ không lưu tin nào trong số này, và tiến trình bot không ghi gì xuống đĩa.

Khung bên trong Telegram (`TELEGRAM_APP=1`) không gửi gì qua máy chủ của Telegram: app Telegram mở trang của bảng trong trình duyệt riêng, và trình duyệt đó đọc phần treo tường từ bảng qua HTTPS, như tiện ích trình duyệt. Telegram chỉ biết là khung đã được mở. Phiên của khung nằm trong bộ nhớ của webhook, dạng băm, và không bao giờ được ghi xuống đĩa.

## 3. Bản ghi của một máy

`devices.body`, phiên bản `v: 1`, với `ledger`, `tasks` và `blocks` nằm ở các dòng `device_hours` từ lược đồ phiên bản 6 (`read_book` trong `devices.py` ghép chúng lại, và `--export-json` ghi cả bản ghi như trước). Máy chủ làm sạch mọi trường trước khi ghi và lại làm sạch khi nạp một dòng vào bộ nhớ (`clean_payload` và `DeviceCache` trong `devices.py`); bảng, lịch sử và tổng theo ngày đọc bản đã làm sạch giữ trong bộ nhớ, bản này được ghi cùng lúc với các bảng và nạp lại khi chương trình khác đổi file: bỏ trường lạ, cắt chữ theo độ dài cố định, kiểm tra số. Bộ nhớ giữ bản ghi của mỗi máy không kèm sổ giờ, các dòng `device_days` của nó, và chỉ các giờ gần lần gửi cuối: 48 giờ `ledger` và `tasks`, 8 ngày `blocks`. Mọi câu SQL của ba bảng này nằm trong `server/board/devicestore.py`.

| Trường | Ý nghĩa |
|---|---|
| `device` | Mã ngẫu nhiên `device-[a-z0-9]{1,40}` do plugin tạo. Bản cài mới tạo 16 chữ và số từ nguồn ngẫu nhiên an toàn, như bộ nối; mã do bản cũ tạo (8 ký tự) được giữ nguyên |
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

### Định dạng v: 2

Plugin mới có thể gửi `v: 2` thay cho `v: 1`. Máy chủ đọc cả hai, chừng nào còn máy gửi `v: 1`; thứ nó giữ luôn là bản ghi `v: 1` ở trên, nên bảng, lịch sử và tổng theo ngày không biết máy đã dùng định dạng nào. Bộ dữ liệu mẫu chung trong `tests/contract/ingest-v2/` (đầu vào và kết quả phải ra) và `server/test_contract.py` buộc hai định dạng cho ra cùng một bảng; bộ nhận viết bằng ngôn ngữ khác chạy cùng file đó.

- **Phần trạng thái** (`name`, `account`, số phiên, `models`, `quota`, `pluginVersion` và các trường khác) có cùng tên trường như `v: 1` và được gửi đủ mỗi lần.
- **Các giờ** nằm trong `hours: {ledger, tasks, blocks}` và chỉ gồm các giờ đã đổi kể từ lần gửi gần nhất máy chủ đã nhận. Mỗi giờ là giá trị đầy đủ của giờ đó, không phải phần cộng thêm, và thay giờ cũ; giờ không gửi thì giữ nguyên; giờ gửi lên là bảng rỗng thì bị xoá (nó đã rời 8 ngày của máy). Gửi lặp một giờ vẫn ra cùng kết quả, nên không cần số thứ tự (`merge_hours` trong `devices.py`, hàm thuần để bộ nhận khác chép lại).
- **`full: true`** nghĩa là `hours` chứa cả sổ của máy và thay toàn bộ sổ đó. Nếu máy chủ không yêu cầu, mỗi máy được làm vậy một lần mỗi giờ (`FULL_BOOK_SECONDS`); sổ đủ gửi sớm hơn được ghép từng giờ, không mất gì.
- **Tiền** là `usdMicro`, số nguyên phần triệu đô la. Gói `v: 1` chỉ có đô la (`usd`); máy chủ đổi sang `usdMicro` (làm tròn) và cộng mọi tổng bằng số nguyên, nên tổng đúng tuyệt đối và như nhau dù cộng theo thứ tự nào, ở ngôn ngữ nào. Dòng lưu vẫn giữ `usd` bên cạnh cho các bản máy chủ cũ.
- **Giới hạn:** làm sạch như `v: 1`, thêm: mỗi loại tối đa 240 giờ, không giờ nào sớm hơn đồng hồ máy chủ quá một ngày, không giờ nào cũ hơn 240 giờ.
- **Tới sai thứ tự:** gói `v: 2` có giờ cũ hơn bản máy chủ đang giữ trong vòng một phút (`REORDER_WINDOW_MS`; hai phiên của một máy gửi cùng lúc) bị bỏ. Cũ hơn nữa thì coi là đồng hồ bị chỉnh lùi, và vẫn ghi.
- **Mỗi máy ghi lần lượt:** đọc dòng đang giữ, ghép và ghi nằm trong một khoá, nên hai lần gửi cùng lúc của một máy không bao giờ làm mất giờ của nhau.

Câu trả lời cho mọi lần gửi, ở cả hai định dạng (plugin cũ chỉ đọc `ok` và `deviceKey`):

| Trường | Ý nghĩa |
|---|---|
| `accepts` | Các định dạng máy chủ này đọc được: `[1, 2]`. Plugin chỉ gửi `v: 2` tới máy chủ nói vậy; máy chủ cũ chỉ trả `{"ok": true}` |
| `minGapMs`, `stateGapMs` | Khoảng ngắn nhất giữa hai lần gửi số và gửi trạng thái: mặc định 2 giây (`INGEST_MIN_GAP_MS`, `INGEST_STATE_GAP_MS`). Máy chủ Python kéo dài nó khi số máy đã gửi trong phút vừa qua nhiều hơn mức `INGEST_SENDS_PER_SECOND` (mặc định 1.000) trả lời được mỗi 2 giây, và bộ nhận Go kéo dài nó khi số máy kết nối nhiều hơn sức máy trả lời mỗi 2 giây ([RECEIVER.vi.md](RECEIVER.vi.md), `RECEIVER_SENDS_PER_SECOND`). Plugin giữ đúng khoảng này, dài nhất 2 phút, và sau một lần 429 hay 503 kèm `Retry-After` thì không gửi gì trước thời điểm đó (lâu nhất 10 phút) |
| `maxGapMs` | Dù không có gì đổi, vẫn gửi ít nhất mỗi chừng này: 4 phút (`INGEST_MAX_GAP_MS`, tối đa 5), thấp hơn nhiều so với 12 phút là lúc máy hiện ngoại tuyến |
| `needFull` | `true` khi một gói `v: 2` chỉ có các giờ đã đổi đến từ máy mà máy chủ không có sổ (máy mới, dòng bị mất hay hỏng): không giữ gì của gói đó, và lần gửi sau phải là `full: true` |
| `boot` | Một giá trị ngẫu nhiên mới mỗi lần máy chủ khởi động. Plugin thấy nó đổi thì gửi lại các giờ gần nhất, phòng khi vài giây cuối trước lúc sập chưa kịp ghi |
| `deviceKey` | Như trước: khoá riêng của máy này, khi máy gửi bằng khoá chung hoặc khoá sắp cũ |
| `ingestUrls`, `ingestTtlMs` | Chỉ cho máy được chọn cho bộ nhận Go và gửi bằng khoá riêng: từ giờ gửi tới đâu, và trong bao lâu rồi mới hỏi lại `GET /ingest/route` ([RECEIVER.vi.md](RECEIVER.vi.md), "Máy nào gửi tới bộ nhận") |

### Tổng theo từng người từng ngày

Mỗi máy giữ số liệu theo giờ trong 8 ngày, và dòng của máy rời khỏi máy chủ 30 ngày sau lần gửi cuối. Để so được tuần này với tuần khác, tháng này với tháng khác, máy chủ nhớ lâu hơn đúng một thứ: con số tổng của mỗi người trong mỗi ngày, ở bảng `daily`.

- **Không thu thêm gì mới.** Các tổng là phép cộng những con số mà máy vốn đã gửi. Người được phân biệt như trên bảng: tài khoản cộng với tên.
- **Đếm lại không bao giờ cộng trùng.** Mỗi lần chạy lấy 7 ngày gần nhất từ thứ các máy đang giữ rồi ghi đè lên các dòng đang có. Là 7 ngày vì máy nào cũng còn giữ đủ những ngày đó; ngày cũ hơn sẽ bị thiếu, nên không bao giờ bị đụng lại.
- **Văn phòng là văn phòng của hôm đó.** Ngày đã qua giữ văn phòng lúc nó được chốt; người chuyển chỗ thì được tính cho văn phòng mới từ ngày chuyển.
- **Đây là việc giữ dữ liệu nhân viên lâu hơn trước.** Trước khi có bảng này, chi phí của một người mất đi 30 ngày sau lần gửi cuối của máy họ. Giờ con số tổng mỗi ngày ở lại tối đa 13 tháng, kèm tên và email tài khoản. Hãy nói rõ điều đó trong thông báo gửi nhân viên: [employee-notice.vi.md](employee-notice.vi.md).
- **Người đã nghỉ việc** vẫn nằm trong các tổng cho tới khi các dòng hết hạn. Muốn xoá sớm: `webhook.py --forget-usage <email hoặc tên>`, xem [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 6.
- **Ai đọc được:** quản trị và người xem, trên `/board`. Vai treo tường chỉ nhận một thứ: chi phí của cả team trong từng ngày của 7 ngày gần nhất, mỗi ngày một con số, không có người, không có văn phòng, cho biểu đồ nhỏ trong khung thanh menu (`teamDays` trong `/data`). Không phần nào theo từng người hay từng văn phòng tới được màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt, plugin của quản lý hay cổng MCP ([PERMISSIONS.vi.md](PERMISSIONS.vi.md)).

## 4. Cách dùng cơ sở dữ liệu

- **Mỗi file một kết nối, sau một khoá.** Máy chủ web trả lời mỗi yêu cầu trong một luồng riêng; mọi luồng dùng chung một kết nối và lần lượt dùng. Với 300 máy, mỗi máy nhiều nhất 2 giây gửi một lần, tức cao nhất khoảng 150 lần ghi mỗi giây; docs/BENCHMARK.vi.md có mức trần đã đo.
- **Giao dịch.** Mỗi thay đổi là một giao dịch: ghi đủ cả, hoặc không ghi gì. Mỗi kho giữ bảng của mình dạng dict trong bộ nhớ và chỉ ghi các dòng đã đổi.
- **Chế độ WAL.** Đọc không phải chờ ghi. `synchronous=NORMAL` cho số liệu, `FULL` cho tài khoản.
- **Phiên bản lược đồ.** `PRAGMA user_version` giữ số phiên bản. Khi khởi động, máy chủ chạy lần lượt các bước nâng cấp còn thiếu. Cơ sở dữ liệu mới hơn chương trình thì bị từ chối, để bản cũ không lỡ chạy trên dữ liệu mới. `board.db` ở phiên bản 6 kể từ khi sổ giờ chuyển sang `device_hours` và `device_days` (phiên bản 5 thêm khoá riêng cho từng máy, 4 thêm dự án AI, 3 thêm biên bản giao việc, 2 thêm tổng theo ngày). Một bước có thể là hàm Python chạy trong giao dịch của lần nâng: phiên bản 6 lấy sổ của mỗi bản ghi ra khỏi dòng `devices`, ghi các giờ và các ngày của nó, và để nguyên dòng nó không đọc được. Các bí mật ký những khoá đó nằm trong bảng `meta` của `accounts.db`.
- **Một bản sao trước mỗi lần nâng.** Trước khi nâng một cơ sở dữ liệu đã có sẵn, máy chủ chép nó thành `<file>.schema-<phiên bản cũ>.bak` nằm ngay cạnh (quyền `600`), kiểm rằng bản sao mở được và đúng phiên bản cũ, rồi ghi một dòng vào nhật ký dịch vụ. Không chép được thì không nâng gì cả và dừng lại kèm thông báo. Máy chủ xoá bản sao sau 30 ngày. Cách quay lui bằng bản sao này: [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 5.
- **Dùng cú pháp SQL cũ ở chỗ cần.** Không dùng `RETURNING` và không dùng hàm JSON của SQLite: JSON do Python đọc và ghi. Ghi đè một dòng dùng `INSERT ... ON CONFLICT ... DO UPDATE` khi SQLite có cú pháp này (3.24, năm 2018), và một `UPDATE` rồi một `INSERT` với bản cũ hơn, để máy chủ vẫn chạy được trên Linux đời cũ. Không bao giờ dùng `INSERT OR REPLACE` ở các bảng mới: nó xoá dòng trước.
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
- Sao lưu `accounts.db` riêng, chỉ root đọc được. Mất file này thì mọi tài khoản phải quét lại mã QR. Khoá OTP trong đó được niêm phong bằng `/etc/ai-worker-otp.key` (lược đồ phiên bản 2): giữ một bản của khoá đó tách khỏi các bản sao lưu, xem [OPERATIONS.vi.md](OPERATIONS.vi.md) mục 4.

Quay về bản trước SQLite mà không mất phần đã thay đổi từ đó: `webhook.py --export-json <thư-mục>` ghi cơ sở dữ liệu ngược ra file JSON cũ. Tổng theo ngày không có chỗ trong các file đó nên không được xuất. Xem [OPERATIONS.vi.md](OPERATIONS.vi.md), mục 5.
