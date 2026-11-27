[Tiếng Việt](OPERATIONS.vi.md) | English <!-- i18n-allow -->

# Operations handbook

For the admin who runs the dashboard server: daily checks, problems, backup, upgrade and rollback, logs. Installing the first time is in [server/README.md](../server/README.md).

All commands run on the server unless stated otherwise.

## 1. Where things are

| Item | Place |
|---|---|
| Program | `/opt/ai-worker/` (`webhook.py`, `board/`, `static/`, `menubar/`, `releases/`) |
| Data | `/opt/ai-worker/data/board.db`, see [DATA-MODEL.md](DATA-MODEL.md) |
| Accounts | `/opt/ai-worker/keys/accounts.db` |
| Settings | `/etc/ai-worker.env` (root only) |
| Service | `ai-worker-webhook` (systemd), runs as user `ai-worker` |
| The key that seals the OTP secrets | `/etc/ai-worker-otp.key` (root only); keep a copy apart from the backups |
| Telegram bot, only with `TELEGRAM_ASK=1` | Service `ai-worker-telegram`, its own user of the same name, settings in `/etc/ai-worker-telegram.env` |
| Go receiver, only when set up with `install-receiver.sh` | Service `ai-worker-receiver` (user `ai-worker`), program `/opt/ai-worker/ai-worker-receiver`, settings in `/etc/ai-worker-receiver.env` |
| HTTPS and IP allow-list | Caddy, for example `/etc/caddy/aiworker.caddy` (sample: `server/aiworker.caddy`) |
| Access log | `/var/log/caddy/aiworker.log`, 10 files of 20 MB |

## 2. Daily checks

```bash
systemctl status ai-worker-webhook
```

Correct result: `active (running)`.

```bash
curl http://127.0.0.1:8788/health
```

Correct result: `{"ok": true}`.

```bash
journalctl -u ai-worker-webhook -n 50
```

Correct result: logins and the odd refusal, no `Traceback`.

On the dashboard, a computer silent for 12 minutes shows as offline and one silent for a day is dimmed. Many offline at once usually means the network or Caddy, not the webhook.

## 3. Problems

