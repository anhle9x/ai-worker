Tiếng Việt | [English](README.md)

# Văn phòng AI Worker

Triển khai Claude cho cả văn phòng, kể cả người không viết code, và nhìn là biết ai đang chờ trả lời.

<p>
  <a href="LICENSE"><img alt="Giấy phép MIT" src="https://img.shields.io/badge/license-MIT-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28"></a>
  <a href="https://github.com/anhle9x/ai-worker/actions/workflows/test-install.yml"><img alt="Kiểm thử" src="https://img.shields.io/github/actions/workflow/status/anhle9x/ai-worker/test-install.yml?style=for-the-badge&amp;labelColor=000000&amp;label=tests" height="28"></a>
  <img alt="Plugin Claude Code" src="https://img.shields.io/badge/Claude%20Code-plugin-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28">
  <img alt="Máy chủ: thư viện chuẩn Python và SQLite" src="https://img.shields.io/badge/server-Python%20%2B%20SQLite-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28">
</p>

AI Worker dành cho người phải triển khai Claude cho cả văn phòng rồi trả lời hai câu hỏi: mọi người có dùng không, và ai đang kẹt? Nó gồm một plugin Claude Code trên máy từng nhân viên và một máy chủ nhỏ trên một máy Linux do bạn tự chạy. Nhân viên bấm đúp vào bộ cài, gõ họ tên là xong. Quản lý có một bảng cập nhật theo thời gian thực, cho thấy ai đang làm, ai đang chờ trả lời và đã chờ bao lâu, cho cả Claude lẫn các trợ lý phụ (Gemini, ChatGPT, Gemma). Một bộ nối nhỏ đưa người làm việc trong Codex, Cursor hoặc Gemini CLI lên cùng bảng, dù máy có Claude Code hay không. Không cần gói Team hay Enterprise, không cần phần mềm quản lý thiết bị. Máy nhân viên gửi lên máy chủ tên người dùng, tài khoản Claude, vài thông tin về máy và các con số (số phiên, token, chi phí, hạn mức); không bao giờ gửi nội dung chat, prompt, tên file hay tên dự án.

<!-- one row that scrolls sideways, one picture to a view. GitHub shrinks pictures in a table to fit the page; the line of em spaces under each caption cannot wrap (nowrap), so it holds the cell at the width of the page -->
<table>
  <tr>
    <td nowrap align="center" valign="top"><img src="assets/dashboard.vi.png" alt="Bảng điều hành 3D với dữ liệu mẫu" height="377"><br><sub><b>Bảng điều hành (dữ liệu mẫu).</b> Ai đang làm, ai chờ trả lời, chi phí và hạn mức, cập nhật trực tiếp.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/map-2d.jpg" alt="Bản đồ phẳng với bốn văn phòng" width="808"><br><sub><b>Bản đồ phẳng.</b> Mỗi văn phòng hiện số người đang làm, chi phí hôm nay và trợ lý đang dùng.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/map-25d.jpg" alt="Bản đồ nghiêng, mỗi văn phòng có một cột" width="808"><br><sub><b>Bản đồ 2.5D.</b> Cột trên mỗi văn phòng thể hiện chi phí, số người hoặc hạn mức, tuỳ bạn chọn.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/globe.jpg" alt="Quả địa cầu có đánh dấu các văn phòng" width="808"><br><sub><b>Quả địa cầu.</b> Vẫn các văn phòng đó trên quả địa cầu 3D: kéo để xoay, cuộn để phóng to, thu nhỏ.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/wall.jpg" alt="Màn hình treo tường với sơ đồ và ba vòng hạn mức" width="808"><br><sub><b>Màn hình treo tường.</b> Dành cho TV: toàn màn hình, có vòng hạn mức, ghép bằng mã do quản trị duyệt.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/board.jpg" alt="Bảng mỗi người một dòng" width="808"><br><sub><b>Bảng chi tiết.</b> Mỗi người một dòng: trạng thái, mô hình, hạn mức, chi phí, token, bản plugin.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/admin.jpg" alt="Trang quản trị với tài khoản, màn hình TV và các bản tải về" width="808"><br><sub><b>Trang quản trị.</b> Tài khoản và vai trò, ghép màn hình TV, tải biểu tượng thanh menu và tiện ích.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/login.png" alt="Trang đăng nhập: tên tài khoản và mã 6 số, hoặc Log in with Telegram" height="377"><br><sub><b>Đăng nhập.</b> Tên tài khoản và mã 6 số, hoặc Log in with Telegram.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/phone.jpg" alt="Bảng trên màn hình hẹp, các ô xếp chồng lên nhau" height="377"><br><sub><b>Màn hình hẹp.</b> Trên điện thoại các ô xếp chồng lên nhau, từ trên xuống dưới.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
  </tr>
