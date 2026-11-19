Tiếng Việt | [English](CONTRIBUTING.md)

# Đóng góp

Cảm ơn bạn đã giúp. Báo lỗi, sửa lỗi, dịch và viết tài liệu đều được hoan nghênh.

## Trước khi bắt đầu

- **Lỗi:** mở issue theo mẫu, ghi phiên bản và chỗ chạy (plugin, máy chủ, file cài, thanh menu, tiện ích).
- **Lỗi bảo mật:** đừng mở issue; xem [SECURITY.vi.md](SECURITY.vi.md).
- **Thay đổi lớn:** mở issue trước để thống nhất cách làm rồi mới viết code.

## Quy tắc của repo

- **Hai ngôn ngữ.** Code, chú thích và thông báo viết tiếng Anh; mỗi chú thích và docstring có một dòng tiếng Anh rồi một dòng tiếng Việt. Chữ tiếng Việt chỉ nằm trong chú thích, docstring hoặc file `*.vi.*`. Mỗi tài liệu có bản tiếng Anh `.md` và bản tiếng Việt `.vi.md`.
- **Máy chủ không dùng thư viện ngoài.** Chỉ thư viện chuẩn của Python, từ Python 3.8 trở lên.
- **Không có dữ liệu riêng.** Không commit tên thật, email, địa chỉ, khoá hay số liệu công ty. `packaging/check-clean.sh` kiểm việc này.
- **Mọi đường dẫn máy chủ đều có quyền.** Đường mới thêm vào bảng đường dẫn trong `server/webhook.py` và bảng quyền trong `server/test_webhook.py`.
- **Đổi lược đồ là thêm bước mới.** Thêm bước vào `DATA_STEPS` hoặc `KEYS_STEPS` trong `server/board/db.py`; không sửa bước đã phát hành.

## Các bước kiểm

Chạy đủ mười một bước từ thư mục gốc repo trước khi gửi thay đổi. GitHub Actions chạy đúng các bước này.

```bash
claude plugin test .
cd server && python3 -m unittest
```

```bash
python3 tests/connectors/test_connectors.py
python3 tests/appmeter/test_appmeter.py
node tests/extension/check-extension.js
node tests/check-map-layout.js
python3 tests/check-i18n.py
python3 tests/check-maps.py
python3 tests/check-frontmatter.py
bash tests/test-check-clean.sh
uvx ruff check .
```

Khối lệnh đầu kết thúc ở trong `server/`, nên quay về thư mục gốc repo trước khi chạy khối thứ hai. Không có `uv` thì lệnh cuối là `pipx run ruff check .`. `python3 tests/check-i18n.py --comments` kiểm thêm việc mỗi chú thích có một dòng tiếng Anh rồi một dòng tiếng Việt.

`bash packaging/check-clean.sh` không nằm trong danh sách này: nó tìm dữ liệu riêng trong thư mục đang chạy, nên dùng cho phần sẽ được công bố. Ở bản checkout có file `packaging/company.json` của riêng bạn, nó sẽ báo file đó, và như vậy là đúng.

`web/ops.js`, `ops.css`, `ops3d.js` (và `i18n.js`, `ops.vi.js`) phải giống hệt bản trong `server/static/`; script đóng gói sẽ kiểm. `server/board/costreport.py`, `labels.json` và `prices.json` phải giống hệt `skills/ai-cost-report/report.py`, `labels.json` và `prices.json`; `server/test_projects.py` sẽ kiểm. Sửa `web/` thì gõ `/reload-plugins` rồi `/office` để trang trên máy nhận bản mới.

Thiết kế, đặc tả, sơ đồ luồng và ngôn ngữ lập trình từng phần dùng: xem [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).

Thư viện và kỹ năng đi kèm: xem [THIRD-PARTY.md](THIRD-PARTY.md).

GitHub Actions chạy mọi bước kiểm trên Ubuntu và Windows; mỗi bước kiểm gì xem [docs/TEST-PLAN.vi.md](docs/TEST-PLAN.vi.md).

## Pull request

Mỗi pull request một thay đổi, điền theo mẫu, và ghi đã kiểm bằng cách nào. Gửi pull request nghĩa là bạn đồng ý phát hành phần việc đó theo [Giấy phép MIT](LICENSE).
