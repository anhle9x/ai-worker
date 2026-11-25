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
| `keys/receiver-secrets.json` | `/opt/ai-worker/keys/`, only with `RECEIVER=1` | `ai-worker`, `600` | What the optional Go receiver reads: the secrets that sign computer keys and the code of the internal paths. Written again at every start ([RECEIVER.md](RECEIVER.md)) |

The accounts are in their own file, in their own folder, so a backup of the numbers never carries the login secrets. The systemd service may write only to these two folders (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Tables

`board.db`:

| Table | Content | Written when | Kept |
|---|---|---|---|
| `devices` | One row per computer for the plugin, and one more for the connector for Codex, Cursor and Gemini CLI where it is installed: the latest numbers in `body` (section 3) without the hour book, `seen_at` = when the server received them | On a send that changes more than its time, and at least once a minute while the computer sends (`STATE_REWRITE_SECONDS`) | Deleted 30 days after `seen_at` (`KEEP_DAYS`), with its rows of `device_hours` and `device_days` |
| `device_hours` | The hour book of each computer, one row per hour and kind (`ledger`, `tasks`, `blocks`): the hour (hours since 1970, UTC), the kind, the computer, and that hour's numbers as JSON in `body`. The key starts with the hour, so the newest hours of every computer sit together at the end of the table; a second index reads one computer's hours. Since schema version 6 | A send writes only the hours that changed | The newest 240 hours of each kind (`MAX_HOURS_PER_DEVICE`), and while the computer is in `devices` |
| `device_days` | One row per computer per local day (the day follows `TZ_OFFSET`): money in millionths of a dollar, tokens in and out, tasks given to Gemini, ChatGPT and Gemma, added up from that day's rows of `device_hours`. The board and the daily totals read these instead of adding up the hours again. Since schema version 6 | With the hours of that day | As long as that day has hours in `device_hours` |
| `identities` | `device → account, name` of the first send | A new computer's first send | Until removed with `--forget-device` |
| `device_keys` | `device → when the newest key of its own it has sent with was issued, when it was revoked`. Never the key itself: keys are checked by their signature (`server/board/devicekeys.py`). A key only issued writes nothing | A computer's first send with a newer key of its own, or a revoke | Until removed with `--forget-device` |
| `device_roaming` | `device → since when, by which admin` for the computers an admin let send numbers and fetch updates from any network (`OFFICE_NETS`). Only the computer's id, no address. Since schema version 7 | **Any network** or **Office only** on the Admin page | Until taken back, or the computer is revoked or forgotten |
| `history` | One row each time a person's state changes: time, person, state, tasks delegated | State changes | 24 hours (rewind button) |
| `daily` | One row per person per day (the day follows `TZ_OFFSET`): name, account email, the office the person was in when the day closed, cost in dollars, tokens in and out, tasks given to Gemini, ChatGPT and Gemma. Added up from `ledger` and `tasks` of that person's computers (section 3); no computer sends anything new for it | Every 5 minutes the last 7 days are counted again and written over; an older day is left as it was last written | The current month and the 12 before it (`DAILY_KEEP_MONTHS` = 13), then deleted by the server. `webhook.py --forget-usage` deletes one person's rows sooner |
| `screens` | Paired TV screens, menu bar icons, browser extensions, keys for AI tools (kind `mcp`), keys for AI projects and applications (kind `project`, with `keyStart` too) and Telegram chats approved to ask the board (kind `telegram`): hash of the key, name, owner, kind, expiry; the rest in `body`. A key for an AI tool also holds what it may read (`scope`: `people` or `totals`) and its first 12 characters (`keyStart`), so an admin can tell rows apart. A Telegram chat holds its `scope` too, and the Telegram user's number and @name (`telegramId`, `telegramUser`); that number is what stands in for its key. A chat an admin allowed the window inside Telegram has `app: true`; a chat that turned alerts on has `notify`, `notifyMinutes` and `notifyLang` | Pairing, use, rename, revoke | 30 days, renewed while in use, 1 year at most |
| `revoked` | Hashes of revoked keys, to log a later use | Revoke | 30 days, at most 500 |
| `documents` | Documents changed as a whole: `locations` (office names, IP ranges, map position, sales team), `team-csv` (latest Team plan spend, merged per person) and `project-prices` (prices an admin pasted for AI projects and applications) | Admin edits | Until changed |
| `audit` | Who did what: login, account and pairing changes, refused actions; `month` for reading by month. Also one row per call of the board's MCP tool (action `mcp-call`): the key's name and id, the tool called, whether it ran, the IP, the name the AI tool gave for itself and the protocol generation; never the key and never the question. And one row per answer to a Telegram chat (action `telegram-ask`): the chat's name and id and the command it was answered; never the words the person typed. And one row per piece of work a computer handed to a helper (action `ai-delegation`): the person's name and account, the computer's id, and the fields of the record above; never the prompt or the answer. Each row also holds `prev` and `hash`: the fingerprint of the row before it and of itself, so a row changed or taken out by hand breaks the chain, which the Admin page checks | Each admin action; each call of the MCP tool; each answer and alert to a Telegram chat (`telegram-ask`, `telegram-alert`, the latter with how many people and never who); each opening of the window inside Telegram, each refusal, and each chat allowed or stopped (`telegram-app-*`) | 12 months (`KEEP_MONTHS`); `mcp-call`, `telegram-ask` and `ai-delegation` rows 3 months (`MCP_CALL_KEEP_MONTHS`) |
| `delegations_seen` | The computer's id and the record's id of each `ai-delegation` row already written, so a record a computer sends again on its next beats is written once | On each send that holds a new record | 4 days (`SEEN_DAYS`) |
| `project_turns` | Each turn an AI project or application sent (only with `AI_PROJECTS=1`): the project (the id of its key), `turn_id`, time, UTC day, environment, and the turn in the meter's line format, cleaned to the known fields: times, outcome, and per model the provider, the model name, calls, errors, retries and token counts. Never a question, an answer, a user or an error message; the meter does not have them | Each send to `/projects/ingest`; a turn sent again is ignored | 30 days (`PROJECT_TURN_KEEP_DAYS`), or until an admin deletes a revoked project's numbers |
| `project_daily` | One row per project, UTC day, environment and model: the project's name, turns, calls, errors, retries, turns not measured and token counts; a row with no provider and no model counts each turn once. Money is never stored: it is worked out from the tokens and the price file when someone looks | With each new turn | The current month and the 12 before it, like `daily`, or until an admin deletes a revoked project's numbers |
| `meta` | When the old JSON files were moved in, and how many rows; the first day the daily totals cover (`daily_since`); the fingerprint of the newest audit row (`audit_head`); the offset from UTC, in seconds, `device_days` counted its days in (`device_days_tz`: when `TZ_OFFSET` changes, the server counts `device_days` again at its next start) | Once; `audit_head` on every audit row | Always |

`accounts.db`:

| Table | Content |
|---|---|
| `accounts` | Name, role, OTP secret (base32), created at and by, last login; the linked Telegram user id and @name when Telegram login is used |
| `imported` | Names already imported from `OTP=` in the settings file, so an account deleted on `/admin` does not come back |

Kept only in memory, lost on restart: login sessions (8 hours, 7 days for wall accounts), TV pairing codes (10 minutes), menu bar one-time codes (90 seconds), TV online status, how often each key for an AI tool has asked in the last 10 minutes and the name its tool last gave.

Sent to Telegram, only when asking from Telegram is on (`TELEGRAM_ASK=1`) and only to a chat an admin approved: the text of each answer, and of each alert a chat turned on with `/alerts` (how many people have waited longer than the chat's minutes, and, for a chat that reads each person, their names as a wall screen shows them with their minutes). It is made from the wall view: counts and costs of the team and of each office, and, for a chat that reads each person, names as a wall screen shows them, state, minutes waiting, cost and quota. Telegram also has what the person wrote to the bot. The server stores none of these messages, and the bot process keeps nothing on disk.

The window inside Telegram (`TELEGRAM_APP=1`) sends nothing through Telegram's servers: Telegram's app opens the board's page in its own browser, and that browser reads the wall view from the board over HTTPS, as the browser extension does. Telegram learns only that the window was opened. The sessions of the window live in the webhook's memory, as a hash, and are never written to disk.

## 3. Record of one computer

`devices.body`, version `v: 1`, with `ledger`, `tasks` and `blocks` in rows of `device_hours` since schema version 6 (`read_book` in `devices.py` puts them together again, and `--export-json` writes the record whole, as before). The server cleans every field before writing and again when it loads a row into memory (`clean_payload` and `DeviceCache` in `devices.py`); the board, the history and the daily totals read the cleaned copy kept in memory, which is written together with the tables and loaded again when another program changes the file: unknown fields are dropped, text is cut to a fixed length and numbers are checked. The memory holds each computer's record without its hour book, its rows of `device_days`, and only its hours near its last send: 48 hours of `ledger` and `tasks`, 8 days of `blocks`. All the SQL of these three tables is in `server/board/devicestore.py`.

| Field | Meaning |
|---|---|
| `device` | Random id `device-[a-z0-9]{1,40}` made by the plugin. A new install makes 16 letters and digits from secure randomness, as the connector does; an id made by an older version (8) is kept |
| `name`, `account`, `enteredAccount` | Declared name and Claude account email |
| `ip`, `lanIp`, `ipHistory` | Sending IP (taken from the connection), internal IP, the last 10 IPs of 30 days. The history is built by the server, never sent by the computer |
| `hardwareMark` | One-way hash of the computer's own id; computers with the same mark count as one; never shown |
| `openSessions`, `working`, `waiting` | Session counts |
| `ledger` | Tokens and money per hour, last 8 days |
| `tasks`, `delegating` | Tasks delegated to Gemini, ChatGPT and Gemma, per hour and now |
| `blocks` | Per hour, last 8 days: how many times ai-worker stopped or asked about something, by kind `secret`, `commit`, `risky`, `page`, `answer`; counts only, never what it was (`BLOCK_KINDS` in `devices.py`) |
| `delegations` | Only on the way in, never stored with the computer's row: the records of work handed to ChatGPT, Gemini or Gemma in the last two days (at most 100), each with an id, the time, the tool, the helper, `plugin` or `ai-workers`, the lengths of the prompt and the answer, a salted fingerprint of the prompt, the outcome (`ok`, `error`, `refused`, `declined`), what the check of the answer found (`secret`, `aimed`, `command`) and the kinds of secret that stopped it. Never the prompt or the answer. Each new one becomes an `ai-delegation` row of `audit` (`clean_delegations` in `devices.py`) |
| `models`, `subagents` | Counts per model and per helper agent |
| `assistants`, `quota` | Which helper assistants are set up; usage limit windows in percent |
| `pluginVersion`, `updatedAt` | Plugin version and time of the numbers |
| `tools` | Only in a report from the connector for Codex, Cursor and Gemini CLI: for each of `codex`, `cursor`, `gemini`, the three session counts. A report with this table is a connector report |

**A connector report** holds `device`, `name`, `account`, `updatedAt`, `tools` and the IP fields the server adds, nothing else that the plugin sends. The server adds up `openSessions`, `working` and `waiting` from `tools` itself. It counts for 2 hours after `updatedAt` (`CONNECTOR_OFFLINE_SECONDS`), where a plugin report counts for 12 minutes, because the connector sends only when something happens in a tool; a report with no session open does not show the person as online, and its `working` count is believed for 30 minutes only (`CONNECTOR_WORKING_SECONDS`), because a tool whose turn fails sends no event. It is merged into the person with the same account and name, and is not counted as a computer or a plugin install. The format in full: [connectors/README.md](../connectors/README.md).

**Never stored:** chat content, questions, file names, project names.

### Format v: 2

A newer plugin may send `v: 2` instead of `v: 1`. The server reads both, for as long as any computer sends `v: 1`; what it keeps is always the `v: 1` record above, so the board, the history and the daily totals do not know which format a computer used. The shared sample in `tests/contract/ingest-v2/` (inputs and the results they must give) and `server/test_contract.py` hold the two formats to the same board; a receiver written in another language plays the same file.

- **The state** (`name`, `account`, session counts, `models`, `quota`, `pluginVersion` and the rest) has the same fields as `v: 1` and is sent in full every time.
- **The hours** are in `hours: {ledger, tasks, blocks}` and hold only the hours that changed since the server last accepted a send. Each hour is the whole value of that hour, not what was added, and replaces it; an hour not sent stays as it was; an hour sent as an empty table is removed (it left the computer's 8 days). Sending the same hour twice gives the same result, so no sequence number is needed (`merge_hours` in `devices.py`, a pure function another receiver copies).
- **`full: true`** means `hours` holds the computer's whole book and replaces it. Unless the server asked for it, a computer may do that once an hour (`FULL_BOOK_SECONDS`); a full book sent sooner is merged hour by hour, which loses nothing.
- **Money** is `usdMicro`, a whole number of millionths of a dollar. A `v: 1` send has only dollars (`usd`); the server turns them into `usdMicro` (rounded) and adds every total up in whole numbers, so the sums are exact and the same in any order and any language. The row keeps `usd` beside it for older versions of the server.
- **Limits:** the same cleaning as `v: 1`, plus: at most 240 hours of each kind, none more than a day ahead of the server's clock, none older than 240 hours.
- **Out of order:** a `v: 2` send stamped up to a minute older than what the server holds (`REORDER_WINDOW_MS`; two sessions of one computer sending at once) is dropped. Further back is taken as a clock put back, and saved.
- **One computer, one write at a time:** reading the row kept, merging and writing happen under one lock, so two sends of one computer at the same moment never lose each other's hours.

The answer to every send, in both formats (an older plugin reads only `ok` and `deviceKey`):

| Field | Meaning |
|---|---|
| `accepts` | The formats this server reads: `[1, 2]`. A plugin sends `v: 2` only to a server that says so; an older server answers only `{"ok": true}` |
| `minGapMs`, `stateGapMs` | The shortest gap between sends of numbers and of state: 2 seconds by default (`INGEST_MIN_GAP_MS`, `INGEST_STATE_GAP_MS`). The Python server makes it longer when more computers sent in the last minute than `INGEST_SENDS_PER_SECOND` (default 1,000) answers every 2 seconds, and the Go receiver when more computers are connected than the machine answers every 2 seconds ([RECEIVER.md](RECEIVER.md), `RECEIVER_SENDS_PER_SECOND`). The plugin keeps it, at most 2 minutes, and after a 429 or 503 with `Retry-After` sends nothing before that time (at most 10 minutes) |
| `maxGapMs` | Send at least this often even when nothing changed: 4 minutes (`INGEST_MAX_GAP_MS`, at most 5), well under the 12 minutes after which a computer shows as offline |
| `needFull` | `true` when a `v: 2` send of changed hours came from a computer the server has no book for (a new computer, a lost or broken row): nothing of it was kept, and the next send must be `full: true` |
| `boot` | A new random value each time the server starts. A plugin that sees it change sends its latest hours again, in case the last seconds before a crash were not written |
| `deviceKey` | As before: this computer's own key, when it sent with the shared key or its key is getting old |
| `ingestUrls`, `ingestTtlMs` | Only to a computer chosen for the Go receiver and sending with its own key: where to send from now on, and for how long before asking `GET /ingest/route` again ([RECEIVER.md](RECEIVER.md), "Which computers send to the receiver") |

### Totals per person per day

A computer holds its hours for 8 days, and its row leaves the server 30 days after its last send. To compare one week or month with another, the server keeps a longer memory of one thing only: a total per person per day, in the table `daily`.

- **Nothing new is collected.** The totals are sums of numbers the computers already send. A person is told apart the same way as on the board: account plus name.
- **Counting again never adds twice.** Each run takes the last 7 days from what the computers hold now and writes them over the rows that are there. Seven days, because every computer still holds those in full; an older day would come out short, so it is never touched again.
- **The office is the one of that day.** A finished day keeps the office it closed with; a person who moves counts for the new office from the day of the move.
- **This is a longer hold of staff data.** Before this table, a person's cost was gone 30 days after their computer last sent. Now a total per day stays for up to 13 months, with their name and account email. Say so in your notice to staff: [employee-notice.md](employee-notice.md).
- **A person who leaves** stays in the totals until the rows expire. To delete them sooner: `webhook.py --forget-usage <email or name>`, see [OPERATIONS.md](OPERATIONS.md), section 6.
- **Who reads it:** admins and viewers, on `/board`. The wall role gets one thing only: the whole team's cost on each of the last 7 days, one number per day with no person and no office, for the small chart in the menu bar window (`teamDays` in `/data`). Nothing per person or per office of it reaches a TV screen, a menu bar icon, the browser extension, a manager's plugin or the MCP endpoint ([PERMISSIONS.md](PERMISSIONS.md)).

## 4. How the database is used

- **One connection per file, behind a lock.** The web server answers each request in its own thread; all of them share one connection and take turns. At 300 computers, each sending at most every 2 seconds, that is at most about 150 writes a second; docs/BENCHMARK.md has the measured ceiling.
- **Transactions.** Every change is one transaction: all of it is written, or nothing. A store keeps its table as a dict in memory and writes only the rows that changed.
- **WAL mode.** Reading does not wait for writing. `synchronous=NORMAL` for the numbers, `FULL` for accounts.
- **Schema versions.** `PRAGMA user_version` holds the version. At start the server runs the missing upgrade steps in order. A database newer than the program is refused, so an older version cannot run on newer data by mistake. `board.db` is at version 6 since the hour books moved into `device_hours` and `device_days` (version 5 brought keys of their own for computers, 4 AI projects, 3 the records of work handed to helpers, 2 the daily totals). A step may be a Python function run in the upgrade's transaction: version 6 takes each record's book out of its `devices` row, writes its hours and days, and leaves a row it cannot read as it was. The secrets that sign those keys live in the `meta` table of `accounts.db`.
- **A copy before every upgrade.** Before it upgrades a database that already exists, the server copies it to `<file>.schema-<old version>.bak` next to it (mode `600`), checks that the copy opens and holds the old version, and writes one line to the service log. If the copy cannot be made, it upgrades nothing and stops with a message. The server deletes the copy after 30 days. Going back with it: [OPERATIONS.md](OPERATIONS.md), section 5.
- **Old SQL where it counts.** No `RETURNING` and no JSON function of SQLite: the JSON is read and written by Python. A row written over another uses `INSERT ... ON CONFLICT ... DO UPDATE` when SQLite has it (3.24, 2018), and an `UPDATE` then an `INSERT` on an older one, so the server still runs on older Linux. Never `INSERT OR REPLACE` in the new tables: it deletes the row first.
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
- Back up `accounts.db` separately, readable by root only. Without it, every account must scan a new QR code. Its OTP secrets are sealed with `/etc/ai-worker-otp.key` (schema version 2): keep a copy of that key apart from the backups, see [OPERATIONS.md](OPERATIONS.md) section 4.

To go back to a version before SQLite without losing what changed since: `webhook.py --export-json <folder>` writes the databases back as the old JSON files. The totals per day have no place in those files and are left out. See [OPERATIONS.md](OPERATIONS.md), section 5.
