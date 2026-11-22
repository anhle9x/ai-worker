# Bộ nhận bằng Go (tuỳ chọn, cho tổ chức lớn)

Tiếng Việt | [English](RECEIVER.md)

Công ty nhỏ không cần trang này: máy chủ Python tự nhận mọi lần gửi. Bộ nhận trong `receiver/` là một chương trình thứ hai, viết chỉ bằng thư viện chuẩn của Go, cho tổ chức có nhiều nghìn máy. Nó nhận các lần gửi của máy trên một địa chỉ riêng qua TLS, trả lời ngay, rồi trao chúng cho máy chủ Python theo lô. Python vẫn là bản gốc: đăng nhập, vai, bảng, lịch sử và các file SQLite không đổi.

**Đợt đầu này làm gì và chưa làm gì.** Nó nhận số đúng và đưa cho Python đúng những bản ghi mà Python tự ghi sẽ ra; các bài kiểm giữ hai bên như vậy. Nó còn phục vụ các bảng số trực tiếp, theo chi nhánh hoặc cho cả tổ chức, ở `/live` (mục 3, "Luồng số trực tiếp"), và trang bảng mở luồng đó khi luồng đã được cài. Có đạt 100.000 máy dưới 5 giây không thì đo trên Linux ở cuối đợt này. Plugin cũng chưa gửi tới bộ nhận: chưa máy nào đi đường này cho tới khi một bản plugin sau biết địa chỉ bộ nhận từ máy chủ (`ingestUrls`).

## 1. Một lần gửi đi thế nào

| Lần gửi | Bộ nhận làm gì |
|---|---|
| Có khoá riêng của máy (`awd1.…`), chưa tới hạn gia hạn | Kiểm khoá, làm sạch lần gửi, đặt lên các giờ hôm nay nó giữ cho máy đó, trả lời, và đặt lên dòng duy nhất đang chờ Python của máy đó |
| Có khoá chung `INGEST_KEY`, có khoá tới hạn gia hạn (cũ hơn 30 ngày, hoặc cấp trước `--rotate-device-secret`), hoặc các byte bộ nhận không chắc Python đọc giống hệt | Chuyển nguyên văn cho Python, kèm địa chỉ thật của máy; câu trả lời của Python được trả lại với `boot` của bộ nhận thay cho của Python |

- Tên và tài khoản máy tự khai bị bỏ; Python điền chúng từ người mà máy đã ghi danh (`identities`).
- Bộ nhận không bao giờ tin `X-Forwarded-For` do máy gửi: nó đưa cho Python địa chỉ của socket.
- Biên bản giao việc cho trợ lý, lịch sử IP và lịch sử của bảng do Python ghi, như với một lần gửi ở `/ingest`.
- Máy được Python xin cả sổ (`needFull`), lần gửi tới sai thứ tự, hay cả sổ gửi lại trong vòng một giờ được xử lý đúng như Python làm (`save_ingest`).
- Câu trả lời một lần gửi có đúng các trường như của Python, với `boot` riêng của bộ nhận: các dòng chưa ghi bị mất nếu bộ nhận dừng, và máy thấy `boot` đổi thì gửi lại các giờ gần nhất.

## 2. Bộ nhận chép gì của Python, và giữ cho giống nhau ra sao

Bước làm sạch một lần gửi là ranh giới của những gì tới được bảng. Bộ nhận chép nó từ `server/board/devices.py`: `clean_payload`, `clean_delegations`, `merge_hours`, các lựa chọn của `save_ingest`, tiền theo số nguyên `usdMicro`, và tổng theo ngày của `add_up_hours`. Bốn chi tiết quan trọng được chép có chủ đích:

- thứ tự khoá của một bảng JSON, và khoá tới hai lần giữ chỗ đầu và giá trị cuối (như `dict` của Python);
- số không có dấu chấm hay số mũ là số nguyên, số khác là số thực, và hai loại được giữ riêng;
- `round` làm tròn nửa về số chẵn (`math.RoundToEven`);
- giờ là khoá dạng chữ, xếp theo con số của nó bằng cách sắp ổn định.

