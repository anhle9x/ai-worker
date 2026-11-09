[Tiếng Việt](README.vi.md) | English <!-- i18n-allow -->

# AI Worker Office dashboard webhook (for the IT team)

A small program that runs on a Linux server inside the internal network. Staff computers send their Claude usage numbers to it;
the manager's computer reads them back to show the **Whole team** dashboard. No outside libraries: it needs only `python3` (3.8 or newer) and systemd.

## Install (once, about 5 minutes)

Copy this `server/` folder to the server, then:

```bash
sudo bash install.sh
```

The script will:
- create the system user `ai-worker` and copy the program to `/opt/ai-worker`;
- generate the send key `INGEST_KEY` into `/etc/ai-worker.env` (readable by root only);
- create the service `ai-worker-webhook` (it restarts itself when the server boots or the program fails), default port **8788**;
- on the first install, print the **webhook address** and the **INGEST_KEY**: send these two lines to whoever builds the package. When you run it again to update,
  it does not print the key (the key stays in the env file);
- if the env file has `TRUST_PROXY=1` (behind Caddy): set `BIND_ADDR=127.0.0.1` and let only localhost call in
  (systemd `IPAddressAllow=localhost`), so all access goes through HTTPS; the list of allowed IPs is in `aiworker.caddy`.

To change the port: `sudo PORT=9000 bash install.sh` (first install). Firewall: open the port to the internal network,
for example `ufw allow from 192.168.0.0/16 to any port 8788`. It does not need to be open to the Internet.

All settings, with notes: [`ai-worker.env.example`](ai-worker.env.example).

## The send key and the safeguards

`INGEST_KEY` is in every staff member's install package: it is only for sending and cannot read anyone's numbers (viewing the dashboard needs an OTP login).
Because anyone with the install package has the key, the webhook also blocks by itself:
- **each device is tied to one person**: the first send writes `device-... → account + name` to the `identities` table; the same device sending
  under another person's name is refused (409, written to the log). When a computer goes to someone else: stop the service, run
  `sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys python3 /opt/ai-worker/webhook.py --forget-device <device-id>`, start the service;
- at most 300 sends per 10 minutes and 10 new devices per day for each IP, 300 devices in total;
- OTP login: 5 wrong tries from one IP lock that IP for 15 minutes; 20 wrong tries on one account lock that account for 15 minutes.

To change the key: edit `/etc/ai-worker.env`, run `sudo systemctl restart ai-worker-webhook`, then rebuild the package.

## The whole-team dashboard in the browser (OTP login)

