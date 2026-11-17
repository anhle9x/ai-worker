Tiếng Việt | [English](README.md)

# Bộ nối cho Codex, Cursor và Gemini CLI

Cho người làm việc trong Codex, Cursor hoặc Gemini CLI hiện lên bảng AI Worker: số phiên đang mở, đang làm và đang chờ, theo từng công cụ. Không cần Claude Code hay plugin AI Worker.

Cách cài và gỡ: [docs/INSTALL.vi.md](../docs/INSTALL.vi.md#codex-cursor-và-gemini-cli-trên-bảng). Trang này dành cho người muốn đọc xem nó làm gì, hoặc muốn viết bộ nối cho một công cụ khác.

## Các file

| File | Việc |
|---|---|
| `ai-worker-hook.sh` | Hook trên macOS và Linux. Cần sh, awk, sed, grep và curl hoặc wget |
| `ai-worker-hook.ps1` | Cùng hook đó trên Windows, viết bằng PowerShell |
| `install.sh`, `install.ps1` | Hỏi cho công cụ nào hiện lên bảng, thêm hook vào cấu hình của từng công cụ, gỡ bằng `--uninstall` |
| `merge-hooks.js` | Thêm hoặc gỡ hook của ta trong một file cấu hình JSON mà không đụng phần còn lại. Chạy bằng `osascript` trên macOS, Node ở nơi khác; `install.ps1` tự làm việc này bằng PowerShell |

Test: `python3 tests/connectors/test_connectors.py`.

## Đã thử tới đâu

| | Tình trạng |
|---|---|
| Hook và bộ cài bản sh | Đã qua các bài test với sự kiện mẫu và thư mục nhà tạm, trên macOS và Ubuntu (máy thử của GitHub) |
| Codex CLI | Trong một phiên Codex CLI 0.164.0 thật trên macOS, các hook mở phiên, gửi câu hỏi, hết lượt, bị ngắt và đóng phiên đã chạy, và một câu hỏi của Codex đã hiện trên bảng mẫu là đang chờ. Hook xin duyệt và hook sau từng bước chưa thấy chạy trong phiên thật |
| Cursor, Gemini CLI | Viết theo tài liệu của hai công cụ; chưa thử bên trong công cụ thật |
| Windows (`.ps1`) | Đã qua cùng các bài test trên Windows (máy thử của GitHub, Windows PowerShell); chưa thử trong công cụ thật trên Windows |

Nếu bạn thử một dòng chưa được thử, hãy mở một issue ghi lại điều bạn thấy, dù chạy được hay không.

## Sự kiện của từng công cụ có nghĩa gì ở đây

Công cụ chạy `ai-worker-hook.sh <tool> <event>` và đưa sự kiện dạng JSON qua đầu vào chuẩn.

| Của ta | Codex | Gemini CLI | Cursor | Phiên trở thành |
|---|---|---|---|---|
| `start` | `SessionStart` | `SessionStart` | `sessionStart` | rảnh, nếu là phiên mới |
| `prompt` | `UserPromptSubmit` | `BeforeAgent` | `beforeSubmitPrompt` | đang làm |
| `ask` | `PermissionRequest` | `Notification` | không có | đang chờ: công cụ xin duyệt |
| `tool` | `PostToolUse` | `AfterTool` | không có | đang làm trở lại, nếu trước đó đang chờ duyệt |
| `reply` | không có | không có | `afterAgentResponse` | không đổi; ghi nhận câu trả lời có kết thúc bằng dấu hỏi hay không |
| `stop` | `Stop`, `Interrupt` | `AfterAgent` | `stop` | đang chờ nếu câu cuối kết thúc bằng dấu hỏi, không thì rảnh |
| `end` | `SessionEnd` | `SessionEnd` | `sessionEnd` | bị bỏ khỏi danh sách |

Từ sự kiện, hook đọc mã phiên (`session_id`, hoặc `conversation_id` trong Cursor) và, với `reply` và `stop`, việc câu cuối (`last_assistant_message`, `prompt_response`, `text`) có kết thúc bằng dấu hỏi hay không. Nó trả lời công cụ trước khi làm bất cứ việc gì khác: không in gì cho Codex, `{}` cho Gemini CLI và Cursor, `{"continue":true}` cho `beforeSubmitPrompt` của Cursor. Nó không bao giờ chặn hay thay đổi việc công cụ đang làm. Codex không gửi `Stop` khi người dùng bấm Esc cắt ngang một lượt (đã thấy trong phiên thật), nên `Interrupt` cũng được gắn hook.

## Các file trên máy

Tất cả nằm trong `~/.local/share/ai-worker/connector/`:

| File | Chứa |
|---|---|
| `config` | `url`, `key` (khoá gửi), `name`, `account`; chỉ tài khoản đó đọc được |
| `device` | Mã ngẫu nhiên `device-...` của bộ nối này |
| `sessions` | Mỗi phiên đang mở một dòng: công cụ, mã phiên, trạng thái, thời điểm sự kiện cuối, một dấu |
| `sent`, `last-error` | Lần gần nhất bảng nhận một báo cáo, hoặc lần gần nhất bảng từ chối ra sao |
| `report.json` | Báo cáo đã gửi gần nhất |
| `skills-installed` | Các skill bộ cài đã chép vào `~/.agents/skills/`, mỗi skill kèm một dấu của nội dung lấy lúc chép. Skill nào nội dung không còn khớp dấu thì đã được người dùng sửa, và sẽ không bị thay hay bị gỡ |
| `ai-worker-hook.sh`, `install.sh`, `merge-hooks.js`, `lang.sh` | Các file của chính bộ nối (`.ps1` trên Windows), để hook vẫn chạy và `--uninstall` vẫn dùng được sau khi gói cài đã bị xoá |

## Báo cáo

Một lệnh `POST <bảng>/ingest` kèm `Authorization: Bearer <khoá gửi>` và phần thân JSON dưới đây, gửi khi các số đếm thay đổi, và nhiều nhất 5 phút một lần khi chúng không đổi:

```json
{
  "v": 1,
  "device": "device-k3v9x1q7m2p8c4zt",
  "name": "An",
  "account": "an@example.com",
  "updatedAt": 1794816190000,
  "openSessions": 2,
  "working": 1,
  "waiting": 1,
  "tools": {
    "codex": { "openSessions": 1, "working": 0, "waiting": 1 },
    "cursor": { "openSessions": 1, "working": 1, "waiting": 0 }
  }
}
```

| Trường | Quy tắc |
|---|---|
| `v` | Luôn là `1` |
| `device` | `device-` rồi 1 tới 40 ký tự `a-z0-9`. Máy chủ gắn mã này với `name` và `account` của lần gửi đầu tiên; sau đó gửi tên khác sẽ bị từ chối với mã 409 |
| `name`, `account` | Như bảng sẽ hiện người đó. Dùng đúng cặp mà plugin AI Worker dùng trên máy, nếu không một người sẽ hiện thành hai dòng |
| `updatedAt` | Thời điểm của báo cáo, tính bằng mili giây |
| `tools` | Bảng đánh dấu đây là báo cáo của bộ nối. Các khoá máy chủ biết: `codex`, `cursor`, `gemini`; khoá khác bị bỏ. `{}` nghĩa là không có phiên nào đang mở |
| `openSessions`, `working`, `waiting` | Các tổng, dành cho máy chủ cũ hơn tính năng này. Máy chủ hiện tại tự cộng từ `tools` |

Máy chủ tính một báo cáo trong 2 giờ kể từ `updatedAt`, riêng `working` trong 30 phút: lượt bị lỗi không gửi sự kiện nào, nên hãy gửi lại trong lúc việc còn chạy. Trả lời: 200 đã nhận; 400 không phải một báo cáo; 401 sai khoá; 409 mã máy thuộc về một tên khác; 413 quá lớn; 429 gửi quá nhiều hoặc quá nhiều máy mới từ địa chỉ này; 507 đã chạm giới hạn số máy.

## Bộ nối cho một công cụ khác

Máy chủ nhận tên công cụ theo một danh sách cố định, `CONNECTOR_TOOLS` trong `server/board/settings.py`, nên thêm một công cụ mới là sửa ba chỗ: danh sách đó, các tên trong `TOOL_NAMES` (`server/board/pages.py` và `server/static/ops.js`), và bảng sự kiện trong `install.sh` và `install.ps1`. Hãy giữ quy tắc làm cho việc cài đặt này an toàn: chỉ gửi các số đếm, không bao giờ gửi câu hỏi, câu trả lời, tên file, thư mục hay tên dự án.
