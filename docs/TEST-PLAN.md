[Tiếng Việt](TEST-PLAN.vi.md) | English <!-- i18n-allow -->

# Test plan

What is tested automatically on every push, what still needs a person, and the checklist before a release.

## 1. Automatic tests

GitHub Actions runs `.github/workflows/test-install.yml` on every push. In a private repository, where the minutes are limited, the two Windows jobs run only when the push changes something they test (`packaging/`, `connectors/`, `server/menubar/`, `tests/connectors/`, `tests/menubar/`, `tests/windows/`, the workflow itself, `.claude-plugin/`) or when the workflow is started by hand; a push that changes none of these shows them as skipped. In a public repository, where the minutes are free, they run on every push. A release is made only when every job is green, the Windows ones included: raising the version in `.claude-plugin/plugin.json` runs them.

| Job | Machine | Checks | Files |
|---|---|---|---|
| `code-check` | Ubuntu | Python lint (ruff); hook tests through the Claude Code CLI; over 100 server tests; the Chrome extension logic against a real local server | `ruff.toml`, `tests/*.test.ts(x)`, `server/test_webhook.py`, `tests/extension/check-extension.js` |
| `build` | Ubuntu | Package build; the private-data check; skill front matter; the two-language rules | `packaging/build.sh`, `tests/test-check-clean.sh`, `tests/check-frontmatter.py`, `tests/check-i18n.py` |
| `ubuntu` | Ubuntu | Installer on a clean machine, case by case; server install with systemd; menu bar script; the `.deb` installed and removed by apt; notification badge picture | `tests/linux/test-install.sh`, `tests/linux/test-server.sh`, `tests/menubar/test-menubar.sh`, `tests/menubar/test-deb.sh` |
| `windows` | Windows | Installer on a clean machine, case by case; icon next to the clock; notification badge picture | `tests/windows/test-install.ps1`, `tests/menubar/test-menubar.ps1` |
| `windows-app` | Windows | Build `AI Worker.exe` and `.msi`; install for one user without admin rights; pair; count waiting people; remove | `tests/menubar/test-windows-app.ps1` |

### What the tests cover

