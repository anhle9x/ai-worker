Tiếng Việt | [English](AI-PROJECTS.md)

# Đo một dự án hay ứng dụng AI

Dành cho nhóm đã làm một dự án hay ứng dụng có gọi LLM (chatbot, định giá, đọc tài liệu...) và cần báo cáo chi phí và hiệu năng. Bộ đo đi kèm skill `ai-cost-report` của plugin này.

Bộ đo chỉ ghi **số đếm và thời gian**: mỗi lượt mất bao lâu, kết thúc ra sao, gọi model nào bao nhiêu lần, bao nhiêu token. Bộ đo **không bao giờ** ghi câu hỏi, câu trả lời, tên hay mã người dùng, hay thông báo lỗi. Hãng LLM nào cũng dùng được.

Có hai cách dùng:

- **Dùng riêng:** bộ đo ghi một file cạnh dự án, và skill biến file đó thành báo cáo ngay trên máy. Không cần máy chủ. Làm bước 2, 3 và 6.
- **Dùng với bảng AI Worker:** bộ đo gửi thêm từng lượt lên bảng của bạn, nơi quản trị và người xem đọc và tải báo cáo. Làm bước 1 tới 6.

Cách nhanh nhất: mở Claude Code trong thư mục code của dự án, gõ `/ai-worker:ai-cost-report`. Claude tìm chỗ dự án gọi LLM và đưa bạn xem từng dòng định thêm trước khi sửa gì. Các bước dưới đây là cách làm tay cùng việc đó.

---

## Bước 1. Tạo khoá cho dự án (chỉ khi dùng bảng)

