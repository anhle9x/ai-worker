[Tiếng Việt](PERMISSIONS.vi.md) | English <!-- i18n-allow -->

# Permission model

Who can see and do what on the dashboard server. The rules live in one place: the route table at the end of `server/webhook.py` (`GET_ROUTES`, `POST_ROUTES`) and the gate `Handler.gate`. A path that is not in the table answers 404. The test `test_webhook.py` holds a copy of the table and fails if the two differ.

## 1. Who is calling

| Caller | Proves itself with | Role on the server |
|---|---|---|
| Employee computer (plugin, connector) | Its own key (`awd1.…`) in the `Authorization` header, or `INGEST_KEY` until it has one | None: may only send numbers for itself and download signed updates |
| Admin | Account name + 6-digit OTP, then a session cookie (8 hours) | `admin` |
| Manager | Account name + OTP, session cookie (8 hours) | `viewer` |
| Admin or manager with Telegram linked (optional) | Telegram's signature checked with the bot token (5 minutes, once), session cookie | Their own role; admin changes still ask for the OTP |
| Wall account | Account name + OTP, session cookie (7 days) | `wall` |
| TV screen | Pairing key approved by an admin (30 days, renewed while used) | `wall` |
| Menu bar icon | Pairing key, approved by a manager with their own account and OTP, at most 2 computers per account | Always `wall` |
| Browser extension | Pairing key in the `Authorization` header, approved by an admin | Always `wall` |
| Claude plugin of a manager (`/ai-worker:board`) | The same pairing key as the extension, approved by an admin; named "plugin" in the list and the audit log | Always `wall`: Claude on that computer reads names, states, cost and quota, never an email or an IP |
| AI tool that speaks MCP (Claude Code, Codex CLI, Cursor, Gemini CLI) | A key of its own in the `Authorization` header, asked for on `/mcp/connect` and approved by an admin. It opens `/mcp` only, and no other key opens `/mcp` | Always `wall`, given as text. The admin chooses whether the key reads each person, or team and office totals only |
| Telegram chat (only with `TELEGRAM_ASK=1`, which makes the installer set up the bot process that talks to Telegram) | Nothing of its own: the bot process on the server hands over each message with the sender's Telegram number, and the chat counts once an admin has approved its 8-digit code. The number opens nothing else | Always `wall`, given as a few lines of text. The admin chooses whether the chat reads each person, or team and office totals only |
| AI project or application your team built (only with `AI_PROJECTS=1`) | A key of its own (`prj_…`) in the `Authorization` header, made by an admin on the Admin page and shown once. It opens `/projects/ingest` only, and no other key opens that path; a request with an `Origin` header (a browser) is refused | None: it may only send what it measured |

The server does not trust the IP of a request unless the request comes through the local proxy (`TRUST_PROXY`). The office IP allow-list is enforced by Caddy or nginx in front, not by the webhook.

## 2. What each role sees

| Data | `admin` | `viewer` | `wall` |
|---|---|---|---|
| 3D office, status, cost, tasks, quota | Yes | Yes | Yes |
| Email | Yes | Yes | No: replaced by a short code made with a secret kept in the keys database, the same after a restart |
| Name that is an email or IP | Yes | Yes | No: shown as "Device xxxxxx" |
| The code of each person's row (`row`, only with `RECEIVER=1`), which the Go receiver's live feed puts its numbers on | Yes | Yes | Yes: 12 characters made with the same secret under another label, so it gives back neither the email nor the name, and is not the code above |
| Internal IPs, accounts typed by staff | Yes | Yes | No |
| Team plan spend | Yes | Yes | No |
| Use by week and month, per office and per person (totals per day, kept 13 months) | Yes | Yes | No |
| The whole team's cost on each of the last 7 days, one number per day (the chart of the menu bar window) | Yes | Yes | Yes |
| How many times ai-worker stopped something across the team in the last 7 days, counts only (`blocked7d`) | Yes | Yes | No |
| Work handed to ChatGPT, Gemini or Gemma: one record each, who, which helper, lengths, what stopped it, what the check of the answer found, a fingerprint of the prompt; never the text | Yes | No | No |
| Computer groups with no name | Yes | No | No |
| Text board `/board` | Yes | Yes | No |
| `/admin` page and installers | Yes | No | No |

