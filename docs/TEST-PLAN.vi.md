Tiếng Việt | [English](TEST-PLAN.md)

# Kế hoạch kiểm thử

Phần nào được kiểm tự động mỗi lần đẩy code, phần nào vẫn cần người kiểm, và danh sách kiểm trước khi phát hành.

## 1. Kiểm thử tự động

GitHub Actions chạy `.github/workflows/test-install.yml` ở mỗi lần đẩy code lên repo công khai, nơi số phút miễn phí: mọi việc dưới đây đều chạy. Ở repo riêng tư, như bản phát triển, một lần đẩy không chạy gì, vì số phút ở đó tính vào tài khoản: các bài test chạy trên máy người phát triển (mục 2), và workflow được bấm chạy tay (`gh workflow run test-install.yml`) thì chạy mọi việc, kể cả ba việc trên Windows. Chỉ phát hành khi mọi việc đều xanh.

| Việc | Máy | Kiểm gì | File |
|---|---|---|---|
| `code-check` | Ubuntu | Soát lỗi code Python (ruff); test các hook qua Claude Code CLI; mọi module test của máy chủ (`python3 -m unittest`, có Node 22 cho bài gửi như plugin gửi); bộ nhận Go (`go vet`, `go test`, có máy chủ Python làm trọng tài); bộ nối cho Codex, Cursor và Gemini CLI; bộ đo cho dự án hay ứng dụng AI; logic tiện ích Chrome với máy chủ thật chạy trong máy; chỗ các bản đồ đặt nhãn văn phòng | `ruff.toml`, `tests/*.test.ts(x)`, `server/test_webhook.py` và tám module nữa của `server/`, `receiver/`, `tests/connectors/test_connectors.py`, `tests/appmeter/test_appmeter.py`, `tests/extension/check-extension.js`, `tests/check-map-layout.js` |
| `build` | Ubuntu | Đóng gói; kiểm dữ liệu riêng; phần đầu YAML của skill; quy tắc hai ngôn ngữ; shader bản đồ và tên chuyến bay | `packaging/build.sh`, `tests/test-check-clean.sh`, `tests/check-frontmatter.py`, `tests/check-i18n.py`, `tests/check-maps.py` |
| `ubuntu` | Ubuntu | File cài trên máy sạch, từng tình huống; cài máy chủ với systemd; dựng bộ nhận Go cho máy chủ, rồi bộ cài của nó; script thanh menu; gói `.deb` được apt cài và gỡ; ảnh huy hiệu thông báo | `tests/linux/test-install.sh`, `tests/linux/test-server.sh`, `packaging/build-receiver.sh`, `tests/linux/test-receiver.sh`, `tests/menubar/test-menubar.sh`, `tests/menubar/test-deb.sh` |
| `windows` | Windows | File cài trên máy sạch, từng tình huống; các script đóng rồi mở lại app Claude sau `/update`, trong Windows PowerShell 5; hook và bộ cài PowerShell của bộ nối; biểu tượng cạnh đồng hồ; ảnh huy hiệu thông báo | `tests/windows/test-install.ps1`, `tests/windows/dump-restart-scripts.mjs`, `tests/windows/test-restart.ps1`, `tests/connectors/test_connectors.py`, `tests/menubar/test-menubar.ps1` |
| `windows-app` | Windows | Dựng `AI Worker.exe` và `.msi`; cài cho một người dùng, không cần quyền quản trị máy; ghép; đếm người đang chờ; gỡ | `tests/menubar/test-windows-app.ps1` |
| `plugin-msi` | Windows | Dựng `AI Worker plugin.msi`; máy chủ điền một bản công ty; cài, cửa sổ cài, plugin đã cập nhật bằng `/update`, nâng cấp, hạ cấp bị từ chối, gỡ, và một bản cá nhân để nguyên không điền | `packaging/windows-msi/`, `tests/windows/test-msi.ps1` |

### Phạm vi các test

