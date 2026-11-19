[Tiếng Việt](AI-PROJECTS.vi.md) | English <!-- i18n-allow -->

# Measure an AI project or application

For a team that built a project or application calling an LLM (a chatbot, a price check, a document reader...) and needs a cost and performance report. The meter comes with the `ai-cost-report` skill of this plugin.

The meter writes **counts and times only**: how long each turn took, how it ended, which model was called how many times, how many tokens. It **never** writes a question, an answer, a user's name or id, or an error message. It works with any LLM provider.

There are two ways to use it:

- **On its own:** the meter writes a file next to the project, and the skill turns that file into a report on your computer. No server needed. Steps 2, 3 and 6.
- **With an AI Worker board:** the meter also sends each turn to your board, where admins and viewers read and download the report. Steps 1 to 6.

The quickest way: open Claude Code in the project's code folder and type `/ai-worker:ai-cost-report`. Claude finds where the project calls an LLM and shows each line it would add before changing anything. The steps below are the same work done by hand.

---

## Step 1. Make a key for the project (only with a board)

- **Where:** your AI Worker board, the **Admin** page, section **AI projects and applications**. The section is there only when the server has `AI_PROJECTS=1` ([INSTALL.md](INSTALL.md#ai-projects-and-applications-optional)).
- **Do:** type the project's name, click **Make a key**, enter your OTP code.
- **Right result:** two lines, shown once:
  ```
  AI_METER_URL=https://<board domain>/projects/ingest
  AI_METER_KEY=prj_…
  ```
  `<board domain>` is the domain of the server that runs your AI Worker board, the one in the browser's address bar when you open it, for example `https://board.example.com/projects/ingest`. The Admin page writes it in for you. Copy both now. Do not send the key by chat, email or screenshot.

## Step 2. Copy the meter into the project

- **Where:** a terminal on the computer that has the project's code.
- **Do:** pick the project's language and copy its file into the code folder. Each one is a single file with nothing to install, and writes the same line as the others.

  | Language | File to copy | Needs | Reads the provider's answer itself | Sends to the board |
  |---|---|---|---|---|
  | Python | `ai_meter.py` | Python 3.8+ | yes | yes |
  | JavaScript (Node) | `ai-meter.cjs` | Node 18+ | yes | yes |
  | TypeScript | `ai-meter.cjs` and `ai-meter.d.cts`, side by side | Node 18+ (tested with TypeScript 5.9) | yes | yes |
  | C# | `AiMeter.cs` | .NET 6+ | yes | yes |
  | Go | `aimeter.go`, in a folder `aimeter/` | Go 1.21+ | yes | yes |
  | Java, Kotlin and other JVM languages | `AiMeter.java`, in a folder `aimeter/` | Java 11+ | yes | yes |
  | Rust | `ai_meter.rs`, in `src/` | Rust 1.63+ | no: you pass the token counts | no: file only |
  | C or C++ | `ai_meter.h` | C99 or C++11 | no: you pass the token counts | no: file only |

  - From the plugin installed by the package (Mac, Linux; on Windows the folder is `%USERPROFILE%\claude-plugins-ai-worker`). First name the folder that holds the meters:
    ```bash
    M=~/claude-plugins-ai-worker/ai-worker/skills/ai-cost-report/meter
    ```
    Then the line for your language, with `<project folder>` being the folder of the project's code:
    ```bash
    cp "$M/ai_meter.py" <project folder>/
    ```
    ```bash
    cp "$M/ai-meter.cjs" <project folder>/
    ```
    ```bash
    cp "$M/ai-meter.cjs" "$M/ai-meter.d.cts" <project folder>/src/
    ```
    ```bash
    cp "$M/AiMeter.cs" <project folder>/
    ```
    ```bash
    mkdir -p <project folder>/aimeter && cp "$M/aimeter.go" <project folder>/aimeter/
    ```
    ```bash
    mkdir -p <project folder>/src/main/java/aimeter && cp "$M/AiMeter.java" <project folder>/src/main/java/aimeter/
    ```
    ```bash
    cp "$M/ai_meter.rs" <project folder>/src/
    ```
    ```bash
    cp "$M/ai_meter.h" <project folder>/
    ```
  - Or download it from this repository, at the version you run (here `v0.47.0`), in the folder where the file goes:
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.47.0/skills/ai-cost-report/meter/ai_meter.py
    ```
    Change the file name at the end for the other languages: `ai-meter.cjs`, `ai-meter.d.cts`, `AiMeter.cs`, `aimeter.go`, `AiMeter.java`, `ai_meter.rs` or `ai_meter.h`.
  - Another language (PHP, Ruby, Swift...): there is no file to copy yet, so the project's own code does what the meter does. After each request of a user, append one line of JSON to the file `ai-meter.jsonl`: how long the request took, how it ended, and for each model called, the provider, the model's name, how many calls and the token counts the provider returned. One line looks like this:
    ```json
    {"v":1,"turnId":"3f9c0a7d5be14c21","at":"2026-11-20T08:15:02.481Z","durationMs":2140,"outcome":"ok","env":"prod","models":[{"provider":"openai","model":"gpt-6.1-terra","calls":1,"errors":0,"retries":0,"unmeasured":0,"input":1830,"output":412,"cacheRead":0,"cacheWrite":0}]}
    ```
    `turnId` is 16 random hex characters, new for each request; `at` is when the request started, in UTC. Never put the question, the answer or the user in it. Every field and where to read each token count for each provider: [FORMAT.md](../skills/ai-cost-report/FORMAT.md). The skill and the board read this file the same way as the one a meter writes.
- **Right result:** the file of your language sits next to the code (for Go, `aimeter/aimeter.go`; for Java, `src/main/java/aimeter/AiMeter.java`; for Rust, `src/ai_meter.rs`), and the project still builds.

## Step 3. Wrap each request of a user

- **Where:** the code that handles one request: where the user's question comes in and the LLM is called.
- **Do:** make the meter once when the program starts, then wrap the work of each request. Find your language below.

### Python

```python
from ai_meter import Meter
meter = Meter("ai-meter.jsonl")          # once, at the top of the file

# in the function that handles each request:
with meter.turn() as t:                  # or: async with meter.turn() as t:
    resp = client.messages.create(...)   # the LLM call you already have
    t.record(resp)                       # add this after EACH LLM call
```

An error inside `with` is written as `error` (or `timeout`) and raised again as it was.

### JavaScript (Node)

```js
const { Meter } = require('./ai-meter.cjs')   // or, in an ES module: import { Meter } from './ai-meter.cjs'
const meter = new Meter({ file: 'ai-meter.jsonl' })

// in the function that handles each request:
const answer = await meter.turn(async (t) => {
  const resp = await client.chat.completions.create(...)
  t.record(resp)
  return resp
})
```

`meter.turn` returns what your function returns, and throws again what it throws. When the work does not fit in one function, use `const t = meter.start()` and call `t.end()` (or `t.end('error')`) yourself.

### TypeScript

Keep the two files side by side with these names: TypeScript finds the types of `ai-meter.cjs` in `ai-meter.d.cts`.

```ts
import { Meter } from './ai-meter.cjs'
const meter = new Meter({ file: 'ai-meter.jsonl' })

const answer = await meter.turn(async (t) => {
  const resp = await client.messages.create(...)
  t.record(resp)
  return resp
})
```

The same calls as JavaScript, now checked: `env` can only be `'prod'` or `'test'`, token counts must be numbers. It works whatever the project's `module` setting (`commonjs`, `node16`, `nodenext`, `bundler`, `preserve`) and in a project with `"type": "module"`.

### C#

```csharp
// once, when the program starts; in ASP.NET Core: builder.Services.AddSingleton(new AiMeter.Meter("ai-meter.jsonl"));
var meter = new AiMeter.Meter("ai-meter.jsonl");

// in the code that handles each request:
using (var t = meter.Turn())
{
    try
    {
        var res = await http.PostAsync(url, content);           // the LLM call you already have
        var body = await res.Content.ReadAsStringAsync();
        t.Record(body);                                         // the provider's answer, as JSON text
    }
    catch (TaskCanceledException) { t.Outcome = "timeout"; throw; }
    catch { t.Outcome = "error"; throw; }
}                                                               // the line is written here

await meter.FlushAsync();                                       // before the program ends, when it sends to a board
```

- `t.Record(...)` takes the answer as JSON text or as a `JsonElement` already read. For a provider other than Anthropic, OpenAI and Gemini, give its name: `t.Record(body, provider: "deepseek")`.
- When an SDK gives you an object rather than JSON, read the numbers from its usage and call `t.Count("openai", "gpt-6.1-terra", input: 1530, output: 412, cacheRead: 300)`.
- Unlike Python, an exception does not set the outcome by itself: set `t.Outcome` in `catch` as above.

### Go

```go
import "example.com/yourproject/aimeter"   // the module name in your go.mod, then /aimeter

var meter = aimeter.New("ai-meter.jsonl", "prod")   // once

func main() {
	defer meter.Close()   // sends what is still waiting, when it sends to a board
	// ...
}

// in the handler of each request:
t := meter.Turn()
defer t.End()                     // the line is written when the handler returns
res, err := http.DefaultClient.Do(req)   // the LLM call you already have
if err != nil {
	t.Fail("openai", "gpt-6.1-terra", false)
	t.SetOutcome("error")
	return
}
body, _ := io.ReadAll(res.Body)
t.Record(body)                    // the provider's answer, as JSON bytes
```

- For a provider other than Anthropic, OpenAI and Gemini, give its name: `t.RecordWith(body, aimeter.Opt{Provider: "deepseek"})`. A call that repeats a failed one: `aimeter.Opt{Retry: true}`.
- When an SDK gives you a struct rather than JSON, read the numbers from its usage and call `t.Count("openai", "gpt-6.1-terra", &aimeter.Counts{Input: 1530, Output: 412, CacheRead: 300})`; `nil` in place of the counts means not measured.
- The board's address and key: `aimeter.NewSending(path, env, url, key)`, or the variables of step 4.

### Java, Kotlin and other JVM languages

Java 11 has no JSON reader of its own, so `AiMeter.java` carries a small one: `record` takes the provider's answer as JSON text, as most HTTP clients give it, or as a `Map` already parsed by Jackson or Gson. Sending to the board uses `java.net.http`, which comes with Java 11.

```java
import aimeter.AiMeter;

AiMeter meter = new AiMeter("ai-meter.jsonl");   // once, when the program starts

// in the code that handles each request:
String answer = meter.turn(t -> {
    HttpResponse<String> res = http.send(request, HttpResponse.BodyHandlers.ofString());   // the LLM call you already have
    t.record(res.body());                        // the provider's answer, as JSON text
    return res.body();
});
```

`meter.turn(t -> ...)` returns what your code returns and throws again what it throws; an exception whose name says timeout (`HttpTimeoutException`, `SocketTimeoutException`...) is written as `timeout`, any other as `error`. Where a lambda does not fit, use `try (AiMeter.Turn t = meter.turn()) { ... }` and call `t.setOutcome("error")` in `catch` yourself.

Spring Boot: make the meter a bean, so it is closed (and what waits is sent) when the application stops.

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

Kotlin (and Scala, Groovy...) calls the same class:

```kotlin
import aimeter.AiMeter

val meter = AiMeter("ai-meter.jsonl")

meter.turn().use { t ->
    val body = http.send(request, HttpResponse.BodyHandlers.ofString()).body()
    t.record(body)
}
```

- For a provider other than Anthropic, OpenAI and Gemini, give its name: `t.record(body, "deepseek")`. A call that repeats a failed one: `t.record(body, provider, null, true)`.
- An SDK object: read the numbers from its usage and call `t.count("openai", "gpt-6.1-terra", 1530L, 412L)`, or `t.count(provider, model, input, output, cacheRead, cacheWrite, cacheWriteLong, retry)`; `null` for input or output means not measured.
- A failed call: `t.fail(provider, model)`; streaming: `t.firstToken()`. The board's address and key: `new AiMeter(file, env, sendUrl, sendKey)`, or the variables of step 4. Call `meter.close()` before the program ends (Spring does it for the bean above).
- The meter's package is `aimeter`: keep the file in a folder `aimeter/` of the source path, or change the first line to your own package.

### Rust

Rust has no JSON reader of its own, so the meter takes the token counts your client already parsed. It writes the file only.

```rust
mod ai_meter;   // in main.rs or lib.rs
use ai_meter::{Counts, Meter};
use std::sync::OnceLock;

static METER: OnceLock<Meter> = OnceLock::new();

// in the handler of each request:
let meter = METER.get_or_init(|| Meter::new("ai-meter.jsonl", "prod"));
let mut t = meter.turn();
// after each LLM call, from the usage in its answer (Anthropic here: input_tokens has no cache in it)
t.count("anthropic", "claude-sonnet-5-5", Some(Counts {
    input: u.input_tokens,
    output: u.output_tokens,
    cache_read: u.cache_read_input_tokens,
    ..Default::default()
}));
// an answer with no token counts: t.count("anthropic", "claude-sonnet-5-5", None);
t.end();   // or let t go out of scope; a panic writes "error"
```

- `input` is the input billed at the normal price, without cache reads and writes. For OpenAI and the APIs that copy it, that is `prompt_tokens - cached_tokens`. The table in [FORMAT.md](../skills/ai-cost-report/FORMAT.md#reading-token-counts) gives each provider's fields.
- A failed call: `t.fail(provider, model, false)`; a retry: `t.count_with(..., true)`; streaming: `t.first_token()`; a timeout: `t.set_outcome("timeout")`.
- To reach a board, send the file's lines from your own HTTP client as [FORMAT.md](../skills/ai-cost-report/FORMAT.md#sending-to-the-ai-worker-board) says, or make the report from the file with the skill.

### C or C++

C and C++ have no JSON reader of their own, so the meter takes the token counts your JSON library already read. It writes the file only.

```c
#include "ai_meter.h"   /* on Linux, before the other headers (or compile with -D_POSIX_C_SOURCE=200809L) */

static ai_meter meter;

int main(void) {
    ai_meter_init(&meter, "ai-meter.jsonl", "prod");   /* once */
    /* ... */
}

/* in the code that handles each request: */
void handle_request(void) {
    ai_turn t;
    ai_turn_begin(&t, &meter);
    /* after each LLM call: provider, model, input, output, cache read, cache write, longer cache write */
    ai_turn_count(&t, "openai", "gpt-6.1-terra", prompt_tokens - cached_tokens, completion_tokens, cached_tokens, 0, 0);
    /* an answer with no token counts: -1 for input and output */
    ai_turn_end(&t);
}
```

- The same functions work from C++ (C++11 or newer); the header compiles with `-Wall -Wextra -Werror`.
- A failed call: `ai_turn_fail(&t, provider, model, 0)`; a retry: `ai_turn_count_retry(..., 1)`; streaming: `ai_turn_first_token(&t)`; a timeout: `ai_turn_set_outcome(&t, "timeout")`.
- One `ai_turn` belongs to one thread. A turn holds at most 16 different models; more are left out.
- To reach a board, send the file's lines from your own HTTP client as [FORMAT.md](../skills/ai-cost-report/FORMAT.md#sending-to-the-ai-worker-board) says, or make the report from the file with the skill.

### React, Next.js and other web front ends

There is no meter for the browser, on purpose. The LLM must be called from the project's server, never from code that runs in the browser: the provider's API key would be in the page for anyone to copy, and so would the board's key (the board refuses requests from a browser anyway). Put the meter where the LLM is called: a Next.js Route Handler or API route, a Server Action, an Express or Fastify route, a Remix or SvelteKit server function. There, use the JavaScript or TypeScript meter above.

A Next.js Route Handler, with `ai-meter.cjs` and `ai-meter.d.cts` copied into `lib/`:

```ts
// app/api/ask/route.ts: runs on the server, never in the browser
import { Meter } from '@/lib/ai-meter.cjs'

export const runtime = 'nodejs'   // the meter writes a file: Node, not the Edge runtime
const meter = new Meter({ file: process.env.AI_METER_FILE ?? 'ai-meter.jsonl' })

export async function POST(req: Request) {
  const { question } = await req.json()
  const resp = await meter.turn(async (t) => {
    const r = await client.messages.create({ model: 'claude-sonnet-5-5', max_tokens: 1024, messages: [{ role: 'user', content: question }] })
    t.record(r)
    return r
  })
  await meter.sender?.flush()      // on a serverless host, send before the function is frozen
  return Response.json({ answer: resp.content })
}
```

A Server Action is the same: wrap the LLM call inside the `'use server'` function with `meter.turn(...)`.

- On a serverless host (Vercel, Netlify, AWS Lambda...) the disk is wiped between runs: set `AI_METER_FILE=/tmp/ai-meter.jsonl`, send to a board (step 4), and call `await meter.sender?.flush()` before answering, as above.
- The meter on the server measures the server's time: from the request arriving to the answer leaving, and the first streamed piece with `t.firstToken()`. What the user sees adds the network and the page's own drawing. To measure that, measure it in the browser (for example `performance.now()` from the click to the first word shown) and send only the number of milliseconds to the project's own backend, which keeps it in its own logs. Never put a key in the page for this; the meter's lines do not hold that number.

### For every language

- A request that calls an LLM several times (read a photo, then answer) records or counts each call.
- `record` (`Record` in C# and Go, `record` in Java) reads the answers of Anthropic, OpenAI, Gemini, xAI Grok, every API that copies OpenAI's shape (DeepSeek, Mistral, Groq, OpenRouter, Azure OpenAI, vLLM, LM Studio...), Bedrock, Cohere, Ollama and the Vercel AI SDK. For a provider other than the first three, give its name: `t.record(resp, provider="deepseek")`.
- Any other provider: read the token counts from its answer as its documentation says, and call `count` (`t.count("provider", "model-name", input=..., output=...)` in Python).
- Streaming answers: call `first_token()` (`firstToken()` in Node and Java, `FirstToken()` in C# and Go) when the first piece arrives. OpenAI and many APIs that copy it send token counts while streaming only with `stream_options={"include_usage": True}`; without it the turn is written as "not measured".
- A failed call: `fail(provider, model)`. Never pass the error text.
- A problem in the meter never breaks the project.
- **Right result:** after one question, the file `ai-meter.jsonl` appears next to the project, one line per turn, with numbers only.

## Step 4. Set the key so turns go to the board (only with a board)

- **Where:** the environment of the project's **server**: its `.env` file, the environment settings of the cloud service, or the start command. **Never** in code that runs in a browser or a phone app: the board refuses requests from a browser, and a key in an app can be copied out.
- **Do:** add the two lines from step 1. While trying it out, add `AI_METER_ENV=test` as well.
- **Right result:** restart the project, ask a few questions, wait about 10 seconds. On the board, click **AI projects** on the home page, pick the project and **Trial runs (test)**: the number of turns has grown by the number of questions.

The meter sends in batches in the background and never makes the project wait. It sends the key only over HTTPS, or to the same machine. The file is still written.

## Step 5. Only for a project on a cloud server (only with a board)

The board usually answers only inside your office networks. A project on a cloud server is outside them.

- **Where:** the board's server, the file `aiworker.caddy` (whoever has SSH to it).
- **Do:** uncomment the block that starts "Only for an AI project or application that runs on a cloud server", put the project's IP in place of `192.0.2.10`, and use that block in place of the two lines at the top that keep other IPs out. Run `caddy validate`, then `sudo systemctl reload caddy`.
- **Right result:** `caddy validate` reports no error, and the check in step 4 shows the turns.

A project that runs inside your office network skips this step.

## Step 6. Run it for real and get the report

- **Do:** remove `AI_METER_ENV=test`, restart, and let real users use the project for the period you report on.
- **With a board:** click **AI projects**, pick the days and **Real users (prod)**, then **Open the print version** (it opens in a new tab: press Ctrl+P, ⌘P on a Mac, and choose **Save as PDF**) or **Download CSV**.
- **Without a board:** in Claude Code, type `/ai-worker:ai-cost-report` and give it the `ai-meter.jsonl` file.
- **Right result:** a report with the number of turns, LLM calls and tokens per turn, cost per turn and an estimate for 1,000 turns, average, 95th percentile and slowest time, by model.

## Your own board, or another one

The meter is not tied to any board: it sends to the address in `AI_METER_URL`, and to nothing when that is empty.

- A key works only on the board that made it.
- The board must run AI Worker 0.45.0 or newer, with `AI_PROJECTS=1`.
- Turns go only to the board named in `AI_METER_URL`. Leave both variables out to keep everything on the project's machine and make the report there.

## Reading the report

- These are numbers the project measured, not a bill. What was charged is on the provider's billing page.
- A turn whose answer carried no token counts says "not measured"; a model with no price says "no price". Neither is counted as zero. Prices for other providers, or a negotiated price, go in a price file of your own: `--add-prices` for the skill, **Prices of your own** on the board's Admin page.
- A model that runs on your own machines (Ollama, vLLM...) says "runs on own machine, no API cost". Its tokens and times are there; the cost of the machines is not.
- On the board, each turn is kept 30 days, so the 95th percentile covers the last 30 days at most; totals per day are kept 13 months.
- "If the same tokens went to another model" is only an estimate. For a real comparison, run the project on that model with `AI_METER_ENV=test` and read the test report.
