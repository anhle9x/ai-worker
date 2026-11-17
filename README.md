[Tiếng Việt](README.vi.md) | English <!-- i18n-allow -->

# AI Worker Office

Bring Claude to your whole office, including people who do not write code, and see at a glance who is waiting for an answer.

<p>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28"></a>
  <a href="https://github.com/anhle9x/ai-worker/actions/workflows/test-install.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/anhle9x/ai-worker/test-install.yml?style=for-the-badge&amp;labelColor=000000&amp;label=tests" height="28"></a>
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28">
  <img alt="Server: Python standard library and SQLite" src="https://img.shields.io/badge/server-Python%20%2B%20SQLite-0a0a0a.svg?style=for-the-badge&amp;labelColor=000000" height="28">
</p>

AI Worker is for the person who has to roll Claude out to an office and then answer two questions: is it being used, and who is stuck? It is a Claude Code plugin on each employee's computer and a small server on one Linux machine that you run yourself. Staff double-click an installer and type their name. Managers get a live board of who is working, who is waiting for an answer and for how long, for Claude and for the helper assistants (Gemini, ChatGPT, Gemma). A small connector puts people who work in Codex, Cursor or Gemini CLI on the same board, with or without Claude Code. It needs no Team or Enterprise plan and no device-management software. An employee's computer sends the server the person's name, their Claude account, a few facts about the computer and the numbers (sessions, tokens, cost, quota); it never sends chat content, prompts, file names or project names.

<!-- one row that scrolls sideways, one picture to a view. GitHub shrinks pictures in a table to fit the page; the line of em spaces under each caption cannot wrap (nowrap), so it holds the cell at the width of the page -->
<table>
  <tr>
    <td nowrap align="center" valign="top"><img src="assets/dashboard.png" alt="The 3D operations board with sample data" height="377"><br><sub><b>Operations board (sample data).</b> Who is working, who waits for an answer, cost and quota, live.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/map-2d.jpg" alt="Flat map with four offices" width="808"><br><sub><b>Flat map.</b> Each office shows people working, cost today and the assistants in use.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/map-25d.jpg" alt="Tilted map with a column on each office" width="808"><br><sub><b>2.5D map.</b> The column on each office stands for cost, people or quota: you choose.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/globe.jpg" alt="Globe with the offices marked" width="808"><br><sub><b>Globe.</b> The same offices on a 3D globe: drag to turn it, scroll to zoom in or out.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/wall.jpg" alt="Wall screen with the diagram and three quota rings" width="808"><br><sub><b>Wall screen.</b> Made for a TV: full screen, quota rings, paired with a code an admin approves.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/board.jpg" alt="Table with one row for each person" width="808"><br><sub><b>Detail board.</b> One row for each person: status, model, quota, cost, tokens, plugin version.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/admin.jpg" alt="Admin page with accounts, TV screens and downloads" width="808"><br><sub><b>Admin page.</b> Accounts and roles, TV pairing, downloads for the menu bar icon and extension.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/login.png" alt="The login page: account name and 6-digit code, or Log in with Telegram" height="377"><br><sub><b>Login.</b> Account name and a 6-digit code, or Log in with Telegram.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
    <td nowrap align="center" valign="top"><img src="assets/phone.jpg" alt="The board on a narrow screen, one panel under the other" height="377"><br><sub><b>Narrow screen.</b> On a phone the panels stack one under the other, from top to bottom.</sub><br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&ensp;</td>
  </tr>
</table>

## What makes it different

- **You see who is stuck, as it happens.** The board shows who is working, who is waiting for an answer and for how long, per office on a map. You can also watch it on a TV wall screen, or see the number of people waiting on a menu bar icon (macOS, Windows, Ubuntu) and a Chrome or Edge extension. Rewind the last 24 hours to see how the day went.
- **A whole office can use it, not only developers.** One package for the company: staff double-click an installer on macOS, Windows or Linux, shared rules and skills reach every computer, and updates arrive signed. The guides use simple language, in English and Vietnamese.
- **Self-hosted: the board's data stays on your own server.** The server runs on your own Linux machine with Python's standard library and SQLite. Employee computers send who is using Claude and the numbers, not what they are working on; every field is listed in [docs/DATA-MODEL.md](docs/DATA-MODEL.md).

## Other features

