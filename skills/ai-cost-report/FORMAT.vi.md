# Định dạng dòng ai-meter, phiên bản 1

Tiếng Việt | [English](FORMAT.md)

Mỗi lượt người dùng, dự án hay ứng dụng AI ghi một đối tượng JSON trên một dòng (JSON Lines, UTF-8): mọi việc nó làm để trả lời một yêu cầu của người dùng, với bất kỳ hãng LLM nào. `meter/ai_meter.py` và `meter/ai-meter.cjs` ghi sẵn cho Python và Node; dự án viết bằng ngôn ngữ khác tự ghi đúng dòng này. `report.py` đọc nó.

## Những thứ một dòng không bao giờ có

Không có câu hỏi, câu trả lời, prompt hay chữ của tài liệu; không có mã, tên, email hay IP của người dùng; không có thông báo lỗi; không có nhãn tự đặt. Chỉ có các trường dưới đây. Báo cáo bỏ mọi trường khác mà không đọc.

## Một dòng

```json
{"v":1,"turnId":"3f9c0a7d5be14c21","at":"2026-11-20T08:15:02.481Z","durationMs":2140,"ttftMs":610,"outcome":"ok","env":"prod",
 "models":[{"provider":"anthropic","model":"claude-sonnet-5-5","calls":2,"errors":0,"retries":1,"unmeasured":0,
            "input":1830,"output":412,"cacheRead":5120,"cacheWrite":0,"cacheWriteLong":0}]}
```

(Trong file viết trên một dòng.)

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `v` | 1 | Phiên bản định dạng |
| `turnId` | 16 tới 64 ký tự hex thường, ngẫu nhiên | Để báo cáo bỏ dòng đã đọc rồi. Không gắn với người dùng |
| `at` | thời điểm ISO 8601 theo UTC, có `Z` | Lúc lượt bắt đầu (giờ thật) |
| `durationMs` | số nguyên ≥ 0 | Từ đầu tới cuối lượt, đo bằng đồng hồ đơn điệu (`time.monotonic`, `performance.now`, `System.nanoTime`, `time.Since`), không lấy hai giờ thật trừ nhau |
| `ttftMs` | số nguyên, tuỳ chọn | Chỉ khi streaming: từ đầu lượt tới mẩu đầu tiên của câu trả lời. Không lớn hơn `durationMs` |
| `outcome` | `ok`, `error` hay `timeout` | Lượt kết thúc ra sao với người dùng |
| `env` | `prod` hay `test` | Chạy thử thì dùng `test`, không lẫn vào báo cáo thật |
| `models` | danh sách, tối đa 50 | Mỗi hãng và model dùng trong lượt một mục; rỗng khi lượt không gọi LLM |

Mỗi mục của `models`:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `provider` | một tên ngắn khớp `^[a-z0-9][a-z0-9_.-]{0,31}$`, ví dụ `anthropic`, `openai`, `google`, `deepseek`, `openrouter`, `ollama`, `vllm` | Ai phục vụ model. Tên khác mẫu này: ghi `other`. Model chạy trên máy của chính nhóm dùng `local`, `ollama`, `vllm`, `llamacpp`, `lmstudio`, `localai`, `tgi` hay `sglang` (báo cáo không tính tiền API cho nó), hoặc một tên mà file giá liệt kê |
| `model` | khớp `^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$` | Tên model API trả về, không có thì tên đã yêu cầu. Tên khác mẫu này: ghi `unknown` |
| `calls` | số nguyên | Số lần gọi model này trong lượt, gồm cả lần lỗi và lần gọi lại |
| `errors` | số nguyên ≤ `calls` | Số lần gọi bị lỗi (không có trả lời) |
| `retries` | số nguyên ≤ `calls` | Số lần gọi lặp lại một lần đã lỗi hay quá giờ |
| `unmeasured` | số nguyên ≤ `calls` | Số lần gọi có trả lời nhưng trả lời không kèm số token |
| `input` | số nguyên, hoặc `null` | Token đầu vào tính giá đầu vào thường: không đọc từ cache, không ghi vào cache |
| `output` | số nguyên, hoặc `null` | Token đầu ra, gồm cả token suy nghĩ |
| `cacheRead` | số nguyên, tuỳ chọn | Token đầu vào đọc từ cache |
| `cacheWrite` | số nguyên, tuỳ chọn | Token đầu vào ghi vào cache, mọi thời hạn |
| `cacheWriteLong` | số nguyên ≤ `cacheWrite`, tuỳ chọn | Phần của `cacheWrite` giữ lâu hơn (Anthropic 1 giờ, OpenAI 12 giờ), giá cao hơn |

