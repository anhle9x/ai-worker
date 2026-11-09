[English](SECURITY.md) | Tiếng Việt

# Chính sách bảo mật

## Báo một lỗi

Đừng mở issue công khai cho lỗi bảo mật: ai cũng có thể lợi dụng trước khi lỗi được sửa.

1. Báo kín trên GitHub: tab **Security** của repo này, rồi **Report a vulnerability**.
2. Nếu không làm được, nhắn riêng qua Telegram tới [t.me/anhle9x](https://t.me/anhle9x), nói là có báo cáo bảo mật; chi tiết gửi theo cách hai bên thống nhất.

Ghi rõ phần bị ảnh hưởng (plugin, máy chủ, file cài, thanh menu), phiên bản, và các bước để thấy lỗi. Đừng gửi dữ liệu của người thật.

## Sau khi báo

- Bạn nhận trả lời trong vòng 7 ngày.
- Lỗi được xác nhận sẽ sửa trong bản phát hành kế tiếp, và tên bạn được ghi trong phần ghi chú phát hành nếu bạn muốn.
- Xin giữ kín tới khi có bản sửa, hoặc chậm nhất 90 ngày.

## Phiên bản được hỗ trợ

Chỉ bản phát hành mới nhất nhận bản sửa bảo mật.

## Dự án được thiết kế để chống những gì

AI Worker được thiết kế để chống tám rủi ro web thường gặp dưới đây, theo danh sách OWASP Top 10 năm 2013. Mã đã được rà soát cùng các trợ lý AI và các tấn công chính đã được chạy lại trên bản thử. Chưa có công ty bảo mật độc lập nào kiểm định, và không phần mềm nào cam kết được là không có lỗi.

| Rủi ro | Sản phẩm làm gì | Còn lại |
|---|---|---|
| **Giả mạo yêu cầu (CSRF)** | Cookie phiên đặt `SameSite=Strict`. Yêu cầu sai `Origin` bị từ chối, thao tác quản trị còn từ chối cả khi thiếu `Origin`. Gửi số liệu dùng mã trong header, không dùng cookie | Trình duyệt cũ không có `SameSite` chỉ còn dựa vào kiểm tra `Origin` |
| **Chèn mã vào trang (XSS)** | Trang máy chủ thoát ký tự đặc biệt, script trên trang đưa dữ liệu vào dưới dạng chữ. Trang máy chủ gửi Content-Security-Policy, chỉ cho chạy script cùng trang | Chính sách vẫn cho phép style viết trực tiếp. Trang trên máy không có chính sách này; trang chỉ hiện dữ liệu của chính máy đó |
| **Nhúng mã (Injection)** | Máy chủ không chạy lệnh shell, và các câu truy vấn SQLite chỉ nhận giá trị qua tham số, không bao giờ ghép chữ vào câu truy vấn. Yêu cầu lấy file được đối chiếu với danh sách hoặc mẫu cố định. Plugin chạy chương trình bằng danh sách tham số. Chữ cho ChatGPT đi qua đầu vào chuẩn, và Gemini bị từ chối nếu phải chạy qua file `.cmd` hoặc `.bat` trên Windows | Tài liệu vẫn có thể tìm cách điều khiển trợ lý qua đoạn chữ nó nhận. Vì vậy ChatGPT chạy trong sandbox chỉ đọc |
| **Lỗi xác thực** | Mỗi tài khoản có khoá OTP riêng, mỗi mã chỉ dùng một lần. Số lần sai bị giới hạn theo IP và theo tài khoản. Mã phiên ngẫu nhiên và có hạn; cookie đặt `HttpOnly`, và `Secure` khi dùng HTTPS. Đổi tài khoản hay màn hình TV phải nhập lại OTP | OTP là yếu tố đăng nhập duy nhất, nên hãy giữ danh sách IP |
| **Truy cập trực tiếp đối tượng (IDOR)** | Người xem và màn hình treo tường nhận một bản đã lọc theo vai, không có cách xin một bản ghi theo mã. Thao tác lên một tài khoản hay màn hình cụ thể chỉ dành cho quản trị | Người xem được thấy số của mọi người, đây là chủ ý. Ai có mã gửi dùng chung đều gửi được dưới một tên chưa gắn với máy nào |
| **Thiếu kiểm soát quyền theo chức năng** | Mọi đường dẫn được liệt kê kèm quyền, một cổng kiểm tất cả. Đường không có trong bảng trả 404. Có test chốt mỗi vai được gì trên từng đường. Máy chủ tự kiểm, không chỉ ẩn nút | Người viết đường dẫn mới phải tự thêm vào bảng đó |
| **Sai cấu hình bảo mật** | Không có tài khoản hay khoá mặc định, thiếu `INGEST_KEY` thì máy chủ không chạy. Sau Caddy thì chỉ nghe trong máy. Dịch vụ chạy bằng người dùng riêng với quyền hạn chế; file khoá và dữ liệu chỉ dịch vụ đọc được | Bạn phải tự đặt danh sách IP, bật HTTPS và giữ ít người có sudo |
| **Lộ dữ liệu nhạy cảm** | Không bao giờ gửi nội dung trò chuyện, tên file, tên dự án. Màn hình treo tường không nhận email, IP nội bộ. Phiên TV lưu dạng mã băm, nhật ký không chứa khoá, file trông như chứa bí mật chỉ được ghi tên | Không có HTTPS thì số liệu đi không mã hoá. Khoá OTP nằm trên máy chủ không mã hoá, dịch vụ và người có sudo đọc được. Gói cài có chứa mã gửi |

Chi tiết hơn: [docs/ARCHITECTURE.vi.md](docs/ARCHITECTURE.vi.md).
