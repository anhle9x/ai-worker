[Tiếng Việt](INSTALL.vi.md) | English <!-- i18n-allow -->

# Install and configure

For the IT person who deploys AI Worker: what you need, the first deployment, releasing updates, the data sent, settings and protection. Using it day to day is in [USER-GUIDE.md](USER-GUIDE.md); running the server is in [OPERATIONS.md](OPERATIONS.md).

## What you need

- **A Linux server** with `python3` 3.8 or newer and systemd. The webhook needs no outside libraries.
- **A dedicated subdomain**, for example `board.company.com`, with a DNS `A` record pointing to the server IP.
- **Caddy** (or nginx) on the server for HTTPS. The webhook listens only inside the server; Caddy takes the outside connections.
- **An allow-list of IPs:** the network IPs of the offices. A computer outside the list cannot see the dashboard, send numbers or download updates.
- **One IT computer** with `ssh-keygen` to keep the update signing key.

Real addresses, the `INGEST_KEY` and the keys do not go into git. The repo only uses sample addresses such as `https://board.company.com`.

## First deployment

1. **Install the webhook.** Copy `server/` to the server and run `sudo bash install.sh`. The first time, the script prints the `INGEST_KEY` and creates the first admin account. Details in [`server/README.md`](../server/README.md).
2. **Turn on HTTPS.** Add a Caddy block for the domain with the allow-list of IPs (template: `server/aiworker.caddy`, change it to your domain and IPs), then add `TRUST_PROXY=1` to `/etc/ai-worker.env` and run `install.sh` again.
3. **Make the signing keys**, on the IT computer:
   ```bash
   mkdir -p ~/.ai-worker-keys && chmod 700 ~/.ai-worker-keys
   ssh-keygen -t ed25519 -C ai-worker-main -f ~/.ai-worker-keys/main
   ssh-keygen -t ed25519 -C ai-worker-backup -f ~/.ai-worker-keys/backup
   ```
   Put the two public keys into `~/.ai-worker-keys/allowed_signers`, one per line like `ai-worker ssh-ed25519 AAAA...`. `build.sh` and `release.sh` copy that file into the package; `keys/allowed_signers` in git stays comments only, so the public repository never carries your keys. Private keys do not go to the server or into git; keep the backup one off this computer.
4. **Build the package.** Copy `packaging/company.example.json` to `packaging/company.json` (this file does not go into git), fill in `webhook` and `ingestKey`, then run:
   ```bash
   bash packaging/build.sh packaging/company.json
   ```
   This makes `dist/AI-Worker-<version>-company.zip`.
5. **Employees install.** Unzip, double-click `INSTALL-Mac.command` or `INSTALL-Windows.bat`, type the full name. The package contains the send code, so give it out inside the company only.
6. **View the dashboard.** Open the webhook address and sign in with the OTP code. The `/board` page has a Plugin column showing which computers are not on the latest version yet.

## Commands on an employee's computer

- `/office`: opens the control panel of the sessions on this computer.
- `/office-pane`: opens the 2D view next to the chat box.
- `/update`: checks for a new version and installs it.

## Menu bar icon for managers

Managers see in the menu bar how many people are waiting for an answer, without opening the board: a native app on macOS, an app next to the clock on Windows (installed from an .msi, no admin rights), a top bar icon on Ubuntu (a .deb package). A click opens a small window with Waiting, Working, Quota, Cost today and Settings. Details: [docs/menu-bar-spec.md](menu-bar-spec.md).

- **Download:** the Admin page, section "Menu bar icon": "Download for macOS" (.zip, and .dmg when the server has the built app), "Download for Windows (.msi)" (the old PowerShell installer stays as "Windows, old installer (.zip)"), "Download for Ubuntu (.deb)". Without `MENUBAR_MAC_APP`, "Download for macOS" gives the SwiftBar-based installer instead of the app.
- **Ubuntu:** open the .deb with App Center, or `sudo apt install ./ai-worker-menubar.deb`; apt adds the AppIndicator libraries, the icon starts at every login, and `sudo apt remove ai-worker-menubar` takes it away.
- **Pairing:** the manager clicks the icon and enters their own account and 6-digit code; an account may pair 2 computers. A manager without an account reads the icon's code to an admin, who enters it under TV screens.
- **The macOS app is built once per company** on a Mac with Apple's Command Line Tools, then served by the server:

```bash
bash server/menubar/macos-app/build.sh https://your-board-address auto "AI Worker"
```