Thứ gì bộ nhận không chắc Python đọc giống hệt (một nửa cặp UTF-16 đứng riêng, dấu thứ tự byte, NaN, độ lồng sâu hơn 200) thì được chuyển nguyên văn cho Python.

Ba lớp đối chiếu giữ hai bên giống nhau:

1. **Bộ mẫu chung** `tests/contract/ingest-v2/cases.json`, chạy ở máy chủ Python (`server/test_contract.py`) và ở bộ nhận (`receiver/internal/clean/contract_test.go`).
2. **Bài thử ngẫu nhiên có Python làm trọng tài**: `tests/contract/ingest-v2/fuzz_judge.py` tạo các lần gửi ngẫu nhiên và làm sạch chúng bằng chính mã của máy chủ; bài test Go làm sạch cùng các byte đó và phải ra cùng kết quả, khoá cùng thứ tự. `FUZZ_SEED` và `FUZZ_COUNT` đổi hạt giống và số lượng.
3. **Khi chạy thật**, bộ nhận còn chuyển nguyên văn `RECEIVER_CHECK_PERCENT` số lần gửi (mặc định 1%) cho Python; Python làm sạch lại và đếm mọi chỗ khác (`checked`, `mismatches` trong tài liệu chính sách bên dưới, và một dòng trong nhật ký).

Python cũng làm sạch lại từng dòng khi ghi, nên bước làm sạch của chính nó vẫn là ranh giới.

Số trực tiếp (`receiver/internal/live`) chép cách bảng dựng một người: `is_fresh`, `status_of`, và các phần của `group_by_person` và `_raw_data` làm ra `status`, `openSessions`, `working`, `waiting`, `delegating`, `tools`, `usdToday`, `tokensIn`, `tokensOut`, `tasks` và `updatedAt`. Lớp đối chiếu thứ tư giữ chúng đúng như vậy: `receiver/internal/ingest/live_test.go` chạy máy chủ Python thật bên trong `tests/contract/ingest-v2/view_judge.py`, chạy bộ mẫu chung qua bộ nhận (dời về vài ngày trước, mỗi lượt chạy một người riêng), và sau mỗi bước so các dòng của bộ nhận với `role_view` lấy từ bộ nhớ của máy chủ đó, lúc gửi, ngay trước và ngay sau khi máy thành ngoại tuyến, và sang ngày hôm sau; bài test thứ hai làm như vậy cho mọi trạng thái, một bộ nối mở hai công cụ và tổng của từng chi nhánh.

## 3. Giữa bộ nhận và Python

Bộ nhận gọi máy chủ Python trên chính máy này (`RECEIVER_WEBHOOK`, mặc định `http://127.0.0.1:8788`). Các đường dưới đây chỉ có khi `RECEIVER=1`, chỉ nhận lời gọi thẳng từ máy này (không có header chuyển tiếp) và chỉ với mã nội bộ trong file bí mật; mọi thứ khác nhận 404, như thể đường đó không tồn tại.