| Sign | Likely cause | What to do |
|---|---|---|
| Service will not start, log says `INGEST_KEY is required` | Settings file missing or empty | Check `/etc/ai-worker.env`, run `sudo bash install.sh` again |
| Admin page says *Log check: a line … was changed or taken out* | Someone edited `board.db` by hand, or restored an old copy over a newer one | Find who has sudo or file access on the server; compare the last fingerprint with the one you noted; restoring a backup made before the chain began does not trigger it |
| Admin page says *Cost check: the numbers of … were changed after the day was sealed* | A row of `daily` for a day older than a week was edited, added or deleted by hand | As above; the day's line `daily-seal` in the log holds the numbers it had when sealed |
| Admin page lists keys for AI tools *not used for N days* | A tool was set up once and dropped, or its config file was copied elsewhere | Ask whose it is; **Revoke** what nobody needs, so a key left in an old config file cannot read the board |
| Every computer offline | Caddy stopped, certificate expired, or the office IP changed | `systemctl status caddy`; update the IP list in the Caddy file and `systemctl reload caddy` |
| One computer missing | Its IP is outside the allow-list, or it was installed with an old package | Ask the user to run `/office`; check the Caddy access log for its IP |
| Log shows `401 wrong ingest key` | The package was built with another `INGEST_KEY` | Rebuild the package with the current key and reinstall on that computer |
| Log shows `use this computer's own key` | The computer has already sent with a key of its own but now sends with the shared key, usually because its plugin data was wiped. A key the server only gave, never used, does not cause this | `--forget-device <device id>` (as for a computer that changed hands); it enrols again at its next send |
| A computer must stop sending (lost, stolen, left) | | On the Admin page, **Computers and their keys**, press **Revoke** on its row; or from the command line `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --revoke-device <device id>`: its key stops at once and the shared key no longer sends for it |
| Log shows `outside the office network` or `this computer may not send from outside the office` | A send or `/update` came from outside `OFFICE_NETS`: with the shared key, or from a computer not let send from any network. If it comes from computers in the office, `OFFICE_NETS` and the Caddy list differ (the Admin page warns when your own address counts as outside) | Make `OFFICE_NETS` in `/etc/ai-worker.env` the same as `remote_ip` in the Caddy file and restart the webhook; or press **Any network** on that computer's row ([INSTALL.md](INSTALL.md#sending-from-outside-the-office-chosen-computers)). A lost computer: **Revoke** it, do not let it back |
| Every computer must get a new key (the secret that signs them is old, or the file of secrets leaked) | | Stop the webhook, run `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --rotate-device-secret`, start it again: every computer gets a new key at its next send, and old keys still work until then. With `--drop-old` the old keys stop at once and every computer enrols again with the shared key ([RECEIVER.md](RECEIVER.md), section 6) |
| Log shows `409 this device is linked to another person` | The computer changed hands | `sudo systemctl stop ai-worker-webhook`, then `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <device id>`, then start the service |
| Log shows `busy: 32 requests at once, … answered 503 in the last minute` | More than `BUSY_REQUESTS` (32) requests were being answered at once: sends and requests from people not logged in got 503 with a `Retry-After` of 30 to 90 seconds; people logged in still got the board | Nothing when it is rare: the computers send again by themselves. When it keeps coming, see [which setup for your size](INSTALL.md#which-setup-for-your-size) |
| Log shows `429 too many submissions` | One computer sends too often, usually a loop | Check that computer; each computer may send 20 times at once, then once a second |
| The Go receiver does not answer, or a new version of it misbehaves (only with `install-receiver.sh`, [RECEIVER.md](RECEIVER.md#the-installer)) | Its service stopped, its certificate ran out or cannot be read, or the new program has a fault | `sudo sh install-receiver.sh --check` in `server/` says which of the five checks fails and asks its `/health`; `sudo journalctl -u ai-worker-receiver -n 50` for its log; `--rollback` puts the program before back; `--remove` stops it, and the computers go back to the webhook on their next send |
| Log shows `507 device limit reached` | The limit of computers is reached (`MAX_DEVICES`, 300 by default) | Wait for old computers to drop after 30 days, or raise `MAX_DEVICES` in `/etc/ai-worker.env` and restart the webhook ([which setup for your size](INSTALL.md#which-setup-for-your-size)) |
| "Too many wrong tries" at login | 5 wrong OTP codes in 15 minutes | Wait 15 minutes; check the phone clock is set automatically |
| A TV shows "not seen for a while" | The TV is off or lost its network | Turn it on; if it asks for a code, pair it again on `/admin` |
| Staff do not get the update | Plugin older than 0.23.0, signature check failed, or the plugin folder has `.git` | See section 5 |
| Lost every admin | | `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder |
| Service will not start after an upgrade, log says `Cannot back up ... before upgrading its schema` | The disk is full, or the service may not write in the data folder | Nothing was changed. Free some space (`df -h /opt/ai-worker/data`), check the folder belongs to `ai-worker`, start the service again |
| Service will not start, log says `has schema version 2, newer than this program` | An older program was installed over a database the newer one had upgraded | Install the newer version again, or go back with the copy from before the upgrade: section 5 |
| Telegram's page says the bot domain is invalid | The bot is not tied to the board's address | Send `/setdomain` to @BotFather with the board's domain |
| "This Telegram account is not linked yet" | The person has not linked Telegram | They log in with name and code, then link it on `/telegram` |
| The Telegram token leaked | Anyone with it can sign a login | Revoke it with `/revoke` in @BotFather, put the new token in `/etc/ai-worker.env`, restart the service |
| The Admin page says Telegram refuses the bot's token | The token for asking from Telegram is wrong or was revoked | Put the right token in `/etc/ai-worker-telegram.env` (`TELEGRAM_ASK_TOKEN=`), run `sudo bash install.sh` |
| The Admin page says another program reads the same bot | The token is also used somewhere else, or a webhook is set on the bot | One bot has one reader: make a bot with @BotFather for this alone and use its token |
| The Admin page says the server cannot reach Telegram | The firewall, the limit on the bot's service, or a network that blocks Telegram | On the server: `curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org`. A number means Telegram is reachable: set `TELEGRAM_NETS` in `/etc/ai-worker-telegram.env` and run `install.sh` (see INSTALL) |
| The Admin page says the bot process has not been heard from, or the bot does not answer | The service is not running | `systemctl status ai-worker-telegram`, then `journalctl -u ai-worker-telegram -n 30`. The log names the reason, never the token |
| The window inside Telegram shows *Forbidden* | Caddy refused the IP the phone or computer came from. An office with several Internet lines may send Telegram out through one that is missing from the list | `sudo grep '/tg/app' /var/log/caddy/aiworker.log \| tail -3`, read `remote_ip`; add it to the `remote_ip` line only if it is one of your own lines, then `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`. A proxy set in Telegram or a VPN: turn it off |
| No **AI Worker** button in a chat | The chat is not allowed the window, `TELEGRAM_APP_URL` is missing, or the bot process is not running | On `/admin` the chat's row must say *opens the window*; `install.sh` says when `TELEGRAM_APP_URL` is wrong; `journalctl -u ai-worker-telegram -n 30` shows `a menu button could not be set` when Telegram refused it. Close the chat in Telegram and open it again |
| The window says to close it and open it again | Its session ended: the webhook restarted, an hour passed without use, or the chat lost the window | Close the window and tap **AI Worker** again; if it still says so, check the chat on `/admin` |
| A chat that turned alerts on gets no message | Alerts are off for that chat, nobody waited past its minutes, it is between 19:00 and 07:00, or the chat reached its cap (6 an hour, 30 a day) | `/alerts` in the chat says whether they are on and after how many minutes; a wait over 4 hours, or a person shown offline, is not told; `journalctl -u ai-worker-telegram -n 30` shows `an answer could not be sent` when Telegram refused a message |
| The token of the bot for asking leaked | Someone can read what people send the bot and write to them in its name; they cannot read the board | `/revoke` in @BotFather, put the new token in `/etc/ai-worker-telegram.env`, run `sudo bash install.sh` |

## 4. Backup and restore

Back up every day, while the server runs. Use SQLite's own backup: `tar` or `cp` could copy a half-written WAL.

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/data/board.db /backup/ai-worker-board-$(date +%F).db
```

Back up the accounts separately, readable by root only, because they hold the OTP secrets (and the linked Telegram users). Keep a copy of `/etc/ai-worker.env` the same way: it holds `INGEST_KEY` and, when used, the Telegram bot token:

```bash
sudo python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' /opt/ai-worker/keys/accounts.db /root/ai-worker-accounts-$(date +%F).db && sudo chmod 600 /root/ai-worker-accounts-*.db
```

Correct result: no output, and the new file is there.

The OTP secrets in `accounts.db` are sealed with the OTP key `/etc/ai-worker-otp.key`, which `install.sh` makes once (root only). A copy of `accounts.db` alone logs nobody in, and the server does not start on it without that key. Keep one copy of the key somewhere safe, apart from your backups of `/opt/ai-worker`, for example on the admin's password manager or a USB stick in a drawer:

```bash
sudo cat /etc/ai-worker-otp.key
```

Correct result: one line of 64 letters and digits. If the key is lost and its copy too, see "The OTP key is lost" in section 5.

Restore:

```bash
sudo systemctl stop ai-worker-webhook
sudo rm -f /opt/ai-worker/data/board.db-wal /opt/ai-worker/data/board.db-shm /opt/ai-worker/keys/accounts.db-wal /opt/ai-worker/keys/accounts.db-shm
sudo cp <board backup> /opt/ai-worker/data/board.db
sudo cp <accounts backup> /opt/ai-worker/keys/accounts.db
sudo chown ai-worker: /opt/ai-worker/data/board.db /opt/ai-worker/keys/accounts.db
sudo chmod 600 /opt/ai-worker/data/board.db /opt/ai-worker/keys/accounts.db
sudo systemctl start ai-worker-webhook
```

Then check `/health` and log in once.

## 5. Upgrade and rollback

### Server

1. Before upgrading, keep the running version: `sudo cp -a /opt/ai-worker /opt/ai-worker.prev` (this includes data and keys).
2. Copy the new `server/` folder to the server and run `sudo bash install.sh` in it. Data, keys and the settings file are kept.
3. Check: `systemctl status ai-worker-webhook`, `/health`, log in, open `/admin`.

Rolling back the server: stop the service, run `install.sh` from the old `server/` folder, start the service. If the new version changed the schema, the older program refuses the database and says so in the log: put the copy from before the upgrade back first, as below.

#### Going back after the schema changed

The schema is the layout of the tables in the database file. The first version with totals per day raises `board.db` from schema version 1 to 2; `accounts.db` does not change. At its first start on a database that already exists, that version:

1. copies `board.db` to `board.db.schema-1.bak` in the same folder (mode `600`) and checks that the copy opens,
2. writes `backed up ... (schema version 1) to ... before upgrading to schema version 2` to the service log,
3. only then upgrades. If the copy cannot be made, nothing is changed and the service stops with `Cannot back up ...`.

To go back to the older version:

```bash
sudo systemctl stop ai-worker-webhook
```

```bash
sudo ls -l /opt/ai-worker/data/board.db.schema-1.bak
```

Correct result: one line with the file, its size above zero. If the file is not there, stop here and use `/opt/ai-worker.prev/data/` or your daily backup instead (section 4).

```bash
sudo rm -f /opt/ai-worker/data/board.db-wal /opt/ai-worker/data/board.db-shm
sudo cp /opt/ai-worker/data/board.db.schema-1.bak /opt/ai-worker/data/board.db
sudo chown ai-worker: /opt/ai-worker/data/board.db
sudo chmod 600 /opt/ai-worker/data/board.db
```

Then run `sudo bash install.sh` in the old `server/` folder (it starts the service), check `/health` and log in once. The two `rm` targets are SQLite's own side files of the newer database; left in place they would be applied to the older file.

What going back loses: everything written to `board.db` after the upgrade, such as the totals per day, audit lines, screens or keys paired and locations named since. The live board fills again within minutes, because every computer sends its last 8 days of hours with each report. Accounts are untouched.

The server deletes `board.db.schema-1.bak` 30 days after the upgrade (log: `deleted the upgrade backup ...`). It is a full copy of people's numbers: keep it as private as `board.db`, and copy it elsewhere before the 30 days are over only if you need it longer.

The same holds for every later schema change, with that version's number in the file name. The version that keeps the hour books in rows of their own (`device_hours`, `device_days`, see [DATA-MODEL.md](DATA-MODEL.md)) raises `board.db` from schema version 5 to 6, so its copy is `board.db.schema-5.bak`: use that name in the steps above. The upgrade runs in one transaction, so a failure half way leaves the database at version 5 and the service stops with the error in the log.

#### Going back after the OTP secrets were sealed

The first version that seals the OTP secrets raises `accounts.db` from schema version 1 to 2 and logs `Sealed <n> OTP secrets with the OTP key`. An older version refuses that file, because it would read a sealed secret as the secret itself and nobody could log in. Before installing the older version, store the secrets as they were, with the newer version still installed, in the `server/` folder you install from (`manage-otp.sh` is not copied to `/opt/ai-worker`):

```bash
sudo bash manage-otp.sh --unseal
```

Correct result: `The OTP secrets are stored as they are again, and the webhook is stopped.` Then run `sudo bash install.sh` in the old `server/` folder. Nothing is lost. The copy `accounts.db.schema-1.bak` also holds the accounts as they were before the upgrade; the server deletes it after 7 days, since its secrets are not sealed.

#### The OTP key is lost

The service log says `... are sealed, but the OTP key cannot be read` or `... it is not the key they were sealed with`, and the webhook does not start. First put the key file back from its copy, as root, then run `sudo bash install.sh` again:

```bash
sudo install -m 600 -o root -g root <copy of the key> /etc/ai-worker-otp.key
```

If the key is gone for good, the sealed secrets cannot be opened by anyone. Remove those accounts, then make a new key and a new admin, in the `server/` folder:

```bash
sudo bash manage-otp.sh --forget-sealed
sudo rm -f /etc/ai-worker-otp.key
sudo bash install.sh
```

`install.sh` makes a new key and, when no admin is left, asks for the name of the first one. Everyone else gets a new account on `/admin` and scans a new QR code.

Going back to a version before SQLite (0.24 or older) without losing what changed since. The export writes each account as it is stored, so with the OTP key its secrets come out sealed, and a version that old does not open them: run `manage-otp.sh --unseal` first, as above (it leaves the webhook stopped).

```bash
sudo systemctl stop ai-worker-webhook
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --export-json /opt/ai-worker/data/export
```

Then run `install.sh` from the old `server/` folder, move `data/export/data/*` into `data/` and `data/export/keys/accounts.json` into `keys/`, run `chown -R ai-worker: /opt/ai-worker/data /opt/ai-worker/keys`, and start the service. The JSON files kept since the move are in `data/legacy-json/`; `keys/legacy-json/accounts.json` is deleted 30 days after the move, since its OTP secrets are not sealed.

### Plugin on staff computers

1. On the signing computer, change `version` in `.claude-plugin/plugin.json` and run `bash packaging/release.sh` (asks for the signing key password).
2. Copy `server/` to the server and run `sudo bash install.sh`.
3. Computers ask the server at most every 4 hours, then show an **Update** button.

Rolling back the plugin: release the old code again under a new version number, signed. On a single computer, rename the `ai-worker.old` folder next to the plugin folder back to the plugin's name.

### Keys

- **Signing key:** add the new key to `~/.ai-worker-keys/allowed_signers`, release one version, then sign with the new key. If the main key leaks, sign at once with the backup key and drop the old key in that version.
- **`INGEST_KEY`:** changing it stops every computer until it gets a package built with the new key. Change it only when it has leaked.

## 6. Logging policy

| Log | Content | Kept | Who reads it |
|---|---|---|---|
| Audit log, table `audit` in `board.db` | Login, account and role changes, pairing and revoking screens, locations, Team CSV loads (date range and count only), refused actions: who, role, IP, path, time. Also, read apart: calls of the board's MCP tool, answers to Telegram chats, and records of work handed to ChatGPT, Gemini or Gemma | 12 months, and 3 months for those three kinds read apart; older rows deleted by the server; each row carries the fingerprint of the one before, and `/admin` says if one was changed or taken out by hand. Each day of `daily` older than a week is sealed in it (`daily-seal`): `/admin` lists the fingerprint of the last 14 sealed days, and each morning a Telegram chat linked to an admin account gets the newest one (day, number of cost rows, fingerprint; no name, no money). Keep those messages or note the fingerprints: a different one later means the log was rewritten | Admin, on `/admin` by month |
| Service log (journald) | Start, login lines, refusals, errors. Not every send | By the system's journald settings | Root on the server |
| Caddy access log | Every request: IP, path, status | 10 files of 20 MB | Root on the server |
| Rewind history, table `history` in `board.db` | State changes per person | 24 hours | Everyone logged in, through the rewind button |
| Totals per day, table `daily` in `board.db` | One row per person per day: cost, tokens, tasks delegated, office, with name and account email | The current month and the 12 before it, older rows deleted by the server | Admin and viewer, on `/board` |
| AI projects and applications, tables `project_turns` and `project_daily` in `board.db` (only with `AI_PROJECTS=1`) | Each turn a project sent: times, outcome, and per model calls, errors and tokens; never a question, an answer or a user. Totals per project, day and model | Turns 30 days, totals the current month and the 12 before it, older rows deleted by the server | Admin and viewer, on `/projects` |

Never logged: chat content, questions, file names, OTP codes, keys.

To delete one person's totals per day before they expire, for example when they ask or after they have left:

```bash
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-usage <email or name>
```

Correct result: `deleted <number> daily rows of <email or name>`. The service can keep running. A day already sealed (older than a week) is sealed again in the audit log, reason `forget-usage`, so the cost check stays clean; the new line does not say who. Days of the last week that a computer of that person still reports are written again at the next count, so for someone who has left, run it a week after their last day.

## 7. Site record

Keep one record per installation in the company's internal documents, **not in this repository**:

| Item | Value |
|---|---|
| Server name and OS | |
| Domain | |
| Allowed office IP ranges | |
| Plugin version in use | |
| Admin accounts (names only) | |
| Where backups go, and how often | |
| Who holds the signing key and the backup key | |
| Date of last upgrade, and by whom | |
| Last audit fingerprint noted from `/admin`, and when | |

## 8. Removing

```bash
sudo systemctl disable --now ai-worker-webhook
sudo rm -rf /opt/ai-worker /etc/ai-worker.env /etc/ai-worker-otp.key /etc/systemd/system/ai-worker-webhook.service /etc/systemd/system/ai-worker-webhook.service.d
```

Before those two lines, when they were set up: the Go receiver with `sudo sh install-receiver.sh --remove` in the `server/` folder, then delete `/etc/ai-worker-receiver.env`; the Telegram bot by setting `TELEGRAM_ASK=0` in `/etc/ai-worker.env` and running `sudo bash install.sh` once more (it removes the service `ai-worker-telegram`), then delete `/etc/ai-worker-telegram.env`. The users `ai-worker` and `ai-worker-telegram` stay until you remove them (`sudo userdel <name>`).

Back up `data/` and `keys/` first if you may need them again.