Copy `server/menubar/macos-app/dist/*-menu-bar-mac-app.zip` to the server and set `MENUBAR_MAC_APP` to its path in the env file. The app has an ad-hoc signature, so the first launch needs System Settings > Privacy & Security > Open Anyway once.

## Browser extension for managers

A Chrome or Edge extension shows, on its icon, how many people are waiting for an answer; a click opens the same small window as the menu bar apps. It reads only part of what a wall screen sees, and holds no password, OTP or login cookie. Details: [docs/chrome-extension-spec.md](chrome-extension-spec.md).

1. **Install by hand** on the manager's computer: copy the `extensions/manager/` folder, open `chrome://extensions` (Edge: `edge://extensions`), turn on Developer mode, click "Load unpacked" and choose the folder.
2. **Pair:** click the icon, type the board address, allow access to that one site when the browser asks, and read the 8-digit code to an admin.
3. **The admin approves** it on the Admin page under TV screens, like a screen; the row is marked "Browser extension". Revoking it there makes the extension show "not paired" within a minute.

Once paired, the popup is the same small window as the menu bar apps (five tabs, Settings with notifications, language and unpair). It runs copies of `server/static/mini.js`, `mini.css` and the logos kept in `extensions/manager/mini/`: after changing those files, copy them again (`cp server/static/mini.js server/static/mini.css extensions/manager/mini/`, and `server/menubar/icons/generic-black.png` and `generic-white.png` to `extensions/manager/mini/logo-black.png` and `logo-white.png`), then hand out the folder again.

Test: `node tests/extension/check-extension.js` (runs a local webhook with made-up people, and fails when the copies differ).

## Log in with Telegram (optional)

People who use Telegram every day can log in to the board with Telegram's button instead of typing their name and code. Off until you set it up; the name and 6-digit code always keep working, and admin changes still ask for the code.

1. **Make a bot** (in the Telegram app, phone or computer):
   1. Search for **@BotFather** and open the account with the blue check mark.
   2. Send `/newbot`. BotFather asks for a name: type the name people will see when they confirm a login, for example `AI Worker`.
   3. BotFather asks for a username: type one that ends in `bot` and is not taken, for example `yourcompany_aiworker_bot`. If it says the name is taken, try another.
   4. BotFather replies "Done! Congratulations on your new bot" with the line **"Use this token to access the HTTP API:"** followed by the **token**, which looks like `1234567890:AAH...`. Keep this message open for step 3. The token can sign a login for anyone: do not post it in a chat or a screenshot.
   5. Optional: send `/setuserpic`, pick the bot and send your logo, so people recognise it when they confirm.
2. **Tie the bot to the board's address** (still in @BotFather): send `/setdomain`, pick the bot, and send the board's domain without `https://`, for example `board.company.com`. Correct result: "Success! Domain updated."
3. **Give the server the token and the username.** From your computer, run this; it asks for the token without showing it on screen:
   ```bash
   ssh -t <admin>@<server> 'read -rsp "Bot token: " T; echo; read -rp "Bot username (no @): " N; printf "TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_BOT_NAME=%s\n" "$T" "$N" | sudo tee -a /etc/ai-worker.env >/dev/null && sudo systemctl restart ai-worker-webhook && echo DONE'
   ```
   At `Bot token:` paste the token from step 1.4 and press Enter (nothing shows, that is expected). At `Bot username (no @):` type the username from step 1.3, for example `yourcompany_aiworker_bot`. Correct result: `DONE`, and the login page shows a **Log in with Telegram** button under "or".
   Or edit the file by hand with `sudo nano /etc/ai-worker.env`, add the two lines below, save, and run `sudo systemctl restart ai-worker-webhook`:
   ```
   TELEGRAM_BOT_TOKEN=<the token>
   TELEGRAM_BOT_NAME=<the bot's username, without @>
   ```
4. **Each person links once:** log in with name and code, open `/telegram` (or **Telegram** on the detail board), enter the 6-digit code, press **Log in with Telegram** and confirm in Telegram. Next time they press the button on the login page.

The server never calls Telegram: the button takes the browser to Telegram's login page and back, and the server only checks the signature with the token. The login page loads nothing from Telegram. A signed login is accepted for 5 minutes and once. If Telegram cannot be reached from the office, people log in with name and code. Admins see who linked Telegram on `/admin` and can unlink it there; reissuing a key or making an account a wall account also unlinks it.

## Releasing an update

1. Change `version` in `.claude-plugin/plugin.json`.
2. On the IT computer, type the key password when asked:
   ```bash
   bash packaging/release.sh
   ```
   This makes the package, manifest and signature in `server/releases/` (outside git).