- **Codex, Cursor and Gemini CLI on the same board:** a connector, installed per tool by whoever uses it, shows sessions open, working and waiting for each tool. It needs no Claude Code, Python or Node, and it sends counts only. New: tried inside a real Codex CLI on macOS; on Linux and Windows, and for Cursor and Gemini CLI, tested with sample events only, not inside the real tools. See the [install guide](docs/INSTALL.md#codex-cursor-and-gemini-cli-on-the-board).
- **Cost and quota:** cost today and over 7 days and quota left, per person and per office.
- **Ask Claude about the team:** a manager pairs their Claude with the board once, then simply asks, for example "who is waiting longest right now?". You can type or dictate the question in your own language; Claude answers from the board's numbers.
- **Ask from other AI tools, or from Telegram:** the server has a read-only MCP endpoint, so any AI tool that speaks MCP can answer the same questions with a key an admin approves. Managers who do not write code can tap a button in a Telegram chat instead: optional, off by default, and no AI model reads the question. The [install guide](docs/INSTALL.md) shows how to turn each one on.
- **Use by week and month:** the detail board compares this week and this month with the last, for the team, each office and each person.
- **Turn a procedure into a skill:** give `/ai-worker:make-skill` an SOP or a description of how a job is done. It writes a draft skill, stops at passwords and keys, leaves personal data out, and switches the skill on only after you say yes.
- **Asks before deleting or sending out:** a command that deletes a whole folder, `git reset --hard`, `git push --force` and `git clean` need your confirmation, and so does sending text to another company's AI unless you allowed it yourself.
- **Roles and audit:** admins, managers and wall screens see different data; log in with a 6-digit OTP code or with Telegram (Telegram needs a bot set up first, see the [install guide](docs/INSTALL.md)); every change is logged for 12 months.

## Is it the right tool?

- **You only want the token cost on your own computer:** a local usage counter is simpler. You do not need a server.
- **Your organization is on a Team or Enterprise plan and manages its devices:** Anthropic's own [analytics](https://code.claude.com/docs/en/analytics) and [managed plugin settings](https://code.claude.com/docs/en/plugins/org) already give usage reports and roll plugins out. AI Worker adds the live board of who is waiting, and works without either.
- **A small or mid-size office where many people do not write code and there is no device management:** this is the case AI Worker fits best.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.svg">
  <img alt="Employee computers send their numbers to the dashboard server (the name, the Claude account, a few details about the computer, and counts of sessions, tokens, cost and tasks; never chat, prompts or file names) and get signed updates back. The server, behind Caddy with HTTPS and an office IP list, keeps data in SQLite and serves the browser dashboard, TV wall screens, the menu bar icon, the browser extension, AI tools over a read-only MCP endpoint, and an optional Telegram chat." src="assets/architecture-light.svg" width="860">
</picture>

Without a server the plugin still runs on each computer, with its own office page, but there is no company board and no self-update. The design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

**Just looking?** Run the board on your own computer with sample people. It needs only Git and Python 3.8 or newer.

macOS and Linux:

```bash
git clone https://github.com/anhle9x/ai-worker.git
cd ai-worker
python3 server/demo.py
```

Windows, in PowerShell or Command Prompt. If Git or Python is missing, install it first, then open a new window so the new commands are found:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Python.Python.3.12 -e --source winget
```

```powershell
git clone https://github.com/anhle9x/ai-worker.git
cd ai-worker
py server\demo.py
```

It prints an address, the account name `demo` and a 6-digit code. Open the address and type both: the board is up with 12 sample people in 4 offices. Nothing is installed and nothing leaves your computer; Ctrl+C stops it and deletes the sample data. Checked on macOS, Linux and Windows.

**The admin, once** (about 30 minutes). Steps and commands: [docs/INSTALL.md](docs/INSTALL.md).

1. Copy `server/` to a Linux server and run `sudo bash install.sh`. It prints the send key and creates the first admin.
2. Put Caddy in front for HTTPS and your office IP list (template: `server/aiworker.caddy`).
3. Make the update signing keys, fill in `packaging/company.json`, run `bash packaging/build.sh packaging/company.json`.

**Each employee:** unzip the package, double-click `INSTALL-Mac.command`, `INSTALL-Windows.bat` or run `INSTALL-Linux.sh`, type your full name. In Claude Code, type `/office` to see your own sessions.

**Managers:** open the server address, sign in with the 6-digit code from Google Authenticator, or press **Log in with Telegram** once Telegram is linked (when the server has a Telegram bot set up). Install the menu bar icon from the **Admin** page if you want alerts.


How to use each screen: [docs/USER-GUIDE.md](docs/USER-GUIDE.md).

## Where it runs

| Part | Runs on | Needs |
|---|---|---|
| Plugin | macOS, Windows, Linux | Claude Code: the desktop app's Code tab, the CLI, or the VS Code extension |
| Connector for Codex, Cursor, Gemini CLI | macOS, Linux, Windows | The tool itself, and curl or wget; no Claude Code |
| Dashboard server | Linux with systemd | Python 3.8 or newer, Caddy or nginx; no other library |
| Menu bar icon | macOS, Windows 10/11, Ubuntu (X11 and Wayland) | Downloaded from the server's Admin page |
| Browser extension | Chrome, Edge | Download from the server's Admin page, pair with a code |

### What is not counted

The board shows Claude Code on computers where the plugin is installed, and Codex, Cursor and Gemini CLI on computers where the connector is installed (sessions only: no tokens, cost or quota). It does not show:

- **claude.ai in a browser, and the Chat tab of the Claude app.** They have no plugins.
- **Claude Code sessions that run in the cloud** (claude.ai/code). They run on Anthropic's servers, not on the staff computer, so the plugin installed there is not loaded. Not tried yet: treat them as not counted.
- **A computer without the plugin or the connector,** or one that cannot reach the server.

Someone who only chats on claude.ai therefore shows as not using Claude, though that use may still count against the same account's quota. Read the board as "who uses Claude Code, and how much", not "who uses Claude the most".

## Roadmap

Where the project is going. There are no dates: an item ships when it has been checked.

- [x] A live board of who is working and who is waiting in Claude Code, with a wall screen, a menu bar icon and a browser extension
- [x] The plugin in the Claude Code extension for VS Code
- [x] Codex, Cursor and Gemini CLI on the same board (0.32.0): sessions only
- [x] Ask the board from any AI tool that speaks MCP: a read-only endpoint on the server, with a key an admin approves. Tried in Claude Code and Codex CLI.
- [x] Ask the board from a Telegram chat, for managers who do not write code: buttons and short questions, no AI model, off by default
- [x] Use by week and month: the server keeps one total per person per day, and the detail board compares this week and this month with the last
- [ ] The Cursor, Gemini CLI and Windows connectors tried inside the real tools. So far only Codex on macOS has been.
- [ ] The MCP endpoint tried from Cursor and Gemini CLI. So far Claude Code, Codex CLI and the Chat tab of the Claude app (through a claude.ai connector) have been.
- [x] Charts of use by week and month on the detail board: cost per week for 12 weeks and per month for up to 13 months, for the team and for each office

## Documents

| | |
|---|---|
| [User guide](docs/USER-GUIDE.md) | Staff, managers, admins |
| [Install and configure](docs/INSTALL.md) | First deployment, updates, settings, data sent |
| [Operations](docs/OPERATIONS.md) | Daily checks, problems, backup, rollback, logs |
| [Architecture](docs/ARCHITECTURE.md), [data](docs/DATA-MODEL.md), [permissions](docs/PERMISSIONS.md) | How it is built |
| [Skills and rules](docs/SKILLS.md) | What every computer gets |
| [Test plan](docs/TEST-PLAN.md) | What is tested, what to check by hand |
| [All documents](docs/README.md) | Grouped by purpose |

## Security

Designed against the common web risks (CSRF, XSS, injection, broken login, access control, exposed data), reviewed with AI assistants, not audited by a security firm. The table of what is protected and what remains, and how to report a problem privately: [SECURITY.md](SECURITY.md).

## Contributing and support

[CONTRIBUTING.md](CONTRIBUTING.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [Changes](CHANGELOG.md) · [Contact and sponsoring](SUPPORT.md)

## License and your responsibilities

AI Worker is under the [MIT License](LICENSE). Third-party parts keep their own licenses: see [THIRD-PARTY.md](THIRD-PARTY.md). Names and trademarks: see [NOTICE](NOTICE).

**Your responsibilities if you deploy it.** AI Worker comes with no warranty. You run your own server and decide what is collected, so you are responsible for:
- **Telling your staff first.** It sends names, account emails, IP addresses and usage numbers to your server. Start from the [employee notice template](docs/employee-notice.md) and have your legal or HR contact review it, because rules differ by country.
- **Securing the server.** Protect access with HTTPS and a network limit, keep admin accounts small, and back up the data.
- **Your own keys.** `keys/allowed_signers` ships empty, so updates stay off until you put your own public key in `~/.ai-worker-keys/allowed_signers` and build the package. Never commit a private key.
- **The terms of Claude, Gemini and ChatGPT.** Check that your plans allow the way you use them, and what data your staff may send to them.

**Publishing your own copy:** `packaging/check-clean.sh` stops private keys, tokens and your private words (a list kept outside the repository) from being published; `--install-hooks` runs it before each commit and push. It refuses to run without that list unless you set `AI_WORKER_NO_DENY=1`. `packaging/export-public.sh` exports a clean copy without history.