| Phần | Test kiểm |
|---|---|
| Quyền của mọi đường dẫn máy chủ | `test_webhook.py` giữ toàn bộ bảng đường dẫn, báo lỗi nếu thêm đường mới mà chưa khai quyền |
| Đăng nhập, OTP, khoá sau khi nhập sai, nhập lại OTP cho thao tác tài khoản | `test_webhook.py` |
| Đăng nhập Telegram: chữ ký, hết hạn, dùng lại, chỉ liên kết được khi có mã và bước dùng một lần, mỗi tài khoản một Telegram, đường sang Telegram và quay về | `test_webhook.py`, lớp `TelegramLogin` |
| Hỏi bảng qua Telegram: một tin nhắn ứng với lệnh nào, câu trả lời bằng hai ngôn ngữ và cho cả hai phạm vi, không trường riêng tư nào trong câu trả lời | `test_ask.py` |
| Hỏi bảng qua Telegram: ai được gọi đường của bot, ghép một chat, giới hạn, nhật ký, số của chat không mở được gì khác, tiến trình bot chạy với một Telegram giả và webhook thật | `test_webhook.py`, lớp `TelegramAsk` |
| Tiến trình bot Telegram: đọc, gửi, trục trặc với Telegram hoặc webhook, không có gì bí mật trong nhật ký của nó | `test_telegram_bot.py` |
| Khung bên trong Telegram: chữ ký của Telegram (sai, cũ, của bot khác, thiếu người dùng), phiên và giới hạn của nó, chỉ chat được cho phép, chat chỉ đọc số gộp nhận số tổng và không có người nào, thu hồi hay `/stop` kết thúc phiên ngay, phiên không mở được gì khác, trang và các file kèm `?v=`, nút menu bot được báo đặt, nhật ký; và tiến trình bot đặt nút | `test_webhook.py`, lớp `TelegramApp`; `test_telegram_bot.py`, lớp `MenuButtons` |
| Tin báo tới chat Telegram: mỗi lần chờ một lần, khoảng cách giữa hai tin, trần mỗi giờ, giờ im lặng, phiên bỏ mở, chỉ nêu tên với chat đọc từng người, dòng đầu không nêu tên ai, ngôn ngữ và số phút của chat; `/alerts` và cài đặt trong khung; nhật ký; bot gửi tin có bảo vệ kèm nút mở khung | `test_webhook.py`, lớp `AlertRules` và `TelegramAlerts`; `test_telegram_bot.py`, lớp `MenuButtons` |
| Dịch vụ của bot sau khi cài: mặc định tắt, người dùng và file cấu hình riêng, giới hạn mạng, gỡ bỏ | `tests/linux/test-server.sh`, phần S5 |
| Bộ cài của bộ nhận Go (`server/install-receiver.sh`) trên máy có systemd: dừng khi thiếu IP hoặc chương trình khác giữ cổng, cài lần đầu (người dùng riêng, một quyền, trần bộ nhớ, cấu hình riêng tư, không chuyển máy nào), chạy lại không đổi gì, cập nhật qua `install.sh`, từ chối file chạy không khớp `SHA256SUMS`, quay lui, gỡ, thay dịch vụ viết tay có hoặc không có file cấu hình trùng tên, lần chạy đầu có hỏi (các đáp án đoán được đưa ra, `n` dừng mà chưa đổi gì, Enter nhận từng cái, đáp án gõ vào thắng) | `tests/linux/test-receiver.sh` |
| Mỗi vai nhận dữ liệu gì (màn hình treo tường không có email, IP) | `test_webhook.py` |
| Bộ nhận tuỳ chọn bằng Go: bộ mẫu chung ở cả hai định dạng, các lần gửi ngẫu nhiên được làm sạch giống hệt Python (khoá đúng thứ tự, số nguyên tách khỏi số thực), bước kiểm khoá so với khoá máy chủ cấp, lần gửi qua bộ nhận kết thúc với đúng sổ trên máy chủ Python thật kèm tên nó biết và địa chỉ thật, lô gửi hai lần chỉ ghi một lần, TLS chỉ HTTP/1.1 và chứng chỉ gia hạn được đọc lại; phía máy chủ, các đường nội bộ (404 trừ khi `RECEIVER=1`, từ chính máy này và có mã nội bộ), file bí mật, tài liệu chính sách, sổ theo trang, lớp đối chiếu thứ ba và việc xoay bí mật ký ; bộ mẫu chung chạy qua bộ nhận vào máy chủ Python thật, mỗi lần gửi một lô riêng và mọi lần gửi gộp thành mỗi máy một dòng, Python kết thúc với đúng sổ và các ngày bộ mẫu chờ; các dòng của một máy gộp lại như Python ghi từng lần một; Python vắng một phút trong khi mọi máy vẫn gửi, mọi lần gửi được trả lời 200 và mỗi máy chờ nhiều nhất một dòng; các giờ giữ dạng số cộng ra như nhau; dòng đối chiếu chỉ được so, không bao giờ được ghi, và các giờ hôm nay bộ nhận nạp | `receiver/` (`go test ./...`), `server/test_receiver.py` |
| Ghép TV, thanh menu, tiện ích; thu hồi; hết hạn | `test_webhook.py`, `check-extension.js`, các test thanh menu |
| Một máy không gửi thay người khác được; giới hạn gửi | `test_webhook.py` |
| Nhãn và ghim văn phòng trên bản đồ: ghim chạm nhau được vẽ cạnh nhau; khi nhiều văn phòng thì nhãn không còn chỗ trống bị ẩn; không nhãn nào đè nhãn khác, đè ghim của văn phòng khác hay đè danh sách văn phòng, không nhãn nào ra khỏi khung | `tests/check-map-layout.js` |
| Plugin Claude của quản lý và bảng: ghép bằng mã, chỉ đọc phần treo tường, thu hồi, bỏ ghép, mạng bị từ chối, quyền bị chặn | `test_webhook.py` (lớp `ExtensionPairing`), `tests/board.test.ts` |
| Chữ gửi cho ChatGPT hay Gemini: vẫn hỏi ở chế độ quyền không hỏi gì, ở lại trên máy khi bị từ chối, chỉ gửi không hỏi khi có quy tắc cho phép | `tests/sending.test.ts`, `tests/workers.test.ts` |
| Ghi chú bàn giao được báo cho phiên mới: chỉ file mà skill sẽ viết, năm ghi chú mới nhất theo tên và ngày, không thêm gì trên máy không có ghi chú, plugin không mở ghi chú nào | `tests/handoff.test.ts` |
| Câu hỏi trước lệnh phá huỷ công việc: lệnh nào bị bắt và lệnh nào được bỏ qua, lệnh đã được cho phép bị đổi thành câu hỏi cho một người, lệnh đã bị cấm vẫn bị cấm, công tắc trong `config.js` | `tests/guard.test.ts` |
| Những gì rời máy hay vào máy: bí mật trong chữ gửi ChatGPT hay Gemini (cả qua server ai-workers riêng), bí mật trên các dòng commit thêm vào, trang nói với AI, thiết lập AI của chính repo, lời nhắc 80% context cho Claude, số lần chặn trong báo cáo của máy | `tests/secrets.test.ts`, `commitscan.test.ts`, `injection.test.ts`, `repoconfig.test.ts`, `nudges.test.ts`, `sending.test.ts`, `team.test.ts` |
| Phần máy chủ của các lớp bảo vệ: chuỗi dấu vân tay của nhật ký (sửa một dòng, xoá một dòng, xoá các dòng mới nhất), số lần chặn được làm sạch và cộng cho quản trị và người xem, khoá cho công cụ AI không dùng 30 ngày | `test_webhook.py`, lớp `AuditChain`, `BlockCounts`, `UnusedKeys` |
| Niêm phong các ngày tổng chi phí vào chuỗi nhật ký: mỗi ngày đã chốt một lần, cả ngày trống, dòng chưa ghi được thì thử lại, ngày đã niêm phong bị đổi số tiền, token hay dòng thì bước kiểm nêu tên, ngày đã bỏ vì quá cũ thì không xét, `--forget-usage` niêm phong lại mà không ghi là ai; tin buổi sáng chỉ tới chat Telegram của quản trị, mỗi ngày một lần, không gửi ban đêm, không tên không tiền | `test_daily_seal.py`, lớp `Sealing`, `MorningMessage` |
| `/ai-worker:voice`: đúng trang cài đặt và đúng các bước cho Mac, Windows và Linux; có bước làm tay khi trang không mở được; không chạy gì khác | `tests/voice.test.ts` |
| Bản thử với dữ liệu giả lập: bật được, vào được bằng mã nó in ra, bỏ qua cấu hình của bảng thật, xoá dữ liệu khi dừng | `test_demo.py` |
| Chi phí theo giờ, không tính trùng khi mở lại phiên | `tests/cost.test.ts` |
| Bộ đo cho dự án hay ứng dụng AI và báo cáo: đọc token của Anthropic, OpenAI, Gemini, API chép theo OpenAI (DeepSeek), Bedrock, Ollama, Cohere, ghi tay cho hãng khác, kiểm tên hãng, mỗi token chỉ đếm một lần; thiếu usage ghi null chứ không ghi 0; streaming, gọi lại, lỗi; không có chữ của người dùng; trường lạ bị bỏ; p95 nearest-rank; model chưa có giá; model chạy trên máy của nhóm; file giá riêng của người dùng; giá theo ngày; bộ đo Node cho ra cùng số | `tests/appmeter/test_appmeter.py` |
| Dự án hay ứng dụng AI trên bảng: chỉ khoá dự án còn hạn mới gửi được, không bao giờ từ trình duyệt, và nó không mở được gì khác; khoá bị thu hồi dừng ngay và số liệu vẫn giữ; các đường biến mất khi tắt `AI_PROJECTS`; bỏ trường lạ và lượt sai, không lưu gì riêng tư; từ chối lần gửi sai và quá lớn; lượt gửi hai lần chỉ giữ một lần; giới hạn theo khoá và theo ngày; token không đo được vẫn là chưa biết; ai được xem và tải (quản trị và người xem, không phải treo tường); báo cáo và p95 khớp với skill; tạo khoá cần OTP và chỉ hiện một lần; giá quản trị dán được kiểm; lượt và ngày cũ được dọn; bộ đo Python và Node gửi ở nền và bảng chết không làm dự án mất gì; bản sao báo cáo trên bảng giống bản của skill | `server/test_projects.py` |
| Không có câu hỏi, nội dung chat hay nội dung file bí mật nào rời máy | `tests/activity.test.ts`, `tests/edits.test.ts`, `tests/team.test.ts`, `tests/office.test.tsx` |
| Trợ lý phụ: chọn model Gemma, truyền tham số an toàn cho Codex | `tests/workers.test.ts` |
| Lưu trữ SQLite: chuyển file JSON cũ vào, phiên bản lược đồ, quyền file, nhiều luồng cùng ghi, sao lưu, xuất ngược ra JSON; cơ sở dữ liệu cũ được chép ra trước khi nâng, bản sao mở được và chương trình cũ chạy được trên đó, không chép được thì không nâng | `test_webhook.py` (`DatabaseStorage`), `tests/linux/test-server.sh` |
| Sổ giờ ở các dòng riêng (lược đồ phiên bản 6): một `board.db` lược đồ phiên bản 5 cho cùng bảng, lịch sử, tổng theo ngày và bản xuất sau khi nâng, dòng không đọc được giữ nguyên và bản sao phiên bản 5 được giữ; các lần gửi ngẫu nhiên ở cả hai định dạng để lại đúng sổ mà `merge_hours` và `replace_hours` cho, đúng các ngày trong `device_days` và trong bộ nhớ, cả sau khi khởi động lại và với SQLite cũ hơn 3.24; lần gửi không đổi gì thì không ghi gì; `TZ_OFFSET` mới thì đếm lại các ngày | `server/test_hour_rows.py` |
| Tổng theo từng người từng ngày: cộng giờ thành ngày, đếm lại không cộng trùng, giữ 13 tháng rồi xoá, đọc ra theo tuần và theo tháng; biểu đồ chi phí theo tuần và theo tháng; chỉ quản trị và người xem nhận được | `test_webhook.py` (`DailyTotals`, `UsageByRole`) |
| Thứ trợ lý (ChatGPT, Gemini, Gemma) trả về: lệnh chỉ được đọc từ khối mã shell và dấu nhắc `$`; câu trả lời có khoá, có lời nhắm vào AI hoặc có lệnh không hoàn tác được thì bị đánh dấu và tới Claude nguyên vẹn kèm ghi chú; biên bản của việc đó giữ độ dài, loại và dấu vân tay có muối, không bao giờ giữ câu lệnh, và chỉ gửi lên một lần, trong hai ngày gần nhất | `tests/answers.test.ts` |
| Bước kiểm lời commit (`commitTrail`): lời commit thiếu gì (dạng của dòng đầu, nguyên nhân của một bản sửa, đã đo gì), merge, revert và fixup được để yên, chỉ nhắc Claude khi `config.js` bật và commit đã thành công | `tests/committrail.test.ts` |
| Sổ chi phí trên máy: một lượt cộng vào giờ của nó, sổ được giữ khi không ghi được trang, chi phí gần nhất của từng phiên (nhiều nhất 50), việc sửa sổ chỉ chạy một lần mỗi máy | `tests/ledger.test.ts` |
| Gửi số liệu (`hooks/send.ts`): mã chung trước, rồi khoá riêng của máy và đường tới bộ nhận; bộ nhận đang bận thì chờ, không bao giờ dồn sang webhook; webhook không trả lời thì lùi dần từ 5 giây tới 5 phút; khoá bị từ chối thì bỏ; đường hết hạn thì hỏi lại; giữ khoảng cách máy chủ dặn | `tests/send.test.ts`, `tests/share.test.ts` |
| Định dạng `v: 2` của một lần gửi: `v: 1` cho tới khi máy chủ báo đọc được `v: 2`, rồi chỉ các giờ đã đổi; cả sổ khi được hỏi, khi thiếu dấu và khi tới hạn; hai ngày gần nhất gửi lại sau khi máy chủ khởi động lần khác; mỗi lần gửi được đánh số cao hơn lần trước; dù mất gì trên đường, máy chủ vẫn kết thúc với đúng số tiền máy đang giữ | `tests/sendv2.test.ts`; chính mã của plugin với `/ingest` thật qua HTTP: `server/test_plugin_v2.py` cùng `tests/contract/plugin-v2/bridge.mjs` |
| Tiêu đề phiên: khi nào tới lúc làm tiêu đề mới, câu trả lời thành tiêu đề ra sao, cuộc trò chuyện người dùng đã đổi tên vẫn là của họ | `tests/titles.test.ts` |
| Lõi của cổng MCP của bảng (`board/mcp.py`): bản tóm tắt một khoá được đọc, bản hiện tại và các bản cũ của giao thức, thông điệp hỏng | `server/test_mcp.py` |
| Định dạng `v: 1` và `v: 2` của `/ingest` so với bộ mẫu chung: cùng một hoạt động gửi theo cách nào cũng cho cùng bảng, lịch sử và tổng theo ngày, và đúng sổ mà bộ mẫu mong đợi | `server/test_contract.py` cùng `tests/contract/ingest-v2/cases.json` |
| Giờ nào của một lần gửi được ghi, được để nguyên hay bị xoá (`board/order.py`), so trên nhiều ca ngẫu nhiên với quy tắc như nó được viết trước đây | `server/test_order.py` |
| Một lần gửi sẽ thành gì trước khi ghi bất cứ gì (`decide`), cùng các lựa chọn như của bộ nhận Go; và hai cách một lần gửi được nhận, gửi thẳng trên `/ingest` và thành một dòng của bộ nhận, đặt cạnh nhau sau khi lưu | `server/test_decide.py`, `server/test_two_paths.py` |
| Một lô của bộ nhận được ghi trọn (`DeviceCache.write_batch`): các máy được giữ đúng thứ tự trong cả lô, lần thử nhanh hỏng thì được hoàn lại và ghi lại từng dòng, dòng hỏng được nêu tên riêng; `RECEIVER_FAST_APPLY` bật hay tắt đều để lại cùng các bảng và cùng `/data` cho mọi vai, đúng từng byte | `server/test_batch.py`, `server/test_apply_paths.py` |
| Một lần dựng bảng chỉ nghỉ khi đang có lần ghi, và không bao giờ lâu hơn giới hạn của nó (`board/turns.py`); chi nhánh của một người tìm qua chỉ mục cho cùng kết quả như duyệt mọi chi nhánh | `server/test_turns.py`, `server/test_branch_of.py` |
| Khoá OTP được niêm phong bằng khoá để tách khỏi chúng: niêm phong và mở niêm phong, tài khoản được lưu ở dạng đã niêm phong, cơ sở dữ liệu tài khoản | `server/test_sealing.py` |
| Chọn ngôn ngữ và ngôn ngữ dự phòng | `tests/lang.test.ts` |
| Gói cài không có từ riêng, địa chỉ hay khoá | `tests/test-check-clean.sh` với `packaging/check-clean.sh` |

