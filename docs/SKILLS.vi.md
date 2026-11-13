Tiếng Việt | [English](SKILLS.md)

# Skill và quy tắc

**Mọi skill đều đi kèm plugin.** Ba skill cho việc hằng ngày: `meeting-notes`, `lesson-generator`, `handoff`. Các skill còn lại dành cho người viết code hoặc vận hành hệ thống: kiểm thử, viết mã, bảo mật, giao diện, `write-spec` để viết đặc tả, `draw-flow` để vẽ sơ đồ Mermaid. Plugin cũng mang theo trợ lý `planner`, quy tắc cho việc kỹ thuật, và quy tắc hướng dẫn, bảo mật (chỉ bật ở gói công ty). Gõ `/ai-worker:help` trong một phiên để xem danh sách trên máy bạn.

**Công cụ mà một số skill đó cần là một bước riêng, cho người viết code.** Trong gói đã giải nén, mở thư mục `setup` rồi bấm đúp `INSTALL-DevTools-Mac.command` hoặc `INSTALL-DevTools-Windows.bat`, sau khi đã cài plugin. File này cài Node từ 20.19, đăng ký Playwright và Chrome DevTools, và hỏi có tải thêm `stageshow`, `video-shotcraft` không. Windows dùng `winget` để cài thêm Python, Chrome, ffmpeg khi thiếu. Mac cần Homebrew ghi được mới tự cài được ba thứ đó; không thì file cài báo còn thiếu gì ở cuối. Không chạy bước này thì skill vẫn có; riêng `qa-test`, `qa-site` và `browser-testing-with-devtools` không điều khiển được trình duyệt.

`video-shotcraft` dùng Remotion có giấy phép riêng và một số âm thanh chưa rõ nguồn: kiểm tra trước khi làm video cho công ty.

Nguồn và giấy phép skill: `skills/SOURCES.md`. Skill do người khác viết được giữ nguyên như tác giả viết.

## Toàn bộ skill

| Skill | Cho ai | Làm gì | Tác giả | Giấy phép |
|---|---|---|---|---|
| `meeting-notes` | Mọi người | Biến ghi chép họp thành biên bản: quyết định, việc cần làm có người phụ trách và hạn | Muse (alapha888/agent-skills-en) | MIT |
| `lesson-generator` | Mọi người | Tạo khoá học ngắn nhiều bài, có thẻ ghi nhớ và câu hỏi | Elvis Saravia, DAIR.AI | MIT |
| `handoff` | Mọi người | Viết ghi chú bàn giao để phiên sau làm tiếp | Dự án này | MIT |
| `qa-test` | Viết code, vận hành | Thử một luồng của trang web và viết báo cáo lỗi | Dự án này | MIT |
| `qa-site` | Viết code, vận hành | Thử cả dự án web, từng luồng một, gộp thành một báo cáo | Dự án này | MIT |
| `write-spec` | Viết code, vận hành | Viết đặc tả: mục tiêu, phạm vi, vai, yêu cầu có mã | Dự án này | MIT |
| `draw-flow` | Viết code, vận hành | Vẽ cách hệ thống thật sự chạy bằng sơ đồ Mermaid đã kiểm | Dự án này | MIT |
| `browser-testing-with-devtools` | Viết code, vận hành | Thử trang qua Chrome DevTools: DOM, console, mạng | Addy Osmani | MIT |
| `interview-me` | Viết code, vận hành | Hỏi từng câu một tới khi rõ nhu cầu thật | Addy Osmani | MIT |
| `ui-ux-pro-max` | Viết code, vận hành | Hướng dẫn giao diện và trải nghiệm, có kho kiểu và bảng màu | Next Level Builder | MIT |
| `tdd` | Viết code, vận hành | Phát triển theo test, đỏ - xanh - chỉnh | Matt Pocock | MIT |
| `diagnosing-bugs` | Viết code, vận hành | Vòng tìm nguyên nhân cho lỗi khó và chạy chậm | Matt Pocock | MIT |
| `codebase-design` | Viết code, vận hành | Bộ từ chung để thiết kế mô-đun sâu | Matt Pocock | MIT |
| `domain-modeling` | Viết code, vận hành | Dựng bảng thuật ngữ và ghi chép quyết định của dự án | Matt Pocock | MIT |
| `improve-codebase-architecture` | Viết code, vận hành | Tìm chỗ mã có thể làm sâu hơn và báo cáo | Matt Pocock | MIT |
| `grilling` | Viết code, vận hành | Hỏi vặn kế hoạch hay ý tưởng bằng câu hỏi khó | Matt Pocock | MIT |
| `security-audit` | Viết code, vận hành | Rà soát bảo mật mã, API và dịch vụ | Cloudflare, Inc. | MIT |

`stageshow` và `video-shotcraft` không nằm trong repo này; file cài công cụ hỏi có tải về không.
