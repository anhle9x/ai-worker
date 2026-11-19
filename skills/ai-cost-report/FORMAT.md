# ai-meter line format, version 1

[Tiếng Việt](FORMAT.vi.md) | English <!-- i18n-allow -->

An AI project or application writes one JSON object per line (JSON Lines, UTF-8) for each user turn: everything it did to answer one request from its user, with any LLM provider. `meter/ai_meter.py` and `meter/ai-meter.cjs` write it for Python and Node; a project in another language writes the same line itself. `report.py` reads it.

## What a line never holds

No question, answer, prompt or document text; no user id, name, email or IP; no error message; no free-form label. Only the fields below. The report drops any other field without reading it.

## A line

```json
{"v":1,"turnId":"3f9c0a7d5be14c21","at":"2026-11-20T08:15:02.481Z","durationMs":2140,"ttftMs":610,"outcome":"ok","env":"prod",
 "models":[{"provider":"anthropic","model":"claude-sonnet-5-5","calls":2,"errors":0,"retries":1,"unmeasured":0,
            "input":1830,"output":412,"cacheRead":5120,"cacheWrite":0,"cacheWriteLong":0}]}
```

(Written on one line in the file.)

| Field | Type | Meaning |
|---|---|---|
| `v` | 1 | Format version |
| `turnId` | 16 to 64 lowercase hex characters, random | Lets the report drop a line it has already read. Not tied to the user |
| `at` | ISO 8601 time in UTC, with `Z` | When the turn started (wall clock) |
| `durationMs` | whole number ≥ 0 | From the start of the turn to its end, measured with a monotonic clock (`time.monotonic`, `performance.now`, `System.nanoTime`, `time.Since`), never by subtracting two wall-clock times |
| `ttftMs` | whole number, optional | Streaming only: from the start of the turn to the first piece of the answer. At most `durationMs` |
| `outcome` | `ok`, `error` or `timeout` | How the turn ended for the user |
| `env` | `prod` or `test` | Trial runs use `test` and stay out of the production report |
| `models` | list, at most 50 | One entry per provider and model used in the turn; empty when the turn made no LLM call |

Each entry of `models`:

| Field | Type | Meaning |
|---|---|---|
| `provider` | a short name matching `^[a-z0-9][a-z0-9_.-]{0,31}$`, such as `anthropic`, `openai`, `google`, `deepseek`, `openrouter`, `ollama`, `vllm` | Who served the model. Anything else: write `other`. A model that runs on the team's own machines uses `local`, `ollama`, `vllm`, `llamacpp`, `lmstudio`, `localai`, `tgi` or `sglang` (the report counts no API cost for it), or a name the price file lists |
| `model` | matches `^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$` | The model name the API returned, else the one requested. Anything else: write `unknown` |
| `calls` | whole number | LLM calls to this model in the turn, failed ones and retries included |
| `errors` | whole number ≤ `calls` | Calls that failed (no answer) |
| `retries` | whole number ≤ `calls` | Calls that repeated a failed or timed-out call |
| `unmeasured` | whole number ≤ `calls` | Calls that answered but whose answer carried no token counts |
| `input` | whole number, or `null` | Input tokens billed at the normal input price: not read from the cache, not written to it |
| `output` | whole number, or `null` | Output tokens, thinking tokens included |
| `cacheRead` | whole number, optional | Input tokens read from the cache |
| `cacheWrite` | whole number, optional | Input tokens written to the cache, at any lifetime |
| `cacheWriteLong` | whole number ≤ `cacheWrite`, optional | The part of `cacheWrite` kept longer (Anthropic 1 hour, OpenAI 12 hours), which costs more |

`input` and `output` are `null` together when no answered call carried token counts: the tokens are unknown, and `null` says so. Never write `0` for a number you did not get. A missing cache field means 0.

## Reading token counts

Take them from the `usage` the provider returned with each answer; never estimate them from the length of the text. Each input token is counted once:

| Provider | `input` | `output` | `cacheRead` | `cacheWrite` (`cacheWriteLong`) |
|---|---|---|---|---|
| Anthropic | `usage.input_tokens` (already excludes the cache) | `usage.output_tokens` | `usage.cache_read_input_tokens` | `usage.cache_creation_input_tokens` (`usage.cache_creation.ephemeral_1h_input_tokens`) |
| OpenAI, Responses | `usage.input_tokens` − cached − written | `usage.output_tokens` | `usage.input_tokens_details.cached_tokens` | `usage.input_tokens_details.cache_write_tokens` (`…cache_write_tokens_details.ttl_12h_tokens`) |
| OpenAI, Chat Completions | `usage.prompt_tokens` − cached − written | `usage.completion_tokens` | `usage.prompt_tokens_details.cached_tokens` | `usage.prompt_tokens_details.cache_write_tokens`, when present |
| Gemini | `usageMetadata.promptTokenCount` − cached | `candidatesTokenCount` + `thoughtsTokenCount` | `usageMetadata.cachedContentTokenCount` | none |
| APIs that copy OpenAI's Chat Completions (Azure OpenAI, DeepSeek, Mistral, Groq, OpenRouter, xAI Grok, vLLM, LM Studio, Ollama's `/v1`...) | as OpenAI Chat Completions | `usage.completion_tokens`, plus `completion_tokens_details.reasoning_tokens` when `total_tokens` shows they were left out of it (xAI does this: its example has 32 + 9 + 110 = 151) | `prompt_tokens_details.cached_tokens`, or DeepSeek's `prompt_cache_hit_tokens` | as OpenAI, when present |
| Vercel AI SDK (`generateText` and the like) | `usage.inputTokenDetails.noCacheTokens`, else `inputTokens` − cache read − cache write | `usage.outputTokens` | `inputTokenDetails.cacheReadTokens` | `inputTokenDetails.cacheWriteTokens` |
| Bedrock Converse | `usage.inputTokens` (already excludes the cache) | `usage.outputTokens` | `usage.cacheReadInputTokens` | `usage.cacheWriteInputTokens` |
| Ollama `/api/chat` | `prompt_eval_count` | `eval_count` | none | none |
| Cohere v2 chat | `usage.billed_units.input_tokens` | `usage.billed_units.output_tokens` | none | none |
| Any other provider | read its documentation, and write the input billed at the normal price | its output | its cache reads | its cache writes |

Streaming: Anthropic sends usage in `message_start` and the final `message_delta`; OpenAI Chat Completions sends it in the last chunk only with `stream_options: {"include_usage": true}`; Gemini sends `usageMetadata` with the last chunk.

## Writing the file

Append one line per turn, at the end of the turn, to a file on the machine that runs the project. Each process writes whole lines (one write call per line) or its own file. A failure to write must never break the project.

## Sending to the AI Worker board

`POST https://<board domain>/projects/ingest` with `Authorization: Bearer <key>` and `Content-Type: application/json`, body `{"turns": [line, line, ...]}`: at most 500 turns and 256 KB. Send from the project's server, never from a browser (a request with an `Origin` header is refused). The answer is `{"accepted": n, "duplicates": n, "refused": n, "overDailyLimit": n}`; a turn already sent is counted as a duplicate, so sending again after a timeout is safe. 429 means wait (`Retry-After`), 401 means the key is wrong or revoked. Keep writing the file too.

## How it maps to OpenTelemetry

Each field has an OpenTelemetry GenAI name, so the data can move there later; this version does not send OTLP. Names checked on 2026-11-19 in [open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai), where they are still marked Development.

| Here | OpenTelemetry GenAI |
|---|---|
| `provider` | `gen_ai.provider.name` |
| `model` | `gen_ai.response.model` |
| `input` + `cacheRead` + `cacheWrite` | `gen_ai.usage.input_tokens` |
| `output` | `gen_ai.usage.output_tokens` |
| `cacheRead` | `gen_ai.usage.cache_read.input_tokens` |
| `cacheWrite` | `gen_ai.usage.cache_write.input_tokens` |
| `durationMs` | `gen_ai.client.operation.duration` (seconds there, and per call rather than per turn) |
| `ttftMs` | no client-side name yet; the nearest is the server metric `gen_ai.server.time_to_first_token` |