| Đường | Việc |
|---|---|
| `POST /internal/rows` | Một lô: `{"src", "boot", "seq", "rows": [...]}`. Mỗi dòng là `{"k": ["m", mã máy], "at": ms, "kind", "ip", "v", "raw"?}`: `kind` là `v1`, `hours`, `full` (thứ bộ nhận đã áp) hoặc `delegations` (chỉ biên bản giao việc, cho lần gửi mà số liệu không được ghi); `v` là lần gửi đã làm sạch theo định dạng nó tới. Từ giao thức 2 (`proto` trong tài liệu chính sách) mỗi lô có nhiều nhất một dòng cho mỗi máy: các lần gửi của một máy giữa hai lô được gộp thành một dòng, trạng thái mới nhất cùng mọi giờ đã gửi từ đó (giá trị sau của một giờ thắng, giờ rỗng vẫn xoá giờ đó, các giờ đã đổi sau một sổ đủ thì đặt lên sổ đó) và biên bản giao việc của tất cả các lần gửi, để Python ghi một lần đúng thứ nó đã ghi qua từng lần gửi. Dòng loại `check` mang một lần gửi nguyên văn (`raw`) và như bộ nhận đã làm sạch (`v`), chỉ cho lớp đối chiếu thứ ba: Python so chúng và không ghi gì (chờ nhiều nhất 1.000 dòng, quá thì bỏ). Python ghi cả lô trong một giao dịch, mỗi dòng sau một điểm lưu riêng, và trả `{"ok", "seq", "needFull": [...], "unknown": [...], "incomplete": [...], "bad": [...]}`: `bad` nêu các dòng hỏng đã bị bỏ ra riêng (bộ nhận đọc lại sổ của máy đó), `incomplete` các máy mà người của nó chưa có email hay tên (bộ nhận chuyển lần gửi kế tiếp có mang chúng, để Python điền vào và cấp khoá cho người mới). Bộ nhận giữ lô cho tới khi `seq` của nó được trả lời, không thì gửi lại đúng lô đó, không đổi gì; các lần gửi đến trong lúc đó chờ lô sau. Lô có `seq` đã ghi được trả lời và không ghi hai lần. Khi Python không trả lời, mỗi máy chờ nhiều nhất một dòng, cộng lô đang đi, và mọi lần gửi vẫn được trả lời 200 |
| `POST /internal/ingest` | Một lần gửi chuyển nguyên văn, nhiều nhất 16 lần cùng lúc: quá mức đó máy được báo quay lại ngay (503 kèm `Retry-After`). `Authorization` của máy nằm trong `X-Receiver-Authorization` và địa chỉ của nó trong `X-Receiver-Client-Ip`; Python kiểm khoá đúng như ở `/ingest` |
| `GET /internal/policy?since=<seq>&boot=<boot>` | Tài liệu chính sách có số thứ tự, hỏi mỗi 15 giây: máy bị thu hồi, `renewBefore`, nhịp gửi dặn các máy, `SHARED_KEY_MODE`, các giới hạn, và `written`, các máy Python tự ghi kể từ `since` (bộ nhận bỏ sổ nó đang giữ cho các máy đó). `reset: true` sau một lần Python khởi động lại: bộ nhận bỏ mọi sổ. `proto: 2` là phiên bản của giao thức này |
| `GET /internal/devices?after=<mã máy>&limit=<n>` hoặc `?device=<mã>` | Các giờ từ hôm nay trở đi của từng máy, từng trang khi bộ nhận khởi động, hoặc của một máy khi cần: bộ nhận không giữ hơn. Mỗi bản ghi còn có trạng thái mà số trực tiếp cần (`openSessions`, `working`, `waiting`, `delegating`, và `tools` với bộ nối), không có tên, email hay địa chỉ. `&whole=1` cùng `device` trả cả sổ của máy đó, cho các bài test so bộ nhận với Python |
| `GET /internal/people?since=<seq>&boot=<boot>&limit=<n>` | Bảng người (bên dưới): phần đổi kể từ `since`, theo thứ tự thay đổi, mỗi lần nhiều nhất `limit` (5.000): `{"boot", "reset", "seq", "more", "people": [{"device", "row", "scope"}], "gone": [...]}`. Hỏi khi bộ nhận khởi động và mỗi 15 giây, nên người chuyển sang chi nhánh khác hiện đúng chỗ trong 10 tới 25 giây. Khi `more` còn đúng, bộ nhận hỏi lại với `since=seq`, thêm `&loading=1` trong lúc nạp cả bảng sau một lần `reset` (Python khởi động lại, hoặc một số Python không còn trả lời được: khi đó bộ nhận bỏ bảng nó đang giữ) |

### File bí mật