## 2. Chạy trên máy mình

Chạy đủ mười hai bước trước khi coi một thay đổi là xong. Mỗi lệnh chạy ở thư mục gốc repo. GitHub Actions chạy cùng các bước này, gồm mọi module test của máy chủ (`python3 -m unittest` tìm chúng theo tên, nên module mới không cần thêm vào danh sách nào).

```bash
claude plugin test .
```

Kết quả đúng: mọi test đạt. Chưa cài Claude Code: `npx -y @anthropic-ai/claude-code plugin test .`

```bash
cd server && python3 -m unittest
```

Kết quả đúng: `OK`. Sau đó quay về thư mục gốc repo.

```bash
python3 tests/connectors/test_connectors.py
```

```bash
python3 tests/appmeter/test_appmeter.py
```

```bash
node tests/extension/check-extension.js
```

```bash
node tests/check-map-layout.js
```

```bash
python3 tests/check-i18n.py
```

```bash
python3 tests/check-maps.py
```

```bash
python3 tests/check-frontmatter.py
```

```bash
bash tests/test-check-clean.sh
```

```bash
uvx ruff check .
```

Kết quả đúng của cả chín lệnh này: thoát với mã 0. Không có `uv` thì lệnh cuối là `pipx run ruff check .`.

```bash
cd receiver && go test ./...
```

