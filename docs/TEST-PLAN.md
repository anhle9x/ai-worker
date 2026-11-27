[Tiếng Việt](TEST-PLAN.vi.md) | English <!-- i18n-allow -->

# Test plan

What is tested automatically on every push, what still needs a person, and the checklist before a release.

## 1. Automatic tests

GitHub Actions runs `.github/workflows/test-install.yml` on every push to a public repository, where the minutes are free: every job below runs. In a private repository, such as a development copy, a push runs nothing, since the minutes there count against the account: the tests run on the developer's computer (section 2), and the workflow started by hand (`gh workflow run test-install.yml`) runs every job, the three Windows ones included. A release is made only when every job is green.

| Job | Machine | Checks | Files |
|---|---|---|---|
| `code-check` | Ubuntu | Python lint (ruff); hook tests through the Claude Code CLI; every test module of the server (`python3 -m unittest`, with Node 22 for the one that sends as the plugin does); the Go receiver (`go vet`, `go test`, with the Python server as the judge); the connector for Codex, Cursor and Gemini CLI; the meter for AI projects and applications; the Chrome extension logic against a real local server; where the maps put the office labels | `ruff.toml`, `tests/*.test.ts(x)`, `server/test_webhook.py` and eight more modules of `server/`, `receiver/`, `tests/connectors/test_connectors.py`, `tests/appmeter/test_appmeter.py`, `tests/extension/check-extension.js`, `tests/check-map-layout.js` |
| `build` | Ubuntu | Package build; the private-data check; skill front matter; the two-language rules; the map shader and flight names | `packaging/build.sh`, `tests/test-check-clean.sh`, `tests/check-frontmatter.py`, `tests/check-i18n.py`, `tests/check-maps.py` |
| `ubuntu` | Ubuntu | Installer on a clean machine, case by case; server install with systemd; the Go receiver built for the server, then its installer; menu bar script; the `.deb` installed and removed by apt; notification badge picture | `tests/linux/test-install.sh`, `tests/linux/test-server.sh`, `packaging/build-receiver.sh`, `tests/linux/test-receiver.sh`, `tests/menubar/test-menubar.sh`, `tests/menubar/test-deb.sh` |
| `windows` | Windows | Installer on a clean machine, case by case; the scripts that close and reopen the Claude app after `/update`, in Windows PowerShell 5; the connector's PowerShell hook and installer; icon next to the clock; notification badge picture | `tests/windows/test-install.ps1`, `tests/windows/dump-restart-scripts.mjs`, `tests/windows/test-restart.ps1`, `tests/connectors/test_connectors.py`, `tests/menubar/test-menubar.ps1` |
| `windows-app` | Windows | Build `AI Worker.exe` and `.msi`; install for one user without admin rights; pair; count waiting people; remove | `tests/menubar/test-windows-app.ps1` |
| `plugin-msi` | Windows | Build `AI Worker plugin.msi`; the server fills a company copy; install, the setup window, a plugin updated by `/update`, an upgrade, a refused downgrade, removal, and a personal copy left unfilled | `packaging/windows-msi/`, `tests/windows/test-msi.ps1` |

### What the tests cover