Với `RECEIVER=1`, máy chủ Python ghi `KEYS_DIR/receiver-secrets.json` (hoặc `RECEIVER_SECRETS_FILE`) ở mỗi lần khởi động và mỗi lần `--rotate-device-secret`: ghi ra file tạm rồi đổi tên, chỉ tài khoản của máy chủ đọc được (0600).

```json
[
 {"kid": "…", "alg": "HS256", "org": "…", "secret": "…", "since": 0},
 {"kid": "internal", "alg": "internal", "secret": "…"},
 {"kid": "…", "alg": "ticket", "secret": "…"}
]
```

Các bí mật ký xếp mới nhất trước; bí mật cũ được giữ khi khoá nó đã ký có thể vẫn còn sống. Mục cuối ký vé của luồng số trực tiếp (bên dưới): một bí mật riêng, không bao giờ là bí mật của khoá máy, nên vé không dùng làm khoá được và khoá không dùng làm vé được; `--rotate-device-secret` cũng xoay nó. Bộ nhận đọc lại file khi nó đổi, và khi một khoá nêu `kid` chưa biết (nhiều nhất 10 giây một lần). Ai giữ file này làm được khoá cho mọi máy và gửi số thay nó, nhưng không đọc được dữ liệu nào: giữ nó trên máy chủ, và chạy bộ nhận bằng cùng tài khoản với webhook.

### Mã dòng và phạm vi

Bộ nhận gửi cho bảng số trực tiếp theo từng chi nhánh. Để làm việc đó, mỗi người trên bảng có mã dòng của mình, và bảng đọc được theo từng chi nhánh:

- **Mã dòng** (`row` ở mỗi người của `/data`, chỉ khi `RECEIVER=1`): 12 ký tự, HMAC của người đó (`person_key`: tài khoản và tên) bằng cùng bí mật với mã thay email trên màn treo tường (`wall_alias_secret` trong cơ sở dữ liệu khoá) với nhãn khác. Nó như nhau cho mọi vai, sau khi khởi động lại và ở mọi tiến trình, và không cho ngược lại email hay tên, nên số trực tiếp được đặt đúng dòng mà màn treo tường không bao giờ thấy email. Người được ghép theo mã này, không bao giờ theo `pid` trong khoá của máy.
- **Số trực tiếp** (`receiver/internal/live`): bộ nhận giữ trạng thái của từng máy như lần gửi cuối để lại (thời điểm, số phiên, số theo từng công cụ của bộ nối, số việc đang giao cho trợ lý) và tổng theo từng ngày địa phương của nó, rồi cộng chúng ở một giây cho trước thành mỗi mã một dòng, như bảng làm: `row`, `branch` (phạm vi của nó), `status`, `openSessions`, `working`, `waiting`, `delegating`, `tools`, `usdToday` (làm tròn như bảng làm tròn, kèm `usdMicroToday`), `tokensIn`, `tokensOut`, `tasks`, `updatedAt`; và theo từng chi nhánh là các trường của `branchTotals`. Một máy chỉ lên một dòng khi bảng người đã nêu nó. Khi Python tự ghi một máy (lần gửi được chuyển tiếp, `written` trong chính sách, dòng nó bỏ ra hay không nhận), bộ nhận đọc lại bản ghi của máy đó sau lô hay lần hỏi chính sách kế tiếp, trừ khi máy đó còn dòng đang chờ, nên số trực tiếp không bao giờ lùi về trạng thái cũ hơn; sau một lần khởi động khác của Python thì nó đọc lại mọi sổ. Luồng số trực tiếp bên dưới gửi các con số này tới các bảng.
- **Bảng người**: mỗi máy → (mã dòng của người của nó, phạm vi dòng đó thuộc về: mã chi nhánh, hoặc `""` nếu chưa có). Python dựng nó từ thứ bảng đang hiện, nhiều nhất mỗi `RECEIVER_PEOPLE_SECONDS` một lần, khi bộ nhận hỏi; mỗi thay đổi có số thứ tự riêng. Bảng không chứa tên, email hay địa chỉ nào.
- **`/data?scope=`** (mọi vai đã đăng nhập, có hay không có `RECEIVER`): `scope=org` là cả tổ chức, kèm `branchTotals` (cho từng chi nhánh và `""`: số người, đang trực tuyến, đang làm, đang chờ, phiên mở, chi phí hôm nay, token; người đang chờ ở một phiên trong khi phiên khác chạy được đếm ở cả đang làm lẫn đang chờ) và người của nó chỉ khi có 500 người trở xuống; `scope=branch:<mã>` là một chi nhánh (`branch:` trống: người chưa thuộc chi nhánh nào), mỗi trang 500 người theo thứ tự tên, `&page=<n>` đếm từ 0, kèm `page`, `pages`, `peopleTotal` và `pageNames` (tên đầu và tên cuối của mỗi trang). Cả hai được cắt từ cùng khung nhìn của cùng vai với `/data` thường, vốn giữ nguyên: không có `RECEIVER` thì với bao nhiêu người cũng vậy, nó giống từng byte như trước.

