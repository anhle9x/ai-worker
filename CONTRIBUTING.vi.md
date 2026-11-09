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

```bash
claude plugin test .
cd server && python3 -m unittest test_webhook
python3 tests/check-i18n.py --comments
```

`web/ops.js`, `ops.css`, `ops3d.js` (và `i18n.js`, `ops.vi.js`) phải giống hệt bản trong `server/static/`; script đóng gói sẽ kiểm. Sửa `web/` thì gõ `/reload-plugins` rồi `/office` để trang trên máy nhận bản mới.

Thiết kế, đặc tả, sơ đồ luồng và ngôn ngữ lập trình từng phần dùng: xem [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).

Thư viện và kỹ năng đi kèm: xem [THIRD-PARTY.md](THIRD-PARTY.md).

```bash
python3 tests/check-i18n.py
bash packaging/check-clean.sh
```

GitHub Actions chạy mọi bước kiểm trên Ubuntu và Windows; mỗi bước kiểm gì xem [docs/TEST-PLAN.vi.md](docs/TEST-PLAN.vi.md).

## Pull request

Mỗi pull request một thay đổi, điền theo mẫu, và ghi đã kiểm bằng cách nào. Gửi pull request nghĩa là bạn đồng ý phát hành phần việc đó theo [Giấy phép MIT](LICENSE).