| Area | Covered by |
|---|---|
| Permission of every server path | `test_webhook.py` holds the full route table and fails if a path is added without a permission |
| Login, OTP, lockout after wrong codes, re-entering OTP for account actions | `test_webhook.py` |
| Telegram login: signature, expiry, reuse, linking only with the code and the one-time step, one Telegram per account, the way to Telegram and back | `test_webhook.py`, class `TelegramLogin` |
| Asking from Telegram: which command a message means, the answers in two languages and for both scopes, no private field in any answer | `test_ask.py` |
| Asking from Telegram: who may call the bot's path, pairing a chat, limits, the log, the chat's number opening nothing else, the bot process against a fake Telegram and the real webhook | `test_webhook.py`, class `TelegramAsk` |
| The Telegram bot process: reading, sending, trouble with Telegram or the webhook, nothing secret in its log | `test_telegram_bot.py` |
| The window inside Telegram: Telegram's signature (wrong, old, from another bot, without a user), sessions and their limits, only chats allowed and reading each person, revoking or `/stop` ending a session at once, nothing else opened by a session, the page and its files with `?v=`, the menu buttons the bot is told, the log; and the bot process setting the buttons | `test_webhook.py`, class `TelegramApp`; `test_telegram_bot.py`, class `MenuButtons` |
| Alerts to Telegram chats: each wait once, the gap, the hourly cap, quiet hours, sessions left open, names only for a chat that reads each person, the first line naming nobody, the chat's language and minutes; `/alerts` and the window's settings; the log; the bot sending them protected with the window's button | `test_webhook.py`, classes `AlertRules` and `TelegramAlerts`; `test_telegram_bot.py`, class `MenuButtons` |
| The bot's service after install: off by default, its own user and settings file, the network limit, removal | `tests/linux/test-server.sh`, part S5 |
| What each role receives (no email or IP for wall) | `test_webhook.py` |
| Pairing TV, menu bar and extension; revoke; expiry | `test_webhook.py`, `check-extension.js`, menu bar tests |
| A computer cannot send for another person; send limits | `test_webhook.py` |
| Office labels and pins on the maps: pins that meet are drawn side by side; with many offices the labels with no free place are hidden; no label covers another label, another office's pin or the list of offices, none leaves the frame | `tests/check-map-layout.js` |
| A manager's Claude plugin and the board: pairing by code, reading only the wall view, revoke, unpair, refused network, denied permission | `test_webhook.py` (class `ExtensionPairing`), `tests/board.test.ts` |
| Text for ChatGPT or Gemini: asked about in a permission mode that asks nothing, kept on the computer on a no, sent without a question only under an allow rule | `tests/sending.test.ts`, `tests/workers.test.ts` |
| Handoff notes told to a new session: only files the skill would write, the newest five by name and date, nothing on a computer with none, no note opened by the plugin | `tests/handoff.test.ts` |
| The question before a command that destroys work: which commands are caught and which are left alone, an allowed command turned into a question for a person, a denied one left denied, the switch in `config.js` | `tests/guard.test.ts` |
| `/ai-worker:voice`: the right settings page and steps for a Mac, Windows and Linux; steps by hand when the page does not open; nothing else is run | `tests/voice.test.ts` |
| The demo with sample people: starts, opens with the code it prints, ignores a real board's settings, deletes its data when stopped | `test_demo.py` |
| Cost by hour, no double count after reopening a session | `tests/cost.test.ts` |
| No prompt, chat or secret file content leaves the machine | `tests/activity.test.ts`, `tests/edits.test.ts`, `tests/team.test.ts`, `tests/office.test.tsx` |
| Helper assistants: Gemma model choice, safe arguments for Codex | `tests/workers.test.ts` |
| SQLite storage: moving the old JSON files in, schema version, file modes, many threads at once, backup, export back to JSON; an older database is copied before it is upgraded, the copy opens and the older program runs on it, and no copy means no upgrade | `test_webhook.py` (`DatabaseStorage`), `tests/linux/test-server.sh` |
| Totals per person per day: hours added into days, counting again without adding twice, 13 months then deleted, weeks and months read back; the charts of cost per week and per month; only admin and viewer get them | `test_webhook.py` (`DailyTotals`, `UsageByRole`) |
| Language choice and fallback | `tests/lang.test.ts` |
| No private word, address or key in the package | `tests/test-check-clean.sh` with `packaging/check-clean.sh` |

## 2. Run locally

Run all ten before calling a change done. CI runs the same ones. Run each at the repository root.

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

Correct result of each of these eight: exit code 0. Without `uv`, the last one is `pipx run ruff check .`.

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
| TV screen | A real TV or a browser in full screen | Open `/tv`, approve the code on `/admin` | The board shows with no email or IP |
| macOS menu bar | A real Mac | Install the `.dmg` or `.zip`, pair | Icon shows the waiting count, notification arrives |
| Ubuntu menu bar | Ubuntu with X11 **and** Ubuntu with Wayland | Install the `.deb`, pair | Icon shows in the top bar on both |
| Chrome extension | Real Chrome | Load the extension, pair, open the popup | Popup and badge show the waiting count |
| Phone width | A phone or a 375 px window | Open the dashboard | Nothing overflows; buttons can be tapped |

## 4. Before a release

1. Every GitHub Actions job is green, and the two Windows jobs ran instead of being skipped. If the last run skipped them, start the workflow by hand: `gh workflow run test-install.yml`.
2. The checks in section 3 are done for every part this release changed.
3. `version` in `.claude-plugin/plugin.json` is raised, and `CHANGELOG.md` lists the changes.
   If the dashboard looks different, retake `assets/dashboard.png` and `assets/dashboard.vi.png` from a test server with sample people, never a real one.
4. `bash packaging/release.sh` succeeds, and the signature is checked on one computer before the release goes out to everyone.
5. Write down in the site record what was released, when and by whom ([OPERATIONS.md](OPERATIONS.md), section 7).

## 5. Known gaps

- `hooks/register.tsx` and `web/ops.js` (copied to `server/static/ops.js`) have no direct tests of their own yet.
- No automatic test on a real Mac.
- No automatic test on Ubuntu Wayland; it is checked by hand.