### Luồng số trực tiếp

Bảng nhận số từ bộ nhận ngay khi chúng đổi, thay vì mỗi giây hỏi máy chủ Python một lần. Python vẫn quyết ai được thấy gì: tên, email và địa chỉ vẫn chỉ đến từ `/data`, còn luồng chỉ mang số và mã của từng dòng.

1. **Vé.** Trang bảng hỏi máy chủ Python `POST /sse/ticket` với `{"scope": "org"}` hoặc `{"scope": "branch:<mã>"}` (mọi phạm vi `/data?scope=` nhận; vai nào được đọc `/data` thì được đọc mọi phạm vi). Chỉ cho phiên đã đăng nhập, chỉ từ chính trang của bảng (phải có `Origin` và đúng của bảng), chỉ khi có `RECEIVER=1` cùng cả `RECEIVER_LIVE_URL` lẫn `RECEIVER_BOARD_ORIGIN`; nếu không là 404. Câu trả lời là `{"ticket", "scope", "expiresAt", "live", "snap"}`. Một vé là `awt1.<kid>.<vai>.<phạm vi dạng base64url>.<sid>.<hết hạn tính bằng giây>.<chữ ký>`, HMAC-SHA256 bằng bí mật của vé trong file bí mật. Vé sống 5 phút. `sid` được làm từ phiên bằng bí mật đó: nó không cho lại phiên hay tên.
2. **Luồng.** Trang mở `GET <RECEIVER_LIVE_URL>/live?t=<vé>&scope=<phạm vi>` bằng `EventSource`, hoặc `GET …/live/snap?…` để lấy cùng các con số một lần dạng JSON. Bộ nhận kiểm chữ ký, hạn, phạm vi xin đúng là của vé, `Origin` là `RECEIVER_BOARD_ORIGIN` (chỉ nguồn đó được câu trả lời cho đọc), và phiên còn mở; nếu không là 401 hoặc 403, hoặc 503 khi chưa có chính sách từ Python.
3. **Các sự kiện.** `hello` (`scope`, `role`, `expiresAt`, `beatMs`, `tickMs`), rồi `snap` với cả phạm vi, rồi nhiều nhất mỗi giây một `d` với các dòng đã đổi, mỗi dòng mang đủ giá trị, và `gone`, mã các dòng đã rời đi. Một chi nhánh mang dòng của người trong đó (`rows`, các trường của số trực tiếp bên trên); cả tổ chức chỉ mang tổng của từng chi nhánh (`branches`, các trường của `branchTotals`). Luồng lặng thì cứ 15 giây nhận một dòng chú thích để proxy giữ nó mở. Khi vé hết hạn, bộ nhận gửi `bye` (`{"why": "expired"}`) rồi đóng: trang xin vé mới, mở lại, và nhận lại cả phạm vi.
4. **Đăng xuất.** Bộ nhận hỏi chính sách mỗi 15 giây; chính sách nêu trong `endedSessions` các phiên đã được cấp vé còn sống mà nay không còn mở (đã đăng xuất, hết hạn, tài khoản hay màn hình TV bị bỏ, đổi vai). Bộ nhận kết thúc luồng của chúng bằng `bye` (`{"why": "ended"}`) ở nhịp kế tiếp, nên luồng bị cắt trong khoảng 20 giây sau khi đăng xuất. `boardOrigins` trong chính sách là nguồn của bảng.
5. **Dựng một lần, mọi bảng cùng đọc.** Mỗi giây bộ nhận cộng mọi máy một lần, và dựng mỗi phạm vi đang có bảng đọc (hoặc được hỏi ở `/live/snap` trong 30 giây gần nhất) một lần cho mọi bảng của phạm vi đó: JSON của mỗi dòng làm một lần, và mỗi bảng chỉ giữ số của lần đổi cuối nó đã gửi. Nhờ vậy bảng đọc chậm không giữ hàng chờ nào: khi nhận được, nó nhận những gì đã đổi từ đó; một lần ghi được chờ 10 giây, quá thì luồng bị cắt. Bảng chậm hơn cả các dòng đã rời đi hai phút trước thì nhận lại cả phạm vi. Nhiều nhất 5.000 luồng mở cùng lúc (quá thì 503).
6. **Hạn thời gian.** Một lần gửi có 30 giây để được đọc và trả lời (`ReadTimeout`, `WriteTimeout`); luồng tự đặt hạn riêng thay cho chúng, nên không bị cắt ở giây thứ 30.
7. **Trang bảng** (`server/static/page.js`, vẽ bằng `ops.js`). Lúc mở, trang xin vé cho phạm vi của nó: nhận 404 (không có `RECEIVER`, hoặc thiếu `RECEIVER_LIVE_URL` và `RECEIVER_BOARD_ORIGIN`: công ty nhỏ) thì trang hỏi `/data` thường mỗi giây như xưa nay. Nếu không, trang đọc từng phạm vi một, chọn ở ô chọn trên đầu danh sách (**Cả tổ chức**, từng chi nhánh, **Chưa thuộc chi nhánh**, và trang của chi nhánh quá 500 người, đưa ra bằng tên đầu và tên cuối của trang) và giữ trong địa chỉ (`?scope=branch:<mã>&page=<n>`), để tải lại hay màn hình TV vẫn ở đó. Cả tổ chức hiện tổng của từng chi nhánh: mỗi chi nhánh một thẻ thay cho sơ đồ, một dòng trong danh sách, số đếm và chi phí của cả tổ chức cộng từ đó; bấm thẻ hay dòng thì mở chi nhánh đó. Một chi nhánh hiện người của nó như bảng xưa nay. Trang hỏi `/data?scope=` mỗi 20 giây để lấy tên và phần còn lại của bảng (biểu đồ 24 giờ, sự kiện, mô hình), mở luồng bằng vé, và đặt số của mỗi `d` đè lên người có cùng `row` (hay chi nhánh có cùng `id`); dòng của luồng không có trên trang thì bỏ qua, dòng trong `gone` mất số của nó cho tới khi `/data` kế tiếp cho biết người đó còn ở đó không. Nhận `bye` thì xin vé mới rồi mở lại; gặp lỗi thì chờ 1 giây, rồi mỗi lần lâu gấp đôi, tối đa 30 giây. Khi cả tổ chức còn liệt kê người (500 người trở xuống), trang vẫn hỏi `/data?scope=org` mỗi giây và không mở luồng, vì luồng của cả tổ chức chỉ mang tổng của các chi nhánh.

