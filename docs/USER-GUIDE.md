[Tiếng Việt](USER-GUIDE.vi.md) | English <!-- i18n-allow -->

# AI Worker Office: user guide

This guide is for the people who use AI Worker every day. It is split by role: find yours in the table below and read only that part.

Setting up the server and building the install package is the admin's work, covered in [INSTALL.md](INSTALL.md) and [server/README.md](../server/README.md).

## Who uses what

| You are | You use | Read |
|---|---|---|
| **Staff member** working with Claude | The plugin on your own computer: the office page, the side pane, the update bar | [1. Staff](#1-staff) |
| **Manager** following the team | The dashboard in the browser, the menu bar icon or the browser extension | [2. Managers](#2-managers) |
| **Admin** of the board | The Admin page: accounts, TV screens, locations, Team plan | [3. Admins](#3-admins) |

Words used in this guide:

- **Session:** one conversation with Claude in the Code tab of the Claude app (or the `claude` command).
- **Helper assistants:** Gemini, ChatGPT and Gemma. Claude hands them side jobs; they are optional.
- **Board** or **dashboard:** the company-wide page on your company's server.
- **OTP code:** the 6-digit code shown by Google Authenticator or Microsoft Authenticator, which changes every 30 seconds.

---

## 1. Staff

### 1.1 Install

Your admin gives you a zip file. Read `GUIDE.txt` inside it; in short:

1. Unzip it into any folder.
2. Double-click `INSTALL-Mac.command` (Mac) or `INSTALL-Windows.bat` (Windows). On Ubuntu, open Terminal in that folder and type `bash INSTALL-Linux.sh`.
   - The first time, a Mac may block the file: right-click it, choose **Open**, then **Open** again.
3. A company package asks for your full name. Type it the way colleagues know you.
4. The installer offers the helper assistants. Say yes to the ones your company uses; you can skip them all.
5. When the window says **Done**, press Enter, then quit the Claude app completely and open it again. On Windows, closing the window only hides the app: right-click the Claude icon next to the clock and choose **Exit**.

**Correct result:** in a new session, typing `/office` opens a page in your browser with your session on it.

You may delete the unzipped folder afterwards: the plugin is copied into your user folder.

### 1.2 Commands

Type these in the chat box of the Code tab:

| Command | What it does |
|---|---|
| `/office` | Opens the office page for this computer in your browser |
| `/office-pane` | Opens the office next to the chat |
| `/update` | Checks the company server for a new version and installs it |
| `/ai-worker:help` | Lists what the plugin gives on this computer: commands, skills, helper assistants |

**What else comes with the plugin.** Type `/ai-worker:help` to see the list as it is on your computer. In short:

- **Skills,** which Claude follows when you type their name or ask in your own words: for everyday work, `/ai-worker:handoff` (write a handoff note so the next session can carry on), `/ai-worker:meeting-notes` (turn rough notes into minutes), `/ai-worker:lesson-generator` (build a small course).
- **Helper assistants** (see 1.4): Claude hands side tasks to Gemma, ChatGPT or Gemini by itself, but only to the ones installed on your computer. The list says which ones yours has.
- **Skills for people who write code or run systems,** such as `/ai-worker:tdd`, `/ai-worker:qa-test`, `/ai-worker:security-audit` and `/ai-worker:write-spec`, and the `planner` assistant for big decisions. They come with the plugin too; if you do not do that kind of work, ignore them. A few need extra tools: see [SKILLS.md](SKILLS.md).

The plugin has no MCP server of its own.

### 1.3 The office page (`/office`)

It shows only the sessions on **your** computer:

- **Diagram:** each open session, linked to Claude and the helper assistants. A green session is working, a yellow one is waiting for you.
- **Click a session** to see its plan, how full its context is, and its cost.
- **Cost:** today, the last 7 days, and a chart you can change (line, bars, candles; by hour or by day).
- **Activity:** what was done in the open sessions, with a filter.
- **Models & quota:** how much of your Claude account's 5-hour and 7-day limits are used. From 80% it turns red, and a bar appears above the chat box. Click **Hide** to hide that bar until the level rises again.

The plugin never changes the model by itself. To save quota, type `/model sonnet` yourself.

The page opens from a file on your computer. Chat content goes nowhere.

**Cost** is calculated at API prices. On a subscription plan it is a figure for comparison, not money you are charged.

### 1.4 Helper assistants

Claude hands side jobs to the helper assistants following the company rules:

| Assistant | Good at | Data rule |
|---|---|---|
| **Gemma** | Summaries and sorting, on your own computer | The only one allowed sensitive data, because nothing leaves the computer |
| **ChatGPT** | Code review, finding bugs | Never receives names, internal documents, figures or passwords |
| **Gemini** | Web research, images | Same as ChatGPT |

Before sending anything to ChatGPT or Gemini, Claude asks you, unless your company rules already allow it. A desk for an assistant that is not installed is hidden in the office.

To sign in later: open Terminal or PowerShell and type `codex login` (ChatGPT) or `agy` (Gemini).

### 1.5 Updates

When your admin releases a new version, a bar above the chat box shows **New version** with an **Update** button; you can also type `/update`.

1. Click **Update** and wait for the message that it is installed.
2. In the Claude desktop app (Mac, Windows, Linux), a question offers to close the app and open it again: choose **Reopen now** (sessions that are still working stop), or **Later** and do it yourself. Anywhere else, quit the Claude app completely and open it again.

A version is installed only when it carries the admin's signature. Your computer must be on the company network to download it. The previous version is kept in the `ai-worker.old` folder next to the plugin.

### 1.6 What your computer sends

Only a company package sends anything; a normal package sends nothing.

- **Sent to the company server:** your name, your Claude account email, a computer ID, IP addresses, how many sessions are open, working or waiting, tokens, cost, quota, how many tasks went to each assistant, the plugin version.
- **Never sent:** chat content, questions, answers, file names, file contents, project names.

To stop sending from one computer, add `"sharing": { "enabled": false }` to `config.js` (see 1.7) and tell your admin.

### 1.7 Your settings

Two files in your user folder, under `.local/share/ai-worker/` (Windows: `%USERPROFILE%\.local\share\ai-worker\`):

| File | What you can change |
|---|---|
| `user.json` | Your name, your email, and `language` (`"en"` or `"vi"`) |
| `config.js` | Display names, `usdRate` (dollar to dong, used only in Vietnamese), each assistant on or off under `workers` |

Updates never overwrite `config.js`. Pages in the browser also have an **EN / VI** switch at the top.

### 1.8 Uninstall

In Terminal or PowerShell:

```bash
claude plugin uninstall ai-worker@ai-worker
claude plugin marketplace remove ai-worker
```

Then delete the `claude-plugins-ai-worker` folder in your user folder.

### 1.9 Problems

| What you see | What to do |
|---|---|
| In a new session the list shows no `/office` or `/update`, or a line says `/office isn't a command here` | Before your first message the app only knows the names `ai-worker:office`, `ai-worker:office-pane` and `ai-worker:update`: pick one from the list. Typing `/office` and pressing Enter also works. |
| `/office` does nothing | Quit the Claude app completely and open it again, or type `/reload-plugins` |
| The installer says the server cannot be reached | Your numbers are not on the board yet. Check you are on the company network and send a screenshot to your admin |
| A helper assistant's desk is missing | It is not installed or not signed in; see 1.4 |
| The update fails | Make sure you are on the company network; otherwise ask your admin for the new install package |

---

## 2. Managers

### 2.1 Sign in to the board

1. Ask an admin for an account. They send you a QR code.
2. On your phone, open **Google Authenticator** (or Microsoft Authenticator), tap **+**, choose **Scan a QR code**, and scan it.
3. On your computer, open the board address your admin gives you (for example `https://board.company.com`).
4. Type your account name and the 6-digit code shown in the app, then click **Log in**.

**Correct result:** the dashboard opens. A login lasts 8 hours. Each code works only once; if it is refused, wait for the next one.

**With Telegram** (when your admin has turned it on): log in once with name and code, open the detail board, click **Telegram**, enter the 6-digit code and press the Telegram button. From then on, press **Log in with Telegram** on the login page and confirm in Telegram. Admin changes still ask for the 6-digit code.

The board only opens from the company network.

### 2.2 The dashboard

It updates by itself every 10 seconds:

- **Status bar at the top:** how many people are working, waiting and idle, and warnings such as someone near their quota.
- **Diagram:** each person linked to Claude and the helper assistants; moving dots mean work is happening or being handed over. **Click a person** to see their numbers.
- **Heat map:** who used the most, and at what hour, over the past 24 hours.
- **Today's numbers, usage per assistant, an event log** (newest on top) **and a 24-hour chart.**
- **View mode:** switch between the diagram and the map of branches, in 2D or 3D.
- **Replay last 24 hours:** play back the day; **Back to now** returns to live.
- **Explain** shows what each colour and line means.
- **Detail board** (`/board`): the same numbers as a table, with the Plugin column showing which computers are not on the latest version.

Colours: green is working, yellow is waiting for an answer, light blue is idle, grey is offline.

The board only knows about Claude Code on computers where the plugin is installed. Chatting on claude.ai in a browser, the Chat tab of the Claude app and Claude Code sessions that run in the cloud are not counted, so a person who works there shows as idle or offline. Do not read the board as "who uses Claude the most".

### 2.3 Menu bar icon

An icon in the menu bar (Mac), next to the clock (Windows) or in the top bar (Ubuntu) shows how many people are waiting for an answer, even with the browser closed. It turns blue when someone has waited past your limit.

**Install:**

1. On the board, open the **Admin** page if you have one, or ask an admin; the installers are in the **Menu bar icon** section.
2. Download the one for your computer:
   - **Mac:** **Download for macOS ▾**, then **AI-Worker.dmg** (or **AI-Worker-mac.zip**; without a .dmg on the server it is a single button). Open it and move **AI Worker** to Applications. The first time you open it, go to **System Settings > Privacy & Security** and click **Open Anyway**.
   - **Windows:** **Download for Windows ▾ > AI-Worker.msi**. Windows warns 2 to 3 times because the file has no big-brand signature; choose **Keep**, then **More info > Run anyway**. Tick the licence box and click **Install**. No admin password is needed.
   - **Ubuntu:** **Download for Ubuntu (.deb)**, open it with App Center, or type `sudo apt install ./ai-worker-menubar.deb`.
3. Only install a file you downloaded yourself from the board. Never open an installer sent by email or chat.

**Pair it (first time only):** click the icon, then **Pair with my account**, and type your account name and 6-digit code. An account may pair 2 computers.

**Correct result:** within a minute the icon shows the number of people waiting, and a click opens a small window with five tabs: **Waiting, Working, Quota, Cost today, Settings**.

In **Settings** you can turn notifications on or off and choose how long a wait triggers one (5, 10, 15, 30 or 60 minutes; default 10), change the language, start at login, unpair, or remove the app. You get one notification per long wait, not one every minute.

**To update:** download the new installer from the board and install it over the old one. The pairing is kept.

### 2.4 Browser extension

For a manager who prefers the browser: a Chrome or Edge extension shows the number of people waiting on its icon, and a click opens the same small window.

1. Get the `AI-Worker-extension.zip` file from an admin (the **Extension for Chrome, Edge** button on the Admin page). Unzip it somewhere it will stay, for example Documents: deleting the folder breaks the extension.
2. Open `chrome://extensions` (Edge: `edge://extensions`), turn on **Developer mode**, click **Load unpacked**, choose the `AI-Worker-extension` folder.
3. Click the extension icon, type the board address, allow access to that one site, and read the 8-digit code to an admin.

**Correct result:** within a minute of the admin approving it, the icon shows the number waiting.

The extension holds no password, OTP or login cookie.

---

## 3. Admins

Everything here is on the **Admin** page (the **Admin** link at the top of the board). Only accounts with the admin role can open it.

### 3.1 Roles

| | Admin | View only | Wall display |
|---|---|---|---|
| Admin page | Yes | No | No |
| Emails, internal IPs, the detail board | Yes | Yes | No |
| Stays logged in | 8 hours | 8 hours | 7 days |

The server checks the role itself; hiding a button is not the only protection.

### 3.2 Accounts

- **Create account:** type a name (letters without accents, digits, `.`, `_`, `-`), choose a role, re-enter your OTP code. A QR code appears: send it to the person privately, then click **Scanned, hide**.
- **Change role:** takes effect at once; nobody is logged out.
- **Reissue key:** if you suspect a leak, end that person's sessions first, then reissue the key and send the new QR code.
- **Delete account:** also removes the menu bar computers that account paired.

Creating, reissuing, changing a role and deleting all ask for your OTP code again, valid for 5 minutes. The last admin cannot be deleted or demoted, and nobody can delete themselves.

**Lost every admin?** Someone with sudo on the server runs `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder.

### 3.3 TV screens

1. On the TV, open the board address. A smart TV shows an 8-digit code by itself; on a computer plugged into a TV, click **Wall screen: pair with a code** on the login page.
2. Scan the QR code on the TV with a phone on the company network, or type the code under **TV screens** on the Admin page.
3. Check the device and IP, choose **Add a new screen** (or replace an old one so no extra row is made), give it a name such as "Meeting room TV", and click **Approve**.

**Correct result:** the TV shows the wall display within a few seconds. It shows short names only, no emails or IPs.

From the list you can **Rename**, **Reload** a screen remotely, or **Revoke** it. At most 20 screens; a screen unused for 30 days leaves the list by itself. For a computer that should open the board by itself at startup, open `/tv` on it and download the file at the bottom of the page.

Menu bar icons and browser extensions paired by code also appear here, marked as such.

### 3.4 Locations and branches

The board groups computers by the network they send from.

- **Unnamed groups of devices:** choose a group, then a province or city, and give it a name (empty uses the province name).
- New computers on the same network join the right branch by themselves.
- A branch appears on the board's map once a computer there has sent numbers, and stays while one has sent in the last 30 days. A branch that is only declared, with no computer yet, is listed on the Admin page but not on the map.
- A person who moves to another office is counted there from the next time their computer sends from that office's network; nobody has to change anything.
- Staff at home, on 4G or travelling fall under "Mobile / unassigned".

### 3.5 Team plan

Costs outside the plugin (Claude on phones and the web) come from the Team plan report:

1. In your Claude Team admin settings, download the **Export spend report** CSV file.
2. On the Admin page, under **Team plan**, click **Load CSV** and choose the file.
3. Under **Each person**, tick **Mark as sales** for the market sales team if you want them counted apart.

Personal plans (Pro, Max) are not in that report.

### 3.6 Open sessions and the audit log

- **Open sessions:** who is logged in, from where. **End** one, or **End the other sessions** to log everyone else out.
- **Audit log:** logins, changes and refusals for the chosen month. Kept 12 months; the page shows the newest 300 lines.

### 3.7 Menu bar downloads

The **Menu bar icon** section offers the installers for managers (see 2.3). The server writes its own address into each file, so a manager only installs and pairs.

---

## Questions

- **Can a manager read what staff typed to Claude?** No. Chat content is never sent; the board only has numbers.
- **Someone uses Claude all day but the board shows them idle. Why?** They are probably on claude.ai in a browser or in the Chat tab of the app. Only Claude Code (the Code tab, the terminal, an editor) on a computer with the plugin is counted.
- **Does it work outside the office?** The plugin works anywhere. Sending numbers, the board and updates need the company network.
- **Do I need Gemini, ChatGPT or Gemma?** No. Everything works with Claude alone.
- **Is the cost real money?** It is the price at API rates. On a subscription plan it is for comparison only.
- **Where do I report a problem?** Take a screenshot and send it to your admin. For the open-source project, open an issue on GitHub; security problems go through [SECURITY.md](../SECURITY.md).