| Area | Covered by |
|---|---|
| Permission of every server path | `test_webhook.py` holds the full route table and fails if a path is added without a permission |
| Login, OTP, lockout after wrong codes, re-entering OTP for account actions | `test_webhook.py` |
| Telegram login: signature, expiry, reuse, linking only with the code and the one-time step, one Telegram per account, the way to Telegram and back | `test_webhook.py`, class `TelegramLogin` |
| Asking from Telegram: which command a message means, the answers in two languages and for both scopes, no private field in any answer | `test_ask.py` |
| Asking from Telegram: who may call the bot's path, pairing a chat, limits, the log, the chat's number opening nothing else, the bot process against a fake Telegram and the real webhook | `test_webhook.py`, class `TelegramAsk` |
| The Telegram bot process: reading, sending, trouble with Telegram or the webhook, nothing secret in its log | `test_telegram_bot.py` |
| The window inside Telegram: Telegram's signature (wrong, old, from another bot, without a user), sessions and their limits, only chats allowed, a chat that reads totals only getting totals and no person, revoking or `/stop` ending a session at once, nothing else opened by a session, the page and its files with `?v=`, the menu buttons the bot is told, the log; and the bot process setting the buttons | `test_webhook.py`, class `TelegramApp`; `test_telegram_bot.py`, class `MenuButtons` |
| Alerts to Telegram chats: each wait once, the gap, the hourly cap, quiet hours, sessions left open, names only for a chat that reads each person, the first line naming nobody, the chat's language and minutes; `/alerts` and the window's settings; the log; the bot sending them protected with the window's button | `test_webhook.py`, classes `AlertRules` and `TelegramAlerts`; `test_telegram_bot.py`, class `MenuButtons` |
| The bot's service after install: off by default, its own user and settings file, the network limit, removal | `tests/linux/test-server.sh`, part S5 |
| The Go receiver's installer (`server/install-receiver.sh`) on a machine with systemd: stops when the IP is missing or another program holds the port, first install (its own user, one capability, the memory ceiling, private settings, no computer moved), run again with nothing changed, update through `install.sh`, a program that does not match `SHA256SUMS` refused, rollback, removal, taking over a service written by hand with or without a settings file of the same name, the first run with questions (the guesses offered, `n` stopping with nothing changed, Enter taking each, a typed answer winning) | `tests/linux/test-receiver.sh` |
| What each role receives (no email or IP for wall) | `test_webhook.py` |
| The optional receiver in Go: the shared sample in both formats, random sends cleaned the same as Python cleans them (keys in order, whole numbers apart from floats), its key check against keys the server issued, sends through the receiver ending in the same book on the real Python server with the name it knows and the real address, a batch sent twice written once, TLS with HTTP/1.1 only and a renewed certificate read again; on the server, the internal paths (404 unless `RECEIVER=1`, from this machine and with the internal code), the file of secrets, the policy, the books by page, the third check and turning the signing secret; the shared sample played through the receiver into the real Python server, each send in a batch of its own and all of them put together into one row per computer, Python ending with the book and the days the sample expects; the rows of one computer put together as Python would write them one by one; Python away a minute while every computer sends, every send answered 200 and at most one row per computer waiting; the hours held as numbers adding up the same; check rows compared and never written, and the hours of today the receiver loads | `receiver/` (`go test ./...`), `server/test_receiver.py` |
| Pairing TV, menu bar and extension; revoke; expiry | `test_webhook.py`, `check-extension.js`, menu bar tests |
| A computer cannot send for another person; send limits | `test_webhook.py` |
| Office labels and pins on the maps: pins that meet are drawn side by side; with many offices the labels with no free place are hidden; no label covers another label, another office's pin or the list of offices, none leaves the frame | `tests/check-map-layout.js` |
| A manager's Claude plugin and the board: pairing by code, reading only the wall view, revoke, unpair, refused network, denied permission | `test_webhook.py` (class `ExtensionPairing`), `tests/board.test.ts` |
| Text for ChatGPT or Gemini: asked about in a permission mode that asks nothing, kept on the computer on a no, sent without a question only under an allow rule | `tests/sending.test.ts`, `tests/workers.test.ts` |
| Handoff notes told to a new session: only files the skill would write, the newest five by name and date, nothing on a computer with none, no note opened by the plugin | `tests/handoff.test.ts` |
| The question before a command that destroys work: which commands are caught and which are left alone, an allowed command turned into a question for a person, a denied one left denied, the switch in `config.js` | `tests/guard.test.ts` |
| What leaves or enters the computer: secrets in text for ChatGPT or Gemini (also through a separate ai-workers server), secrets on the lines a commit adds, pages that speak to an AI, a repository's own AI settings, the 80% context note for Claude, block counts in the device report | `tests/secrets.test.ts`, `commitscan.test.ts`, `injection.test.ts`, `repoconfig.test.ts`, `nudges.test.ts`, `sending.test.ts`, `team.test.ts` |
| The server side of the protections: the audit log's fingerprint chain (a changed, a removed and a newest row taken out), block counts cleaned and added up for admins and viewers only, keys for AI tools unused for 30 days | `test_webhook.py`, classes `AuditChain`, `BlockCounts`, `UnusedKeys` |
| Days of cost totals sealed into the audit chain: each closed day once, empty days too, a line not written tried again, a sealed day whose numbers, tokens or rows changed named by the check, days dropped by age left out, `--forget-usage` sealing again without who; the morning message to an admin's Telegram chat only, once per day, none at night, no name and no money | `test_daily_seal.py`, classes `Sealing`, `MorningMessage` |
| `/ai-worker:voice`: the right settings page and steps for a Mac, Windows and Linux; steps by hand when the page does not open; nothing else is run | `tests/voice.test.ts` |
| The demo with sample people: starts, opens with the code it prints, ignores a real board's settings, deletes its data when stopped | `test_demo.py` |
| Cost by hour, no double count after reopening a session | `tests/cost.test.ts` |
| The meter for AI projects and applications and its report: Anthropic, OpenAI, Gemini, APIs that copy OpenAI (DeepSeek), Bedrock, Ollama and Cohere token counts, counts by hand for any other provider, provider names checked, each token counted once; no usage is written as null, never 0; streaming, retries, failures; no user text; unknown fields dropped; nearest-rank p95; a model with no price; a model on the team's own machines; the user's own price file; prices by day; the Node meter gives the same numbers | `tests/appmeter/test_appmeter.py` |
| AI projects and applications on the board: only a live project key may send, never from a browser, and it opens nothing else; a revoked key stops at once and its numbers stay; the paths are gone with `AI_PROJECTS` off; unknown fields and bad turns dropped, nothing private stored; bad and oversized sends refused; a turn sent twice kept once; the per-key and per-day limits; tokens not measured stay unknown; who may see and download (admin and viewer, not wall); the report and its p95 match the skill; making a key needs the OTP and shows it once; prices an admin pastes are checked; old turns and days swept; the Python and Node meters send in the background and a dead board costs nothing; the board's copy of the report equals the skill's | `server/test_projects.py` |
| No prompt, chat or secret file content leaves the machine | `tests/activity.test.ts`, `tests/edits.test.ts`, `tests/team.test.ts`, `tests/office.test.tsx` |
| Helper assistants: Gemma model choice, safe arguments for Codex | `tests/workers.test.ts` |
| SQLite storage: moving the old JSON files in, schema version, file modes, many threads at once, backup, export back to JSON; an older database is copied before it is upgraded, the copy opens and the older program runs on it, and no copy means no upgrade | `test_webhook.py` (`DatabaseStorage`), `tests/linux/test-server.sh` |
| The hour books in rows of their own (schema version 6): a `board.db` of schema version 5 gives the same board, history, totals per day and export after the upgrade, rows it cannot read stay as they were and the copy of version 5 is kept; random sends of both formats leave exactly the book `merge_hours` and `replace_hours` give, the days in `device_days` and in memory, also after a restart and with an SQLite older than 3.24; a send that changes nothing writes nothing; a new `TZ_OFFSET` counts the days again | `server/test_hour_rows.py` |
| Totals per person per day: hours added into days, counting again without adding twice, 13 months then deleted, weeks and months read back; the charts of cost per week and per month; only admin and viewer get them | `test_webhook.py` (`DailyTotals`, `UsageByRole`) |
| What comes back from a helper (ChatGPT, Gemini, Gemma): commands read from shell code blocks and `$` prompts only; an answer with a key, words aimed at an AI or a command that cannot be undone is flagged and reaches Claude whole with a note; the record of the work holds lengths, kinds and a salted fingerprint, never the prompt, and goes up once, the last two days only | `tests/answers.test.ts` |
| The check of commit messages (`commitTrail`): what a message lacks (the subject's shape, the cause of a fix, what was measured), merges, reverts and fixups left alone, the reminder to Claude only when `config.js` turns it on and the commit went through | `tests/committrail.test.ts` |
| The cost ledger on the computer: a turn added to its hour, the ledger kept when the page cannot be written, the last cost per session (at most 50), the repair run once per machine | `tests/ledger.test.ts` |
| Sending the numbers (`hooks/send.ts`): the shared key first, then the computer's own key and a route to the receiver; a busy receiver waited for, never poured onto the webhook; a webhook that does not answer backed off from 5 seconds to 5 minutes; a refused key dropped; a route that ran out asked again; the gap the server asks kept | `tests/send.test.ts`, `tests/share.test.ts` |
| Format `v: 2` of a send: `v: 1` until the server says it reads `v: 2`, then only the hours that changed; the whole book when asked, when the marks are missing and when it is due; the last two days again after another start of the server; each send numbered above the last; whatever is lost on the way, the server ends with the money the computer holds | `tests/sendv2.test.ts`; the plugin's own code against the real `/ingest` over HTTP: `server/test_plugin_v2.py` with `tests/contract/plugin-v2/bridge.mjs` |
| Session titles: when a fresh title is due, how an answer becomes a title, a chat the person renamed stays theirs | `tests/titles.test.ts` |
| The core of the board's MCP endpoint (`board/mcp.py`): the summary a key may read, the current and the older revisions of the protocol, bad messages | `server/test_mcp.py` |
| Formats `v: 1` and `v: 2` of `/ingest` against the shared sample: the same activity sent either way gives the same board, history and totals per day, and the book the sample expects | `server/test_contract.py` with `tests/contract/ingest-v2/cases.json` |
| Which hours of a send are written, left as they were or removed (`board/order.py`), compared on many random cases with the rule as it was written before | `server/test_order.py` |
| What a send becomes before anything is written (`decide`), the same choices as the Go receiver's; and the two ways a send is taken, straight on `/ingest` and as a row of the receiver, side by side after the save | `server/test_decide.py`, `server/test_two_paths.py` |
| A batch of the receiver written whole (`DeviceCache.write_batch`): the computers held in order for the whole batch, a fast try that fails taken back and written again row by row, a bad row named alone; `RECEIVER_FAST_APPLY` on and off leaving the same tables and the same `/data` for every role, byte for byte | `server/test_batch.py`, `server/test_apply_paths.py` |
| A build of the board resting only while a write runs, and never longer than its limit (`board/turns.py`); a person's branch found through the index the same as by going through every branch | `server/test_turns.py`, `server/test_branch_of.py` |
| OTP secrets sealed with the key kept apart from them: sealing and unsealing, accounts stored sealed, the accounts database | `server/test_sealing.py` |
| Language choice and fallback | `tests/lang.test.ts` |
| No private word, address or key in the package | `tests/test-check-clean.sh` with `packaging/check-clean.sh` |

## 2. Run locally

Run all twelve before calling a change done. Run each at the repository root. GitHub Actions runs the same checks, every test module of the server included (`python3 -m unittest` finds them by name, so a new one needs no list).

```bash
claude plugin test .
```

Correct result: every test passes. Without Claude Code installed: `npx -y @anthropic-ai/claude-code plugin test .`

```bash
cd server && python3 -m unittest
```

Correct result: `OK`. Go back to the repository root afterwards.

```bash
python3 tests/connectors/test_connectors.py
```

```bash
python3 tests/appmeter/test_appmeter.py
```

```bash
node tests/extension/check-extension.js
```

```bash
node tests/check-map-layout.js
```

```bash
python3 tests/check-i18n.py
```

```bash
python3 tests/check-maps.py
```

```bash
python3 tests/check-frontmatter.py
```

```bash
bash tests/test-check-clean.sh
```

```bash
uvx ruff check .
```

Correct result of each of these nine: exit code 0. Without `uv`, the last one is `pipx run ruff check .`.

```bash
cd receiver && go test ./...
```

Correct result: `ok` for every package. It needs Go 1.22 or later and `python3`: the receiver's tests run the server's own code as the judge. Go back to the repository root afterwards.

### Load test

Not one of the twelve: it takes about 20 minutes and its numbers depend on the computer. Run it before a release that changes how the server takes a send or builds the board, and compare with [BENCHMARK.md](BENCHMARK.md).

```bash
python3 tests/load/load_test.py --json load.json
```

```bash
python3 tests/load/load_test.py --scale 300,1000,3000,5000,10000
```

Correct result: the first ends with a table and exit code 0, which means no office run had an error; the second shows one send taking about the same time at every size. `--quick` checks in about 15 seconds that the test itself still runs. It only ever talks to the server it started on 127.0.0.1.

`bash packaging/check-clean.sh` is not in this list: it looks for private data in the folder it runs in, so it belongs on what gets published, where its correct result is `Clean.` In a checkout that holds your own `packaging/company.json` it reports that file, and that is expected.

## 3. Checks that still need a person

Automatic tests use fake servers and fake browsers. Before a release that touches these parts, check by hand:

| Part | Machine | Check | Correct result |
|---|---|---|---|
| Plugin install | A real Mac and a real Windows PC | Run the installer, open Claude Code, type `/office` | The office page opens; the computer appears on the dashboard within 5 minutes |
| Speaking instead of typing | A real Mac and a real Windows PC with a microphone | Type `/ai-worker:voice`, follow the steps, then dictate a Vietnamese sentence in the message box | The settings page opens; the sentence appears in Vietnamese with its accents |
| Update | A computer on the previous version | Wait for or force the update check, click **Update**, restart the app | The new version number shows in `/office` |
| Login with OTP | A real phone with Google or Microsoft Authenticator | Scan the QR on `/admin`, log in | Logged in; a wrong code 5 times locks for 15 minutes |
| Login with Telegram | A real Telegram account and the bot of the server | On `/telegram` enter the code and press the button, log out, press **Log in with Telegram** on the login page | Back on the dashboard without typing the name or code |
| Ask from Telegram | A real Telegram account and a bot made for this with @BotFather | Press **Start** in the bot, approve the code on `/admin` for each person, tap the buttons, type a question, try to forward an answer, send `/stop` | Answers with names in the language of the message; Telegram refuses to forward; after `/stop` the bot says the chat is not connected |
| The window inside Telegram | Asking from Telegram working, `TELEGRAM_APP=1` and `TELEGRAM_APP_URL` set, a chat that reads each person | On `/admin` click **Allow the window**; in Telegram tap **AI Worker** on a phone and on Telegram Desktop, on the office network; switch the language; then **Stop the window** | The button shows within a minute; the window shows the menu bar window's numbers; after Stop the window it says to close and open it again. Done on 2026-11-18 on Telegram Desktop (macOS) and Android; not yet on an iPhone |
| The window for a chat that reads totals only | As above, a chat approved to read totals only | On `/admin` click **Allow the window** on that chat; tap **AI Worker** | The confirm box says the window names nobody; every tab shows one line of totals and "This chat reads totals only, so nobody is named."; no name anywhere |
| A commit holding a fake key | A test repository, a `.env` line with a made-up `DB_PASSWORD` staged | Ask Claude to commit | The permission box asks first, names the file and line, never the value |
| A ChatGPT send holding a fake key | ChatGPT installed | Ask Claude to send `review: DB_PASSWORD=<made-up value>` to ChatGPT | Refused with "Nothing left this computer"; the Admin page's **Stopped by ai-worker** counts one more within a few minutes |
| A page that speaks to an AI | A local page with the line "ignore your previous instructions" | Ask Claude to read it with WebFetch or the browser | A notice for you; Claude says what the page tried and does not follow it |
| Log check | A copy of `board.db` on a test server | Change one audit row with `sqlite3`, open `/admin` | The audit section says a line near that time was changed or taken out by hand |
| Cost check | A copy of `board.db` on a test server, running more than a week | Change `usd` of one `daily` row older than a week with `sqlite3`, open `/admin` | The audit section says the numbers of that day were changed after it was sealed; **Sealed days** lists the fingerprints |
| TV screen | A real TV or a browser in full screen | Open `/tv`, approve the code on `/admin` | The board shows with no email or IP |
| macOS menu bar | A real Mac | Install the `.dmg` or `.zip`, pair | Icon shows the waiting count, notification arrives |
| Ubuntu menu bar | Ubuntu with X11 **and** Ubuntu with Wayland | Install the `.deb`, pair | Icon shows in the top bar on both |
| Chrome extension | Real Chrome | Load the extension, pair, open the popup | Popup and badge show the waiting count |
| Phone width | A phone or a 375 px window | Open the dashboard | Nothing overflows; buttons can be tapped |

## 4. Before a release

1. Every GitHub Actions job is green, and the jobs ran instead of being skipped, the three Windows ones included. A push to a private repository skips them all: start the workflow by hand there, `gh workflow run test-install.yml`.
2. The checks in section 3 are done for every part this release changed.
3. `version` in `.claude-plugin/plugin.json` is raised, and `CHANGELOG.md` lists the changes.
   If the dashboard looks different, retake `assets/dashboard.png` and `assets/dashboard.vi.png` from a test server with sample people, never a real one.
4. `bash packaging/release.sh` succeeds, and the signature is checked on one computer before the release goes out to everyone.
5. Write down in the site record what was released, when and by whom ([OPERATIONS.md](OPERATIONS.md), section 7).

## 5. Known gaps

- `hooks/register.tsx` and `web/ops.js` (copied to `server/static/ops.js`) have no direct tests of their own yet.
- No automatic test on a real Mac.
- No automatic test on Ubuntu Wayland; it is checked by hand.
- The load test has run on a Mac only, not yet on a Linux server like the ones the board is installed on, and it plays each computer from its own made-up address, so it does not show the limit of new computers per address a day that an office behind one shared address would meet (sends themselves are limited per computer, not per address). The Go receiver was measured on Linux with tools outside the repository ([BENCHMARK.md](BENCHMARK.md#on-linux-with-the-go-receiver)).