Open `http://<server-IP>:8788/` on a computer or phone (inside a network allowed to reach the webhook) and enter the 6-digit code
from **Google Authenticator** (or Microsoft Authenticator). It is an operations dashboard in the style of a monitoring center:
a list of people who are active, a diagram person -> Claude -> Gemini/ChatGPT/Gemma (light beads move while work is done or delegated;
click a card to see one person's numbers), a 24-hour cost heat map, indicators, tasks delegated per hour to each AI,
an event stream (state changes, delegation), and a 24-hour chart. It updates every 10 seconds. The separate text board is at `/board`.
The page needs the `static/` folder next to `webhook.py` (install.sh copies it); without it the webhook falls back to the text board. No plugin is needed.

Daily work is done on the `/admin` page (admin role only): accounts and QR codes, role changes, locations, the Team plan, open sessions, the log. Creating, reissuing, changing the role of and deleting an account needs the OTP code again, valid for 5 minutes. The last admin cannot be deleted or demoted, and nobody can delete themselves.

Three roles; the server checks them itself, it does not just hide buttons:

| | Admin | View only | Wall display |
|---|---|---|---|
| `/admin` page | Yes | No | No |
| Email, internal IP, `/board` | Yes | Yes | No |
| Stay logged in | 8 hours | 8 hours | 7 days |

TV screens: open the dashboard page on the TV (a smart TV shows the code by itself; for a computer plugged into a TV, click "Wall screen" on the login page), then scan the QR code on the TV with a phone camera that is on the company network, or enter the code in the TV screens section of `/admin`; check the device and IP, give it a name, approve it. The TV gets the wall role, is not logged out when the webhook restarts, renews itself for 30 days while in use, and after one year at most must be paired again. Revoke it right on the page. After a new version is installed, an open screen reloads by itself within about 10 seconds; the Admin page shows which screens are running, which version, and has a remote reload button. At most 20 screens. To pair an old screen again, choose "Replace" so no extra row is made; a screen unused for over 30 days drops out of the list by itself. Sessions are stored only as hashes in `data/tv.json`; delete this file and restart to revoke them all.

Full screen: the browser only allows it when someone acts on that very computer, so a wall display uses the first touch or key press for this. A computer plugged into a TV opens Chrome in kiosk mode so nobody has to touch it; use a separate profile folder, otherwise the command is ignored when Chrome is already open:

```bash
# Windows (cmd): put this shortcut in the shell:startup folder so it comes up when the computer starts
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --user-data-dir=C:\ai-worker-tv https://<board-address>/
# macOS
open -na "Google Chrome" --args --kiosk --user-data-dir="$HOME/ai-worker-tv" https://<board-address>/
# Linux
google-chrome --kiosk --user-data-dir="$HOME/ai-worker-tv" https://<board-address>/
```

An easier way: on that computer open `/tv`, download the file at the bottom of the page and double-click it; choose 1 to open by itself at startup, 2 to remove. Windows may show SmartScreen; macOS needs right-click > Open the first time.

To leave kiosk mode: Alt+F4 (macOS: Cmd+Q). The Exit button on the screen only logs out, it does not close the window.

Commands on the server, only for rescue, in the `server/` folder:

```bash
sudo bash manage-otp.sh --rescue it-team  # lost the admin: create or reissue an admin, print the QR code
sudo bash manage-otp.sh --delete it-team  # emergency delete when the page cannot be opened
sudo bash manage-otp.sh --list            # who has an account, with what role
```

Accounts and keys are in `keys/accounts.db`, a folder only the webhook can read, apart from `data/board.db`. A backup of `board.db` has no keys; to restore without scanning again, back up `keys/` separately, readable by root only. On the first run the webhook imports the accounts from `OTP=` in the env file by itself, with no new scan; keep those lines so you can roll back to the old version.

Action log: the `audit` table in `data/board.db` records logins, changes and refusals; kept 12 months, with no keys or CSV content.

- Anyone with sudo on the server can issue keys for themselves (and read all the numbers): keep the number of people with sudo small. Every issue/revoke is logged, see it with `journalctl -t ai-worker-otp`.
- One key per person, revoked separately.
- Restarting the webhook means entering the code again, wall displays included. Each code can be used only once.
- 5 wrong tries within 15 minutes block that IP for 15 minutes. The log shows who logged in and from which IP: `journalctl -u ai-worker-webhook`.
- The hour of "today" follows `TZ_OFFSET` (default 7, Vietnam time); the exchange rate follows `USD_RATE` (default 26000) and is used only on Vietnamese pages (English pages show US dollars, with no conversion).
- Language of the pages: the visitor's own choice first (the EN / VI buttons, kept in the `lang` cookie), then `DEFAULT_LANG` in `/etc/ai-worker.env` (`en` or `vi`; empty follows the browser), then English. After changing `DEFAULT_LANG`, run `sudo systemctl restart ai-worker-webhook`. Messages the server writes to its log, the refusals sent to `/ingest`, and the TV install files are always English.
- An HTTP connection is not encrypted: open this page only inside the company network. To view it from outside you need HTTPS first.

## Operation

```bash
systemctl status ai-worker-webhook          # is it running
journalctl -u ai-worker-webhook -n 50       # log (errors only, not every send)
curl http://127.0.0.1:8788/health       # {"ok": true}
```

Data: `/opt/ai-worker/data/board.db` (SQLite), one row of a few KB per computer, overwritten when the computer sends again. Tables and backup: [docs/DATA-MODEL.md](../docs/DATA-MODEL.md).
A computer silent for over 30 days has its row deleted by itself. The load is very light: each computer sends at most once every 30 seconds when its numbers change,
and at least once every 5 minutes while Claude is open.

To update the program: copy the new version over the old one and run `sudo bash install.sh` again (the key and data are kept).
To remove: `sudo systemctl disable --now ai-worker-webhook`, delete `/opt/ai-worker`, `/etc/ai-worker.env`,
`/etc/systemd/system/ai-worker-webhook.service`.

## What is stored

Name, Claude account email, a random device id, the **sending computer's IP** (the server writes it from the connection, staff computers cannot claim one), the internal IP the computer reports (the server keeps the ones used in the last 30 days, at most 10), a hardware mark (a one-way hash of the computer's own id; devices with the same mark count as one, the mark is never shown on a page), the number of sessions open / working / waiting for a reply, tokens and money per hour
(last 8 days), the number of tasks delegated to Gemini/ChatGPT/Gemma per hour. **Not stored**: chat content, questions, file names,
project names. The connection is HTTP inside the internal network (not encrypted); for HTTPS put it behind your existing nginx/Caddy and use an
`https://...` address when building the package; then add `TRUST_PROXY=1` to `/etc/ai-worker.env` so the staff computer's real IP is recorded instead of the proxy's IP.