Kết quả đúng: `ok` ở mọi gói. Cần Go 1.22 trở lên và `python3`: bài test của bộ nhận chạy chính mã của máy chủ làm trọng tài. Xong thì quay về thư mục gốc repo.

### Đo chịu tải

Không nằm trong mười hai bước: chạy mất khoảng 20 phút và số đo tuỳ máy. Chạy trước khi phát hành bản có đổi cách máy chủ nhận số hay dựng bảng, rồi so với [BENCHMARK.vi.md](BENCHMARK.vi.md).

```bash
python3 tests/load/load_test.py --json load.json
```

```bash
python3 tests/load/load_test.py --scale 300,1000,3000,5000,10000
```

Kết quả đúng: lệnh đầu in ra một bảng và thoát với mã 0, nghĩa là không lượt office nào có lỗi; lệnh sau cho thấy một lần gửi mất gần như cùng thời gian ở mọi cỡ. `--quick` kiểm trong khoảng 15 giây rằng chính bài đo vẫn chạy. Nó chỉ nói chuyện với máy chủ nó tự bật trên 127.0.0.1.

`bash packaging/check-clean.sh` không nằm trong danh sách này: nó tìm dữ liệu riêng trong thư mục đang chạy, nên dùng cho phần sẽ được công bố, ở đó kết quả đúng là `Clean.` Ở bản checkout có file `packaging/company.json` của riêng bạn, nó sẽ báo file đó, và như vậy là đúng.