</table>

## Điểm khác biệt

- **Thấy ngay ai đang kẹt.** Bảng cho thấy ai đang làm, ai đang chờ trả lời và chờ bao lâu, theo từng văn phòng trên bản đồ. Cũng xem được trên màn hình treo tường, hoặc qua số người đang chờ hiện trên biểu tượng thanh menu (macOS, Windows, Ubuntu) và tiện ích Chrome, Edge. Tua lại 24 giờ qua để xem cả ngày diễn ra thế nào.
- **Cả văn phòng dùng được, không riêng lập trình viên.** Một gói cho cả công ty: nhân viên bấm đúp vào bộ cài trên macOS, Windows hoặc Linux, skill và quy tắc dùng chung được đưa tới mọi máy, bản cập nhật có chữ ký số. Hướng dẫn viết dễ hiểu, có tiếng Việt và tiếng Anh.
- **Tự host: số liệu của bảng nằm trên máy chủ của bạn.** Máy chủ chạy trên máy Linux của chính bạn, chỉ cần thư viện chuẩn Python và SQLite. Máy nhân viên gửi thông tin ai đang dùng và các con số, không gửi nội dung công việc; từng trường dữ liệu ghi trong [docs/DATA-MODEL.vi.md](docs/DATA-MODEL.vi.md).

## Tính năng khác