Khi có `RECEIVER_LIVE_URL`, các trang của bảng cho phép địa chỉ đó trong `connect-src` của `Content-Security-Policy`; không có thì như cũ. Luồng đi thẳng tới bộ nhận, không qua Caddy. Vé được giữ cùng một dạng nhờ bộ mẫu chung (`tests/contract/ticket/cases.json`, máy chủ làm, `receiver/internal/feed` kiểm), và bộ nhận còn kiểm các vé do chính mã của máy chủ cấp (`keys_judge.py`).

## 4. Cấu hình

Ở máy chủ Python (`/etc/ai-worker.env`):

| Thiết lập | Việc |
|---|---|
| `RECEIVER` | `1` mở các đường bên trên và ghi file bí mật. Để trống: tắt |
| `RECEIVER_SECRETS_FILE` | Nơi đặt file; để trống là `receiver-secrets.json` trong `KEYS_DIR` |
| `RECEIVER_CHECK_PERCENT` | Phần trăm số lần gửi bộ nhận cũng chuyển nguyên văn, cho lớp đối chiếu thứ ba (mặc định 1) |
| `RECEIVER_PEOPLE_SECONDS` | Bảng người được dựng lại nhiều nhất bao lâu một lần, tính bằng giây (mặc định 5; bộ nhận hỏi mỗi 15 giây) |
| `RECEIVER_LIVE_URL` | Địa chỉ của bộ nhận như các bảng tới được, ví dụ `https://ingest.example.com`: nó nằm trong câu trả lời cấp vé và trong `connect-src` của các trang. Để trống: không có luồng trực tiếp |
| `RECEIVER_BOARD_ORIGIN` | Địa chỉ của chính bảng, ví dụ `https://board.example.com`: trang duy nhất bộ nhận cho mở luồng. Để trống: không có luồng trực tiếp |