## 3. Phần vẫn cần người kiểm

Test tự động dùng máy chủ giả và trình duyệt giả. Trước khi phát hành bản có đụng tới các phần này, kiểm tay:

| Phần | Máy | Kiểm | Kết quả đúng |
|---|---|---|---|
| Cài plugin | Một máy Mac thật và một máy Windows thật | Chạy file cài, mở Claude Code, gõ `/office` | Trang văn phòng mở; máy hiện trên bảng tổng trong vòng 5 phút |
| Nói thay vì gõ | Một máy Mac thật và một máy Windows thật có micro | Gõ `/ai-worker:voice`, làm theo các bước, rồi đọc một câu tiếng Việt trong ô soạn tin | Trang cài đặt mở ra; câu đó hiện bằng tiếng Việt có dấu |
| Cập nhật | Máy đang ở bản trước | Chờ hoặc ép kiểm bản mới, bấm **Cập nhật**, mở lại app | Số phiên bản mới hiện trong `/office` |
| Đăng nhập OTP | Điện thoại thật có Google hoặc Microsoft Authenticator | Quét mã QR trên `/admin`, đăng nhập | Vào được; nhập sai 5 lần thì bị khoá 15 phút |
| Đăng nhập Telegram | Tài khoản Telegram thật và bot của máy chủ | Ở `/telegram` nhập mã rồi bấm nút, đăng xuất, bấm **Log in with Telegram** ở trang đăng nhập | Vào thẳng bảng điều khiển, không gõ tên hay mã |
| Hỏi bảng qua Telegram | Tài khoản Telegram thật và một bot tạo riêng cho việc này bằng @BotFather | Bấm **Start** trong bot, duyệt mã ở `/admin` cho đọc từng người, bấm các nút, gõ một câu hỏi, thử chuyển tiếp một câu trả lời, gửi `/stop` | Câu trả lời có tên người, theo ngôn ngữ của tin nhắn; Telegram không cho chuyển tiếp; sau `/stop` bot báo chat chưa nối với bảng |
| Khung bên trong Telegram | Việc hỏi qua Telegram đang chạy, đã đặt `TELEGRAM_APP=1` và `TELEGRAM_APP_URL`, một chat được đọc từng người | Ở `/admin` bấm **Cho mở khung**; trong Telegram bấm **AI Worker** trên điện thoại và trên Telegram Desktop, ở mạng văn phòng; đổi ngôn ngữ; rồi bấm **Thôi mở khung** | Nút hiện trong vòng một phút; khung hiện đúng các con số của khung thanh menu; sau Thôi mở khung, khung báo đóng rồi mở lại. Đã làm ngày 2026-11-18 trên Telegram Desktop (macOS) và Android; chưa làm trên iPhone |
| Khung cho chat chỉ đọc số gộp | Như trên, một chat được duyệt chỉ đọc số gộp | Ở `/admin` bấm **Cho mở khung** ở chat đó; bấm **AI Worker** | Hộp xác nhận nói khung không nêu tên ai; mỗi thẻ chỉ một dòng số tổng và câu "Chat này chỉ đọc số gộp, nên không nêu tên ai."; không có tên ai ở đâu cả |
| Commit có khoá giả | Một repo thử, một dòng `.env` có `DB_PASSWORD` bịa đã stage | Nhờ Claude commit | Hộp xin phép hỏi trước, nêu file và dòng, không bao giờ nêu giá trị |
| Gửi ChatGPT có khoá giả | Đã cài ChatGPT | Nhờ Claude gửi `review: DB_PASSWORD=<giá trị bịa>` sang ChatGPT | Bị từ chối kèm "Nothing left this computer"; mục **ai-worker đã chặn** ở trang Quản trị tăng một trong vài phút |
| Trang nói với AI | Một trang trên máy có dòng "ignore your previous instructions" | Nhờ Claude đọc bằng WebFetch hay trình duyệt | Có thông báo cho bạn; Claude nói trang định làm gì và không làm theo |
| Kiểm nhật ký | Một bản sao `board.db` trên máy chủ thử | Sửa một dòng nhật ký bằng `sqlite3`, mở `/admin` | Mục nhật ký báo một dòng gần lúc đó đã bị sửa hay bị xoá bằng tay |
| Kiểm sổ chi phí | Một bản sao `board.db` trên máy chủ thử, đã chạy hơn một tuần | Sửa `usd` của một dòng `daily` cũ hơn một tuần bằng `sqlite3`, mở `/admin` | Mục nhật ký báo số liệu ngày đó đã bị sửa sau khi niêm phong; bảng **Các ngày đã niêm phong** liệt kê các mã |
| Màn hình TV | TV thật hoặc trình duyệt toàn màn hình | Mở `/tv`, duyệt mã trên `/admin` | Bảng hiện ra, không có email hay IP |
| Thanh menu macOS | Máy Mac thật | Cài `.dmg` hoặc `.zip`, ghép | Biểu tượng hiện số người chờ, có thông báo |
| Thanh menu Ubuntu | Ubuntu chạy X11 **và** Ubuntu chạy Wayland | Cài `.deb`, ghép | Biểu tượng hiện trên thanh trên cùng ở cả hai |
| Tiện ích Chrome | Chrome thật | Nạp tiện ích, ghép, mở khung bật lên | Khung và huy hiệu hiện số người chờ |
| Khổ điện thoại | Điện thoại hoặc cửa sổ 375 px | Mở bảng tổng | Không tràn ngang; bấm được các nút |

