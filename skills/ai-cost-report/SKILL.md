---
name: ai-cost-report
description: "Measure the cost and speed of an AI project or application your team built, with any LLM provider, and make a report of it. Adds a small meter to the project (one copied file for Python or Node, or the line format for any other language), then turns what it wrote into an HTML page that prints to PDF and a CSV, with turns, LLM calls and tokens per turn, cost per turn and per 1,000 turns, average, p95 and slowest time, by model. Use when the user types /ai-cost-report, asks for a cost and performance report of their own AI project or application, or wants to know what its LLM calls cost. Not for the cost of Claude Code itself (the office page shows that). Đo chi phí và tốc độ của một dự án hay ứng dụng AI do nhóm tự làm, với bất kỳ hãng LLM nào, rồi làm báo cáo. Gắn một bộ đo nhỏ vào dự án (chép một file cho Python hay Node, hoặc theo định dạng dòng cho ngôn ngữ khác), rồi biến số đo thành trang HTML in ra PDF được và file CSV: số lượt, số lần gọi LLM và token mỗi lượt, tiền mỗi lượt và mỗi 1.000 lượt, thời gian trung bình, p95, chậm nhất, theo model. Dùng khi người dùng gõ /ai-cost-report, nhờ làm báo cáo chi phí và hiệu năng cho dự án hay ứng dụng AI của họ, hoặc muốn biết các lần gọi LLM tốn bao nhiêu. Không dùng cho chi phí của chính Claude Code (trang văn phòng đã có)."
---

# Cost and speed report for an AI project or application

Answer in the user's language and make the report in it (`--lang vi` for Vietnamese, `--lang en` otherwise). Call the thing being measured "the AI project or application", in Vietnamese too (the words the report's Vietnamese labels use), not "the app".

The numbers come from the project itself: each LLM answer carries token counts (`usage`), and the meter adds them up per user turn with the time it took. The meter never writes a question, an answer, a user id or an error message. Say this in the report and to the user: these are numbers the project measured, not a bill.

Files in this skill's folder (`<SKILL_DIR>` below):
- `meter/ai_meter.py`: the meter for Python 3.8+, standard library only.
- `meter/ai-meter.cjs`: the meter for Node 18+, no package; works with `require` and `import`.
- `FORMAT.md`: the line format, for a project in any other language (Go, Java, C#, PHP, Ruby...), and the table of which `usage` fields each provider returns.
- `prices.json`: list prices from the pricing pages of Anthropic, OpenAI, Google and xAI (Grok), with the page and the day they were read.
- `my-prices.example.json`: the shape of a price file of the user's own.
- `report.py`: makes the report.

## 1. Find out about the project
Ask once, only what you cannot see in the code: where the code is, which LLM providers it calls (any provider: the meter is not tied to one), whether answers stream, and whether a model runs on the team's own machines. Read the code to find each place that calls an LLM and the place where one user request starts and ends (a web route, a chat handler, a job).

## 2. Add the meter (only with the user's yes)
Show the change first; edit the project only when the user agrees. Do not commit in the project's repository.
- **Python**: copy `meter/ai_meter.py` into the project. Wrap each user request:
  ```python
  from ai_meter import Meter
  meter = Meter("ai-meter.jsonl", env="prod")   # one per process

  with meter.turn() as t:            # or: async with meter.turn() as t:
      resp = client.messages.create(...)
      t.record(resp)                 # once per LLM call, with the whole response
  ```
- **Node / TypeScript**: copy `meter/ai-meter.cjs`. `const { Meter } = require('./ai-meter.cjs')` (or `import { Meter } from './ai-meter.cjs'`), then `await meter.turn(async (t) => { const r = await client...; t.record(r); return r })`, or `const t = meter.start()` ... `t.end()`.
- **Any other language**: write one line per turn as `FORMAT.md` says.

Which call to use for each LLM call:
- `t.record(resp)` reads the answers of Anthropic, OpenAI (Chat Completions and Responses), every API that copies OpenAI's shape (Azure OpenAI, DeepSeek, Mistral, Groq, OpenRouter, xAI Grok, vLLM, LM Studio, Ollama's `/v1`...), the Vercel AI SDK, Gemini, Bedrock Converse, Ollama's own `/api/chat` and Cohere v2. Pass `provider="..."` (`{ provider: '...' }` in Node) when the provider is not one of the first ones, so the report names it: a short lowercase name such as `deepseek`, `openrouter`, `vllm`.
- `t.count(provider, model, input=..., output=..., cache_read=..., cache_write=...)` (`t.count(provider, model, { input, output, cacheRead, cacheWrite })` in Node) for any other provider: read the numbers from its answer by its own documentation. `input` is the input billed at the normal price, without cache reads and writes. Leave `input`/`output` out when the answer has none: the call is then "not measured".
- Never compute tokens from text length.
- Streaming: call `t.first_token()` (`t.firstToken()` in Node) when the first piece arrives, and `record()` the final message or the last event that carries usage. OpenAI Chat Completions and many APIs that copy it only send usage when streaming with `stream_options={"include_usage": True}`; add it, or the call is written as "not measured".
- A failed call: `t.fail(provider, model)`. A call that repeats a failed one: pass `retry=True` (`{ retry: true }` in Node). Never pass error text.
- Set `env="test"` (or `AI_METER_ENV=test`) for trial runs, so they stay out of the production report.
- The file stays on the machine that runs the project. `AI_METER_FILE` moves it; `AI_METER_OFF=1` turns the meter off. The meter never stops the project: its own errors are swallowed.
- On a server with several processes, give each process its own file (for example with the process id in the name); the report reads many files and drops a turn it has already seen.

## 3. Make the report
When the project has run with real users for the period to report, get the JSONL file(s) and run:
```bash
python3 "<SKILL_DIR>/report.py" ai-meter.jsonl --out report --lang vi
```
Options: `--env test|all` (default `prod`), `--from 2026-11-20 --to 2026-11-29` (UTC days), `--compare MODEL ...` (see below), `--add-prices my-prices.json` (the user's own prices, on top of `prices.json`; can be given more than once), `--title "..."`.

The user's own price file has the shape of `my-prices.example.json`: models with a price (their models replace ours, so a negotiated price wins), `"local": true` on a model that runs on their own machines, and `localProviders` for a provider name that always does. Write a price only from the provider's pricing page or the user's contract; never guess. The providers `local`, `ollama`, `vllm`, `llamacpp`, `lmstudio`, `localai`, `tgi` and `sglang` count as the team's own machines when the model has no price.

It writes `ai-cost-report.html` and `ai-cost-report.csv` and prints a short summary as JSON. Open the HTML page in a browser and print it to PDF if a PDF is needed.

## 4. Tell the user
In a few lines: the period, the number of turns, cost per turn and per 1,000 turns, average and p95 time, and what the report could not count: turns whose answer carried no usage ("not measured", left out, never counted as zero), models with no price ("no price": tokens are shown, cost is not, never counted as zero), models that run on the team's own machines ("runs on own machine, no API cost": tokens and times are shown; the machines' own cost is not in the report), and models that cost more for very long prompts.

"A cheaper model" (`--compare`) only prices the same token counts at another model's price: say it is an estimate. For a real number, run the project with `env=test` on the other model and make a report of those turns with `--env test`.

If `prices.json` is older than a month or a model the project uses has no price, say so, and read the provider's pricing page before quoting a price. Never guess one.
