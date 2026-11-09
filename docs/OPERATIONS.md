[Tiếng Việt](OPERATIONS.vi.md) | English <!-- i18n-allow -->

# Operations handbook

For the IT person who runs the dashboard server: daily checks, problems, backup, upgrade and rollback, logs. Installing the first time is in [server/README.md](../server/README.md).

All commands run on the server unless stated otherwise.

## 1. Where things are

| Item | Place |
|---|---|
| Program | `/opt/ai-worker/` (`webhook.py`, `board/`, `static/`, `menubar/`, `releases/`) |
| Data | `/opt/ai-worker/data/board.db`, see [DATA-MODEL.md](DATA-MODEL.md) |
| Accounts | `/opt/ai-worker/keys/accounts.db` |
| Settings | `/etc/ai-worker.env` (root only) |
| Service | `ai-worker-webhook` (systemd), runs as user `ai-worker` |
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
| Every computer offline | Caddy stopped, certificate expired, or the office IP changed | `systemctl status caddy`; update the IP list in the Caddy file and `systemctl reload caddy` |
| One computer missing | Its IP is outside the allow-list, or it was installed with an old package | Ask the user to run `/office`; check the Caddy access log for its IP |
| Log shows `401 wrong ingest key` | The package was built with another `INGEST_KEY` | Rebuild the package with the current key and reinstall on that computer |
| Log shows `409 this device is linked to another person` | The computer changed hands | `sudo systemctl stop ai-worker-webhook`, then `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <device id>`, then start the service |
| Log shows `429 too many submissions` | One address sends too often, often a loop or many computers behind one IP | Check that address; the limit is 300 sends per 10 minutes per IP |
| Log shows `507 device limit reached` | 300 computers reached | Wait for old computers to drop after 30 days, or raise `MAX_DEVICES` in code |
| "Too many wrong tries" at login | 5 wrong OTP codes in 15 minutes | Wait 15 minutes; check the phone clock is set automatically |
| A TV shows "not seen for a while" | The TV is off or lost its network | Turn it on; if it asks for a code, pair it again on `/admin` |
| Staff do not get the update | Plugin older than 0.23.0, signature check failed, or the plugin folder has `.git` | See section 5 |
| Lost every admin | | `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder |
| Telegram's page says the bot domain is invalid | The bot is not tied to the board's address | Send `/setdomain` to @BotFather with the board's domain |
| "This Telegram account is not linked yet" | The person has not linked Telegram | They log in with name and code, then link it on `/telegram` |
| The Telegram token leaked | Anyone with it can sign a login | Revoke it with `/revoke` in @BotFather, put the new token in `/etc/ai-worker.env`, restart the service |

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

Rolling back the server: stop the service, run `install.sh` from the old `server/` folder, start the service. If the new version changed the schema, also restore `data/` and `keys/` from `/opt/ai-worker.prev/`; a newer database refuses to start with an older program and says so in the log.

Going back to a version before SQLite (0.24 or older) without losing what changed since:

```bash
sudo systemctl stop ai-worker-webhook
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --export-json /opt/ai-worker/data/export
```

Then run `install.sh` from the old `server/` folder, move `data/export/data/*` into `data/` and `data/export/keys/accounts.json` into `keys/`, run `chown -R ai-worker: /opt/ai-worker/data /opt/ai-worker/keys`, and start the service. The JSON files kept since the move are in `data/legacy-json/` and `keys/legacy-json/`.

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
| Audit log, table `audit` in `board.db` | Login, account and role changes, pairing and revoking screens, locations, Team CSV loads (date range and count only), refused actions: who, role, IP, path, time | 12 months, older files deleted by the server | Admin, on `/admin` by month |
| Service log (journald) | Start, login lines, refusals, errors. Not every send | By the system's journald settings | Root on the server |
| Caddy access log | Every request: IP, path, status | 10 files of 20 MB | Root on the server |
| Rewind history, table `history` in `board.db` | State changes per person | 24 hours | Everyone logged in, through the rewind button |

Never logged: chat content, questions, file names, OTP codes, keys.

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

## 8. Removing

```bash
sudo systemctl disable --now ai-worker-webhook
sudo rm -rf /opt/ai-worker /etc/ai-worker.env /etc/systemd/system/ai-worker-webhook.service /etc/systemd/system/ai-worker-webhook.service.d
```

Back up `data/` and `keys/` first if you may need them again.