## 4. Trước khi phát hành

1. Mọi việc trên GitHub Actions đều xanh, và các việc đã thật sự chạy chứ không bị bỏ qua, kể cả ba việc trên Windows. Một lần đẩy lên repo riêng tư bỏ qua tất cả: ở đó hãy bấm chạy tay workflow, `gh workflow run test-install.yml`.
2. Đã kiểm tay mục 3 cho mọi phần mà bản này thay đổi.
3. Đã tăng `version` trong `.claude-plugin/plugin.json`, và `CHANGELOG.md` đã ghi các thay đổi.
   Nếu giao diện bảng tổng đổi, chụp lại `assets/dashboard.png` và `assets/dashboard.vi.png` từ máy chủ thử với người giả, không bao giờ từ máy chủ thật.
4. `bash packaging/release.sh` chạy thành công, và đã thử kiểm chữ ký trên một máy trước khi phát cho mọi người.
5. Ghi vào hồ sơ triển khai: bản nào, khi nào, ai phát hành ([OPERATIONS.vi.md](OPERATIONS.vi.md), mục 7).

## 5. Chỗ còn thiếu

- `hooks/register.tsx` và `web/ops.js` (chép sang `server/static/ops.js`) chưa có test riêng.
- Chưa có test tự động trên máy Mac thật.
- Chưa có test tự động trên Ubuntu Wayland; đang kiểm tay.
- Bài đo chịu tải mới chạy trên Mac, chưa chạy trên máy chủ Linux như nơi bảng được cài, và mỗi máy giả gửi từ một địa chỉ bịa riêng, nên chưa thấy giới hạn số máy mới mỗi ngày theo địa chỉ mà một văn phòng đi chung một địa chỉ sẽ gặp (bản thân lần gửi thì giới hạn theo từng máy, không theo địa chỉ). Bộ nhận Go đã được đo trên Linux bằng công cụ ngoài repo ([BENCHMARK.vi.md](BENCHMARK.vi.md#trên-linux-có-bộ-nhận-go)).
