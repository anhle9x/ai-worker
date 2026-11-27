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
- **Làm gì:** chọn ngôn ngữ của dự án và chép file tương ứng vào thư mục code. Mỗi bộ đo là một file, không cần cài thêm gì, và ghi ra cùng một kiểu dòng như các bộ khác.

  | Ngôn ngữ | File cần chép | Cần có | Tự đọc câu trả lời của hãng | Gửi lên bảng |
  |---|---|---|---|---|
  | Python | `ai_meter.py` | Python 3.8+ | có | có |
  | JavaScript (Node) | `ai-meter.cjs` | Node 18+ | có | có |
  | TypeScript | `ai-meter.cjs` và `ai-meter.d.cts`, nằm cạnh nhau | Node 18+ (đã thử với TypeScript 5.9) | có | có |
  | C# | `AiMeter.cs` | .NET 6+ | có | có |
  | Go | `aimeter.go`, trong thư mục `aimeter/` | Go 1.21+ | có | có |
  | Java, Kotlin và ngôn ngữ JVM khác | `AiMeter.java`, trong thư mục `aimeter/` | Java 11+ | có | có |
  | Rust | `ai_meter.rs`, trong `src/` | Rust 1.63+ | không: bạn đưa số token vào | không: chỉ ghi file |
  | C hay C++ | `ai_meter.h` | C99 hoặc C++11 | không: bạn đưa số token vào | không: chỉ ghi file |

  - Từ plugin đã cài bằng gói cài (Mac, Linux; trên Windows thư mục là `%USERPROFILE%\claude-plugins-ai-worker`). Trước hết đặt tên cho thư mục chứa các bộ đo:
    ```bash
    M=~/claude-plugins-ai-worker/ai-worker/skills/ai-cost-report/meter
    ```
    Rồi chạy dòng của ngôn ngữ bạn dùng, với `<thư mục dự án>` là thư mục code của dự án:
    ```bash
    cp "$M/ai_meter.py" <thư mục dự án>/
    ```
    ```bash
    cp "$M/ai-meter.cjs" <thư mục dự án>/
    ```
    ```bash
    cp "$M/ai-meter.cjs" "$M/ai-meter.d.cts" <thư mục dự án>/src/
    ```
    ```bash
    cp "$M/AiMeter.cs" <thư mục dự án>/
    ```
    ```bash
    mkdir -p <thư mục dự án>/aimeter && cp "$M/aimeter.go" <thư mục dự án>/aimeter/
    ```
    ```bash
    mkdir -p <thư mục dự án>/src/main/java/aimeter && cp "$M/AiMeter.java" <thư mục dự án>/src/main/java/aimeter/
    ```
    ```bash
    cp "$M/ai_meter.rs" <thư mục dự án>/src/
    ```
    ```bash
    cp "$M/ai_meter.h" <thư mục dự án>/
    ```
  - Hoặc tải từ repo này, đúng bản bạn đang chạy (ở đây là `v0.50.30`), ngay trong thư mục sẽ chứa file:
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.50.30/skills/ai-cost-report/meter/ai_meter.py
    ```
    Ngôn ngữ khác thì đổi tên file ở cuối: `ai-meter.cjs`, `ai-meter.d.cts`, `AiMeter.cs`, `aimeter.go`, `AiMeter.java`, `ai_meter.rs` hay `ai_meter.h`.
  - Ngôn ngữ khác nữa (PHP, Ruby, Swift...): chưa có file chép sẵn, nên code của dự án tự làm việc của bộ đo. Sau mỗi yêu cầu của người dùng, thêm một dòng JSON vào cuối file `ai-meter.jsonl`: yêu cầu đó mất bao lâu, kết thúc ra sao, và với mỗi model đã gọi: tên hãng, tên model, số lần gọi và số token hãng trả về. Một dòng trông như sau:
    ```json
    {"v":1,"turnId":"3f9c0a7d5be14c21","at":"2026-11-20T08:15:02.481Z","durationMs":2140,"outcome":"ok","env":"prod","models":[{"provider":"openai","model":"gpt-6.1-terra","calls":1,"errors":0,"retries":0,"unmeasured":0,"input":1830,"output":412,"cacheRead":0,"cacheWrite":0}]}
    ```
    `turnId` là 16 ký tự hex ngẫu nhiên, mỗi yêu cầu một mã mới; `at` là lúc yêu cầu bắt đầu, theo giờ UTC. Không bao giờ ghi câu hỏi, câu trả lời hay người dùng vào đó. Đủ các trường và chỗ đọc số token của từng hãng: [FORMAT.vi.md](../skills/ai-cost-report/FORMAT.vi.md). Skill và bảng đọc file này giống hệt file mà một bộ đo ghi.
- **Kết quả đúng:** file của ngôn ngữ bạn dùng nằm cạnh code (Go là `aimeter/aimeter.go`, Java là `src/main/java/aimeter/AiMeter.java`, Rust là `src/ai_meter.rs`), và dự án vẫn dịch được.

## Bước 3. Bọc mỗi yêu cầu của người dùng

- **Ở đâu:** đoạn code xử lý một yêu cầu: chỗ câu hỏi của người dùng đi vào và LLM được gọi.
- **Làm gì:** tạo bộ đo một lần khi chương trình khởi động, rồi bọc phần xử lý mỗi yêu cầu. Tìm ngôn ngữ của bạn bên dưới.

### Python

```python
from ai_meter import Meter
meter = Meter("ai-meter.jsonl")          # một lần, ở đầu file