The fields each role receives are fixed in `server/board/views.py` (`COMMON_FIELDS_BY_ROLE`, `PERSON_FIELDS_BY_ROLE`). A field not listed there is never sent. `/data?scope=org` and `/data?scope=branch:<id>` ([RECEIVER.md](RECEIVER.md), section 3) are cut from the same view of the same role, plus totals per branch that hold numbers only, so a scope never shows a role more than plain `/data`. Use by week and month has its own lists in the same file (`USAGE_FIELDS_BY_ROLE`, `USAGE_OFFICE_FIELDS_BY_ROLE`, `USAGE_PERSON_FIELDS_BY_ROLE`), empty for `wall`: it is on `/board` only, so a TV screen, a menu bar icon, the browser extension, a manager's plugin and the MCP endpoint, which all read as `wall`, get none of it.

## 3. What each role can do

| Action | Path | Who | Extra check |
|---|---|---|---|
| Send numbers | `POST /ingest` | Computer with its own key, or `INGEST_KEY` while it has none and `SHARED_KEY_MODE` allows it | A key sends only for its own computer; the computer stays tied to the person of its first send; a revoked computer is refused. From outside `OFFICE_NETS` (or marked so by Caddy): only the own key of a computer an admin let send from any network, else 403 |
| Ask where to send now | `GET /ingest/route` | Computer with its own key (the shared key: 403) | Writes nothing; an empty list unless the Go receiver takes this computer's sends. From outside the office: as for `/ingest` |
| Download an update | `GET /releases/...` | Computer with its own key or `INGEST_KEY` | The computer checks the signature before installing. From outside the office: as for `/ingest` |
| Cut a computer off (Revoke), or let it enrol again (Let back) | `POST /admin/device-revoke`, `POST /admin/device-forget` | `admin` | Re-enter OTP, valid 5 minutes; written in the Admin log |
| Let a computer send from any network, or take it back | `POST /admin/device-roam` | `admin` | Re-enter OTP, valid 5 minutes; only a computer sending with its own key; written in the Admin log |
| Name locations, mark the sales team, load the Team CSV | `POST /locations`, `/team-sale`, `/team-csv` | `admin` | Same-origin request |
| Create, delete, change role of accounts; end sessions | `POST /admin/accounts`, `/admin/sessions` | `admin` | Re-enter OTP, valid 5 minutes |
| Approve, rename, revoke TV screens, extensions, keys for AI tools and Telegram chats; choose what such a key or chat may read | `POST /admin/tv-*` | `admin` | Re-enter OTP, valid 5 minutes |
| Reload a TV screen | `POST /admin/tv-reload` | `admin` | Same-origin request |
| Approve own menu bar icon | `POST /mini/pair` | Account with role `admin` or `viewer` | That account's OTP |
| Ask for a key for an AI tool | `GET /mcp/connect`, `POST /mcp/request-code`, `/mcp/poll` | Anyone the IP allow-list lets in | The request must come from the board's own page. Nothing is given out until an admin approves the code |
| Read the board from an AI tool | `POST /mcp` | AI tool with a key for the MCP endpoint | Read-only. 120 requests per key in 10 minutes; a web page on another site is refused; each call of the tool is logged for 3 months |
| The board's window inside Telegram: trade Telegram's signed fields for a session, read the wall view (the team's totals alone for a chat that reads totals only), read and set its own chat's alerts, disconnect its own chat | `POST /tg/session`, `GET /tg/data`, `GET /tg/state`, `POST /tg/settings`, `POST /tg/unpair` | A chat an admin approved and allowed the window; the session from `/tg/session` in the Authorization header | Off (404) unless `TELEGRAM_APP=1`. Telegram's signature checked with a key derived from the bot token, fields at most 5 minutes old; session in memory, 1 hour after last use, 12 hours at most, 3 per chat; the chat is found again on every call. 10 sessions per IP a minute, 20 per chat in 10 minutes, 60 reads per session in 10 minutes |
| Hand over a message from a Telegram chat and get the answer to send | `POST /bot/telegram` | The Telegram bot process on the server itself, with `TELEGRAM_ASK_KEY` | Off (404) unless `TELEGRAM_ASK=1`. Only a direct call from the same machine: a request that came through the proxy gets 404, a login or any other key gets 401. Private chats only; 20 messages per chat in 10 minutes; each answer with numbers is logged for 3 months, never the words typed |
| The optional Go receiver: write a batch of rows, pass on a send as it came, read the numbered policy, the hour books and the table of people (each computer's row code and branch, no name, email or address) | `POST /internal/rows`, `POST /internal/ingest`, `GET /internal/policy`, `GET /internal/devices`, `GET /internal/people` | The receiver on the server itself, with the internal code of its file of secrets | Off (404) unless `RECEIVER=1`. Only a direct call from the same machine with the internal code: anything else, a login included, gets 404. A send passed on has its own key checked as on `/ingest` ([RECEIVER.md](RECEIVER.md)) |
| Get a ticket to the board's live feed | `POST /sse/ticket` | Any logged-in account or TV screen | Off (404) unless `RECEIVER=1` and `RECEIVER_LIVE_URL`, `RECEIVER_BOARD_ORIGIN` are set. The request must come from the board's own page. Any scope of `/data?scope=`; the ticket lives 5 minutes and carries the role, the scope and a code of the session, no name ([RECEIVER.md](RECEIVER.md), "The live feed") |
| Read the board's live numbers | `GET /live`, `GET /live/snap` on the Go receiver | A page of `RECEIVER_BOARD_ORIGIN` with a ticket that is still good, for the scope it asks | The same numbers for every role, and only numbers and row codes: no name, email or address. Cut within about 20 seconds once the session is closed |
| Send what an AI project or application measured | `POST /projects/ingest` | The project's own server, with its key | Off (404) unless `AI_PROJECTS=1`. Refused from a browser. Each turn cleaned by the report's code (unknown fields dropped, bad turns refused, turns older than 30 days refused) and kept once per key and `turnId`. 120 sends per key in 10 minutes, 256 KB and 500 turns per send, 100,000 turns per key a day |
| Read and download the report of an AI project or application | `GET /projects`, `/projects/report.html`, `/projects/report.csv` | `admin`, `viewer` | Off (404) unless `AI_PROJECTS=1`. The print version opens in its own tab and runs no script |
| Make a key for an AI project or application; paste prices of your own; delete the numbers of a project whose key is revoked | `POST /admin/project-key`, `/admin/project-prices`, `/admin/project-delete` | `admin` | Re-enter OTP, valid 5 minutes. Rename and revoke the key with `/admin/tv-*`. Deleting is refused while the key works |

## 4. Guards

- **At least one admin:** the server refuses to delete or demote the last admin.
- **Wrong OTP:** 5 wrong codes from one address in 15 minutes lock that address. 20 wrong codes on one account in 15 minutes lock that account, so a stranger cannot lock the whole site.
- **Telegram:** linking needs the 6-digit code and a one-time step tied to that session, so a stolen session or a link sent by someone else cannot add a Telegram. One Telegram per account; wall accounts cannot use it. Reissuing a key or making an account a wall account unlinks it.
- **Account limit:** 200 accounts, 20 TV screens, 50 keys for AI tools, 20 keys for AI projects and applications, 300 computers by default (`MAX_DEVICES` raises it).
- **Every refusal and every change is written to the audit log** (table `audit` in `board.db`), with who, role, IP and path. CSV content is not copied into it. Each day of cost totals is sealed into the same log once it is no longer counted again; only admins see the seals, on `/admin`, and only a Telegram chat linked to an admin account gets the morning message with the day's fingerprint (day, number of rows, fingerprint: no name, no money).
- **If every admin is lost:** someone with sudo on the server runs `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder. See [USER-GUIDE.md](USER-GUIDE.md).