- **Codex, Cursor và Gemini CLI trên cùng bảng:** một bộ nối, do chính người dùng cài cho từng công cụ, cho thấy số phiên đang mở, đang làm và đang chờ của mỗi công cụ. Không cần Claude Code, Python hay Node, và chỉ gửi các con số đếm. Tính năng mới: đã thử trong Codex CLI thật trên macOS; trên Linux và Windows, và với Cursor và Gemini CLI, mới chỉ kiểm bằng sự kiện mẫu, chưa thử trong công cụ thật. Xem [hướng dẫn cài đặt](docs/INSTALL.vi.md#codex-cursor-và-gemini-cli-trên-bảng).
- **Chi phí và hạn mức:** chi phí hôm nay và 7 ngày, hạn mức còn lại, theo từng người và từng văn phòng.
- **Hỏi Claude về team:** quản lý ghép Claude của mình với bảng một lần, rồi cứ hỏi tự nhiên, ví dụ "ai đang chờ lâu nhất?". Hỏi bằng tiếng Việt cũng được, gõ hoặc nói đều được; Claude trả lời từ số liệu của bảng.
- **Hỏi từ công cụ AI khác, hoặc từ Telegram:** máy chủ có một cổng MCP chỉ đọc, nên công cụ AI nào hỗ trợ MCP cũng trả lời được các câu hỏi đó bằng một khoá do quản trị viên duyệt. Quản lý không viết code thì bấm nút trong một chat Telegram, hoặc mở khung thanh menu ngay trong Telegram từ menu của bot: tuỳ chọn, mặc định tắt, và không mô hình AI nào đọc câu hỏi. Cách bật từng thứ có trong [hướng dẫn cài đặt](docs/INSTALL.vi.md).
- **Bảng ngay trong Telegram, trên điện thoại:** quản lý có chat Telegram được quản trị cho phép thì mở khung thanh menu ngay trong Telegram, từ nút **AI Worker** của bot: người đang chờ, biểu đồ chi phí 7 ngày, hạn mức và chi phí. Bot còn tự nhắn khi có người chờ quá lâu (`/baocho 10`), kèm nút mở khung. Cả hai đều tuỳ chọn và mặc định tắt; khung mở được ở mạng văn phòng. Xem [khung bên trong Telegram](docs/INSTALL.vi.md#khung-của-bảng-bên-trong-telegram-tuỳ-chọn) và [tin báo khi có người chờ quá lâu](docs/INSTALL.vi.md#tin-báo-khi-có-người-chờ-quá-lâu-tuỳ-chọn-theo-từng-chat).
- **Mức dùng theo tuần và tháng:** bảng chi tiết so tuần này, tháng này với tuần trước, tháng trước, cho cả đội, từng văn phòng và từng người.
- **Biến quy trình thành skill:** đưa cho `/ai-worker:make-skill` một SOP hoặc mô tả cách làm một việc. Nó viết bản nháp skill, dừng lại khi thấy mật khẩu hay khoá, bỏ dữ liệu cá nhân, và chỉ bật skill sau khi bạn đồng ý.
- **Hỏi lại trước khi xoá hay gửi ra ngoài:** lệnh xoá cả thư mục, `git reset --hard`, `git push --force`, `git clean`, chạy ngay một script vừa tải về (`curl … | sh`), tắt Gatekeeper của macOS, ghi thẳng ra ổ đĩa hay `chmod 777` phải được bạn xác nhận; gửi nội dung sang AI của hãng khác cũng vậy, trừ khi bạn đã tự cho phép. Chữ có thứ trông như khoá, token hay mật khẩu thì hoàn toàn không được gửi sang AI đó, và commit sẽ đưa thứ đó vào git thì được đưa bạn xem trước. Trang web tìm cách ra lệnh cho Claude thì bị đánh dấu, cho cả Claude lẫn bạn.
- **Phân quyền và nhật ký:** quản trị viên, quản lý và màn hình treo tường được xem những phần dữ liệu khác nhau; đăng nhập bằng mã OTP 6 số hoặc bằng Telegram (Telegram cần cài thêm bot, xem [hướng dẫn cài đặt](docs/INSTALL.vi.md)); nhật ký mọi thay đổi được lưu 12 tháng.

## Có hợp với bạn không?

- **Bạn chỉ muốn biết chi phí token trên máy mình:** một công cụ đếm chạy trên máy là đủ và gọn hơn, không cần máy chủ.
- **Tổ chức của bạn dùng gói Team hoặc Enterprise và có quản lý thiết bị:** [bảng thống kê](https://code.claude.com/docs/en/analytics) và [phần quản lý plugin](https://code.claude.com/docs/en/plugins/org) của chính Anthropic đã có báo cáo sử dụng và cách đưa plugin tới mọi máy. AI Worker thêm bảng theo thời gian thực cho thấy ai đang chờ, và chạy được mà không cần hai thứ đó.
- **Văn phòng nhỏ hoặc vừa, nhiều người không viết code, không có quản lý thiết bị:** đây là trường hợp AI Worker hợp nhất.

## Cách hoạt động

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.vi.svg">
  <img alt="Máy nhân viên gửi số liệu lên máy chủ bảng tổng (tên người dùng, tài khoản Claude, vài thông tin về máy, và số phiên, token, chi phí, việc giao; không bao giờ gửi chat, câu hỏi hay tên file) và nhận lại bản cập nhật có chữ ký. Máy chủ đứng sau Caddy có HTTPS và danh sách IP văn phòng, lưu dữ liệu trong SQLite, phục vụ bảng trên trình duyệt, màn hình TV, biểu tượng thanh menu, tiện ích trình duyệt, công cụ AI qua một cổng MCP chỉ đọc, và một bot Telegram tuỳ chọn trả lời trong chat và tự nhắn khi có người chờ quá lâu; điện thoại mở khung thanh menu ngay trong Telegram qua HTTPS. Trên máy, plugin hỏi trước lệnh rủi ro và commit có bí mật, báo trang tìm cách lái Claude, và không bao giờ gửi sang ChatGPT hay Gemini chữ có khoá, token hay mật khẩu. Máy chủ giữ nhật ký có các dòng nối với nhau, và trang Quản trị đếm số lần chặn, chỉ ra khoá MCP bỏ quên." src="assets/architecture-light.vi.svg" width="860">
</picture>

Khung bên trong Telegram tới máy chủ bằng đường riêng `/tg/`; xem [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md#khung-bảng-bên-trong-telegram-tuỳ-chọn). Những gì plugin chặn trên máy có trong [SECURITY.vi.md](SECURITY.vi.md#những-gì-plugin-chặn-trên-máy).

Không có máy chủ thì plugin vẫn chạy trên từng máy với trang văn phòng riêng, nhưng không có bảng cả công ty và không tự cập nhật. Thiết kế xem [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).

## Cài nhanh

**Chỉ muốn xem thử?** Chạy bảng ngay trên máy bạn với dữ liệu giả lập. Chỉ cần Git và Python 3.8 trở lên.

macOS và Linux:

```bash
git clone https://github.com/anhle9x/ai-worker.git
cd ai-worker
python3 server/demo.py
```

Windows, trong PowerShell hoặc Command Prompt. Nếu máy chưa có Git hoặc Python thì cài trước, rồi mở một cửa sổ mới để máy nhận lệnh vừa cài:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Python.Python.3.12 -e --source winget
```

```powershell
git clone https://github.com/anhle9x/ai-worker.git
cd ai-worker
py server\demo.py
```

Lệnh in ra một địa chỉ, tên tài khoản `demo` và một mã 6 số. Mở địa chỉ đó rồi nhập cả hai: bảng hiện lên với 12 nhân viên giả lập ở 4 văn phòng. Không cài gì và không có gì rời khỏi máy bạn; bấm Ctrl+C để dừng và xoá dữ liệu mẫu. Đã thử trên macOS, Linux và Windows.

**Người quản trị, một lần** (khoảng 30 phút). Các bước và lệnh: [docs/INSTALL.vi.md](docs/INSTALL.vi.md).

1. Chép `server/` lên một máy chủ Linux và chạy `sudo bash install.sh`. Script in ra mã gửi và tạo quản trị đầu tiên.
2. Đặt Caddy phía trước để có HTTPS và danh sách IP văn phòng (mẫu: `server/aiworker.caddy`).
3. Tạo khoá ký bản cập nhật, điền `packaging/company.json`, chạy `bash packaging/build.sh packaging/company.json`.

**Mỗi nhân viên:** giải nén gói, bấm đúp `INSTALL-Mac.command`, `INSTALL-Windows.bat` hoặc chạy `INSTALL-Linux.sh`, gõ họ tên đầy đủ. Trong Claude Code, gõ `/office` để xem các phiên của mình.

**Quản lý:** mở địa chỉ máy chủ, đăng nhập bằng mã 6 số trong Google Authenticator, hoặc bấm **Log in with Telegram** sau khi đã liên kết Telegram (nếu máy chủ đã cài bot Telegram). Muốn có báo thì cài biểu tượng thanh menu ở trang **Quản trị**.


Cách dùng từng màn hình: [docs/USER-GUIDE.vi.md](docs/USER-GUIDE.vi.md).

## Chạy trên đâu

| Phần | Chạy trên | Cần |
|---|---|---|
| Plugin | macOS, Windows, Linux | Claude Code: thẻ Code của app máy tính, CLI, hoặc phần mở rộng VS Code |
| Máy chủ bảng tổng | Linux có systemd | Python 3.8 trở lên, Caddy hoặc nginx; không thư viện nào khác |
| Bộ nối cho Codex, Cursor, Gemini CLI | macOS, Linux, Windows | Chính công cụ đó, và curl hoặc wget; không cần Claude Code |
| Biểu tượng thanh menu | macOS, Windows 10/11, Ubuntu (X11 và Wayland) | Tải ở trang Quản trị của máy chủ |
| Bot Telegram, tin báo và khung của nó (tuỳ chọn) | Telegram trên điện thoại hoặc máy tính | Một bot tạo bằng @BotFather; `TELEGRAM_ASK=1` trên máy chủ, thêm `TELEGRAM_APP=1` cho khung, khung mở được ở các mạng mà máy chủ cho vào. Khung đã thử trên Android và Telegram Desktop, chưa thử trên iPhone |
| Tiện ích trình duyệt | Chrome, Edge | Tải ở trang Quản trị, ghép bằng mã |

### Những gì không được đếm

Bảng cho thấy Claude Code trên các máy đã cài plugin, và Codex, Cursor, Gemini CLI trên các máy đã cài bộ nối (chỉ có số phiên: không có token, chi phí hay hạn mức). Bảng không cho thấy:

- **claude.ai trên trình duyệt, và thẻ Chat của app Claude.** Hai nơi này không có plugin.
- **Phiên Claude Code chạy trên đám mây** (claude.ai/code). Phiên chạy trên máy chủ của Anthropic, không phải máy nhân viên, nên plugin cài trên máy không được nạp. Chưa thử thật: hãy coi như không đếm.
- **Máy chưa cài plugin hoặc bộ nối,** hoặc máy không tới được máy chủ.

Vì vậy người chỉ chat trên claude.ai sẽ hiện là không dùng Claude, dù phần dùng đó vẫn có thể tính vào hạn mức của cùng tài khoản. Hãy đọc bảng là "ai dùng Claude Code, và dùng bao nhiêu", không phải "ai dùng Claude nhiều nhất".

## Lộ trình

Hướng đi của dự án. Không ghi ngày: mục nào kiểm xong thì phát hành mục đó.

- [x] Bảng theo thời gian thực cho thấy ai đang làm, ai đang chờ trong Claude Code, kèm màn hình treo tường, biểu tượng thanh menu và tiện ích trình duyệt
- [x] Plugin chạy trong phần mở rộng Claude Code của VS Code
- [x] Codex, Cursor và Gemini CLI lên cùng một bảng (0.32.0): mới có số phiên
- [x] Hỏi bảng từ mọi công cụ AI hỗ trợ MCP: một cổng chỉ đọc trên máy chủ, khoá do quản trị viên duyệt. Đã thử trong Claude Code và Codex CLI.
- [x] Hỏi bảng từ một chat Telegram, cho quản lý không viết code: nút bấm và câu hỏi ngắn, không dùng mô hình AI, mặc định tắt
- [x] Mức dùng theo tuần và tháng: máy chủ lưu mỗi người mỗi ngày một tổng, bảng chi tiết so tuần này, tháng này với kỳ trước
- [ ] Thử bộ nối Cursor, Gemini CLI và bản Windows trong công cụ thật. Hiện mới thử Codex trên macOS.
- [ ] Thử cổng MCP từ Cursor và Gemini CLI. Hiện đã thử Claude Code, Codex CLI và thẻ Chat của app Claude (qua một kết nối của claude.ai).
- [x] Biểu đồ mức dùng theo tuần và tháng trên bảng chi tiết: chi phí theo tuần trong 12 tuần và theo tháng trong tối đa 13 tháng, cho cả đội và từng văn phòng
- [x] Khung thanh menu ngay trong Telegram (0.37.0), cho các chat quản trị cho phép: đã thử trên Telegram Desktop và Android, ở mạng văn phòng
- [ ] Khung trong Telegram cho chat chỉ đọc số gộp, và mở được từ ngoài mạng văn phòng
- [x] Tin nhắn Telegram khi có người chờ quá lâu, do từng chat tự bật (`/baocho`), kèm nút mở khung

## Tài liệu

| | |
|---|---|
| [Hướng dẫn sử dụng](docs/USER-GUIDE.vi.md) | Nhân viên, quản lý, quản trị |
| [Cài đặt và cấu hình](docs/INSTALL.vi.md) | Triển khai lần đầu, cập nhật, tuỳ chỉnh, dữ liệu gửi đi |
| [Vận hành](docs/OPERATIONS.vi.md) | Kiểm tra hằng ngày, sự cố, sao lưu, quay về bản cũ, nhật ký |
| [Kiến trúc](docs/ARCHITECTURE.vi.md), [dữ liệu](docs/DATA-MODEL.vi.md), [phân quyền](docs/PERMISSIONS.vi.md) | Cách hệ thống được làm |
| [Skill và quy tắc](docs/SKILLS.vi.md) | Mỗi máy nhận được gì |
| [Kế hoạch kiểm thử](docs/TEST-PLAN.vi.md) | Kiểm tự động gì, kiểm tay gì |
| [Toàn bộ tài liệu](docs/README.vi.md) | Xếp theo mục đích |

## Bảo mật

Được thiết kế để chống các rủi ro web phổ biến (CSRF, XSS, nhúng mã, đăng nhập yếu, kiểm soát truy cập, lộ dữ liệu), đã rà bằng trợ lý AI, chưa được công ty bảo mật độc lập kiểm định. Bảng những gì được bảo vệ, những gì còn lại, và cách báo lỗi riêng: [SECURITY.vi.md](SECURITY.vi.md).

## Đóng góp và ủng hộ

[CONTRIBUTING.vi.md](CONTRIBUTING.vi.md) · [Quy tắc ứng xử](CODE_OF_CONDUCT.vi.md) · [Các thay đổi](CHANGELOG.md) · [Liên hệ và ủng hộ](SUPPORT.vi.md)

## Giấy phép và trách nhiệm của bạn

AI Worker dùng [giấy phép MIT](LICENSE). Các phần của bên thứ ba giữ giấy phép riêng: xem [THIRD-PARTY.md](THIRD-PARTY.md). Tên và nhãn hiệu: xem [NOTICE](NOTICE).

**Trách nhiệm của bạn khi triển khai.** AI Worker không kèm bảo hành. Bạn tự chạy máy chủ và tự quyết định thu thập gì, nên bạn chịu trách nhiệm về:
- **Báo trước cho nhân viên.** Plugin gửi tên, email tài khoản, địa chỉ IP và số liệu sử dụng về máy chủ của bạn. Hãy bắt đầu từ [mẫu thông báo nhân viên](docs/employee-notice.vi.md) và nhờ bộ phận pháp lý hoặc nhân sự xem lại, vì quy định mỗi nước mỗi khác.
- **Bảo vệ máy chủ.** Dùng HTTPS và giới hạn mạng, giữ ít tài khoản quản trị, sao lưu dữ liệu.
- **Khoá của riêng bạn.** `keys/allowed_signers` để trống, nên cập nhật tự động chưa chạy cho tới khi bạn ghi khoá công khai của mình vào `~/.ai-worker-keys/allowed_signers` rồi đóng gói. Không bao giờ commit khoá riêng.
- **Điều khoản của Claude, Gemini và ChatGPT.** Kiểm tra gói đang dùng có cho phép cách bạn dùng không, và nhân viên được gửi dữ liệu gì cho các dịch vụ đó.

**Công khai bản của bạn:** `packaging/check-clean.sh` chặn khoá riêng, token và các từ riêng của bạn (danh sách để ngoài repo) lọt ra ngoài; `--install-hooks` cho công cụ này chạy trước mỗi lần commit và đẩy. Không có danh sách đó thì công cụ từ chối chạy, trừ khi bạn đặt `AI_WORKER_NO_DENY=1`. `packaging/export-public.sh` xuất một bản sạch không kèm lịch sử.