`input` và `output` cùng là `null` khi không lần gọi có trả lời nào kèm số token: số token là chưa biết, và `null` nói đúng điều đó. Không bao giờ ghi `0` cho số mình không có. Trường cache vắng nghĩa là 0.

## Đọc số token

Lấy từ `usage` hãng trả kèm mỗi câu trả lời; không ước lượng theo độ dài chữ. Mỗi token đầu vào chỉ đếm một lần:

| Hãng | `input` | `output` | `cacheRead` | `cacheWrite` (`cacheWriteLong`) |
|---|---|---|---|---|
| Anthropic | `usage.input_tokens` (đã không gồm cache) | `usage.output_tokens` | `usage.cache_read_input_tokens` | `usage.cache_creation_input_tokens` (`usage.cache_creation.ephemeral_1h_input_tokens`) |
| OpenAI, Responses | `usage.input_tokens` − đọc cache − ghi cache | `usage.output_tokens` | `usage.input_tokens_details.cached_tokens` | `usage.input_tokens_details.cache_write_tokens` (`…cache_write_tokens_details.ttl_12h_tokens`) |
| OpenAI, Chat Completions | `usage.prompt_tokens` − đọc cache − ghi cache | `usage.completion_tokens` | `usage.prompt_tokens_details.cached_tokens` | `usage.prompt_tokens_details.cache_write_tokens`, khi có |
| Gemini | `usageMetadata.promptTokenCount` − đọc cache | `candidatesTokenCount` + `thoughtsTokenCount` | `usageMetadata.cachedContentTokenCount` | không có |
| API chép theo Chat Completions của OpenAI (Azure OpenAI, DeepSeek, Mistral, Groq, OpenRouter, xAI Grok, vLLM, LM Studio, `/v1` của Ollama...) | như OpenAI Chat Completions | `usage.completion_tokens`, cộng `completion_tokens_details.reasoning_tokens` khi `total_tokens` cho thấy phần đó không nằm trong nó (xAI làm vậy: ví dụ của họ là 32 + 9 + 110 = 151) | `prompt_tokens_details.cached_tokens`, hoặc `prompt_cache_hit_tokens` của DeepSeek | như OpenAI, khi có |
| Vercel AI SDK (`generateText` và tương tự) | `usage.inputTokenDetails.noCacheTokens`, không có thì `inputTokens` − đọc cache − ghi cache | `usage.outputTokens` | `inputTokenDetails.cacheReadTokens` | `inputTokenDetails.cacheWriteTokens` |
| Bedrock Converse | `usage.inputTokens` (đã không gồm cache) | `usage.outputTokens` | `usage.cacheReadInputTokens` | `usage.cacheWriteInputTokens` |
| Ollama `/api/chat` | `prompt_eval_count` | `eval_count` | không có | không có |
| Cohere v2 chat | `usage.billed_units.input_tokens` | `usage.billed_units.output_tokens` | không có | không có |
| Hãng khác | đọc tài liệu của hãng, ghi phần đầu vào tính giá thường | đầu ra của hãng | phần đọc cache | phần ghi cache |

Streaming: Anthropic gửi usage trong `message_start` và `message_delta` cuối; OpenAI Chat Completions chỉ gửi usage ở mẩu cuối khi có `stream_options: {"include_usage": true}`; Gemini gửi `usageMetadata` kèm mẩu cuối.

## Ghi file

Cuối mỗi lượt, nối thêm một dòng vào file trên máy chạy dự án. Mỗi tiến trình ghi trọn dòng (một lệnh ghi cho một dòng) hoặc ghi file riêng. Ghi lỗi không bao giờ được làm hỏng dự án.

## Ánh xạ sang OpenTelemetry

Mỗi trường có tên tương ứng trong OpenTelemetry GenAI, để sau này chuyển dữ liệu sang đó được; bản này chưa gửi OTLP. Tên đã kiểm ngày 2026-11-19 ở [open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai), nơi chúng vẫn ở mức Development.

| Ở đây | OpenTelemetry GenAI |
|---|---|
| `provider` | `gen_ai.provider.name` |
| `model` | `gen_ai.response.model` |
| `input` + `cacheRead` + `cacheWrite` | `gen_ai.usage.input_tokens` |
| `output` | `gen_ai.usage.output_tokens` |
| `cacheRead` | `gen_ai.usage.cache_read.input_tokens` |
| `cacheWrite` | `gen_ai.usage.cache_write.input_tokens` |
| `durationMs` | `gen_ai.client.operation.duration` (ở đó tính bằng giây, và cho từng lần gọi chứ không cho cả lượt) |
| `ttftMs` | chưa có tên phía client; gần nhất là số đo phía máy chủ `gen_ai.server.time_to_first_token` |
