Tiếng Việt | [English](SKILLS.md)

# Skill và quy tắc

**Gói chung, có sẵn trong plugin:** `meeting-notes`, `lesson-generator`, `handoff`, và quy tắc hướng dẫn, bảo mật (chỉ bật ở gói công ty).

**Gói kỹ thuật `ai-worker-dev`, cho lập trình viên và phòng IT, cài riêng:**
```bash
bash packaging/build-dev-pack.sh
```
Được `dist/AI-Worker-Dev-<phiên bản>.zip`. Giải nén, bấm đúp `INSTALL-Dev-Mac.command` hoặc `INSTALL-Dev-Windows.bat`. Gói gồm các skill kiểm thử, viết mã, bảo mật, giao diện, `write-spec` để viết đặc tả, `draw-flow` để vẽ sơ đồ Mermaid, trợ lý `planner` và quy tắc `chia phiên`.

File cài tự cài Node từ 20.19, đăng ký Playwright và Chrome DevTools, và hỏi có tải thêm `stageshow`, `video-shotcraft` không. Windows dùng `winget` để cài thêm Python, Chrome, ffmpeg khi thiếu. Mac cần Homebrew ghi được mới tự cài được ba thứ đó; không thì file cài báo còn thiếu gì ở cuối.

`video-shotcraft` dùng Remotion có giấy phép riêng và một số âm thanh chưa rõ nguồn: kiểm tra trước khi làm video cho công ty.

Nguồn và giấy phép skill: `skills/SOURCES.md`, `dev-pack/skills/SOURCES.md`.

## Toàn bộ skill

| Skill | Gói | Làm gì | Tác giả | Giấy phép |
|---|---|---|---|---|
| `meeting-notes` | Plugin | Biến ghi chép họp thành biên bản: quyết định, việc cần làm có người phụ trách và hạn | Muse (alapha888/agent-skills-en) | MIT |
| `lesson-generator` | Plugin | Tạo khoá học ngắn nhiều bài, có thẻ ghi nhớ và câu hỏi | Elvis Saravia, DAIR.AI | MIT |
| `handoff` | Plugin | Viết ghi chú bàn giao để phiên sau làm tiếp | Dự án này | MIT |
| `qa-test` | Gói kỹ thuật | Thử một luồng của trang web và viết báo cáo lỗi | Dự án này | MIT |
| `qa-site` | Gói kỹ thuật | Thử cả dự án web, từng luồng một, gộp thành một báo cáo | Dự án này | MIT |
| `write-spec` | Gói kỹ thuật | Viết đặc tả: mục tiêu, phạm vi, vai, yêu cầu có mã | Dự án này | MIT |
| `draw-flow` | Gói kỹ thuật | Vẽ cách hệ thống thật sự chạy bằng sơ đồ Mermaid đã kiểm | Dự án này | MIT |
| `browser-testing-with-devtools` | Gói kỹ thuật | Thử trang qua Chrome DevTools: DOM, console, mạng | Addy Osmani | MIT |
| `interview-me` | Gói kỹ thuật | Hỏi từng câu một tới khi rõ nhu cầu thật | Addy Osmani | MIT |
| `ui-ux-pro-max` | Gói kỹ thuật | Hướng dẫn giao diện và trải nghiệm, có kho kiểu và bảng màu | Next Level Builder | MIT |
| `tdd` | Gói kỹ thuật | Phát triển theo test, đỏ - xanh - chỉnh | Matt Pocock | MIT |
| `diagnosing-bugs` | Gói kỹ thuật | Vòng tìm nguyên nhân cho lỗi khó và chạy chậm | Matt Pocock | MIT |
| `codebase-design` | Gói kỹ thuật | Bộ từ chung để thiết kế mô-đun sâu | Matt Pocock | MIT |
| `domain-modeling` | Gói kỹ thuật | Dựng bảng thuật ngữ và ghi chép quyết định của dự án | Matt Pocock | MIT |
| `improve-codebase-architecture` | Gói kỹ thuật | Tìm chỗ mã có thể làm sâu hơn và báo cáo | Matt Pocock | MIT |
| `grilling` | Gói kỹ thuật | Hỏi vặn kế hoạch hay ý tưởng bằng câu hỏi khó | Matt Pocock | MIT |
| `security-audit` | Gói kỹ thuật | Rà soát bảo mật mã, API và dịch vụ | Cloudflare, Inc. | MIT |

`stageshow` và `video-shotcraft` không nằm trong repo này; file cài gói kỹ thuật hỏi có tải về không.
