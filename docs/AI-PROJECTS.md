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
- **Do:** copy one file into the code folder.
  - From the plugin installed by the package (Mac, Linux; on Windows the folder is `%USERPROFILE%\claude-plugins-ai-worker`):
    ```bash
    cp ~/claude-plugins-ai-worker/ai-worker/skills/ai-cost-report/meter/ai_meter.py <project folder>/
    ```
    For Node or TypeScript, the file is `ai-meter.cjs` in the same folder.
  - Or download it from this repository, at the version you run (here `v0.45.2`):
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.45.2/skills/ai-cost-report/meter/ai_meter.py
    ```
    ```bash
    curl -fLO https://raw.githubusercontent.com/anhle9x/ai-worker/v0.45.2/skills/ai-cost-report/meter/ai-meter.cjs
    ```
  - Another language (Go, Java, C#, PHP...): write one line per turn as [FORMAT.md](../skills/ai-cost-report/FORMAT.md) says.
- **Right result:** `ai_meter.py` (Python 3.8+, standard library only) or `ai-meter.cjs` (Node 18+, no package) sits next to the code.

## Step 3. Wrap each request of a user

- **Where:** the code that handles one request: where the user's question comes in and the LLM is called.
- **Do:** make the meter once when the program starts, then wrap the work of each request.

  Python:
  ```python
  from ai_meter import Meter
  meter = Meter("ai-meter.jsonl")          # once, at the top of the file

  # in the function that handles each request:
  with meter.turn() as t:
      resp = client.messages.create(...)   # the LLM call you already have
      t.record(resp)                       # add this after EACH LLM call
  ```

  Node:
  ```js
  const { Meter } = require('./ai-meter.cjs')
  const meter = new Meter({ file: 'ai-meter.jsonl' })

  // in the function that handles each request:
  const answer = await meter.turn(async (t) => {
    const resp = await client.chat.completions.create(...)
    t.record(resp)
    return resp
  })
  ```

- **Good to know:**
  - A request that calls an LLM several times (read a photo, then answer) calls `t.record(...)` after each one.
  - `record` reads the answers of Anthropic, OpenAI, Gemini, xAI Grok, every API that copies OpenAI's shape (DeepSeek, Mistral, Groq, OpenRouter, Azure OpenAI, vLLM, LM Studio...), Bedrock, Cohere, Ollama and the Vercel AI SDK. For a provider other than the first three, give its name: `t.record(resp, provider="deepseek")`.
  - Any other provider: read the token counts from its answer as its documentation says, and call `t.count("provider", "model-name", input=..., output=...)`.
  - Streaming answers: call `t.first_token()` (`t.firstToken()` in Node) when the first piece arrives. OpenAI and many APIs that copy it send token counts while streaming only with `stream_options={"include_usage": True}`; without it the turn is written as "not measured".
  - A failed call: `t.fail(provider, model)`. Never pass the error text.
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
- **With a board:** click **AI projects**, pick the days and **Real users (prod)**, then **Download the report** (open it and **Print** to save a PDF) or **Download CSV**.
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