# trong hàm xử lý mỗi yêu cầu:
with meter.turn() as t:                  # hoặc: async with meter.turn() as t:
    resp = client.messages.create(...)   # lời gọi LLM bạn đã có
    t.record(resp)                       # thêm dòng này sau MỖI lần gọi LLM
```

Lỗi xảy ra trong `with` được ghi là `error` (hay `timeout`) rồi ném lại đúng như cũ.

### JavaScript (Node)

```js
const { Meter } = require('./ai-meter.cjs')   // hoặc, trong ES module: import { Meter } from './ai-meter.cjs'
const meter = new Meter({ file: 'ai-meter.jsonl' })

// trong hàm xử lý mỗi yêu cầu:
const answer = await meter.turn(async (t) => {
  const resp = await client.chat.completions.create(...)
  t.record(resp)
  return resp
})
```

`meter.turn` trả về đúng thứ hàm của bạn trả về, và ném lại đúng lỗi hàm đó ném. Khi phần xử lý không gói gọn trong một hàm, dùng `const t = meter.start()` rồi tự gọi `t.end()` (hay `t.end('error')`).

### TypeScript

Để hai file nằm cạnh nhau, giữ nguyên tên: TypeScript tìm kiểu của `ai-meter.cjs` trong `ai-meter.d.cts`.

```ts
import { Meter } from './ai-meter.cjs'
const meter = new Meter({ file: 'ai-meter.jsonl' })

const answer = await meter.turn(async (t) => {
  const resp = await client.messages.create(...)
  t.record(resp)
  return resp
})
```

Các lệnh giống JavaScript, nay có kiểm kiểu: `env` chỉ được là `'prod'` hay `'test'`, số token phải là số. Chạy được với mọi giá trị `module` của dự án (`commonjs`, `node16`, `nodenext`, `bundler`, `preserve`) và trong dự án có `"type": "module"`.

### C#

```csharp
// một lần, khi chương trình khởi động; với ASP.NET Core: builder.Services.AddSingleton(new AiMeter.Meter("ai-meter.jsonl"));
var meter = new AiMeter.Meter("ai-meter.jsonl");

// trong đoạn code xử lý mỗi yêu cầu:
using (var t = meter.Turn())
{
    try
    {
        var res = await http.PostAsync(url, content);           // lời gọi LLM bạn đã có
        var body = await res.Content.ReadAsStringAsync();
        t.Record(body);                                         // câu trả lời của hãng, dạng chữ JSON
    }
    catch (TaskCanceledException) { t.Outcome = "timeout"; throw; }
    catch { t.Outcome = "error"; throw; }
}                                                               // dòng được ghi ở đây

await meter.FlushAsync();                                       // trước khi chương trình kết thúc, khi có gửi lên bảng
```

- `t.Record(...)` nhận câu trả lời dạng chữ JSON hoặc dạng `JsonElement` đã đọc sẵn. Hãng ngoài Anthropic, OpenAI và Gemini thì ghi thêm tên: `t.Record(body, provider: "deepseek")`.
- Khi SDK trả về một đối tượng chứ không phải JSON, đọc số trong phần usage của nó rồi gọi `t.Count("openai", "gpt-6.1-terra", input: 1530, output: 412, cacheRead: 300)`.
- Khác Python, lỗi không tự đặt kết quả của lượt: đặt `t.Outcome` trong `catch` như trên.

### Go

```go
import "example.com/yourproject/aimeter"   // tên module trong go.mod của bạn, thêm /aimeter

