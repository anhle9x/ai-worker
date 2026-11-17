[Tiếng Việt](DATA-MODEL.vi.md) | English <!-- i18n-allow -->

# Data design

What the dashboard server stores, where, for how long and who can read it. The server stores everything in two SQLite databases. SQLite comes with Python, so nothing is added to install.

Settings named here (`DATA_DIR`, `KEYS_DIR`, limits) are in `server/board/settings.py`. The schema, its upgrades and the move from the old JSON files are in `server/board/db.py`. The code that reads and writes each table is in `server/board/stores.py`, `server/board/devices.py`, `server/board/daily.py` and `server/board/views.py`.

## 1. Files

| File | Default after install | Owner and mode | Holds |
|---|---|---|---|
| `data/board.db` (with `-wal`, `-shm`) | `/opt/ai-worker/data/` | `ai-worker`, `600`, folder `750` | Numbers from computers, totals per person per day, pairings, locations, Team plan, audit log, rewind history |
| `data/board.db.schema-N.bak` | Next to `board.db`, only after an upgrade that changed the schema | `ai-worker`, `600` | A full copy of `board.db` as it was at schema version `N`, made by the server before it upgraded. The server deletes it after 30 days |
| `keys/accounts.db` (with `-wal`, `-shm`) | `/opt/ai-worker/keys/` | `ai-worker`, `600`, folder `700` | Accounts and their OTP secrets |
| `/etc/ai-worker.env` | | `root`, `600` | Settings and the `INGEST_KEY` |

