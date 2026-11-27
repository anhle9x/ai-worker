Tiếng Việt | [English](INSTALL.md)

# Cài đặt và cấu hình

Dành cho người quản trị triển khai AI Worker: cần chuẩn bị gì, triển khai lần đầu, phát hành bản cập nhật, dữ liệu gửi đi, tuỳ chỉnh và bảo vệ. Cách dùng hằng ngày xem [USER-GUIDE.vi.md](USER-GUIDE.vi.md); vận hành máy chủ xem [OPERATIONS.vi.md](OPERATIONS.vi.md).

## Cần chuẩn bị

Muốn xem bảng trước khi triển khai, chạy `python3 server/demo.py` (trên Windows: `py server\demo.py`) trên máy mình: lệnh này hiện bảng với dữ liệu giả lập và không cần máy chủ (xem [README](../README.vi.md#cài-nhanh)).

- **Máy chủ Linux** có `python3` từ 3.8 và systemd. Webhook không cần thư viện ngoài.
- **Một tên miền con riêng**, ví dụ `bang.cong-ty.vn`, trỏ bản ghi DNS `A` về IP máy chủ.
- **Caddy** (hoặc nginx) trên máy chủ để có HTTPS. Webhook chỉ nghe nội bộ, Caddy nhận kết nối từ ngoài.
- **Danh sách IP được vào:** IP mạng các văn phòng. Máy ngoài danh sách không xem được bảng, không gửi được số liệu và không tải được bản cập nhật.
- **Một máy giữ khoá ký** có `ssh-keygen` để giữ khoá ký bản cập nhật.

Địa chỉ thật, `INGEST_KEY` và khoá không đưa vào git. Trong repo chỉ dùng địa chỉ mẫu như `https://bang.cong-ty.vn`.

## Chọn cách cài theo quy mô

Máy chủ đếm máy, không đếm người: laptop, máy bàn và bộ nối cho Codex là ba máy, nên 300 máy là khoảng 100 tới 150 người.

| Số máy | Cài gì | Đã kiểm tới đâu |
|---|---|---|
| Tới khoảng 300 | Không cần thêm gì: mặc định (`MAX_DEVICES=300`) | Mặc định; đo với 300 máy gửi mỗi 10 giây và 30 bảng mở: một lần gửi p95 5 ms, 10% của một lõi ([BENCHMARK.vi.md](BENCHMARK.vi.md)) |
| Vài trăm tới vài nghìn | Nâng `MAX_DEVICES` trong `/etc/ai-worker.env`, rồi chạy lại `install.sh`. Python một mình vẫn đủ. Trần bộ nhớ của nó mặc định là 1 GB, và nó giữ khoảng 20 tới 35 KB mỗi máy trong bộ nhớ (2 tới 3,5 GB ở 100.000 máy), nên quá khoảng 20.000 máy thì nâng cả `WEBHOOK_MEMORY_MB` | Mới đo trên máy Mac, một tiến trình: tới 10.000 máy một lần gửi tốn 0,8 ms và dựng bảng 154 ms ([BENCHMARK.vi.md, Vượt 10.000 máy](BENCHMARK.vi.md#vượt-10000-máy)). Python một mình chưa được đo trên máy chủ Linux: chạy `tests/load/load_test.py` trên máy chủ của bạn trước |
| Hàng chục nghìn | Bộ nhận Go tuỳ chọn cạnh webhook: `sudo sh install-receiver.sh` ([RECEIVER.vi.md](RECEIVER.vi.md)) | Đã đo trên máy Linux thuê với máy giả: tới khoảng 40.000 tới 50.000 máy trên 4 vCPU và 8 GB. Chạy thật tới nay: một tổ chức, vài máy, một tuần từ cuối tháng 11/2026. Hãy thử với vài máy của bạn trước ([Thử với vài máy](RECEIVER.vi.md#thử-với-vài-máy)) |

Khi chạm giới hạn, máy mới bị từ chối (`507 device limit reached` trong nhật ký, [OPERATIONS.vi.md](OPERATIONS.vi.md)); các máy đã có trên bảng vẫn gửi bình thường.

## Triển khai lần đầu

1. **Cài webhook.** Chép `server/` lên máy chủ rồi chạy `sudo bash install.sh`. Lần đầu script in `INGEST_KEY` và tạo tài khoản quản trị đầu tiên. Chi tiết ở [`server/README.md`](../server/README.md).
2. **Bật HTTPS.** Thêm khối Caddy cho tên miền với danh sách IP được vào (mẫu: `server/aiworker.caddy`, đổi sang tên miền và IP của bạn), rồi thêm `TRUST_PROXY=1` vào `/etc/ai-worker.env` và chạy lại `install.sh`.
3. **Tạo khoá ký**, trên máy giữ khoá ký:
   ```bash
   mkdir -p ~/.ai-worker-keys && chmod 700 ~/.ai-worker-keys
   ssh-keygen -t ed25519 -C ai-worker-main -f ~/.ai-worker-keys/main
   ssh-keygen -t ed25519 -C ai-worker-backup -f ~/.ai-worker-keys/backup
   ```
   Đưa hai khoá công khai vào `~/.ai-worker-keys/allowed_signers`, mỗi dòng dạng `ai-worker ssh-ed25519 AAAA...`. `build.sh` và `release.sh` chép file đó vào gói; `keys/allowed_signers` trong git chỉ có chú thích, nên repo công khai không bao giờ mang khoá của bạn. Khoá riêng không lên máy chủ, không vào git; cất bản dự phòng ở ngoài máy.
4. **Đóng gói.** Chép `packaging/company.example.json` thành `packaging/company.json` (file này không vào git), điền `webhook` và `ingestKey`, rồi:
   ```bash
   bash packaging/build.sh packaging/company.json
   ```
   Được `dist/AI-Worker-<phiên bản>-company.zip`.
5. **Nhân viên cài.** Giải nén, bấm đúp `INSTALL-Mac.command` hoặc `INSTALL-Windows.bat` (trên Linux chạy `bash INSTALL-Linux.sh`), nhập họ tên. Gói có mã gửi nên chỉ phát trong công ty.
   Trên Windows còn có một file cài duy nhất, `AI-Worker-Plugin.msi`, do máy chủ điền sẵn địa chỉ và mã gửi của nó: xem [Gói cài plugin cho Windows (.msi)](#gói-cài-plugin-cho-windows-msi).
6. **Xem bảng.** Mở bảng trên trình duyệt: `https://<domain của bảng>` sau proxy HTTPS (ví dụ `https://aiworker.example.com`). Webhook chỉ nghe trong máy chủ, nên chưa dựng proxy thì chưa có địa chỉ nào để mở. Đăng nhập bằng mã OTP. Trang `/board` có cột Plugin cho biết máy nào chưa lên bản mới nhất.
7. **Cài thêm bộ nhận Go** (tuỳ chọn; chỉ khi có hàng chục nghìn máy, xem [Chọn cách cài theo quy mô](#chọn-cách-cài-theo-quy-mô)). Một văn phòng bỏ qua bước này.
   - **Chuẩn bị:** một IP thứ hai cho máy chủ, hoặc một cổng khác trên cùng IP như 8443; một bản ghi DNS cho tên miền con của bộ nhận (ví dụ `ingest.example.com`) khi nó có tên riêng; một chứng chỉ TLS cho tên đó đặt dưới `/etc`, tài khoản `ai-worker` đọc được; cổng đã mở ở tường lửa. Trên máy giữ repo chạy `sh packaging/build-receiver.sh`, rồi chép lại `server/` lên máy chủ (không có Go thì lấy ba file ở trang Releases của dự án trên GitHub, đặt vào `server/receiver-bin/`).
   - **Ở đâu:** trên máy chủ, trong thư mục `server/`. **Làm gì:**
     ```bash
     sudo sh install-receiver.sh
     ```
     Nó hỏi năm câu, mỗi câu kèm một đáp án đoán từ máy chủ (Enter là nhận), hiện lại tất cả rồi chờ Enter trước khi đổi bất cứ gì.
   - **Kết quả đúng:** năm dòng có dấu ✔, rồi `✔ Bộ nhận trả lời ở https://<tên miền con của bộ nhận>/health`. Dòng có dấu ✘ cho biết thiếu gì và lệnh để sửa; chưa có gì bị đổi, nên sửa xong chạy lại đúng lệnh đó.
   - **Sau đó:** chưa máy nào gửi tới bộ nhận. Việc chọn máy nào gửi, thử với vài máy trước, quay lui và gỡ bỏ nằm ở [RECEIVER.vi.md](RECEIVER.vi.md#bộ-cài). Từ đó mỗi lần `sudo bash install.sh` cũng cập nhật bộ nhận.

## Lệnh trên máy nhân viên

- `/office`: mở bảng điều khiển các phiên trên máy.
- `/office-pane`: mở bản 2D cạnh khung chat.
- `/update`: kiểm tra và cài bản mới.
- `/ai-worker:board`: số liệu của cả nhóm lấy từ bảng, ngay trong khung chat.
- `/ai-worker:voice`: mở phần cài đặt đọc chính tả của máy và chỉ các bước.
- `/ai-worker:help`: plugin làm gì và các lệnh của nó.

## Codex, Cursor và Gemini CLI trên bảng

Người làm việc trong Codex, Cursor hoặc Gemini CLI cũng hiện được trên cùng bảng, dù máy có Claude Code hay không. Việc này do một bộ nối nhỏ (`connectors/`) đảm nhận: một hook mà từng công cụ tự chạy khi mở phiên, khi gửi câu hỏi, khi công cụ xin duyệt, khi kết thúc lượt và khi đóng phiên.

**Cài trên một máy.** Trong gói công ty đã giải nén:

- macOS: bấm đúp `INSTALL-Other-Tools-Mac.command`.
- Ubuntu: mở Terminal trong thư mục đã giải nén rồi gõ `bash INSTALL-Other-Tools-Linux.sh`.
- Windows: bấm đúp `INSTALL-Other-Tools-Windows.bat`.

Nếu dùng bản sao của kho mã này thay cho gói: `bash connectors/install.sh --server https://aiworker.example.com` (Windows: `powershell -ExecutionPolicy Bypass -File connectors\install.ps1 -Server https://aiworker.example.com`); bộ cài sẽ hỏi khoá gửi.

Bộ cài hỏi về từng công cụ nó tìm thấy trên máy. Nó thêm hook của mình vào cấu hình của chính công cụ đó (`~/.codex/hooks.json` hoặc `config.toml`, `~/.cursor/hooks.json`, `~/.gemini/settings.json`) và để nguyên mọi thứ khác trong đó; một bản sao của file như lúc trước được giữ ngay bên cạnh, tên kết thúc bằng `.ai-worker-backup`. File cấu hình nào nó không đọc được như JSON thuần thì không bị sửa: bộ cài in ra các hook để bạn tự thêm. Nó dùng đúng tên và email mà plugin đã có trên máy, nên một người vẫn là một dòng trên bảng. Khi được yêu cầu, nó chép thêm 17 skill của plugin vào `~/.agents/skills/`, thư mục mà cả ba công cụ đều đọc; `make-skill` và `improve-codebase-architecture` dựa vào Claude Code nên không được chép. Skill nào bạn đã sửa sau khi được chép thì là của bạn: lần chạy sau không thay nó và `--uninstall` không gỡ nó, và bộ cài có báo. Muốn lấy lại bản của gói thì xoá thư mục của skill đó rồi chạy lại bộ cài.

**Codex hỏi một lần.** Codex chỉ chạy hook sau khi chủ máy đã xem qua: mở Codex, gõ `/hooks`, rồi bấm tin cậy bảy hook có lệnh kết thúc bằng `ai-worker-hook.sh`. Cursor và Gemini CLI nhận hook ở lần mở kế tiếp.

**Kiểm tra và gỡ.** `bash ~/.local/share/ai-worker/connector/install.sh --status` cho biết đã cài gì và lần gần nhất bảng trả lời gì; cùng lệnh đó với `--uninstall` sẽ gỡ hook, skill và thư mục của bộ nối. Trên Windows: `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.local\share\ai-worker\connector\install.ps1" -Status` hoặc `-Uninstall`.

**Bảng hiện gì cho các công cụ này:** số phiên đang mở, đang làm và đang chờ, theo từng công cụ. Đang chờ nghĩa là công cụ xin duyệt, hoặc kết thúc lượt bằng một câu hỏi. Token, chi phí, hạn mức và mô hình của các công cụ này không biết được nên hiện gạch ngang.

**Giới hạn cần biết:**

- Bộ nối chỉ gửi khi có việc xảy ra trong công cụ. Phiên không có sự kiện nào trong 2 giờ thì thôi không tính, và công cụ bị đóng mà không có sự kiện kết thúc (gập máy, tắt ngang cửa sổ lệnh) có thể còn hiện trên bảng tới 2 giờ. Lượt kết thúc bằng lỗi không gửi sự kiện nào: phiên đó hiện là đang làm cho tới sự kiện kế tiếp, nhiều nhất 30 phút.
- Mỗi máy có bộ nối được tính thêm một máy vào các giới hạn ghi trong [ARCHITECTURE.vi.md](ARCHITECTURE.vi.md): tổng cộng 300 máy, mỗi IP mỗi ngày 10 máy mới. Văn phòng dùng chung một IP công cộng mà cài cho nhiều người trong cùng một ngày sẽ thấy một số máy bị từ chối tới hôm sau.
- Bộ nối không tự cập nhật: sau khi có bản AI Worker mới, hãy chạy lại bộ cài.
- Máy chủ phải từ bản này trở lên. Máy chủ bản cũ vẫn nhận báo cáo nhưng hiện người đó là ngoại tuyến sau 12 phút và không ghi tên công cụ.
- **Đã thử tới đâu.** Hook và bộ cài đã qua các bài test với sự kiện mẫu và thư mục nhà tạm trên macOS, Ubuntu và Windows (hai hệ sau chạy trên máy thử của GitHub); trong một phiên Codex CLI 0.164.0 thật trên macOS, các hook mở phiên, gửi câu hỏi, hết lượt và đóng phiên đã chạy, một câu hỏi của Codex đã hiện trên bảng mẫu là đang chờ, và việc bấm Esc cắt ngang một lượt được thấy là gửi `Interrupt` chứ không gửi `Stop`, sau đó phiên hiện là rảnh; còn hook xin duyệt và hook sau từng bước thì chưa thấy chạy trong phiên thật. Cursor và Gemini CLI được viết theo tài liệu của hai công cụ, chưa thử bên trong công cụ thật, và chưa có công cụ thật nào được thử trên Windows hay Linux. Trên Windows mỗi lần hook chạy tốn thời gian khởi động PowerShell, khoảng nửa giây trên máy thử. Nếu bạn thử, hãy cho chúng tôi biết bạn thấy gì.

Quy cách báo cáo, để viết bộ nối cho công cụ khác: [connectors/README.vi.md](../connectors/README.vi.md).

## Hỏi bảng từ một công cụ AI (MCP)

Máy chủ có một cổng MCP ở `/mcp`. MCP (Model Context Protocol) là cách chung để một công cụ AI gọi công cụ trên một máy chủ khác. Có khoá, một công cụ AI như Claude Code, Codex CLI, Cursor hay Gemini CLI trả lời được câu "ai đang chờ lâu nhất?" từ số liệu của bảng, giống `/ai-worker:board` trong Claude Code. Cổng này chỉ đọc, và đưa đúng những gì màn hình treo tường nhận: tên, trạng thái, chi phí và hạn mức, không bao giờ có email, IP hay mã máy.

**Cổng bật sẵn, và không đưa gì ra cho tới khi quản trị duyệt một khoá.** Muốn gỡ cổng và các trang của nó, thêm `MCP=0` vào `/etc/ai-worker.env` rồi khởi động lại dịch vụ.

**Cách lấy khoá.**

1. Người cần khoá mở `https://aiworker.example.com/mcp/connect` bằng trình duyệt trong mạng công ty rồi bấm **Lấy mã**. Trang hiện một mã 8 số. Quản trị và tài khoản chỉ xem vào trang này bằng nút **Nối một công cụ AI** trên `/board`; trang Quản trị cũng hiện link kèm nút **Chép link** ở mục **Thiết bị và khoá đã ghép**.
2. Quản trị mở `/admin`, vào mục **Thiết bị và khoá đã ghép**, gõ mã rồi bấm **Xem yêu cầu**. Thẻ hiện ra ghi rõ đây là khoá cho công cụ AI. Quản trị chọn khoá được đọc gì (chỉ số gộp của cả đội và từng văn phòng, hoặc cả từng người), đặt tên cho khoá rồi bấm **Duyệt**.
3. Trang của người xin sẽ hiện khoá một lần, kèm dòng để dán vào từng công cụ. Chỉ duyệt mã do chính người xin đọc cho bạn: bản thân mã không nói lên ai đang xin.

**Điều cần biết về một khoá.**

- Nó chỉ dùng được ở `/mcp`, và không khoá nào khác dùng được ở đó: khoá của TV, tiện ích, plugin hay mã gửi đều không.
- Máy chủ lưu dạng băm của khoá, không bao giờ lưu khoá. Trang Quản trị hiện vài ký tự đầu, khoá đọc được gì và lần dùng cuối; bấm **Thu hồi** là khoá hết dùng được ngay. Khoá đã mất thì không hiện lại được: thu hồi rồi xin khoá mới.
- Khoá hết hạn sau 30 ngày không dùng, và tối đa sau 1 năm.
- Mỗi khoá được hỏi 120 lần trong 10 phút. Tối đa 50 khoá.
- Mỗi lần đọc được ghi nhật ký 3 tháng và hiện ở trang Quản trị, mục **Các lần công cụ AI đọc bảng**: khoá nào, công cụ nào, từ IP nào. Bản thân câu hỏi không bao giờ tới máy chủ.
- Những gì công cụ đọc sẽ được gửi tới hãng làm ra công cụ đó, như một phần câu hỏi của người dùng. Khoá chỉ đọc số gộp thì tên người không đi theo.

**Đã thử tới đâu.** Trong công cụ thật, trên macOS: Claude Code 2.1.318 và Codex CLI 0.164.0 đều đọc được bảng và trả lời từ đó. Claude Code nói giao thức bản 2026-07-28 và, khi được bảo, cả kiểu bắt tay cũ mở đầu bằng `initialize`; Codex nói bản 2025-06-18. Khoá chỉ đọc số gộp đã được thử với Claude Code: nó trả lời rằng số liệu của từng người có tồn tại nhưng khoá của nó không được đọc. Hai dòng `claude mcp add` và `codex mcp add` mà trang đưa ra đã được chạy đúng nguyên văn. Cursor và Gemini CLI chưa được thử trong công cụ thật, và chưa công cụ nào được thử trên Windows hay Linux; các dòng đó viết theo tài liệu của từng công cụ. Tab Chat của app Claude trên máy tính cũng đã được thử, qua một kết nối của claude.ai: xem mục kế tiếp.

### claude.ai và tab Chat của Claude Desktop: tắt mặc định

Mẫu Caddy (`server/aiworker.caddy`) chỉ cho các mạng của bạn vào, và điều đó che luôn `/mcp`: công cụ AI chỉ tới được cổng này từ một máy nằm trong các mạng đó. claude.ai, tab Chat của Claude Desktop và app Claude trên điện thoại thì khác. Chúng kết nối từ máy chủ của Anthropic, không phải từ máy của người dùng, và cần địa chỉ trả lời được trên Internet ở cổng 443 ([trang trợ giúp của Anthropic về custom connector](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp)). Vì vậy chúng bị từ chối, trừ khi bạn tự mở cửa đó.

Muốn mở riêng cho `/mcp` và không gì khác, thay hai dòng `@outside not remote_ip ...` và `respond @outside ...` trong khối Caddy bằng:

```
	# mạng của bạn vào được mọi đường; địa chỉ đi ra của Anthropic chỉ vào được /mcp
	@outside {
		not remote_ip 203.0.113.0/24 198.51.100.0/24
		not {
			remote_ip 160.79.104.0/21 153.61.208.0/20
			path /mcp
		}
	}
	respond @outside "Forbidden" 403
```

Sau đó chạy `caddy validate` với file này rồi `sudo systemctl reload caddy`. Nếu bạn đã mở `/ingest` và `/releases/` cho các máy được chọn ([Gửi từ ngoài văn phòng](#gửi-từ-ngoài-văn-phòng-máy-được-chọn)), giữ cả khối `not { path ... header ... }` đó bên trong `@outside`, cùng các dòng `@away` của nó. Nếu file của bạn đặt tên khối này khác `@outside` thì giữ nguyên tên của bạn. Muốn đóng cửa lại thì đặt lại hai dòng cũ rồi nạp lại.

Hai dải trong khối trên là địa chỉ IPv4 đi ra của Anthropic, công bố ở [platform.claude.com/docs/en/api/ip-addresses](https://platform.claude.com/docs/en/api/ip-addresses), đọc ngày 2026-11-16. Hãy tự đọc trang đó trước khi dùng, và thỉnh thoảng đọc lại: các dải có thể đổi.

Trước khi mở:

- **Khi đó `/mcp` nhận kết nối từ ngoài văn phòng.** Bất kỳ ai trên claude.ai gõ địa chỉ của bạn đều đi tới từ chính các địa chỉ đó của Anthropic, nên khoá là thứ duy nhất đứng giữa họ và số liệu. Mọi đường khác vẫn đóng, kể cả `/mcp/connect`: khoá vẫn phải xin từ bên trong mạng của bạn.
- **Trong claude.ai:** Customize > Connectors > Add custom connector, và địa chỉ `https://aiworker.example.com/mcp`. Lúc đầu Claude đánh dấu "Sign in now" là đã phát hiện, vì bảng trả lời rằng nó cần một khoá: hãy chọn **No sign-in**. Ở mục **Request headers**, thêm header `authorization` với giá trị là chữ `Bearer`, một dấu cách, rồi tới khoá. Để kiểu truyền là **Streamable HTTP**.
- **Claude có thể gọi công cụ mà không hỏi.** Trang của kết nối liệt kê công cụ của bảng là loại chỉ đọc ở mức "Needs approval", và ghi rằng mức này áp dụng ở chế độ Manual. Trong lần thử, Claude gọi công cụ mà không hỏi câu nào. Công cụ đọc được gì là do khoá quyết định, nên hãy duyệt khoá chỉ đọc số gộp, trừ khi bạn chủ ý cho tên người đi ra ngoài.
- **Nhật ký hiện địa chỉ của Anthropic, không phải của người dùng,** và dòng của khoá có thêm một dòng báo khoá được dùng từ IP mới.
- **Đã thử một lần, ngày 2026-11-17, từ tab Chat của app Claude trên máy tính,** với một bảng nằm sau Caddy 2.6.2 dùng khối ở trên và một khoá chỉ đọc số gộp: thêm được kết nối, và Claude trả lời từ số liệu của bảng. Có ba điều thấy được. Lần thêm kết nối đầu tiên báo không tới được địa chỉ, lần thứ hai thì qua; chưa tìm ra lý do. Claude còn hỏi ba đường `/.well-known/oauth-...`, khối này vẫn đóng các đường đó (403), và việc đó không cản trở gì. Mục Request headers có trên tài khoản dùng để thử. claude.ai trên trình duyệt và app trên điện thoại dùng cùng loại kết nối này và chưa được thử.

## Dự án hay ứng dụng AI (tuỳ chọn)

Một dự án hay ứng dụng nhóm tự làm có thể gửi những gì bộ đo `ai-cost-report` của nó đo được (thời gian và token mỗi lượt, không bao giờ có câu hỏi hay câu trả lời) lên bảng, nơi quản trị và người xem đọc và tải báo cáo. Tắt cho tới khi bạn bật.

1. **Ở đâu:** máy chủ, quyền root. **Làm gì:** thêm `AI_PROJECTS=1` vào `/etc/ai-worker.env`, rồi `sudo systemctl restart ai-worker-webhook`. **Kết quả đúng:** trang Quản trị có mục **Dự án và ứng dụng AI**, và `/board` có liên kết tới `/projects`.
2. **Ở đâu:** trang Quản trị. **Làm gì:** gõ tên dự án, bấm **Tạo khoá**, nhập mã OTP. **Kết quả đúng:** hiện hai dòng `AI_METER_URL=…/projects/ingest` và `AI_METER_KEY=prj_…`, chỉ một lần.
3. **Ở đâu:** máy chủ của chính dự án (không bao giờ trong trang web hay app điện thoại). **Làm gì:** đặt hai dòng đó vào biến môi trường, cạnh bộ đo lấy từ `skills/ai-cost-report/meter/`. **Kết quả đúng:** sau vài yêu cầu, dự án hiện trên `/projects`.
4. **Dự án chạy trên cloud:** yêu cầu của nó đến từ ngoài mạng của bạn, nên proxy từ chối. Trong `aiworker.caddy`, dùng khối đang để ở dạng ghi chú cho đúng một IP tới `/projects/ingest`, điền IP của dự án, rồi chạy `sudo systemctl reload caddy`.

Phần người làm dự án tự làm: [AI-PROJECTS.vi.md](AI-PROJECTS.vi.md).

Giá lấy từ `server/board/prices.json`, bản sao bảng giá của skill, đi theo mỗi bản phát hành. Hãng chưa có trong đó, giá đã thương lượng, hay model chạy trên máy của nhóm thì dán file giá riêng ở mục **Giá riêng** trên trang Quản trị.

## Gửi từ ngoài văn phòng (máy được chọn)

Mặc định chỉ các mạng văn phòng tới được máy chủ, nên laptop ở nhà hay dùng 4G không gửi được số liệu và không `/update` được. Bạn có thể cho các máy được chọn làm cả hai việc đó từ mọi mạng, còn mọi máy khác vẫn chỉ ở văn phòng:

- Từ ngoài văn phòng, Caddy chỉ cho qua yêu cầu tới `/ingest` hay `/releases/` có mang khoá riêng của một máy (`awd1.`). Mã gửi chung trong gói cài không gửi được gì từ ngoài.
- Sau đó máy chủ chỉ nhận yêu cầu ấy từ máy mà quản trị viên đã cho gửi từ mọi mạng trên trang Quản trị. Mọi máy khác nhận 403, và vẫn giữ khoá riêng của mình.
- Các trang của bảng, đăng nhập, `/mcp` và phần còn lại vẫn chỉ cho văn phòng, có OTP như trước.

Một máy nhận khoá riêng ở lần gửi đầu từ văn phòng, nên mỗi máy bạn muốn cho phải đã gửi từ văn phòng một lần, với bản plugin mới hơn 0.50.6 để dùng `/update`. Làm theo đúng thứ tự dưới đây: không bước nào máy chủ mở rộng hơn ý bạn.

1. **Sao lưu** các thư mục cơ sở dữ liệu và file Caddy, ví dụ `sudo cp -a /opt/ai-worker/data /opt/ai-worker/data.bak` và `sudo cp /etc/caddy/aiworker.caddy /etc/caddy/aiworker.caddy.bak`. Bản mới hơn có thể nâng cơ sở dữ liệu lên lược đồ mới hơn (phiên bản 8 từ bản 0.50.19), và máy chủ bản cũ từ chối file đã nâng.
2. **Cài bản máy chủ mới** như thường lệ, `OFFICE_NETS` vẫn để trống: chưa có gì thay đổi.
3. **Báo cho máy chủ các mạng văn phòng.** Thêm `OFFICE_NETS=` với đúng các dải của `remote_ip` trong khối Caddy, cách nhau bằng dấu phẩy, vào `/etc/ai-worker.env` (cả dải IPv6, nếu tên miền có bản ghi AAAA), rồi `sudo systemctl restart ai-worker-webhook`. Caddy vẫn đóng, nên mọi yêu cầu vẫn từ văn phòng. Mở trang Quản trị từ văn phòng: trong mục **Máy nhân viên và khoá riêng** không được có cảnh báo địa chỉ của bạn bị tính là ở ngoài. Nếu có, hai danh sách đang lệch nhau: sửa cho khớp rồi mới làm tiếp.
4. **Cho các máy.** Trên trang Quản trị, mục **Máy nhân viên và khoá riêng**, bấm **Mọi mạng** ở dòng của từng máy được chọn rồi nhập lại OTP. Mỗi thay đổi được ghi vào nhật ký Quản trị.
5. **Mở Caddy.** Trong khối Caddy, thay hai dòng `@outside not remote_ip ...` và `respond @outside ...` bằng khối chú thích trong `server/aiworker.caddy` bắt đầu bằng `# @outside {` và có dòng `header Authorization "Bearer awd1.*"`, đặt các dải của bạn vào cả hai dòng `remote_ip`. Chạy `caddy validate --config /etc/caddy/Caddyfile`, rồi `sudo systemctl reload caddy`.
6. **Thử từ ngoài**, ví dụ bằng 4G của điện thoại: `curl -s -o /dev/null -w '%{http_code}\n' https://aiworker.example.com/` trả `403`, và `curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer <mã gửi>' https://aiworker.example.com/releases/latest.json` cũng vậy. Trên máy được chọn, ở ngoài văn phòng, `/update` trả lời được và bảng hiện máy đó đang gửi.

Muốn đóng lại: đặt lại hai dòng Caddy cũ rồi `sudo systemctl reload caddy`; chỉ xoá `OFFICE_NETS` sau bước đó. Muốn thôi cho một máy, bấm **Chỉ văn phòng** ở dòng của nó.

Trước khi mở:

- **Máy bị mất hay bị lấy:** bấm **Thu hồi**, đừng bấm **Cho quay lại**. Thu hồi cũng lấy luôn quyền gửi từ ngoài; cho quay lại làm khoá cũ của máy dùng được trở lại, dù không còn từ ngoài.
- **Địa chỉ ở nhà hiện trên bảng.** Bảng giữ các địa chỉ gần nhất mỗi máy đã gửi từ đó, và quản trị viên nhìn thấy. Báo trước cho người dùng máy trước khi cho.
- **Khoá sống 90 ngày nếu máy không gửi.** Máy tắt lâu hơn, hay mọi máy sau `--rotate-device-secret --drop-old`, phải gửi từ văn phòng thêm một lần.
- **CDN hay proxy khác đứng trước Caddy** (ví dụ Cloudflare) làm mọi yêu cầu như tới từ CDN, nên máy nào cũng bị tính là ở ngoài. Cách này không dành cho trường hợp đó.
- **Có bộ nhận Go** (`RECEIVER=1`, [RECEIVER.vi.md](RECEIVER.vi.md)) thì bộ nhận không tự kiểm danh sách này. Khi đã đặt `OFFICE_NETS` (hoặc `TRUST_PROXY` với Caddy đứng trước), máy để **Chỉ văn phòng** không bao giờ được báo địa chỉ của bộ nhận và vẫn gửi tới webhook, nơi kiểm danh sách; chỉ máy được cho gửi từ **Mọi mạng** mới sang bộ nhận.

## Gói cài plugin cho Windows (.msi)

Thay cho gói zip, máy nhân viên Windows có thể cài từ một file duy nhất, `AI-Worker-Plugin.msi`. File cài cho riêng người dùng, không cần quyền quản trị, và có mục gỡ trong Settings > Apps. Bản thân file giống nhau cho mọi công ty: GitHub dựng nó với một chuỗi giữ chỗ, còn máy chủ của bạn điền địa chỉ của nó, mã gửi (`INGEST_KEY`) và khoá ký bản cập nhật đúng lúc quản trị tải về. Vì vậy mã gửi không bao giờ lên GitHub, và bạn không phải dựng gì trên máy mình.

1. **Lấy file về**, trên máy có repo và lệnh `gh` đã đăng nhập. Lệnh lấy lượt chạy đạt mới nhất của repo phát hành (việc `plugin-msi`), nơi Actions chạy miễn phí; bản fork truyền repo của mình: `bash packaging/windows-msi/fetch-msi.sh chủ/repo nhánh`.
   ```bash
   bash packaging/windows-msi/fetch-msi.sh
   ```
   Kết quả đúng: `Fetched AI-Worker-Plugin.msi ...`, và file nằm trong `server/menubar/` (không đưa vào git). Chép `server/` lên máy chủ và chạy `install.sh` như thường lệ. File mang plugin của phiên bản lúc dựng: lấy lại sau mỗi lần phát hành.
2. **Phát hành một lần** bằng `packaging/release.sh` trước khi phát file: máy chủ lấy khoá ký bản cập nhật từ bản phát hành mới nhất. Chưa phát hành thì plugin vẫn cài được nhưng không tự cập nhật bằng `/update`.
3. **Tải:** trang Quản trị, mục **Plugin cho máy nhân viên (Windows)**, nút **Tải AI-Worker-Plugin.msi**. Mục này chỉ hiện khi máy chủ có file. Lần tải nào cũng được ghi vào nhật ký Quản trị ("Tải gói cài plugin cho nhân viên"). File có mã gửi, như gói zip công ty: chỉ phát trong công ty.
4. **Trên máy nhân viên:** mở file và bấm **Install**. Nếu Windows báo "Windows protected your PC" (file chưa được ký), bấm **More info**, rồi **Run anyway**. Để nguyên ô **Finish the setup now** và bấm **Finish**: một cửa sổ làm đúng các bước của `INSTALL-Windows.bat` (Claude đã đăng nhập, họ tên, đăng ký plugin với Claude Code). Kết quả đúng: cửa sổ kết thúc bằng "Xong. Mở (hoặc mở lại) Claude Code, rồi gõ /office". Chạy lại cửa sổ này được từ menu Start, **Finish AI Worker setup**, ví dụ sau khi cài im lặng (`msiexec /i AI-Worker-Plugin.msi /qn`, không có màn hình cuối).
5. **Cập nhật** vẫn bằng `/update`. Cài `.msi` mới hơn đè lên bản cũ thì plugin vẫn giữ nguyên; chạy lại bước cài không bao giờ đưa về plugin cũ hơn bản `/update` đã cài.
6. **Gỡ cài:** Settings > Apps > **AI Worker plugin** > Uninstall. Việc gỡ bỏ đăng ký plugin khỏi Claude Code và xoá thư mục plugin cùng `company.json`; dữ liệu riêng của người dùng trong `%USERPROFILE%\.local\share\ai-worker` được giữ.

Cần nhớ: file chưa được ký, và để nguyên cách này thì không ký được, vì máy chủ sửa file sau khi dựng. Khi mọi máy đã cài xong, có thể đặt `SHARED_KEY_MODE=known-only` trong `/etc/ai-worker.env` để một bản file bị lộ không thêm được máy mới. Gói zip và file `.bat` vẫn còn, làm đường dự phòng và cho macOS, Linux.

## Biểu tượng thanh menu cho quản lý

Quản lý thấy ngay trên thanh menu có bao nhiêu người đang chờ trả lời, không cần mở bảng: app riêng trên macOS, app cạnh đồng hồ trên Windows (cài từ file .msi, không cần quyền quản trị), biểu tượng trên thanh trên cùng của Ubuntu (gói .deb). Bấm vào là mở khung nhỏ có Đang chờ, Đang làm, Hạn mức, Chi phí hôm nay và Cài đặt. Chi tiết: [docs/menu-bar-spec.vi.md](menu-bar-spec.vi.md).

- **Tải về:** trang Quản trị, mục "Biểu tượng thanh menu": "Tải cho macOS ▾" (.dmg khi máy chủ có app đã dựng, và .zip), "Tải cho Windows ▾" (.msi, và file cài PowerShell cũ "AI-Worker-windows.zip"), "Tải cho Ubuntu (.deb)". Chưa đặt `MENUBAR_MAC_APP` thì "Tải cho macOS" phát gói cài dựa trên SwiftBar, không phải app.
- **Ubuntu:** mở file .deb bằng App Center, hoặc `sudo apt install ./ai-worker-menubar.deb`; apt tự cài thư viện AppIndicator, biểu tượng tự chạy mỗi lần đăng nhập, `sudo apt remove ai-worker-menubar` là gỡ.
- **Ghép máy:** quản lý bấm biểu tượng rồi nhập tài khoản và mã 6 số của chính mình; mỗi tài khoản ghép tối đa 2 máy. Quản lý chưa có tài khoản thì đọc mã trên biểu tượng cho quản trị nhập ở mục Thiết bị và khoá đã ghép.
- **App macOS được dựng một lần cho mỗi công ty** trên một máy Mac có Command Line Tools của Apple, rồi máy chủ phát app đó:

```bash
bash server/menubar/macos-app/build.sh https://dia-chi-bang-cua-ban auto "AI Worker"
```

Chép `server/menubar/macos-app/dist/*-menu-bar-mac-app.zip` lên máy chủ và đặt `MENUBAR_MAC_APP` là đường dẫn tới nó trong file env. App dùng chữ ký tạm, nên lần mở đầu phải vào System Settings > Privacy & Security > Open Anyway một lần.

## Tiện ích trình duyệt cho quản lý

Tiện ích cho Chrome hoặc Edge hiện trên biểu tượng số người đang chờ trả lời; bấm vào là mở đúng khung nhỏ của các app thanh menu. Tiện ích chỉ đọc một phần những gì màn hình treo tường thấy, không giữ mật khẩu, OTP hay cookie đăng nhập. Chi tiết: [docs/chrome-extension-spec.vi.md](chrome-extension-spec.vi.md).

1. **Đóng gói** trên máy giữ repo: `bash packaging/build-extension.sh` tạo `server/menubar/AI-Worker-extension.zip`; chép `server/` lên máy chủ và chạy `install.sh`, trang Quản trị hiện nút **Tiện ích Chrome, Edge** ở mục "Biểu tượng thanh menu". Sửa tiện ích thì chạy lại lệnh này.
2. **Cài tay** trên máy quản lý: giải nén file đó (hoặc chép thư mục `extensions/manager/`), mở `chrome://extensions` (Edge: `edge://extensions`), bật Developer mode, bấm "Load unpacked" rồi chọn thư mục đó.
3. **Ghép:** bấm biểu tượng, nhập địa chỉ dùng để mở bảng (ví dụ `https://aiworker.example.com`), cho phép truy cập đúng trang đó khi trình duyệt hỏi, rồi đọc mã 8 số cho quản trị.
4. **Quản trị duyệt** ở trang Quản trị, mục Thiết bị và khoá đã ghép, như với màn hình; dòng đó được ghi "Tiện ích trình duyệt". Thu hồi ở đó thì trong vòng một phút tiện ích báo "chưa ghép".

Đã ghép thì cửa sổ nhỏ chính là khung nhỏ của các app thanh menu (năm thẻ, Cài đặt có thông báo, ngôn ngữ và bỏ ghép). Cửa sổ chạy bản chép của `server/static/mini.js`, `mini.css` và logo, để trong `extensions/manager/mini/`: sửa các file đó thì chép lại (`cp server/static/mini.js server/static/mini.css extensions/manager/mini/`, và chép `server/menubar/icons/generic-black.png`, `generic-white.png` thành `extensions/manager/mini/logo-black.png`, `logo-white.png`), rồi phát lại thư mục.

Thử: `node tests/extension/check-extension.js` (chạy webhook trên máy với người giả, và báo lỗi khi bản chép khác bản gốc).

## Đăng nhập bằng Telegram (tuỳ chọn)

Ai dùng Telegram hằng ngày có thể đăng nhập bảng tổng bằng nút của Telegram thay vì gõ tên và mã. Tắt cho tới khi bạn cài; tên và mã 6 số luôn dùng được, và thao tác quản trị vẫn hỏi mã.

1. **Tạo bot** (trong app Telegram, điện thoại hay máy tính đều được):
   1. Tìm **@BotFather** và mở đúng tài khoản có dấu tích xanh.
   2. Gửi `/newbot`. BotFather hỏi tên: gõ tên người dùng sẽ thấy khi xác nhận đăng nhập, ví dụ `AI Worker`.
   3. BotFather hỏi username: gõ một tên kết thúc bằng `bot` và chưa ai dùng, ví dụ `congtyban_aiworker_bot`. Nếu báo đã có người dùng thì thử tên khác.
   4. BotFather trả lời "Done! Congratulations on your new bot", trong đó có dòng **"Use this token to access the HTTP API:"** và ngay sau là **token** (khoá của bot), dạng `1234567890:AAH...`. Giữ tin nhắn này để dùng ở bước 3. Token ký được lần đăng nhập của bất kỳ ai: không dán vào chat, không chụp màn hình.
   5. Tuỳ chọn: gửi `/setuserpic`, chọn bot rồi gửi logo công ty, để người dùng nhận ra bot khi xác nhận.
2. **Gắn bot với địa chỉ bảng tổng** (vẫn trong @BotFather): gửi `/setdomain`, chọn bot, rồi gửi tên miền bảng tổng, không có `https://`, ví dụ `aiworker.company.com`. Đúng là: "Success! Domain updated."
3. **Khai token và username cho máy chủ.** Trên máy tính của bạn, chạy lệnh sau; lệnh hỏi token mà không hiện token lên màn hình:
   ```bash
   ssh -t <tài-khoản-ssh>@<IP-hoặc-tên-máy-chủ> 'read -rsp "Bot token: " T; echo; read -rp "Bot username (no @): " N; printf "TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_BOT_NAME=%s\n" "$T" "$N" | sudo tee -a /etc/ai-worker.env >/dev/null && sudo systemctl restart ai-worker-webhook && echo DONE'
   ```
   Ở dòng `Bot token:` dán token ở bước 1.4 rồi Enter (màn hình không hiện gì là đúng). Ở dòng `Bot username (no @):` gõ username ở bước 1.3, ví dụ `congtyban_aiworker_bot`. Đúng là: hiện `DONE`, và trang đăng nhập có nút **Log in with Telegram** dưới chữ "hoặc".
   Hoặc sửa file bằng tay với `sudo nano /etc/ai-worker.env`, thêm hai dòng dưới đây, lưu lại, rồi chạy `sudo systemctl restart ai-worker-webhook`:
   ```
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_BOT_NAME=<username của bot, không có @>
   ```
4. **Mỗi người liên kết một lần:** đăng nhập bằng tên và mã, mở `/telegram` (hoặc nút **Telegram** trên bảng chi tiết), nhập mã 6 số, bấm **Log in with Telegram** và xác nhận trong Telegram. Lần sau chỉ cần bấm nút đó ở trang đăng nhập.

Với việc này máy chủ không bao giờ gọi Telegram: nút đưa trình duyệt sang trang đăng nhập của Telegram rồi quay về, máy chủ chỉ kiểm chữ ký bằng token. Trang đăng nhập không nạp gì từ Telegram. Một lần đăng nhập đã ký chỉ nhận trong 5 phút và một lần. Nếu văn phòng không vào được Telegram thì đăng nhập bằng tên và mã. Quản trị xem ai đã liên kết Telegram ở `/admin` và gỡ được ở đó; cấp lại khoá hoặc chuyển tài khoản sang treo tường cũng gỡ liên kết.

## Hỏi bảng qua Telegram (tuỳ chọn)

Quản lý không viết code có thể hỏi bảng từ một chat Telegram trên điện thoại: bấm **Ai đang chờ** hoặc **Chi phí**, hoặc gõ "ai đang chờ lâu nhất?", và một bot trả lời từ số liệu của bảng. Không mô hình AI nào đọc câu hỏi. Một nút, một lệnh hay một từ khoá chọn một trong năm câu trả lời cố định, nên không tốn tiền, không cần khoá API và không bịa được con số nào. Tắt cho tới khi bạn bật.

**Bật là bạn chấp nhận điều gì.** Với mỗi chat được quản trị duyệt, những gì chat đọc sẽ đi qua máy chủ của Telegram và nằm lại trong chat đó trên điện thoại của người dùng: số gộp của cả đội và từng văn phòng, hoặc tên, trạng thái, chi phí và hạn mức của từng người khi quản trị chọn như vậy. Không bao giờ có email, IP hay mã máy. Telegram là bên thứ ba, và chat với bot không được mã hoá đầu cuối.

**Nó được dựng thế nào.** Một dịch vụ nhỏ thứ hai trên máy chủ, `ai-worker-telegram`, hỏi Telegram xem có tin mới không. Nó chỉ kết nối đi ra, nên không phải mở gì ở Caddy hay tường lửa, và bảng không có địa chỉ công khai vẫn dùng được. Chính webhook vẫn không bao giờ kết nối ra ngoài: tiến trình bot đưa từng tin cho webhook trên cùng máy rồi gửi lại thứ webhook trả lời. Tiến trình bot chạy dưới người dùng riêng, chỉ cầm token của bot chứ không cầm gì của bảng, và chỉ tới được chính máy này, các máy chủ DNS của nó và các mạng của Telegram.

1. **Tạo một bot riêng cho việc này** (trong app Telegram, điện thoại hoặc máy tính): tìm **@BotFather**, gửi `/newbot`, gõ tên hiển thị rồi một tên đăng nhập kết thúc bằng `bot`. BotFather trả lời kèm token, có dạng `1234567890:AAH...`. Sau đó gửi `/setjoingroups`, chọn bot và chọn **Disable**: bot chỉ trả lời trong chat riêng. Hãy tạo bot riêng, đừng dùng lại bot đăng nhập: token của bot đăng nhập ký được lần đăng nhập của bất kỳ ai, không nên để nó nằm cùng một tiến trình nói chuyện với Internet.
2. **Bật.** Trên máy chủ, thêm dòng `TELEGRAM_ASK=1` vào `/etc/ai-worker.env` (`sudo nano /etc/ai-worker.env`), rồi chạy `sudo bash install.sh` trong thư mục `server/`. Kết quả đúng: bộ cài báo chưa có token của bot và nêu tên file `/etc/ai-worker-telegram.env`.
3. **Đưa token cho nó.** Trong thư mục `server/`, chạy lệnh này; nó hỏi token mà không hiện lên màn hình:
   ```bash
   printf "Bot token: "; read -rs T; echo; sudo sed -i "s|^TELEGRAM_ASK_TOKEN=.*|TELEGRAM_ASK_TOKEN=$T|" /etc/ai-worker-telegram.env; unset T; sudo bash install.sh
   ```
   Tại `Bot token:` dán token ở bước 1 rồi bấm Enter (không hiện gì là đúng). Hoặc tự sửa file bằng `sudo nano /etc/ai-worker-telegram.env` rồi chạy lại `sudo bash install.sh`. Kết quả đúng: `✔ Tiến trình bot Telegram đang chạy.`, và ở `/admin`, mục **Thiết bị và khoá đã ghép**, có một dòng cho biết bot đang đọc tin kèm tên của nó.
4. **Mỗi người nối một lần.** Họ mở bot trong Telegram, bấm **Start** và đọc mã 8 số bot đưa cho quản trị. Quản trị mở `/admin`, vào **Thiết bị và khoá đã ghép**, gõ mã và bấm **Xem yêu cầu**. Thẻ hiện tên và số Telegram của người đó, cùng tài khoản bảng mà Telegram ấy đã liên kết, nếu có. Quản trị chọn chat được đọc gì, đặt tên rồi bấm **Duyệt**. Người đó gửi một tin bất kỳ: bot chào và hiện các nút.

**Cần biết.**

- **Lệnh:** `/waiting`, `/cost`, `/offices`, `/team`, `/quota`, `/alerts`, `/help` và `/stop`. Người nói tiếng Việt còn có `/cho`, `/chiphi`, `/vanphong`, `/tongquan`, `/hanmuc` và `/baocho`. Câu gõ tự do chạy được khi có một từ khoá như "chờ", "tốn", "chi phí" hay "văn phòng"; còn lại thì nhận danh sách lệnh. Từ đơn tiếng Việt phải gõ có dấu, cụm hai từ trở lên thì không dấu cũng được. Câu trả lời theo ngôn ngữ của tin nhắn, rồi tới ngôn ngữ app Telegram của người đó.
- **Chat đọc được gì** là do quản trị chọn lúc duyệt: chỉ số gộp của cả đội và từng văn phòng, hay cả từng người. Với số gộp, các văn phòng dưới 3 người dùng chung một dòng.
- **Chat chưa được quản trị duyệt thì không đọc được gì.** Gửi `/stop` trong chat, hoặc bấm **Thu hồi** ở trang Quản trị, là chat dừng ngay. Chat hết hạn sau 30 ngày không dùng, và tối đa sau 1 năm. Tối đa 50 chat, mỗi chat 20 tin trong 10 phút.
- **Mỗi câu trả lời có số liệu được ghi nhật ký 3 tháng** và hiện ở trang Quản trị, mục **Các lần công cụ AI và chat Telegram đọc bảng**: chat nào và lệnh nào. Chữ người dùng gõ không bao giờ được lưu hay ghi nhật ký.
- **Trên điện thoại:** câu trả lời được gửi sao cho các app Telegram không cho chuyển tiếp hay lưu, và dòng đầu không bao giờ có tên người, vì điện thoại hiện dòng đó trên màn hình khoá. Trên chiếc điện thoại đã thử, app Telegram cũng không cho chụp màn hình. Đó không phải lời bảo đảm: trên máy tính vẫn chụp được màn hình, và màn hình nào cũng có thể bị chụp lại bằng máy khác.
- **Bot không bao giờ hỏi mã đăng nhập hay mật khẩu.** Hãy dặn mọi người điều đó: ai lấy được token có thể nhắn cho họ dưới tên bot.
- **Nếu trang Quản trị báo máy chủ không tới được Telegram:** thử ngay trên máy chủ bằng `curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org`. Ra một con số nghĩa là tới được Telegram, và thứ đang chặn là giới hạn mạng của dịch vụ bot: có thể Telegram đã đổi mạng. Ghi danh sách của riêng bạn vào `TELEGRAM_NETS=` trong `/etc/ai-worker-telegram.env`, các địa chỉ cách nhau bằng dấu phẩy, hoặc `any` để bỏ giới hạn, rồi chạy lại `install.sh`. Danh sách mặc định là của chính Telegram, lấy từ [core.telegram.org/resources/cidr.txt](https://core.telegram.org/resources/cidr.txt), đọc ngày 2026-11-16.
- **Nếu lộ token:** gửi `/revoke` cho @BotFather, rồi ghi token mới như ở bước 3. Người có token đọc được những gì mọi người gửi cho bot từ lúc đó và nhắn cho họ dưới tên bot. Họ không đọc được bảng: máy chủ chỉ trả lời chat đã được quản trị duyệt.
- **Muốn tắt:** đổi dòng đó thành `TELEGRAM_ASK=0` trong `/etc/ai-worker.env` rồi chạy lại `install.sh`. Dịch vụ bị gỡ. Nếu không dùng lại thì xoá luôn `/etc/ai-worker-telegram.env` và gửi `/deletebot` cho @BotFather.

**Thử trên máy của bạn trước.** Với bảng mẫu, trong một cửa sổ lệnh:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > /tmp/ai-worker-ask-key && TELEGRAM_ASK=1 TELEGRAM_ASK_KEY="$(cat /tmp/ai-worker-ask-key)" python3 server/demo.py
```

và trong cửa sổ thứ hai, nơi nó hỏi token mà không hiện lên màn hình:

```bash
printf "Bot token: "; read -rs TELEGRAM_ASK_TOKEN; echo; export TELEGRAM_ASK_TOKEN; TELEGRAM_ASK_KEY="$(cat /tmp/ai-worker-ask-key)" PORT=8799 python3 server/telegram_bot.py
```

Khi đó tên của các nhân viên giả lập sẽ đi qua Telegram. Đăng nhập `http://127.0.0.1:8799` bằng tài khoản `demo` với mã hiện ở cửa sổ thứ nhất, rồi duyệt chat của bạn ở `/admin`.

**Đã thử tới đâu.** Với Telegram thật, chạy tay trên macOS như trên: ghép một chat, các nút, menu lệnh, và câu trả lời bằng cả hai ngôn ngữ. Dịch vụ do bộ cài dựng, cùng người dùng riêng và giới hạn mạng của nó, được bài kiểm cài đặt trên Ubuntu (`tests/linux/test-server.sh`) kiểm và đã được cài lên một máy chủ thật, nơi bot tới được Telegram qua giới hạn mạng và một chat chỉ đọc số gộp đã được ghép. Trên điện thoại, app Telegram không cho chuyển tiếp câu trả lời. Chat đọc từng người đã được thử ở đó một lần, ngày 2026-11-17: câu trả lời về chi phí nêu tên người có chi phí cao nhất và cho mỗi văn phòng một dòng riêng. Câu trả lời về người đang chờ và về hạn mức có kèm tên thì chưa thấy, vì lúc đó không ai chờ và chưa ai gần hết hạn mức.

### Khung của bảng bên trong Telegram (tuỳ chọn)

Chat đã được duyệt còn có thể mở khung nhỏ của biểu tượng thanh menu ngay bên trong Telegram: số người đang chờ, biểu đồ chi phí 7 ngày, và các thẻ Đang chờ, Đang làm, Hạn mức, Chi phí. Đây là một Telegram Mini App: Telegram hiện nút menu của bot là **AI Worker**, bấm vào là mở khung. Tắt cho tới khi bạn bật, và khi bật thì chỉ cho những chat quản trị cho phép từng cái một.

**Bật lên thì có gì thay đổi.** Khung là một trang của bảng, mở bằng trình duyệt có sẵn trong Telegram trên điện thoại hay máy tính của người đó. Số liệu đi thẳng từ bảng tới trình duyệt đó qua HTTPS, không qua máy chủ của Telegram; Telegram chỉ biết là khung đã được mở. Vì vậy điện thoại phải tới được bảng: với khối Caddy mẫu, nghĩa là đang ở một mạng có trong danh sách IP được vào (các văn phòng của bạn). Ở ngoài các mạng đó, khung báo không tới được máy chủ, còn các nút của chat vẫn dùng bình thường.

1. **Bật lên.** Việc hỏi bảng qua Telegram phải đang chạy (mục trên). Thêm hai dòng này vào `/etc/ai-worker.env`, thay `aiworker.example.com` bằng domain bảng của bạn, rồi chạy `sudo bash install.sh` trong thư mục `server/`:
   ```
   TELEGRAM_APP=1
   TELEGRAM_APP_URL=https://aiworker.example.com/tg/app
   ```
   Bộ cài ghi thêm `TELEGRAM_APP_KEY` bên cạnh: một khoá nó suy ra từ khoá bot theo quy tắc của Telegram. Webhook dùng khoá này để kiểm phần Telegram ký cho khung, và không dùng được nó để điều khiển bot; bản thân khoá bot vẫn chỉ ở tiến trình bot. Kết quả đúng: không có dòng nào nói về `TELEGRAM_APP_URL`, và ở `/admin`, mục **Thiết bị và khoá đã ghép**, mỗi chat Telegram có nút **Cho mở khung**.
2. **Cho phép một chat.** Bấm **Cho mở khung** ở dòng của chat đó rồi xác nhận. Kết quả đúng: dòng ghi *mở được khung*, và trong vòng một phút nút menu của chat trong Telegram đổi thành **AI Worker**. Nếu Telegram vẫn hiện menu cũ, đóng chat rồi mở lại.
3. **Mở khung.** Trong chat, bấm **AI Worker** cạnh ô nhập tin. Kết quả đúng: khung hiện cùng các con số như biểu tượng thanh menu.

**Cần biết.**

- **Ai được mở:** chỉ chat đã được quản trị duyệt và cho mở khung. Chat được đọc từng người thấy từng cái tên, như màn hình treo tường; chat chỉ đọc số gộp nhận số đếm và chi phí của cả team, cộng sẵn trên máy chủ, không có tên ai, và mỗi thẻ chỉ hiện một dòng số tổng.
- **Cách kiểm:** Telegram ký vài trường cho khung (ai mở, lúc nào) và đặt chúng sau dấu `#` của địa chỉ, nên chúng không bao giờ vào nhật ký nào. Trang đổi chúng một lần lấy một phiên, sống một giờ sau lần dùng cuối, tối đa 12 giờ, chỉ nằm trong bộ nhớ máy chủ: không có cookie. Các trường cũ hơn 5 phút bị từ chối.
- **Kết thúc:** **Thôi mở khung** hay **Thu hồi** ở trang Quản trị, `/stop` trong chat, hoặc **Ngắt chat này** trong phần cài đặt của khung, đều đóng ngay mọi khung đang mở của chat đó. Khởi động lại máy chủ cũng kết thúc các phiên: đóng khung rồi mở lại.
- **Trong nhật ký:** mỗi lần mở, mỗi lần bị từ chối, và mỗi lần quản trị cho phép hay thôi cho một chat. Không bao giờ có các trường Telegram đã ký.
- **Tắt đi:** bỏ dòng `TELEGRAM_APP=1` rồi chạy lại `install.sh`. Các đường dưới `/tg/` trả 404, và nút menu trở về menu thường ở lần chạy kế tiếp của tiến trình bot.
- **Nếu khung hiện chữ *Forbidden*:** chữ đó do Caddy trả, không phải do bảng: điện thoại tới máy chủ bằng một IP không có trong danh sách. Văn phòng có nhiều đường Internet có thể đẩy Telegram ra bằng đường danh sách chưa có, dù trình duyệt của điện thoại vào được. Xem IP bị Caddy chặn bằng `sudo grep '/tg/app' /var/log/caddy/aiworker.log | tail -3` (trường `remote_ip`), và chỉ thêm IP đó vào dòng `remote_ip` khi nó là đường Internet của chính bạn; nếu không phải (proxy đặt trong Telegram, VPN), hãy tắt thứ đó.
- **Mở từ ngoài văn phòng** cần proxy cho `/tg/` vào từ mọi nơi, tức là một quyết định về việc đưa bảng ra Internet. Việc đó không nằm trong bản này.

**Đã thử tới đâu.** Phần kiểm chữ ký của Telegram, phiên, giới hạn và nút menu có bài test máy chủ (`server/test_webhook.py`, `TelegramApp`; `server/test_telegram_bot.py`, `MenuButtons`), còn khoá do bộ cài ghi có bài test cài trên Ubuntu. Bản thân khung đã được xem trong trình duyệt ở khổ điện thoại và máy tính, với các trường do bài test ký. Ngày 2026-11-18 đã bật trên một máy chủ thật: sau khi quản trị cho phép một chat, nút menu của bot đổi thành **AI Worker**, và trong Telegram Desktop trên máy Mac ở mạng văn phòng khung mở ra với số liệu của bảng. Trên một điện thoại Android dùng Wi-Fi văn phòng, lúc đầu khung hiện chữ *Forbidden* của proxy: văn phòng có nhiều đường Internet, và Telegram đi ra bằng một đường chưa có trong danh sách của Caddy, trong khi trình duyệt của điện thoại đi bằng đường khác. Thêm IP của đường đó vào danh sách xong thì khung mở được trên điện thoại. Chưa thử trên iPhone, và chưa thử từ ngoài văn phòng.

### Tin báo khi có người chờ quá lâu (tuỳ chọn, theo từng chat)

Khi chat đã được kết nối (mục trên), nó có thể nhờ bot tự nhắn trước: một tin khi có người chờ trả lời lâu hơn mức chat đã chọn. Không cần bật gì trên máy chủ; mỗi chat tự bật cho mình, và tắt cho tới lúc đó.

- **Bật:** gửi `/baocho 10` cho bot (hoặc `/alerts 10`; 5, 15, 30, 60 cũng được), hoặc trong khung bảng bên trong Telegram, mở **Cài đặt** và đánh dấu **Nhắn tôi khi có người chờ quá**. `/baocho tat` (`/alerts off`) hoặc bỏ dấu ở ô đó là tắt; chỉ gửi `/baocho` thì bot cho biết đang bật hay tắt.
- **Nhận được gì:** mỗi lần chờ chỉ báo một lần. Nhiều lần chờ gộp trong một tin. Mỗi chat tối đa một tin mỗi 5 phút, 6 tin mỗi giờ, 30 tin mỗi ngày, và không gửi từ 19:00 tới 07:00 theo múi giờ của bảng; lần chờ vượt mức ban đêm không được báo vào sáng hôm sau. Lần chờ quá 4 giờ, hoặc người đã ngoại tuyến, được coi là phiên bỏ mở và không báo.
- **Nội dung:** dòng đầu không nêu tên ai (điện thoại hiện dòng này trên màn hình khoá): có bao nhiêu người chờ quá số phút của chat. Sau đó, với chat đọc từng người, là từng cái tên như màn hình treo tường hiện kèm số phút; chat chỉ đọc số gộp thì chỉ nhận con số. Chat được mở khung có thêm nút **AI Worker** dưới tin để mở khung.
- **Trong nhật ký:** mỗi tin, kèm chat và số người, không bao giờ ghi là ai.
- **Thay đổi gì:** từ nay bot tự nhắn vào chat mà không cần được hỏi. Tên và số phút trong các tin này đi qua máy chủ của Telegram và nằm lại trong chat, như câu trả lời cho các câu hỏi của chính chat đó. Những gì bot đã báo được giữ trong bộ nhớ: sau khi máy chủ khởi động lại, một lần chờ còn đang diễn ra có thể được báo thêm một lần.

**Đã thử tới đâu.** Có bài test máy chủ (`server/test_webhook.py`, `AlertRules` và `TelegramAlerts`; `server/test_telegram_bot.py`, `MenuButtons`) và đã thử trên bảng mẫu; chưa thử trên máy chủ thật.

### Mã niêm phong của ngày cho quản trị (tự động)

Mỗi ngày tổng chi phí được niêm phong vào nhật ký sau một tuần (xem [OPERATIONS.vi.md](OPERATIONS.vi.md)). Khi bot đã chạy, chat có Telegram liên kết với tài khoản **quản trị** trên bảng nhận một tin ngắn vào buổi sáng đầu tiên sau khi một ngày được niêm phong (từ 07:00 theo múi giờ của bảng): `Nhật ký tới hết ngày <ngày>: mã <16 ký tự>, <n> dòng chi phí`. Không tên, không tiền. Không cần bật gì: liên kết Telegram với tài khoản quản trị (đăng nhập bằng Telegram, ở trên) và ghép một chat. Hãy giữ các tin này: nếu về sau trang Quản trị hiện mã khác cho ngày đó, nhật ký đã bị viết lại.

**Đã thử tới đâu.** Có bài test máy chủ (`server/test_daily_seal.py`); chưa thử trên chat thật.

## Phát hành bản cập nhật

1. Đổi `version` trong `.claude-plugin/plugin.json`.
2. Trên máy giữ khoá ký, nhập mật khẩu khoá khi được hỏi:
   ```bash
   bash packaging/release.sh
   ```
   Tạo gói, manifest và chữ ký trong `server/releases/` (ngoài git).
3. Chép `server/` lên máy chủ và chạy `sudo bash install.sh`.

Máy nhân viên hỏi máy chủ tối đa 4 giờ một lần, thất bại thì 30 phút sau hỏi lại. Có bản mới thì thanh trên ô nhập hiện nút `Cập nhật`; bấm xong, app Claude trên máy tính đưa nút **Mở lại ngay**, còn ở nơi khác thì thoát hẳn app rồi mở lại. Việc phát hành chỉ tới máy đã cài từ bản 0.23.0 trở lên.

**An toàn:** máy nhân viên chỉ cài khi đúng chữ ký và mã kiểm tra, nên máy chủ bị chiếm cũng không phát được gói độc. Máy không kiểm được chữ ký (OpenSSH quá cũ) chỉ được báo có bản mới, không tự cài. Thư mục có `.git` không bao giờ tự cập nhật.

**Lùi bản:** phát hành lại bản cũ với chữ ký mới, hoặc trên máy đó đổi tên thư mục `ai-worker.old` cạnh thư mục plugin về tên cũ.

**Đổi khoá:** thêm khoá mới vào `~/.ai-worker-keys/allowed_signers`, phát hành một bản, rồi ký bằng khoá mới từ bản sau. Khoá chính lộ thì ký ngay bằng khoá dự phòng và bỏ khoá cũ ở bản đó.

## Dữ liệu gửi lên máy chủ

Chỉ gói công ty mới gửi; gói thường không gửi gì. Số liệu lên máy chủ của công ty, không gửi cho bên ngoài.

**Có gửi:** họ tên, email tài khoản Claude và email nhập lúc cài, mã máy ngẫu nhiên, dấu máy (mã phần cứng đã băm một chiều, để nhận ra cùng máy khi cài lại plugin, không hiện trên bảng), IP nội bộ, số phiên mở, đang làm, chờ trả lời, mô hình đang dùng, hạn mức tài khoản Claude, token và chi phí theo giờ, số việc giao cho từng trợ lý, tên loại trợ lý phụ đang chạy, trợ lý có trên máy, phiên bản plugin, và mỗi giờ plugin đã chặn hay hỏi lại bao nhiêu lần (chỉ số đếm, không có nội dung). Máy chủ tự ghi thêm IP công cộng của máy gửi, và nhớ các IP nội bộ mỗi máy đã dùng trong 30 ngày. Máy chủ cộng chi phí, token và số việc thành một con số tổng cho mỗi người mỗi ngày và giữ các tổng đó tối đa 13 tháng.

**Bộ nối cho Codex, Cursor và Gemini CLI gửi:** họ tên và email gõ lúc cài, một mã máy ngẫu nhiên, thời điểm, và với mỗi công cụ là số phiên đang mở, đang làm và đang chờ. Máy chủ tự ghi IP công cộng của máy gửi. Ngoài ra không gửi gì khác. Trên máy, `~/.local/share/ai-worker/connector/` chứa khoá gửi (file chỉ tài khoản đó đọc được), mỗi phiên đang mở một dòng kèm mã phiên của chính công cụ, và báo cáo gần nhất. Mỗi công cụ đưa cho hook sự kiện của nó, trong đó có câu hỏi hoặc câu trả lời; hook đọc mã phiên và việc câu cuối có kết thúc bằng dấu hỏi hay không, và không giữ lại câu hỏi lẫn câu trả lời.

**Không gửi:** nội dung chat, câu hỏi, câu trả lời, tiêu đề chat, tên file, nội dung file, tên thư mục dự án, mô tả việc giao trợ lý.

**Ai xem được:** quản trị và chỉ xem thấy tên, email, IP; màn treo tường chỉ thấy tên rút gọn. Người có sudo trên máy chủ đọc được mọi số liệu. Xem `server/README.md`.

Trên máy, lịch sử phiên và số liệu nằm ở `~/.local/share/ai-worker/`. File có dấu hiệu chứa bí mật (.env, key, token…) chỉ ghi tên, không ghi nội dung.

Tắt gửi trên một máy: thêm `"sharing": { "enabled": false }` vào `~/.local/share/ai-worker/config.js`.

## Ngôn ngữ

Sản phẩm có tiếng Anh và tiếng Việt.

- **Các trang** (trang văn phòng trên máy, bảng tổng, trang quản trị): mỗi trang có nút chuyển EN / VI ở trên cùng, lựa chọn được nhớ trong trình duyệt. Lần đầu, trang theo ngôn ngữ của trình duyệt.
- **Plugin:** file cài ghi trường `language` (`"en"` hoặc `"vi"`) vào `~/.local/share/ai-worker/user.json`, plugin đọc trường này. Có thể sửa tay trường đó. Biến môi trường `AI_WORKER_LANG` (`en` hoặc `vi`) thắng giá trị trong file.
- **File cài:** `AI_WORKER_LANG=en` hoặc `vi` để ép ngôn ngữ; không đặt thì file cài theo ngôn ngữ của máy (trên Mac hỏi macOS, trên Windows lấy ngôn ngữ Windows), không có nữa thì tiếng Anh.
- **Máy chủ:** ngôn ngữ của mỗi trang là lựa chọn của người xem trước; `DEFAULT_LANG` (`en` hoặc `vi`) trong `/etc/ai-worker.env` đặt ngôn ngữ cho người chưa chọn, không đặt thì theo ngôn ngữ trình duyệt, rồi tiếng Anh.

## Tuỳ chỉnh và chi phí

`~/.local/share/ai-worker/config.js` được tạo một lần, không bị ghi đè khi cập nhật: đổi tên hiển thị, `usdRate` (mặc định 26000), và bật tắt từng trợ lý bằng `workers`.

Chi phí là con số Claude Code tính theo bảng giá API. Dùng gói thuê bao thì đây là chi phí quy đổi để so sánh, không phải số tiền bị trừ thật.

Không có Gemini, ChatGPT hay Gemma thì plugin vẫn chạy với mình Claude. File cài hỏi cài trợ lý nào.

Không có máy chủ nhưng có ổ dùng chung: bỏ `webhook`, ghi `folders` là đường dẫn ổ đã gắn. Cách này không có trang quản trị và không tự cập nhật.

## Chống tấn công làm nghẽn (DDoS)

Máy chủ giới hạn phần một máy được dùng: tổng số kết nối và số kết nối mỗi IP, cỡ header, thời gian sống của kết nối, bộ nhớ và số luồng (`MemoryMax`, `TasksMax`, `LimitNOFILE` trong file dịch vụ; bộ nhớ 1 GB, hoặc 45% bộ nhớ của máy khi có bộ nhận Go, `WEBHOOK_MEMORY_MB` để tự đặt). Vì vậy khi bị tấn công, dịch vụ này chậm hoặc dừng, không kéo sập cả máy chủ. Phần mềm trên máy chủ không chặn được đợt tấn công lớn, vì lưu lượng đã làm nghẽn đường mạng trước khi tới nơi.
- **Tốt nhất:** chỉ cho mạng công ty truy cập, như file mẫu `server/aiworker.caddy`.
- **Nếu buộc phải mở ra Internet:** đặt sau dịch vụ bảo vệ như Cloudflare.
- **Dùng nginx thay Caddy:** đặt `proxy_set_header X-Forwarded-For $remote_addr;` và `proxy_set_header X-Forwarded-Proto $scheme;`, nếu không người ngoài có thể giả IP và vượt giới hạn đăng nhập. Webhook tin các header này khi đến từ proxy trên máy; `TRUST_PROXY=0` để tắt.
- **Một giới hạn vẫn còn:** mọi người trong gói cài dùng chung `INGEST_KEY`. Máy đã có khoá riêng thì không ai gửi thay bằng mã này được nữa, nhưng khi `SHARED_KEY_MODE` còn là `allow`, người cầm gói cài vẫn ghi nhận được một máy mới dưới tên giả. Nếu gói bị lộ, đặt `SHARED_KEY_MODE=known-only` (không máy mới nào vào được) và thu hồi ở trang Quản trị những máy không nên có.
