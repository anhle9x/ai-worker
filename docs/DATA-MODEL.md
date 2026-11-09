[Tiếng Việt](DATA-MODEL.vi.md) | English <!-- i18n-allow -->

# Data design

What the dashboard server stores, where, for how long and who can read it. The server stores everything in two SQLite databases. SQLite comes with Python, so nothing is added to install.

Settings named here (`DATA_DIR`, `KEYS_DIR`, limits) are in `server/board/settings.py`. The schema, its upgrades and the move from the old JSON files are in `server/board/db.py`. The code that reads and writes each table is in `server/board/stores.py`, `server/board/devices.py` and `server/board/views.py`.

## 1. Files

| File | Default after install | Owner and mode | Holds |
|---|---|---|---|
| `data/board.db` (with `-wal`, `-shm`) | `/opt/ai-worker/data/` | `ai-worker`, `600`, folder `750` | Numbers from computers, pairings, locations, Team plan, audit log, rewind history |
| `keys/accounts.db` (with `-wal`, `-shm`) | `/opt/ai-worker/keys/` | `ai-worker`, `600`, folder `700` | Accounts and their OTP secrets |
| `/etc/ai-worker.env` | | `root`, `600` | Settings and the `INGEST_KEY` |

The accounts are in their own file, in their own folder, so a backup of the numbers never carries the login secrets. The systemd service may write only to these two folders (`ProtectSystem=strict`, `ReadWritePaths`).

## 2. Tables

`board.db`:

| Table | Content | Written when | Kept |
|---|---|---|---|
| `devices` | One row per computer: its latest numbers in `body` (section 3), `seen_at` = when the server received them | Each send, at most every 30 seconds | Deleted 30 days after `seen_at` (`KEEP_DAYS`) |
| `identities` | `device → account, name` of the first send | A new computer's first send | Until removed with `--forget-device` |
| `history` | One row each time a person's state changes: time, person, state, tasks delegated | State changes | 24 hours (rewind button) |
| `screens` | Paired TV screens, menu bar icons and browser extensions: hash of the key, name, owner, kind, expiry; the rest in `body` | Pairing, use, rename, revoke | 30 days, renewed while in use, 1 year at most |
| `revoked` | Hashes of revoked keys, to log a later use | Revoke | 30 days, at most 500 |
| `documents` | Two documents changed as a whole: `locations` (office names, IP ranges, map position, sales team) and `team-csv` (latest Team plan spend, merged per person) | Admin edits | Until changed |
| `audit` | Who did what: login, account and pairing changes, refused actions; `month` for reading by month | Each admin action | 12 months (`KEEP_MONTHS`) |
| `meta` | When the old JSON files were moved in, and how many rows | Once | Always |

`accounts.db`:

| Table | Content |
|---|---|
| `accounts` | Name, role, OTP secret (base32), created at and by, last login; the linked Telegram user id and @name when Telegram login is used |
| `imported` | Names already imported from `OTP=` in the settings file, so an account deleted on `/admin` does not come back |

Kept only in memory, lost on restart: login sessions (8 hours, 7 days for wall accounts), TV pairing codes (10 minutes), menu bar one-time codes (90 seconds), TV online status.

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

**Never stored:** chat content, questions, file names, project names.

## 4. How the database is used

- **One connection per file, behind a lock.** The web server answers each request in its own thread; all of them share one connection and take turns. At most 300 computers, each sending at most every 30 seconds, is about 10 writes a second at the very most.
- **Transactions.** Every change is one transaction: all of it is written, or nothing. A store keeps its table as a dict in memory and writes only the rows that changed.
- **WAL mode.** Reading does not wait for writing. `synchronous=NORMAL` for the numbers, `FULL` for accounts.
- **Schema versions.** `PRAGMA user_version` holds the version. At start the server runs the missing upgrade steps in order. A database newer than the program is refused, so an older version cannot run on newer data by mistake.
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

- Back up `board.db` daily. It holds no secrets.
- Back up `accounts.db` separately, readable by root only. Without it, every account must scan a new QR code.

To go back to a version before SQLite without losing what changed since: `webhook.py --export-json <folder>` writes the databases back as the old JSON files. See [OPERATIONS.md](OPERATIONS.md), section 5.