var meter = aimeter.New("ai-meter.jsonl", "prod")   // một lần

func main() {
	defer meter.Close()   // gửi nốt những gì đang chờ, khi có gửi lên bảng
	// ...
}

// trong hàm xử lý mỗi yêu cầu:
t := meter.Turn()
defer t.End()                     // dòng được ghi khi hàm xử lý kết thúc
res, err := http.DefaultClient.Do(req)   // lời gọi LLM bạn đã có
if err != nil {
	t.Fail("openai", "gpt-6.1-terra", false)
	t.SetOutcome("error")
	return
}
body, _ := io.ReadAll(res.Body)
t.Record(body)                    // câu trả lời của hãng, dạng byte JSON
```

- Hãng ngoài Anthropic, OpenAI và Gemini thì ghi thêm tên: `t.RecordWith(body, aimeter.Opt{Provider: "deepseek"})`. Lần gọi lặp lại một lần đã lỗi: `aimeter.Opt{Retry: true}`.
- Khi SDK trả về một struct chứ không phải JSON, đọc số trong phần usage của nó rồi gọi `t.Count("openai", "gpt-6.1-terra", &aimeter.Counts{Input: 1530, Output: 412, CacheRead: 300})`; truyền `nil` thay cho số đếm nghĩa là không đo được.
- Địa chỉ bảng và khoá: `aimeter.NewSending(path, env, url, key)`, hoặc các biến ở bước 4.

### Java, Kotlin và các ngôn ngữ JVM khác

Java 11 không có sẵn bộ đọc JSON, nên `AiMeter.java` mang theo một bộ nhỏ: `record` nhận câu trả lời của hãng dạng chữ JSON, đúng như phần lớn HTTP client trả về, hoặc dạng `Map` mà Jackson hay Gson đã đọc. Phần gửi lên bảng dùng `java.net.http`, có sẵn từ Java 11.

```java
import aimeter.AiMeter;

AiMeter meter = new AiMeter("ai-meter.jsonl");   // một lần, khi chương trình khởi động

// trong đoạn code xử lý mỗi yêu cầu:
String answer = meter.turn(t -> {
    HttpResponse<String> res = http.send(request, HttpResponse.BodyHandlers.ofString());   // lời gọi LLM bạn đã có
    t.record(res.body());                        // câu trả lời của hãng, dạng chữ JSON
    return res.body();
});
```

`meter.turn(t -> ...)` trả về đúng thứ code của bạn trả về và ném lại đúng lỗi nó ném; lỗi có tên chứa timeout (`HttpTimeoutException`, `SocketTimeoutException`...) ghi là `timeout`, lỗi khác ghi là `error`. Chỗ nào không dùng lambda được thì dùng `try (AiMeter.Turn t = meter.turn()) { ... }` và tự gọi `t.setOutcome("error")` trong `catch`.

Spring Boot: tạo bộ đo thành một bean, để nó được đóng (và gửi nốt những gì đang chờ) khi ứng dụng dừng.

```java
@Configuration
class AiMeterConfig {
    @Bean(destroyMethod = "close")
    AiMeter aiMeter() {
        return new AiMeter("ai-meter.jsonl");
    }
}

@RestController
class AskController {
    private final AiMeter meter;
    private final RestClient llm;

    AskController(AiMeter meter, RestClient llm) {
        this.meter = meter;
        this.llm = llm;
    }

    @PostMapping("/ask")
    String ask(@RequestBody String question) throws Exception {
        return meter.turn(t -> {
            String body = llm.post().uri("/v1/messages").body(question).retrieve().body(String.class);
            t.record(body);
            return body;
        });
    }
}
```

Kotlin (và Scala, Groovy...) gọi đúng lớp đó:

```kotlin
import aimeter.AiMeter

val meter = AiMeter("ai-meter.jsonl")