3. Copy `server/` to the server and run `sudo bash install.sh`.

Employee computers ask the server at most once every 4 hours, and 30 minutes later if it failed. When there is a new version, the bar above the input box shows an `Update` button; after clicking, quit the app completely and open it again. A release only reaches computers installed with version 0.23.0 or newer; the technical pack does not self-update yet, reinstall it with the zip.

**Safety:** an employee computer installs only when the signature and the checksum are correct, so even a hijacked server cannot hand out a bad package. A computer that cannot check the signature (OpenSSH too old) is only told there is a new version and does not install it. A folder with `.git` never self-updates.

**Rolling back:** release the old version again with a new signature, or on that computer rename the `ai-worker.old` folder next to the plugin folder back to the old name.

**Changing keys:** add the new key to `~/.ai-worker-keys/allowed_signers`, release one version, then sign with the new key from the next version. If the main key leaks, sign at once with the backup key and drop the old key in that version.

## Data sent to the server

Only the company package sends; the normal package sends nothing. The numbers go to the company's own server, not to outsiders.

**Sent:** full name, the email of the Claude account and the email typed at install, a random computer ID, a hardware mark (the computer's own id after a one-way hash, so a reinstalled plugin is still the same computer; never shown on the board), internal IP, number of open sessions, working, waiting for an answer, the model in use, the Claude account quota, tokens and cost per hour, number of tasks given to each assistant, the kinds of helper assistants running, the assistants present on the computer, the plugin version. The server also records the public IP of the sending computer by itself, and keeps the internal IPs each computer used in the last 30 days.

**Not sent:** chat content, questions, answers, chat titles, file names, file contents, project folder names, descriptions of the tasks given to assistants.

**Who can see it:** admins and viewers see names, emails and IPs; the wall screen shows shortened names only. Anyone with sudo on the server can read all the numbers. See `server/README.md`.

On the computer, the session history and numbers are in `~/.local/share/ai-worker/`. Files that look like they hold secrets (.env, key, token...) are recorded by name only, never by content.

To turn sending off on one computer: add `"sharing": { "enabled": false }` to `~/.local/share/ai-worker/config.js`.

## Language

The product comes in English and Vietnamese.

- **Pages** (the on-computer office page, the dashboard, the admin page): each page has an EN / VI switch, and the choice is remembered in the browser. The first time, the page follows the browser language.
- **Plugin:** the installer saves the `language` field (`"en"` or `"vi"`) in `~/.local/share/ai-worker/user.json`, and the plugin reads it. You can edit that field by hand. The environment variable `AI_WORKER_LANG` (`en` or `vi`) wins over the file.
- **Installers:** `AI_WORKER_LANG=en` or `vi` forces the language; without it the installer uses the computer's language (on a Mac it asks macOS, on Windows it uses the Windows language) and falls back to English.
- **Server:** the language of each page is the visitor's choice first; `DEFAULT_LANG` (`en` or `vi`) in `/etc/ai-worker.env` sets the language for visitors who have not chosen, otherwise the browser language is used, then English.

## Settings and cost

`~/.local/share/ai-worker/config.js` is created once and is not overwritten by updates: change display names, `usdRate` (default 26000, used only for the Vietnamese display), and turn each assistant on or off with `workers`.

Cost is the figure Claude Code calculates at API prices. On a subscription plan it is a converted cost for comparison, not the money actually charged.

Without Gemini, ChatGPT or Gemma the plugin still runs with Claude alone. The installer asks which assistants to install.

No server but a shared drive: leave out `webhook` and set `folders` to the path of the mounted drive. This way there is no admin page and no self-update.

## Protecting against floods (DDoS)

The server limits what one client can use: connections in all and per IP, header size, the life of a connection, memory and threads (`MemoryMax`, `TasksMax`, `LimitNOFILE` in the service file). So a flood makes this service slow or stops it, without taking the whole server down. No software on the server can stop a large flood, because the traffic fills the network before it arrives.
- **Best:** keep it reachable only from your company network, as the template `server/aiworker.caddy` does.
- **If it must be open to the Internet:** put it behind a protection service such as Cloudflare.
- **nginx instead of Caddy:** set `proxy_set_header X-Forwarded-For $remote_addr;` and `proxy_set_header X-Forwarded-Proto $scheme;`, otherwise visitors can fake their IP and get past the login limits. The webhook trusts these headers from a local proxy; `TRUST_PROXY=0` turns that off.
- **One limit that remains:** everyone in the install package shares `INGEST_KEY`, so a staff member can still send false numbers under another name. Change the key and reinstall if a package leaks.