Ở bộ nhận (biến môi trường của nó):

| Thiết lập | Việc |
|---|---|
| `RECEIVER_LISTEN` | `IP:cổng` để nghe. Bắt buộc, và phải nói rõ IP: bộ nhận không bao giờ mặc định nghe mọi địa chỉ |
| `RECEIVER_TLS_CERT`, `RECEIVER_TLS_KEY` | Chứng chỉ (cả chuỗi) và khoá bí mật của nó, dạng file. Đọc lại khi chúng đổi, nên gia hạn không cần khởi động lại |
| `RECEIVER_SECRETS_FILE` | File bí mật bên trên. Bắt buộc |
| `RECEIVER_WEBHOOK` | Máy chủ Python trên máy này; chỉ nhận `http://127.0.0.1:…`, `http://[::1]:…` hoặc `http://localhost:…` |
| `RECEIVER_BATCH_MS` | Bao lâu các dòng được gửi cho Python một lần: 1000 (mặc định) cho tổ chức nhỏ, 5000 tới 10000 cho tổ chức lớn |

Bộ nhận chỉ nói HTTP/1.1 (HTTP/2 tốn hơn ở đây), chờ phần header của một yêu cầu nhiều nhất 10 giây, đọc thân nhiều nhất 256 KB, và giữ kết nối rảnh 5 phút, lâu hơn một chút so với 4 phút giữa hai lần gửi của máy đang rảnh.

## 5. Dựng lên

Nơi nghe đã được quyết cùng bản thiết kế: **một IP công khai thứ hai trên cùng máy chủ, cổng 443 của IP đó**. Bộ nhận và Python ở cùng một máy, nên file bí mật và các đường nội bộ vẫn chỉ ở trong máy; cổng 443 đi qua được proxy công ty; sau này chuyển bộ nhận sang máy riêng chỉ cần đổi DNS.

