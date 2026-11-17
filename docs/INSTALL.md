[Tiếng Việt](INSTALL.vi.md) | English <!-- i18n-allow -->

# Install and configure

For the admin who deploys AI Worker: what you need, the first deployment, releasing updates, the data sent, settings and protection. Using it day to day is in [USER-GUIDE.md](USER-GUIDE.md); running the server is in [OPERATIONS.md](OPERATIONS.md).

## What you need

To look at the board before deploying anything, run `python3 server/demo.py` (on Windows: `py server\demo.py`) on your own computer: it shows the board with sample people and needs no server (see the [README](../README.md#quick-start)).

- **A Linux server** with `python3` 3.8 or newer and systemd. The webhook needs no outside libraries.
- **A dedicated subdomain**, for example `board.company.com`, with a DNS `A` record pointing to the server IP.
- **Caddy** (or nginx) on the server for HTTPS. The webhook listens only inside the server; Caddy takes the outside connections.
- **An allow-list of IPs:** the network IPs of the offices. A computer outside the list cannot see the dashboard, send numbers or download updates.
- **One signing computer** with `ssh-keygen` to keep the update signing key.

Real addresses, the `INGEST_KEY` and the keys do not go into git. The repo only uses sample addresses such as `https://board.company.com`.

## First deployment

1. **Install the webhook.** Copy `server/` to the server and run `sudo bash install.sh`. The first time, the script prints the `INGEST_KEY` and creates the first admin account. Details in [`server/README.md`](../server/README.md).
2. **Turn on HTTPS.** Add a Caddy block for the domain with the allow-list of IPs (template: `server/aiworker.caddy`, change it to your domain and IPs), then add `TRUST_PROXY=1` to `/etc/ai-worker.env` and run `install.sh` again.
3. **Make the signing keys**, on the signing computer:
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

## Codex, Cursor and Gemini CLI on the board

Someone who works in Codex, Cursor or Gemini CLI can show on the same board, with or without Claude Code on their computer. A small connector (`connectors/`) does it: a hook that each tool runs when a session starts, a prompt is sent, the tool asks for an approval, a turn ends and the session closes.

**Install on one computer.** In the unzipped company package:

- macOS: double-click `INSTALL-Other-Tools-Mac.command`.
- Ubuntu: open Terminal in the unzipped folder and type `bash INSTALL-Other-Tools-Linux.sh`.
- Windows: double-click `INSTALL-Other-Tools-Windows.bat`.

From a copy of this repository instead of a package: `bash connectors/install.sh --server https://board.example.com` (Windows: `powershell -ExecutionPolicy Bypass -File connectors\install.ps1 -Server https://board.example.com`); it asks for the send key.

The installer asks about each tool it finds on the computer. It adds its hooks to that tool's own settings (`~/.codex/hooks.json` or `config.toml`, `~/.cursor/hooks.json`, `~/.gemini/settings.json`) and leaves everything else in them alone; a copy of the file as it was is kept next to it, ending in `.ai-worker-backup`. A settings file it cannot read as plain JSON is not changed: the installer prints the hooks to add by hand. It uses the name and email the plugin already has on that computer, so one person stays one row on the board. When asked, it also copies 16 of the plugin's skills to `~/.agents/skills/`, the folder all three tools read; `make-skill` and `improve-codebase-architecture` lean on Claude Code and are not copied. A skill you changed after it was copied is yours: a later run does not replace it and `--uninstall` does not remove it, and the installer says so. To get the package's version again, delete that skill's folder and run the installer.

**Codex asks once.** Codex runs a hook only after its owner has looked at it: open Codex, type `/hooks`, and trust the seven hooks whose command ends in `ai-worker-hook.sh`. Cursor and Gemini CLI pick the hooks up at their next start.

**Check and remove.** `bash ~/.local/share/ai-worker/connector/install.sh --status` shows what is installed and what the board last answered; the same command with `--uninstall` takes the hooks, the skills and the connector's folder out again. On Windows: `powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.local\share\ai-worker\connector\install.ps1" -Status` or `-Uninstall`.

**What the board shows for these tools:** sessions open, working and waiting, per tool. Waiting means the tool asked for an approval, or ended its turn with a question. Tokens, cost, quota and model are not known for them and show as a dash.

**Limits to know:**

- The connector sends only when something happens in a tool. A session with no event for 2 hours is no longer counted, and a tool closed without its end event (a closed laptop lid, a killed terminal) can stay on the board for up to 2 hours. A turn that ends in an error sends no event: that session shows as working until its next event, for 30 minutes at most.
- Each computer with the connector counts as one more device for the limits in [ARCHITECTURE.md](ARCHITECTURE.md): 300 devices in all, 10 new ones per IP per day. An office behind one shared public IP that installs it for many people on one day will see some computers refused until the next day.
- The connector does not update itself: after a new version of AI Worker, run the installer again.
- The server must be this version or newer. An older server accepts the report but shows the person as offline after 12 minutes and does not name the tool.
- **How far it is tested.** The hook and the installer pass their tests with sample events and a temporary home folder on macOS, on Ubuntu and on Windows (the last two on GitHub's test machines); in a real Codex CLI 0.164.0 session on macOS the start, prompt, stop and end hooks ran, a question from Codex showed on a sample board as waiting, and cutting a turn short with Esc was seen to send `Interrupt` and no `Stop`, after which the session showed as idle; the approval and tool hooks have not been seen in a real session yet. Cursor and Gemini CLI are written from their documentation and have not been tried inside the real tools, and no real tool has been tried on Windows or Linux yet. On Windows each hook costs the start of PowerShell, about half a second on the test machine. If you try one, please tell us what you see.

The report format, for writing a connector for another tool: [connectors/README.md](../connectors/README.md).

## Ask the board from an AI tool (MCP)

The server has an MCP endpoint at `/mcp`. MCP (Model Context Protocol) is the common way an AI tool calls a tool on another server. With a key, an AI tool such as Claude Code, Codex CLI, Cursor or Gemini CLI can answer "who is waiting longest right now?" from the board's numbers, the way `/ai-worker:board` does in Claude Code. The endpoint only reads, and it gives what a wall screen gets: names, states, cost and quota, never an email, an IP or a device id.

**It is on, and it gives nothing out until an admin approves a key.** To take the endpoint and its pages away, add `MCP=0` to `/etc/ai-worker.env` and restart the service.

**Getting a key.**

1. The person opens `https://board.example.com/mcp/connect` in a browser on the company network and clicks **Get a code**. The page shows an 8-digit code. Admins and view-only accounts reach this page from the **Connect an AI tool** button on `/board`, and the Admin page shows the link with a **Copy link** button under **TV screens**.
2. An admin opens `/admin`, goes to **TV screens**, types the code and clicks **View request**. The card says it is a key for an AI tool. The admin chooses what the key may read (team and office totals only, or each person too), names the key and clicks **Approve**.
3. The person's page then shows the key once, with the line to paste into each tool. Approve only a code the person read to you themselves: the code says nothing about who is asking.

**What to know about a key.**

- It works on `/mcp` only, and no other key works there: not a TV's, an extension's or a plugin's, nor the send key.
- The server stores a hash of it, never the key. The Admin page shows its first characters, what it reads and when it was last used, and **Revoke** stops it at once. A key that is lost cannot be shown again: revoke it and ask for a new one.
- It lapses after 30 days without use, and after 1 year at most.
- One key may ask 120 times in 10 minutes. At most 50 keys.
- Each read is logged for 3 months and shown on the Admin page under **Reads by AI tools**: which key, which tool, from which IP. The question itself never reaches the server.
- What the tool reads is sent to the company that makes the tool, as part of the person's question. A key that reads totals only keeps people's names out of that.

**Tried so far.** In the real tools, on macOS: Claude Code 2.1.318 and Codex CLI 0.164.0 each read the board and answered from it. Claude Code spoke protocol revision 2026-07-28 and, when told to, the older handshake that opens with `initialize`; Codex spoke revision 2025-06-18. A key that reads totals only was tried with Claude Code: it said that each person's numbers exist but its key may not read them. The `claude mcp add` and `codex mcp add` lines the page gives were run as written. Cursor and Gemini CLI have not been tried in the real tools yet, and no tool has been tried on Windows or Linux; those lines follow each tool's documentation. The Chat tab of the Claude desktop app was tried as well, through a claude.ai connector: see the next section.

### claude.ai and the Chat tab of Claude Desktop: off by default

The Caddy template (`server/aiworker.caddy`) lets only your networks in, and that covers `/mcp`: an AI tool reaches it only from a computer on those networks. claude.ai, the Chat tab of Claude Desktop and the Claude mobile app are different. They connect from Anthropic's servers, not from the person's computer, and they need the address to answer on the public Internet on port 443 ([Anthropic's help page on custom connectors](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp)). So they are refused unless you open that door yourself.

To open it for `/mcp` and nothing else, replace the two lines `@outside not remote_ip ...` and `respond @outside ...` in the Caddy block with:

```
	# your networks reach everything; Anthropic's outbound addresses reach /mcp and nothing else
	@outside {
		not remote_ip 203.0.113.0/24 198.51.100.0/24
		not {
			remote_ip 160.79.104.0/21 153.61.208.0/20
			path /mcp
		}
	}
	respond @outside "Forbidden" 403
```

Then run `caddy validate` on the file and `sudo systemctl reload caddy`. If you opened `/ingest` the way the template shows, keep its `not path /ingest` line inside `@outside` as well. If your file names the matcher something other than `@outside`, keep your name. To close the door again, put the two lines back and reload.

The two ranges in the block are Anthropic's outbound IPv4 addresses as published on [platform.claude.com/docs/en/api/ip-addresses](https://platform.claude.com/docs/en/api/ip-addresses), read on 2026-11-16. Read that page yourself before you use them, and again from time to time: the ranges can change.

Before you open it:

- **`/mcp` then takes connections from outside the office.** Anyone on claude.ai who types your address arrives from those same Anthropic addresses, so the key is the only thing between them and the numbers. Every other path stays closed, `/mcp/connect` included: a key is still asked for from inside your networks.
- **In claude.ai:** Customize > Connectors > Add custom connector, and the address `https://board.example.com/mcp`. Claude first marks "Sign in now" as detected, because the board answers that it wants a key: choose **No sign-in** instead. Under **Request headers** add the header `authorization` with the value `Bearer`, a space, and the key. Leave the transport on **Streamable HTTP**.
- **Claude may call the tool without asking.** The connector's page lists the board's tool as read-only with "Needs approval", and says that this setting applies in Manual mode. In the test Claude called the tool with no question. What the tool reads is decided by the key alone, so approve a key that reads totals only unless people's names are meant to go out.
- **The log shows Anthropic's address, not the person's,** and the key's row gets a line saying it was used from a new IP.
- **Tried once, on 2026-11-17, from the Chat tab of the Claude desktop app,** against a board behind Caddy 2.6.2 with the block above and a key that reads totals only: the connector was added, and Claude answered from the board's numbers. Three things were seen. The first attempt to add the connector said the address could not be reached and the second went through; the reason was not found. Claude also asked three `/.well-known/oauth-...` paths, which this block keeps closed (403), and that did not stop it. Request headers were offered on the account used. claude.ai in a browser and the mobile app use the same connector and were not tried.

## Menu bar icon for managers

Managers see in the menu bar how many people are waiting for an answer, without opening the board: a native app on macOS, an app next to the clock on Windows (installed from an .msi, no admin rights), a top bar icon on Ubuntu (a .deb package). A click opens a small window with Waiting, Working, Quota, Cost today and Settings. Details: [docs/menu-bar-spec.md](menu-bar-spec.md).

- **Download:** the Admin page, section "Menu bar icon": "Download for macOS ▾" (.dmg when the server has the built app, and .zip), "Download for Windows ▾" (.msi, and the old PowerShell installer "AI-Worker-windows.zip"), "Download for Ubuntu (.deb)". Without `MENUBAR_MAC_APP`, "Download for macOS" gives the SwiftBar-based installer instead of the app.
- **Ubuntu:** open the .deb with App Center, or `sudo apt install ./ai-worker-menubar.deb`; apt adds the AppIndicator libraries, the icon starts at every login, and `sudo apt remove ai-worker-menubar` takes it away.
- **Pairing:** the manager clicks the icon and enters their own account and 6-digit code; an account may pair 2 computers. A manager without an account reads the icon's code to an admin, who enters it under TV screens.
- **The macOS app is built once per company** on a Mac with Apple's Command Line Tools, then served by the server:

```bash
bash server/menubar/macos-app/build.sh https://your-board-address auto "AI Worker"
```

Copy `server/menubar/macos-app/dist/*-menu-bar-mac-app.zip` to the server and set `MENUBAR_MAC_APP` to its path in the env file. The app has an ad-hoc signature, so the first launch needs System Settings > Privacy & Security > Open Anyway once.

## Browser extension for managers

A Chrome or Edge extension shows, on its icon, how many people are waiting for an answer; a click opens the same small window as the menu bar apps. It reads only part of what a wall screen sees, and holds no password, OTP or login cookie. Details: [docs/chrome-extension-spec.md](chrome-extension-spec.md).

1. **Package** on the computer with the repository: `bash packaging/build-extension.sh` makes `server/menubar/AI-Worker-extension.zip`; copy `server/` to the server and run `install.sh`, and the Admin page shows an **Extension for Chrome, Edge** button under "Menu bar icon". Run it again after changing the extension.
2. **Install by hand** on the manager's computer: unzip that file (or copy the `extensions/manager/` folder), open `chrome://extensions` (Edge: `edge://extensions`), turn on Developer mode, click "Load unpacked" and choose the folder.
3. **Pair:** click the icon, type the board address, allow access to that one site when the browser asks, and read the 8-digit code to an admin.
4. **The admin approves** it on the Admin page under TV screens, like a screen; the row is marked "Browser extension". Revoking it there makes the extension show "not paired" within a minute.

Once paired, the popup is the same small window as the menu bar apps (five tabs, Settings with notifications, language and unpair). It runs copies of `server/static/mini.js`, `mini.css` and the logos kept in `extensions/manager/mini/`: after changing those files, copy them again (`cp server/static/mini.js server/static/mini.css extensions/manager/mini/`, and `server/menubar/icons/generic-black.png` and `generic-white.png` to `extensions/manager/mini/logo-black.png` and `logo-white.png`), then hand out the folder again.

Test: `node tests/extension/check-extension.js` (runs a local webhook with sample people, and fails when the copies differ).

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

For this the server never calls Telegram: the button takes the browser to Telegram's login page and back, and the server only checks the signature with the token. The login page loads nothing from Telegram. A signed login is accepted for 5 minutes and once. If Telegram cannot be reached from the office, people log in with name and code. Admins see who linked Telegram on `/admin` and can unlink it there; reissuing a key or making an account a wall account also unlinks it.

## Ask the board from Telegram (optional)

A manager who does not write code can ask the board from a Telegram chat on their phone: tap **Who is waiting** or **Cost**, or type "who is waiting longest?", and a bot answers from the board's numbers. No AI model reads the question. A button, a command or a keyword picks one of five fixed answers, so it costs nothing, needs no API key and cannot make a number up. Off until you turn it on.

**What you agree to by turning it on.** For each chat an admin approves, what the chat reads goes through Telegram's servers and stays in that chat on the person's phone: team and office totals, or each person's name, state, cost and quota when the admin chose that. Never an email, an IP or a device id. Telegram is a third party, and a chat with a bot is not end-to-end encrypted.

**How it is built.** A second small service on the server, `ai-worker-telegram`, asks Telegram for new messages. It only connects out, so nothing is opened in Caddy or in the firewall, and a board with no public address can use it. The webhook itself still never connects out: the bot process hands each message to the webhook on the same machine and sends back what the webhook answers. The bot process runs under its own user, holds the bot's token and nothing of the board, and may reach only this machine, its DNS servers and Telegram's networks.

1. **Make a bot for this** (in the Telegram app, phone or computer): search for **@BotFather**, send `/newbot`, type a name and then a username that ends in `bot`. BotFather replies with the token, which looks like `1234567890:AAH...`. Then send `/setjoingroups`, pick the bot and choose **Disable**: the bot answers in private chats only. Make a bot of its own, do not reuse the bot for logging in: the login bot's token can sign a login for anyone, and it should not sit with a process that talks to the Internet.
2. **Turn it on.** On the server, add the line `TELEGRAM_ASK=1` to `/etc/ai-worker.env` (`sudo nano /etc/ai-worker.env`), then run `sudo bash install.sh` in the `server/` folder. Correct result: it says there is no bot token yet and names the file `/etc/ai-worker-telegram.env`.
3. **Give it the token.** In the `server/` folder, run this; it asks for the token without showing it on screen:
   ```bash
   printf "Bot token: "; read -rs T; echo; sudo sed -i "s|^TELEGRAM_ASK_TOKEN=.*|TELEGRAM_ASK_TOKEN=$T|" /etc/ai-worker-telegram.env; unset T; sudo bash install.sh
   ```
   At `Bot token:` paste the token from step 1 and press Enter (nothing shows, that is expected). Or edit the file by hand with `sudo nano /etc/ai-worker-telegram.env` and run `sudo bash install.sh` again. Correct result: `✔ The Telegram bot process is running.`, and on `/admin`, under **TV screens**, a line says the bot is reading messages and names it.
4. **Each person connects once.** They open the bot in Telegram, press **Start** and read the 8-digit code it shows to an admin. The admin opens `/admin`, goes to **TV screens**, types the code and clicks **View request**. The card shows the person's Telegram name and number, and the board account that Telegram is linked to, if any. The admin chooses what the chat may read, names it and clicks **Approve**. The person then sends any message: the bot greets them and shows the buttons.

**What to know.**

- **Commands:** `/waiting`, `/cost`, `/offices`, `/team`, `/quota`, `/help` and `/stop`. Vietnamese speakers also have `/cho`, `/chiphi`, `/vanphong`, `/tongquan` and `/hanmuc`. A typed question works when it holds a keyword such as "waiting", "cost" or "office"; anything else gets the list of commands. The answer follows the language of the message, then the language of the person's Telegram app.
- **What a chat reads** is the admin's choice at approval: team and office totals only, or each person too. With totals, offices of fewer than 3 people share one row.
- **A chat that no admin approved reads nothing.** `/stop` in the chat, or **Revoke** on the Admin page, ends a chat at once. A chat lapses after 30 days without use, and after 1 year at most. At most 50 chats, and 20 messages per chat in 10 minutes.
- **Each answer with numbers is logged for 3 months** and shown on the Admin page under **Reads by AI tools and Telegram chats**: which chat and which command. The words a person typed are never stored or logged.
- **On the phone:** answers are sent so that Telegram's apps refuse to forward or save them, and the first line never names a person, since a phone shows it on the lock screen. On the phone this was tried on, Telegram's app refused a screenshot too. That is not a promise: on a computer the screen can still be captured, and any screen can be photographed.
- **The bot never asks for a login code or a password.** Tell people so: someone who got hold of the token could write to them in the bot's name.
- **If the Admin page says the server cannot reach Telegram:** check from the server with `curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org`. A number means Telegram is reachable, and the limit on the bot's service is what stops it: Telegram may have moved. Put your own list in `TELEGRAM_NETS=` in `/etc/ai-worker-telegram.env`, with commas between the addresses, or `any` for no limit, and run `install.sh` again. The default list is Telegram's own, from [core.telegram.org/resources/cidr.txt](https://core.telegram.org/resources/cidr.txt), read on 2026-11-16.
- **If the token leaks:** send `/revoke` to @BotFather, put the new token in as in step 3. Someone with the token can read what people send the bot from then on and write to them in its name. They cannot read the board: the server answers only chats an admin approved.
- **To turn it off:** change the line to `TELEGRAM_ASK=0` in `/etc/ai-worker.env` and run `install.sh` again. The service is removed. Delete `/etc/ai-worker-telegram.env` too if you will not use it again, and send `/deletebot` to @BotFather.

**Try it on your own computer first.** With the sample board, in one terminal window:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > /tmp/ai-worker-ask-key && TELEGRAM_ASK=1 TELEGRAM_ASK_KEY="$(cat /tmp/ai-worker-ask-key)" python3 server/demo.py
```

and in a second one, where it asks for the token without showing it:

```bash
printf "Bot token: "; read -rs TELEGRAM_ASK_TOKEN; echo; export TELEGRAM_ASK_TOKEN; TELEGRAM_ASK_KEY="$(cat /tmp/ai-worker-ask-key)" PORT=8799 python3 server/telegram_bot.py
```

The sample people's names then go through Telegram. Log in to `http://127.0.0.1:8799` as `demo` with the code the first window shows, and approve your chat on `/admin`.

**Tried so far.** With the real Telegram, by hand on macOS as above: pairing a chat, the buttons, the command menu, and answers in both languages. The service the installer sets up, with its own user and its network limit, is covered by the install test on Ubuntu (`tests/linux/test-server.sh`) and has been installed on one production server, where the bot reached Telegram through the limit and a chat that reads totals only was paired. On a phone, Telegram's app refused to forward an answer. A chat that reads each person was tried there once, on 2026-11-17: the cost answer named the person with the highest cost and gave each office its own line. The waiting and quota answers with names in them were not seen, because nobody was waiting and nobody was near a quota.

## Releasing an update

1. Change `version` in `.claude-plugin/plugin.json`.
2. On the signing computer, type the key password when asked:
   ```bash
   bash packaging/release.sh
   ```
   This makes the package, manifest and signature in `server/releases/` (outside git).
3. Copy `server/` to the server and run `sudo bash install.sh`.

Employee computers ask the server at most once every 4 hours, and 30 minutes later if it failed. When there is a new version, the bar above the input box shows an `Update` button; after clicking, quit the app completely and open it again. A release only reaches computers installed with version 0.23.0 or newer.

**Safety:** an employee computer installs only when the signature and the checksum are correct, so even a hijacked server cannot hand out a bad package. A computer that cannot check the signature (OpenSSH too old) is only told there is a new version and does not install it. A folder with `.git` never self-updates.

**Rolling back:** release the old version again with a new signature, or on that computer rename the `ai-worker.old` folder next to the plugin folder back to the old name.

**Changing keys:** add the new key to `~/.ai-worker-keys/allowed_signers`, release one version, then sign with the new key from the next version. If the main key leaks, sign at once with the backup key and drop the old key in that version.

## Data sent to the server

Only the company package sends; the normal package sends nothing. The numbers go to the company's own server, not to outsiders.

**Sent:** full name, the email of the Claude account and the email typed at install, a random computer ID, a hardware mark (the computer's own id after a one-way hash, so a reinstalled plugin is still the same computer; never shown on the board), internal IP, number of open sessions, working, waiting for an answer, the model in use, the Claude account quota, tokens and cost per hour, number of tasks given to each assistant, the kinds of helper assistants running, the assistants present on the computer, the plugin version. The server also records the public IP of the sending computer by itself, and keeps the internal IPs each computer used in the last 30 days. It adds cost, tokens and tasks up into one total per person per day and keeps those totals for up to 13 months.

**The connector for Codex, Cursor and Gemini CLI sends:** the full name and email typed at install, a random computer ID, the time, and for each tool the number of sessions open, working and waiting. The server records the public IP of the sending computer by itself. Nothing else is sent. On the computer, `~/.local/share/ai-worker/connector/` holds the send key (a file only that account can read), one line per open session with the tool's own session id, and the last report. Each tool hands the hook its event, which holds the prompt or the answer; the hook reads the session id and whether the last message ends with a question mark, and keeps neither the prompt nor the answer.

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