meter.turn().use { t ->
    val body = http.send(request, HttpResponse.BodyHandlers.ofString()).body()
    t.record(body)
}
```

- Hãng ngoài Anthropic, OpenAI và Gemini thì ghi thêm tên: `t.record(body, "deepseek")`. Lần gọi lặp lại một lần đã lỗi: `t.record(body, provider, null, true)`.
- Đối tượng của SDK: đọc số trong phần usage của nó rồi gọi `t.count("openai", "gpt-6.1-terra", 1530L, 412L)`, hoặc `t.count(provider, model, input, output, cacheRead, cacheWrite, cacheWriteLong, retry)`; `null` cho input hay output nghĩa là không đo được.
- Lần gọi lỗi: `t.fail(hãng, model)`; streaming: `t.firstToken()`. Địa chỉ bảng và khoá: `new AiMeter(file, env, sendUrl, sendKey)`, hoặc các biến ở bước 4. Gọi `meter.close()` trước khi chương trình kết thúc (Spring tự làm với bean ở trên).
- Bộ đo nằm trong package `aimeter`: để file trong thư mục `aimeter/` của mã nguồn, hoặc đổi dòng đầu thành package của bạn.

### Rust

Rust không có sẵn bộ đọc JSON, nên bộ đo nhận số token mà client của bạn đã đọc. Bộ đo chỉ ghi file.

```rust
mod ai_meter;   // trong main.rs hay lib.rs
use ai_meter::{Counts, Meter};
use std::sync::OnceLock;

static METER: OnceLock<Meter> = OnceLock::new();

// trong hàm xử lý mỗi yêu cầu:
let meter = METER.get_or_init(|| Meter::new("ai-meter.jsonl", "prod"));
let mut t = meter.turn();
// sau mỗi lần gọi LLM, lấy từ usage trong câu trả lời (ở đây là Anthropic: input_tokens không gồm cache)
t.count("anthropic", "claude-sonnet-5-5", Some(Counts {
    input: u.input_tokens,
    output: u.output_tokens,
    cache_read: u.cache_read_input_tokens,
    ..Default::default()
}));
// câu trả lời không kèm số token: t.count("anthropic", "claude-sonnet-5-5", None);
t.end();   // hoặc để t ra khỏi phạm vi; panic thì ghi "error"
```

- `input` là đầu vào tính giá thường, không gồm đọc và ghi cache. Với OpenAI và các API chép theo nó, đó là `prompt_tokens - cached_tokens`. Bảng trong [FORMAT.vi.md](../skills/ai-cost-report/FORMAT.vi.md#đọc-số-token) ghi trường của từng hãng.
- Lần gọi lỗi: `t.fail(hãng, model, false)`; gọi lại: `t.count_with(..., true)`; streaming: `t.first_token()`; quá thời gian: `t.set_outcome("timeout")`.
- Muốn đưa lên bảng thì gửi các dòng của file bằng HTTP client của bạn như [FORMAT.vi.md](../skills/ai-cost-report/FORMAT.vi.md#gửi-lên-bảng-ai-worker) hướng dẫn, hoặc làm báo cáo từ file bằng skill.

### C hay C++

C và C++ không có sẵn bộ đọc JSON, nên bộ đo nhận số token mà thư viện JSON của bạn đã đọc. Bộ đo chỉ ghi file.

```c
#include "ai_meter.h"   /* trên Linux, đặt trước các header khác (hoặc dịch với -D_POSIX_C_SOURCE=200809L) */

static ai_meter meter;

int main(void) {
    ai_meter_init(&meter, "ai-meter.jsonl", "prod");   /* một lần */
    /* ... */
}

/* trong đoạn code xử lý mỗi yêu cầu: */
void handle_request(void) {
    ai_turn t;
    ai_turn_begin(&t, &meter);
    /* sau mỗi lần gọi LLM: hãng, model, đầu vào, đầu ra, đọc cache, ghi cache, ghi cache giữ lâu */
    ai_turn_count(&t, "openai", "gpt-6.1-terra", prompt_tokens - cached_tokens, completion_tokens, cached_tokens, 0, 0);
    /* câu trả lời không kèm số token: -1 cho đầu vào và đầu ra */
    ai_turn_end(&t);
}
```

- Các hàm này dùng được y nguyên từ C++ (C++11 trở lên); header dịch qua với `-Wall -Wextra -Werror`.
- Lần gọi lỗi: `ai_turn_fail(&t, hãng, model, 0)`; gọi lại: `ai_turn_count_retry(..., 1)`; streaming: `ai_turn_first_token(&t)`; quá thời gian: `ai_turn_set_outcome(&t, "timeout")`.
- Mỗi `ai_turn` chỉ dùng trong một luồng. Một lượt giữ tối đa 16 model khác nhau; quá số đó thì bỏ qua.
- Muốn đưa lên bảng thì gửi các dòng của file bằng HTTP client của bạn như [FORMAT.vi.md](../skills/ai-cost-report/FORMAT.vi.md#gửi-lên-bảng-ai-worker) hướng dẫn, hoặc làm báo cáo từ file bằng skill.

### React, Next.js và các giao diện web khác

Không có bộ đo cho trình duyệt, và đó là cố ý. LLM phải được gọi từ máy chủ của dự án, không bao giờ từ code chạy trên trình duyệt: khoá API của hãng sẽ nằm trong trang cho bất kỳ ai chép ra, khoá của bảng cũng vậy (dù sao bảng cũng từ chối yêu cầu từ trình duyệt). Gắn bộ đo ở chỗ gọi LLM: Route Handler hay API route của Next.js, Server Action, route của Express hay Fastify, hàm chạy trên máy chủ của Remix hay SvelteKit. Ở đó, dùng bộ đo JavaScript hay TypeScript ở trên.

Một Route Handler của Next.js, với `ai-meter.cjs` và `ai-meter.d.cts` chép vào `lib/`:

```ts
// app/api/ask/route.ts: chạy trên máy chủ, không bao giờ trên trình duyệt
import { Meter } from '@/lib/ai-meter.cjs'

