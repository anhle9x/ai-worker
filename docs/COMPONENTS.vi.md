Tiếng Việt | [English](COMPONENTS.md)

# Thành phần và phiên bản

Mọi phần của AI Worker: chạy ở đâu, cần gì, phiên bản nào được ghim. Giấy phép của code bên ngoài xem [THIRD-PARTY.md](../THIRD-PARTY.md).

## 1. Phần do dự án viết

| Phần | Chạy trên | Ngôn ngữ | Phiên bản |
|---|---|---|---|
| Plugin (hook, `/office`, skill) | Máy nhân viên, bên trong Claude Code | TypeScript | `version` trong `.claude-plugin/plugin.json` (hiện 0.27.0) |
| Máy chủ bảng tổng (webhook) | Máy chủ Linux | Python, chỉ thư viện chuẩn; dữ liệu trong SQLite | Theo bản phát hành của plugin |
| Trang văn phòng 3D | Trình duyệt | JavaScript, three.js | Theo bản phát hành của plugin |
| Biểu tượng thanh menu | macOS, Windows, Ubuntu | Python (SwiftBar trên Mac, Ubuntu), app Swift (`macos-app/`), PowerShell và C# (Windows) | Máy chủ dựng cho mỗi lần tải |
| Tiện ích trình duyệt cho quản lý | Chrome | JavaScript | `version` trong `extensions/manager/manifest.json` (hiện 0.1.0) |
| File cài | macOS, Windows, Linux | Bash, PowerShell | Nằm trong gói cài |

## 2. Mỗi máy cần gì

| Máy | Cần | Ai cài |
|---|---|---|
| Máy chủ | Linux có systemd, Python 3.8 trở lên kèm module `sqlite3` có sẵn, Caddy hoặc nginx cho HTTPS | IT cài tay; sau đó chạy `server/install.sh` |
| Máy nhân viên | Claude Code (app máy tính hoặc CLI), một tài khoản Claude | Nhân viên |
| Máy nhân viên, trợ lý phụ tuỳ chọn | Ollama với một model Gemma, Codex CLI (ChatGPT), Antigravity CLI `agy` (Gemini) | File cài hỏi trước khi cài |
| Gói cho lập trình viên | Node 20.19 trở lên, Python, Chrome, ffmpeg | File cài gói lập trình viên (`winget` trên Windows, Homebrew trên Mac) |
| Thanh menu Ubuntu | `python3`, `python3-gi`, `python3-gi-cairo`, GTK 3, AyatanaAppIndicator3 (hoặc AppIndicator3), WebKit2 4.1 (hoặc 4.0) | `apt`, theo phần phụ thuộc của gói `.deb` |
| Thanh menu macOS khi chưa có app dựng sẵn | SwiftBar | `install-mac.command`, từ Homebrew hoặc bản phát hành trên GitHub |
| Thanh menu Windows | WebView2 runtime (có sẵn trong Windows 10 và 11) | Windows |

## 3. Code bên ngoài được ghim phiên bản

| Thành phần | Phiên bản | Nằm ở |
|---|---|---|
| three.js | r186 | `web/three.js`, `server/static/three.js` |
| qrcode-generator | 2.0.4 | `server/static/qrcode.js` |
| Microsoft WebView2 SDK | 1.0.4314.35 | `server/menubar/webview2/` |
| Ranh giới Natural Earth | | `server/static/land.json` |
| `stageshow`, `video-shotcraft` (tải tuỳ chọn) | Ghim theo commit | File cài |

## 4. Công cụ kiểm code

| Công cụ | Phiên bản | Dùng ở |
|---|---|---|
| Claude Code CLI (`plugin test`) | 2.1.319 | GitHub Actions, `code-check` |
| ruff | 0.17.4, quy tắc trong `ruff.toml` | GitHub Actions, `code-check` |
| TypeScript (`tsc`) | chỉ chạy trên máy | Máy lập trình viên |
| Máy chạy GitHub | `ubuntu-latest`, `windows-latest` | `.github/workflows/test-install.yml` |

## 5. Khi nào cập nhật

- **Python trên máy chủ:** theo bản cập nhật hệ điều hành; webhook không dùng gói ngoài nào.
- **Code bên ngoài đã ghim:** mỗi lần phát hành, xem nguồn có bản vá bảo mật không; cập nhật phiên bản ở đây và trong THIRD-PARTY.md cùng lúc.
- **Claude Code CLI trong CI:** nâng phiên bản ghim khi Claude Code mới đổi định dạng plugin.