- **Ở đâu:** bảng AI Worker của bạn, trang **Quản trị**, mục **Dự án và ứng dụng AI**. Mục này chỉ có khi máy chủ có `AI_PROJECTS=1` ([INSTALL.vi.md](INSTALL.vi.md#dự-án-hay-ứng-dụng-ai-tuỳ-chọn)).
- **Làm gì:** gõ tên dự án, bấm **Tạo khoá**, nhập mã OTP.
- **Kết quả đúng:** hiện hai dòng, chỉ một lần:
  ```
  AI_METER_URL=https://<domain của bảng>/projects/ingest
  AI_METER_KEY=prj_…
  ```
  `<domain của bảng>` là domain của máy chủ chạy bảng AI Worker, tức phần trên thanh địa chỉ trình duyệt khi bạn mở bảng, ví dụ `https://board.example.com/projects/ingest`. Trang Quản trị tự điền sẵn domain này. Chép cả hai ngay. Không gửi khoá qua chat, email hay ảnh chụp.

## Bước 2. Chép bộ đo vào dự án

- **Ở đâu:** Terminal trên máy có code dự án.
- **Làm gì:** chép một file vào thư mục code.
  - Từ plugin đã cài bằng gói cài (Mac, Linux; trên Windows thư mục là `%USERPROFILE%\claude-plugins-ai-worker`):
    ```bash
    cp ~/claude-plugins-ai-worker/ai-worker/skills/ai-cost-report/meter/ai_meter.py <thư mục dự án>/
    ```
    Dự án Node hay TypeScript thì file là `ai-meter.cjs` trong cùng thư mục.
  - Hoặc tải từ repo này, đúng bản bạn đang chạy (ở đây là `v0.45.2`):
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.45.2/skills/ai-cost-report/meter/ai_meter.py
    ```
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.45.2/skills/ai-cost-report/meter/ai-meter.cjs
    ```
  - Ngôn ngữ khác (Go, Java, C#, PHP...): tự ghi mỗi lượt một dòng theo [FORMAT.vi.md](../skills/ai-cost-report/FORMAT.vi.md).
- **Kết quả đúng:** `ai_meter.py` (Python 3.8+, chỉ thư viện chuẩn) hoặc `ai-meter.cjs` (Node 18+, không cần gói nào) nằm cạnh code.

## Bước 3. Bọc mỗi yêu cầu của người dùng

- **Ở đâu:** đoạn code xử lý một yêu cầu: chỗ câu hỏi của người dùng đi vào và LLM được gọi.
- **Làm gì:** tạo bộ đo một lần khi chương trình khởi động, rồi bọc phần xử lý mỗi yêu cầu.

  Python:
  ```python
  from ai_meter import Meter
  meter = Meter("ai-meter.jsonl")          # một lần, ở đầu file

  # trong hàm xử lý mỗi yêu cầu:
  with meter.turn() as t:
      resp = client.messages.create(...)   # lời gọi LLM bạn đã có
      t.record(resp)                       # thêm dòng này sau MỖI lần gọi LLM
  ```

  Node:
  ```js
  const { Meter } = require('./ai-meter.cjs')
  const meter = new Meter({ file: 'ai-meter.jsonl' })

  // trong hàm xử lý mỗi yêu cầu:
  const answer = await meter.turn(async (t) => {
    const resp = await client.chat.completions.create(...)
    t.record(resp)
    return resp
  })
  ```

- **Cần biết:**
  - Yêu cầu gọi LLM nhiều lần (đọc ảnh rồi trả lời) thì gọi `t.record(...)` sau mỗi lần.
  - `record` đọc được câu trả lời của Anthropic, OpenAI, Gemini, xAI Grok, mọi API chép theo dạng của OpenAI (DeepSeek, Mistral, Groq, OpenRouter, Azure OpenAI, vLLM, LM Studio...), Bedrock, Cohere, Ollama và Vercel AI SDK. Hãng ngoài ba hãng đầu thì ghi thêm tên: `t.record(resp, provider="deepseek")`.
  - Hãng khác nữa: đọc số token trong câu trả lời theo tài liệu của hãng, rồi gọi `t.count("tenhang", "ten-model", input=..., output=...)`.
  - Trả lời kiểu streaming (chữ hiện dần): gọi `t.first_token()` (Node: `t.firstToken()`) khi mẩu đầu tiên tới. OpenAI và nhiều API chép theo nó chỉ gửi số token khi streaming nếu có `stream_options={"include_usage": True}`; không có thì lượt đó ghi là "không đo được".
  - Lần gọi bị lỗi: `t.fail(hãng, model)`. Không bao giờ truyền chữ của lỗi.
  - Lỗi của bộ đo không bao giờ làm hỏng dự án.
- **Kết quả đúng:** sau một câu hỏi, cạnh dự án có file `ai-meter.jsonl`, mỗi lượt một dòng, chỉ có số.

## Bước 4. Đặt khoá để gửi lên bảng (chỉ khi dùng bảng)

- **Ở đâu:** biến môi trường trên **máy chủ** của dự án: file `.env`, phần cấu hình biến môi trường của dịch vụ cloud, hoặc lệnh khởi động. **Không bao giờ** trong code chạy trên trình duyệt hay app điện thoại: bảng từ chối yêu cầu từ trình duyệt, và khoá nằm trong app có thể bị lấy ra.
- **Làm gì:** thêm hai dòng ở bước 1. Khi còn chạy thử, thêm cả `AI_METER_ENV=test`.
- **Kết quả đúng:** khởi động lại dự án, hỏi vài câu, đợi khoảng 10 giây. Trên bảng, bấm **Dự án AI** ở trang chủ, chọn dự án và **Chạy thử (test)**: số lượt tăng đúng bằng số câu đã hỏi.

Bộ đo gửi theo lô ở nền và không bao giờ bắt dự án chờ. Nó chỉ gửi khoá qua HTTPS, hoặc tới chính máy đó. File vẫn được ghi.

## Bước 5. Chỉ khi dự án chạy trên cloud (chỉ khi dùng bảng)

Bảng thường chỉ trả lời trong mạng văn phòng. Dự án chạy trên cloud nằm ngoài mạng đó.

- **Ở đâu:** máy chủ của bảng, file `aiworker.caddy` (người có quyền SSH làm).
- **Làm gì:** bỏ dấu `#` ở khối bắt đầu bằng "Only for an AI project or application that runs on a cloud server", điền IP của dự án vào chỗ `192.0.2.10`, và dùng khối đó thay cho hai dòng chặn IP ở đầu file. Chạy `caddy validate`, rồi `sudo systemctl reload caddy`.
- **Kết quả đúng:** `caddy validate` không báo lỗi, và kiểm như bước 4 thấy các lượt.

Dự án chạy trong mạng văn phòng thì bỏ qua bước này.

## Bước 6. Chạy thật và lấy báo cáo

- **Làm gì:** bỏ `AI_METER_ENV=test`, khởi động lại, cho người dùng thật dùng trong khoảng thời gian cần báo cáo.
- **Có bảng:** bấm **Dự án AI**, chọn ngày và **Người dùng thật (prod)**, rồi **Tải báo cáo** (mở ra rồi **In** để lưu PDF) hoặc **Tải CSV**.
- **Không có bảng:** trong Claude Code, gõ `/ai-worker:ai-cost-report` và đưa file `ai-meter.jsonl`.
- **Kết quả đúng:** báo cáo có số lượt, số lần gọi LLM và token mỗi lượt, tiền mỗi lượt và ước tính 1.000 lượt, thời gian trung bình, p95 và chậm nhất, theo từng model.

## Bảng của riêng bạn, hay bảng khác

Bộ đo không gắn với bảng nào: nó gửi tới địa chỉ trong `AI_METER_URL`, và không gửi đi đâu khi biến đó trống.

- Khoá chỉ dùng được trên bảng đã tạo ra nó.
- Bảng phải chạy AI Worker 0.45.0 trở lên, có `AI_PROJECTS=1`.
- Các lượt chỉ tới bảng ghi trong `AI_METER_URL`. Bỏ cả hai biến thì mọi thứ ở lại trên máy của dự án, và làm báo cáo ngay tại đó.

## Đọc báo cáo

- Đây là số do dự án tự đo, không phải hoá đơn. Số tiền thật bị tính xem ở trang thanh toán của hãng.
- Lượt mà câu trả lời không kèm số token ghi "không đo được"; model chưa có giá ghi "chưa có giá". Cả hai đều không tính là 0. Giá của hãng khác, hay giá đã thương lượng, đặt vào file giá riêng: `--add-prices` với skill, **Giá riêng** trên trang Quản trị của bảng.
- Model chạy trên máy của nhóm (Ollama, vLLM...) ghi "chạy trên máy, không tính tiền API". Token và thời gian vẫn có; chi phí của chính các máy thì không.
- Trên bảng, mỗi lượt chỉ giữ 30 ngày, nên p95 tính được tối đa trong 30 ngày gần nhất; tổng theo ngày giữ 13 tháng.
- Mục "nếu cùng số token đó gửi cho model khác" chỉ là ước tính. Muốn so thật thì chạy dự án trên model đó với `AI_METER_ENV=test` rồi xem báo cáo môi trường test.