1. Ở nhà cung cấp máy chủ, gắn thêm một IP công khai thứ hai cho máy chủ.
2. Trong Caddyfile, thêm `default_bind <IP thứ nhất>` để Caddy chỉ dùng IP thứ nhất. Máy chủ tự chuyển HTTP sang HTTPS của Caddy không theo tuỳ chọn đó, nên thêm cả một site `http://` rỗng gắn vào IP thứ nhất (xem caddyserver.com/docs/caddyfile/options).
3. Thêm bản ghi DNS A cho `ingest.<tên miền của bạn>` trỏ về IP thứ hai.
4. Lấy chứng chỉ cho tên đó bằng một công cụ ngoài, xác minh qua DNS (cổng 80 của IP thứ hai không có ai nghe).
5. Mở cổng 443 của IP thứ hai trên tường lửa.
6. Dựng bộ nhận (`cd receiver && go build -o /opt/ai-worker/ai-worker-receiver .`), đặt `RECEIVER=1`, `RECEIVER_LIVE_URL=https://ingest.<tên miền của bạn>` và `RECEIVER_BOARD_ORIGIN=https://<tên miền của bảng>` trong `/etc/ai-worker.env` rồi khởi động lại webhook, sau đó chạy bộ nhận bằng systemd với tài khoản `ai-worker` và `AmbientCapabilities=CAP_NET_BIND_SERVICE`, không bao giờ bằng root.
7. Khi mọi máy đã có khoá riêng, đặt `SHARED_KEY_MODE` thành `known-only` hoặc `off`.

Chưa biết: nhà cung cấp của bạn có cho gắn IP thứ hai không, và giá bao nhiêu (không được thì dùng cổng 8443, rồi đo bao nhiêu máy bị chặn); bộ nhận và Python chung 4 vCPU có đủ không (lần đo sau sẽ cho biết).

## 6. Xoay bí mật ký

```bash
sudo systemctl stop ai-worker-webhook
```

```bash
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys RECEIVER=1 python3 /opt/ai-worker/webhook.py --rotate-device-secret
```

```bash
sudo systemctl start ai-worker-webhook
```

Từ lúc đó một bí mật mới ký mọi khoá, và mọi máy nhận khoá mới ở lần gửi kế tiếp; bí mật cũ vẫn kiểm được khoá cho tới khi qua 90 ngày. Nếu file bí mật bị lộ, thêm `--drop-old`: các khoá cũ thôi có hiệu lực ngay và mọi máy ghi danh lại bằng khoá chung, nên trong lúc đó `SHARED_KEY_MODE` không được là `off`. Bộ nhận tự đọc file mới.

## 7. Giới hạn đã biết của đợt này

- Bộ nhận chưa kiểm danh sách máy được gửi từ mọi mạng (`OFFICE_NETS`, [INSTALL.vi.md](INSTALL.vi.md#gửi-từ-ngoài-văn-phòng-máy-được-chọn)): các lô nó ghi qua `/internal/rows` không đi qua bước kiểm của webhook. Giữ địa chỉ của bộ nhận chỉ tới được từ các mạng văn phòng.
- 100.000 máy có ở dưới 5 giây không thì chưa đo: bài đo trên Linux làm ở cuối đợt này.
- Bảng người được dựng từ cả bảng mỗi lần bộ nhận hỏi: chi phí của việc đó ở 100.000 máy được đo cùng phần còn lại trên Linux.
- Luồng số trực tiếp cộng mọi máy mỗi giây một lần, thay vì giữ tổng luôn mới theo từng lần gửi tới. Đo trên Mac chip M ở 100.000 máy, 500 người một chi nhánh: một lượt cộng 83 ms; một giây mà mọi chi nhánh lẫn cả tổ chức đều có bảng đọc mất tổng cộng 175 ms, một nửa là làm JSON của các dòng. Bài đo trên Linux (4 vCPU) quyết có phải giữ tổng theo từng lần gửi hay không.
- Ở trang cả tổ chức không kèm người, biểu đồ 24 giờ, mô hình và hạn mức để trống: chúng được đếm theo người, nên hiện ở trang của từng chi nhánh.
- Số tiền trên một tỷ đô la trong một giờ, chỉ gửi dạng `usd`, bị Python giữ lệch tới từng xu khi làm sạch lại dòng; lớp đối chiếu thứ ba báo điều đó.
- Bộ nhận chỉ giữ của mỗi máy thời điểm lần gửi cuối và các giờ của hôm nay, mỗi giờ ba con số: đo ở 100.000 máy, mỗi máy đủ 24 giờ, Go giữ 261 MB (khoảng 2,6 KB một máy; 739 MB xin từ hệ thống). Cả sổ là của Python.