export const runtime = 'nodejs'   // bộ đo ghi file: cần Node, không phải Edge runtime
const meter = new Meter({ file: process.env.AI_METER_FILE ?? 'ai-meter.jsonl' })

export async function POST(req: Request) {
  const { question } = await req.json()
  const resp = await meter.turn(async (t) => {
    const r = await client.messages.create({ model: 'claude-sonnet-5-5', max_tokens: 1024, messages: [{ role: 'user', content: question }] })
    t.record(r)
    return r
  })
  await meter.sender?.flush()      // trên máy chủ serverless, gửi trước khi hàm bị đóng băng
  return Response.json({ answer: resp.content })
}
```

Server Action cũng vậy: bọc lời gọi LLM trong hàm `'use server'` bằng `meter.turn(...)`.

- Trên máy chủ serverless (Vercel, Netlify, AWS Lambda...) ổ đĩa bị xoá giữa các lần chạy: đặt `AI_METER_FILE=/tmp/ai-meter.jsonl`, gửi lên bảng (bước 4), và gọi `await meter.sender?.flush()` trước khi trả lời, như trên.
- Bộ đo trên máy chủ đo thời gian của máy chủ: từ lúc yêu cầu tới đến lúc câu trả lời đi, và mẩu streaming đầu tiên với `t.firstToken()`. Thời gian người dùng thấy còn cộng thêm mạng và thời gian trang tự vẽ. Muốn đo phần đó thì đo ở trình duyệt (ví dụ `performance.now()` từ lúc bấm tới lúc chữ đầu tiên hiện ra) và chỉ gửi số mili giây về backend của chính dự án, để backend tự lưu vào log của mình. Không bao giờ đặt khoá trong trang để làm việc này; các dòng của bộ đo không chứa con số đó.

### Cho mọi ngôn ngữ

- Yêu cầu gọi LLM nhiều lần (đọc ảnh rồi trả lời) thì ghi hoặc đếm từng lần gọi.
- `record` (C# và Go: `Record`, Java: `record`) đọc được câu trả lời của Anthropic, OpenAI, Gemini, xAI Grok, mọi API chép theo dạng của OpenAI (DeepSeek, Mistral, Groq, OpenRouter, Azure OpenAI, vLLM, LM Studio...), Bedrock, Cohere, Ollama và Vercel AI SDK. Hãng ngoài ba hãng đầu thì ghi thêm tên: `t.record(resp, provider="deepseek")`.
- Hãng khác nữa: đọc số token trong câu trả lời theo tài liệu của hãng, rồi gọi `count` (Python: `t.count("tenhang", "ten-model", input=..., output=...)`).
- Trả lời kiểu streaming (chữ hiện dần): gọi `first_token()` (Node và Java: `firstToken()`, C# và Go: `FirstToken()`) khi mẩu đầu tiên tới. OpenAI và nhiều API chép theo nó chỉ gửi số token khi streaming nếu có `stream_options={"include_usage": True}`; không có thì lượt đó ghi là "không đo được".
- Lần gọi bị lỗi: `fail(hãng, model)`. Không bao giờ truyền chữ của lỗi.
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
- **Có bảng:** bấm **Dự án AI**, chọn ngày và **Người dùng thật (prod)**, rồi **Mở bản in** (mở ở tab mới: bấm Ctrl+P, trên Mac là ⌘P, rồi chọn **Lưu dưới dạng PDF**) hoặc **Tải CSV**.
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
