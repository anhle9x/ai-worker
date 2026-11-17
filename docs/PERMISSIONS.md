[Tiếng Việt](PERMISSIONS.vi.md) | English <!-- i18n-allow -->

# Permission model

Who can see and do what on the dashboard server. The rules live in one place: the route table at the end of `server/webhook.py` (`GET_ROUTES`, `POST_ROUTES`) and the gate `Handler.gate`. A path that is not in the table answers 404. The test `test_webhook.py` holds a copy of the table and fails if the two differ.

## 1. Who is calling

| Caller | Proves itself with | Role on the server |
|---|---|---|
| Employee computer (plugin) | `INGEST_KEY` in the `Authorization` header | None: may only send numbers and download signed updates |
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

The server does not trust the IP of a request unless the request comes through the local proxy (`TRUST_PROXY`). The office IP allow-list is enforced by Caddy or nginx in front, not by the webhook.

## 2. What each role sees

| Data | `admin` | `viewer` | `wall` |
|---|---|---|---|
| 3D office, status, cost, tasks, quota | Yes | Yes | Yes |
| Email | Yes | Yes | No: replaced by a short code that changes at each restart |
| Name that is an email or IP | Yes | Yes | No: shown as "Device xxxxxx" |
| Internal IPs, accounts typed by staff | Yes | Yes | No |
| Team plan spend | Yes | Yes | No |
| Use by week and month, per office and per person (totals per day, kept 13 months) | Yes | Yes | No |
| The whole team's cost on each of the last 7 days, one number per day (the chart of the menu bar window) | Yes | Yes | Yes |
| Computer groups with no name | Yes | No | No |
| Text board `/board` | Yes | Yes | No |
| `/admin` page and installers | Yes | No | No |

The fields each role receives are fixed in `server/board/views.py` (`COMMON_FIELDS_BY_ROLE`, `PERSON_FIELDS_BY_ROLE`). A field not listed there is never sent. Use by week and month has its own lists in the same file (`USAGE_FIELDS_BY_ROLE`, `USAGE_OFFICE_FIELDS_BY_ROLE`, `USAGE_PERSON_FIELDS_BY_ROLE`), empty for `wall`: it is on `/board` only, so a TV screen, a menu bar icon, the browser extension, a manager's plugin and the MCP endpoint, which all read as `wall`, get none of it.

## 3. What each role can do

| Action | Path | Who | Extra check |
|---|---|---|---|
| Send numbers | `POST /ingest` | Computer with `INGEST_KEY` | The computer stays tied to the person of its first send |
| Download an update | `GET /releases/...` | Computer with `INGEST_KEY` | The computer checks the signature before installing |
| Name locations, mark the sales team, load the Team CSV | `POST /locations`, `/team-sale`, `/team-csv` | `admin` | Same-origin request |
| Create, delete, change role of accounts; end sessions | `POST /admin/accounts`, `/admin/sessions` | `admin` | Re-enter OTP, valid 5 minutes |
| Approve, rename, revoke TV screens, extensions, keys for AI tools and Telegram chats; choose what such a key or chat may read | `POST /admin/tv-*` | `admin` | Re-enter OTP, valid 5 minutes |
| Reload a TV screen | `POST /admin/tv-reload` | `admin` | Same-origin request |
| Approve own menu bar icon | `POST /mini/pair` | Account with role `admin` or `viewer` | That account's OTP |
| Ask for a key for an AI tool | `GET /mcp/connect`, `POST /mcp/request-code`, `/mcp/poll` | Anyone the IP allow-list lets in | The request must come from the board's own page. Nothing is given out until an admin approves the code |
| Read the board from an AI tool | `POST /mcp` | AI tool with a key for the MCP endpoint | Read-only. 120 requests per key in 10 minutes; a web page on another site is refused; each call of the tool is logged for 3 months |
| Hand over a message from a Telegram chat and get the answer to send | `POST /bot/telegram` | The Telegram bot process on the server itself, with `TELEGRAM_ASK_KEY` | Off (404) unless `TELEGRAM_ASK=1`. Only a direct call from the same machine: a request that came through the proxy gets 404, a login or any other key gets 401. Private chats only; 20 messages per chat in 10 minutes; each answer with numbers is logged for 3 months, never the words typed |

## 4. Guards

- **At least one admin:** the server refuses to delete or demote the last admin.
- **Wrong OTP:** 5 wrong codes from one address in 15 minutes lock that address. 20 wrong codes on one account in 15 minutes lock that account, so a stranger cannot lock the whole site.
- **Telegram:** linking needs the 6-digit code and a one-time step tied to that session, so a stolen session or a link sent by someone else cannot add a Telegram. One Telegram per account; wall accounts cannot use it. Reissuing a key or making an account a wall account unlinks it.
- **Account limit:** 200 accounts, 20 TV screens, 50 keys for AI tools, 300 computers.
- **Every refusal and every change is written to the audit log** (table `audit` in `board.db`), with who, role, IP and path. CSV content is not copied into it.
- **If every admin is lost:** someone with sudo on the server runs `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder. See [USER-GUIDE.md](USER-GUIDE.md).