The accounts are in their own file, in their own folder, so a backup of the numbers never carries the login secrets. The systemd service may write only to these two folders (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Tables

`board.db`:

| Table | Content | Written when | Kept |
|---|---|---|---|
| `devices` | One row per computer for the plugin, and one more for the connector for Codex, Cursor and Gemini CLI where it is installed: the latest numbers in `body` (section 3), `seen_at` = when the server received them | Each send, at most every 30 seconds | Deleted 30 days after `seen_at` (`KEEP_DAYS`) |
| `identities` | `device → account, name` of the first send | A new computer's first send | Until removed with `--forget-device` |
| `history` | One row each time a person's state changes: time, person, state, tasks delegated | State changes | 24 hours (rewind button) |
| `daily` | One row per person per day (the day follows `TZ_OFFSET`): name, account email, the office the person was in when the day closed, cost in dollars, tokens in and out, tasks given to Gemini, ChatGPT and Gemma. Added up from `ledger` and `tasks` of that person's computers (section 3); no computer sends anything new for it | Every 5 minutes the last 7 days are counted again and written over; an older day is left as it was last written | The current month and the 12 before it (`DAILY_KEEP_MONTHS` = 13), then deleted by the server. `webhook.py --forget-usage` deletes one person's rows sooner |
| `screens` | Paired TV screens, menu bar icons, browser extensions, keys for AI tools (kind `mcp`) and Telegram chats approved to ask the board (kind `telegram`): hash of the key, name, owner, kind, expiry; the rest in `body`. A key for an AI tool also holds what it may read (`scope`: `people` or `totals`) and its first 12 characters (`keyStart`), so an admin can tell rows apart. A Telegram chat holds its `scope` too, and the Telegram user's number and @name (`telegramId`, `telegramUser`); that number is what stands in for its key | Pairing, use, rename, revoke | 30 days, renewed while in use, 1 year at most |
| `revoked` | Hashes of revoked keys, to log a later use | Revoke | 30 days, at most 500 |
| `documents` | Two documents changed as a whole: `locations` (office names, IP ranges, map position, sales team) and `team-csv` (latest Team plan spend, merged per person) | Admin edits | Until changed |
| `audit` | Who did what: login, account and pairing changes, refused actions; `month` for reading by month. Also one row per call of the board's MCP tool (action `mcp-call`): the key's name and id, the tool called, whether it ran, the IP, the name the AI tool gave for itself and the protocol generation; never the key and never the question. And one row per answer to a Telegram chat (action `telegram-ask`): the chat's name and id and the command it was answered; never the words the person typed | Each admin action; each call of the MCP tool; each answer to a Telegram chat | 12 months (`KEEP_MONTHS`); `mcp-call` and `telegram-ask` rows 3 months (`MCP_CALL_KEEP_MONTHS`) |
| `meta` | When the old JSON files were moved in, and how many rows; the first day the daily totals cover (`daily_since`) | Once | Always |

`accounts.db`:

| Table | Content |
|---|---|
| `accounts` | Name, role, OTP secret (base32), created at and by, last login; the linked Telegram user id and @name when Telegram login is used |
| `imported` | Names already imported from `OTP=` in the settings file, so an account deleted on `/admin` does not come back |

Kept only in memory, lost on restart: login sessions (8 hours, 7 days for wall accounts), TV pairing codes (10 minutes), menu bar one-time codes (90 seconds), TV online status, how often each key for an AI tool has asked in the last 10 minutes and the name its tool last gave.

Sent to Telegram, only when asking from Telegram is on (`TELEGRAM_ASK=1`) and only to a chat an admin approved: the text of each answer. It is made from the wall view: counts and costs of the team and of each office, and, for a chat that reads each person, names as a wall screen shows them, state, minutes waiting, cost and quota. Telegram also has what the person wrote to the bot. The server stores none of these messages, and the bot process keeps nothing on disk.

## 3. Record of one computer

`devices.body`, version `v: 1`. The server cleans every field before writing and again when reading (`clean_payload` in `devices.py`): unknown fields are dropped, text is cut to a fixed length and numbers are checked.

| Field | Meaning |
|---|---|
| `device` | Random id `device-[a-z0-9]{1,40}` made by the plugin |
| `name`, `account`, `enteredAccount` | Declared name and Claude account email |
| `ip`, `lanIp`, `ipHistory` | Sending IP (taken from the connection), internal IP, the last 10 IPs of 30 days. The history is built by the server, never sent by the computer |
| `hardwareMark` | One-way hash of the computer's own id; computers with the same mark count as one; never shown |
| `openSessions`, `working`, `waiting` | Session counts |
| `ledger` | Tokens and money per hour, last 8 days |
| `tasks`, `delegating` | Tasks delegated to Gemini, ChatGPT and Gemma, per hour and now |
| `models`, `subagents` | Counts per model and per helper agent |
| `assistants`, `quota` | Which helper assistants are set up; usage limit windows in percent |
| `pluginVersion`, `updatedAt` | Plugin version and time of the numbers |
| `tools` | Only in a report from the connector for Codex, Cursor and Gemini CLI: for each of `codex`, `cursor`, `gemini`, the three session counts. A report with this table is a connector report |

**A connector report** holds `device`, `name`, `account`, `updatedAt`, `tools` and the IP fields the server adds, nothing else that the plugin sends. The server adds up `openSessions`, `working` and `waiting` from `tools` itself. It counts for 2 hours after `updatedAt` (`CONNECTOR_OFFLINE_SECONDS`), where a plugin report counts for 12 minutes, because the connector sends only when something happens in a tool; a report with no session open does not show the person as online, and its `working` count is believed for 30 minutes only (`CONNECTOR_WORKING_SECONDS`), because a tool whose turn fails sends no event. It is merged into the person with the same account and name, and is not counted as a computer or a plugin install. The format in full: [connectors/README.md](../connectors/README.md).

**Never stored:** chat content, questions, file names, project names.

### Totals per person per day

A computer holds its hours for 8 days, and its row leaves the server 30 days after its last send. To compare one week or month with another, the server keeps a longer memory of one thing only: a total per person per day, in the table `daily`.

- **Nothing new is collected.** The totals are sums of numbers the computers already send. A person is told apart the same way as on the board: account plus name.
- **Counting again never adds twice.** Each run takes the last 7 days from what the computers hold now and writes them over the rows that are there. Seven days, because every computer still holds those in full; an older day would come out short, so it is never touched again.
- **The office is the one of that day.** A finished day keeps the office it closed with; a person who moves counts for the new office from the day of the move.
- **This is a longer hold of staff data.** Before this table, a person's cost was gone 30 days after their computer last sent. Now a total per day stays for up to 13 months, with their name and account email. Say so in your notice to staff: [employee-notice.md](employee-notice.md).
- **A person who leaves** stays in the totals until the rows expire. To delete them sooner: `webhook.py --forget-usage <email or name>`, see [OPERATIONS.md](OPERATIONS.md), section 6.
- **Who reads it:** admins and viewers, on `/board`. The wall role gets one thing only: the whole team's cost on each of the last 7 days, one number per day with no person and no office, for the small chart in the menu bar window (`teamDays` in `/data`). Nothing per person or per office of it reaches a TV screen, a menu bar icon, the browser extension, a manager's plugin or the MCP endpoint ([PERMISSIONS.md](PERMISSIONS.md)).

## 4. How the database is used

- **One connection per file, behind a lock.** The web server answers each request in its own thread; all of them share one connection and take turns. At most 300 computers, each sending at most every 30 seconds, is about 10 writes a second at the very most.
- **Transactions.** Every change is one transaction: all of it is written, or nothing. A store keeps its table as a dict in memory and writes only the rows that changed.
- **WAL mode.** Reading does not wait for writing. `synchronous=NORMAL` for the numbers, `FULL` for accounts.
- **Schema versions.** `PRAGMA user_version` holds the version. At start the server runs the missing upgrade steps in order. A database newer than the program is refused, so an older version cannot run on newer data by mistake. `board.db` is at version 2 since the daily totals; `accounts.db` is at version 1.
- **A copy before every upgrade.** Before it upgrades a database that already exists, the server copies it to `<file>.schema-<old version>.bak` next to it (mode `600`), checks that the copy opens and holds the old version, and writes one line to the service log. If the copy cannot be made, it upgrades nothing and stops with a message. The server deletes the copy after 30 days. Going back with it: [OPERATIONS.md](OPERATIONS.md), section 5.
- **Old SQL only.** No `UPSERT`, `RETURNING` or JSON functions, so the server runs on older Linux too.
- **Not on a network folder.** WAL needs a local disk; do not put `DATA_DIR` on NFS.

### What SQLite does not change

SQLite does not encrypt: whoever can read the file reads the data, as with the old JSON files. Protection comes from the file modes, the separate service account, the systemd sandbox, keeping accounts apart, and storing only hashes of pairing keys.

### Moving from the JSON files

Versions before SQLite kept one JSON file per table. At its first start the new version moves them in by itself:

1. Each old file is read; a broken file is skipped and named in the service log.
2. Rows go into the database in one transaction. A row already there is kept.
3. The old files are moved to `data/legacy-json/` and `keys/legacy-json/`. They are never deleted.
4. The log shows `migrated JSON files into ... {"devices": ..., ...}`.

A file put back into `data/` later is moved in at the next start the same way.

## 5. Backup and restore

Back up while the server runs with SQLite's own backup, not `tar` or `cp`, which could copy a half-written WAL. The commands are in [OPERATIONS.md](OPERATIONS.md), section 4.

- Back up `board.db` daily. It holds no secrets. The `.schema-N.bak` file is not a backup for this purpose: it is one copy from the moment of an upgrade.
- Back up `accounts.db` separately, readable by root only. Without it, every account must scan a new QR code.

To go back to a version before SQLite without losing what changed since: `webhook.py --export-json <folder>` writes the databases back as the old JSON files. The totals per day have no place in those files and are left out. See [OPERATIONS.md](OPERATIONS.md), section 5.
