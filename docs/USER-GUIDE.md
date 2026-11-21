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
| `/ai-worker:board` | For managers: pairs this computer with the company board, so Claude can answer questions about the team (see 2.5) |
| `/ai-worker:voice` | Speak instead of typing, in Vietnamese too: opens the dictation settings of this computer and shows the steps |

**Speak instead of typing.** You do not need to find the settings yourself: type `/ai-worker:voice`, or just tell Claude you want to speak instead of typing. On a Mac it opens the Keyboard page of System Settings, where you turn Dictation on and tick your language once; after that, press the microphone key once in the message box (do not hold it: holding calls Siri) and speak. On Windows it opens the Language & region page, where you add your language once; after that, press the Windows key + H. The plugin changes no setting and listens to nothing: the dictation is your computer's own. A Mac says under Dictation whether your voice stays on the Mac or goes to Apple; Windows sends it to Microsoft. Do not say names of people or internal figures aloud when it leaves the computer.

**Before a command that destroys work.** When Claude is about to delete a whole folder, throw away changes not saved in git (`git reset --hard`), overwrite the shared git server (`git push --force`) or delete untracked files (`git clean`), and also before it runs a script it downloads (`curl … | sh`), turns off macOS's check on downloaded apps (Gatekeeper), writes straight to a disk or erases one, or opens a file to every user (`chmod 777`), the permission box of the app opens and says in plain words what will be lost. This happens in every permission mode, the automatic ones too: only you can answer it, and where nobody is there to answer, the command does not run. Folders a build makes again (`node_modules`, `dist`, `build` and the like) and the system's temporary folder are left alone. This is a safety net for the common forms, not a guarantee: a delete written another way, or inside a script, is not seen. To turn it off, see 1.7.

**What else comes with the plugin.** Type `/ai-worker:help` to see the list as it is on your computer. In short:

- **Skills,** which Claude follows when you type their name or ask in your own words: for everyday work, `/ai-worker:handoff` (write a handoff note so the next session can carry on), `/ai-worker:meeting-notes` (turn rough notes into minutes), `/ai-worker:lesson-generator` (build a small course), `/ai-worker:make-skill` (turn a document or your team's procedure into a new skill: it refuses a source holding a password or a key, keeps the skill as a draft, and switches it on only when you say yes).
- **Helper assistants** (see 1.4): Claude hands side tasks to Gemma, ChatGPT or Gemini by itself, but only to the ones installed on your computer. The list says which ones yours has.
- **Skills for people who write code or run systems,** such as `/ai-worker:tdd`, `/ai-worker:qa-test`, `/ai-worker:security-audit` and `/ai-worker:write-spec`, and the `planner` assistant for big decisions. They come with the plugin too; if you do not do that kind of work, ignore them. A few need extra tools: see [SKILLS.md](SKILLS.md).

The plugin has no MCP server of its own.

### 1.3 The office page (`/office`)

It shows only the sessions on **your** computer:

- **Diagram:** each open session, linked to Claude and the helper assistants. A green session is working, a yellow one is waiting for you.
- **Click a session** to see its plan, how full its context is, and its cost.
- **When a conversation gets long,** a note warns you at 60% and at 80% of the context. Past 80%, Claude is told too: it finishes what you asked, then writes a handoff note and suggests a new session in one line. If Claude then summarizes the older part by itself to make room, the plugin asks that summary to keep your instructions, the decisions, what failed and what is still open, and a note tells you so: carry on in the same conversation, no new session is needed.
- **Carrying on in a new session.** When you have written handoff notes with `/ai-worker:handoff`, each new session is told the names and dates of the newest five. Say "continue the monthly report" and Claude reads that note first; say only "continue" and it asks which one. The plugin gives names and dates only: a note is opened when you ask to carry on with it.
- **Cost:** today, the last 7 days, and a chart you can change (line, bars, candles; by hour or by day). In the time range menu, **Date range** shows just the days you pick, from one day to another; **Last 7 days** goes back.
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

Before sending anything to ChatGPT or Gemini, Claude asks you, unless a permission rule already allows that assistant. A permission mode that asks nothing does not count as such a rule: you are still asked, because the text leaves your computer. Text that holds what looks like a key, a token or a password (an AWS or GitHub key, a private key, a password in a connection string or in a `.env` line, and the like) is not sent at all, whatever the rule or the mode: Claude is told what was found and on which line, without the value, so it can take it out and send again. A desk for an assistant that is not installed is hidden in the office.

Before Claude runs `git commit`, the lines the commit adds are read the same way. If one holds what looks like a secret, you are asked first, with the file and the line but not the value: once a secret is in git it stays in the history, even if a later commit takes it out. And when a web page or a search result Claude reads holds text aimed at an AI (an order to ignore earlier instructions, to hide something from you, or to send keys somewhere), you see a short notice and Claude is told it is the page's text, not your request.

When you open Claude in a repository whose files set up the AI themselves, you see one line about what is new: for example `.mcp.json declares an MCP server "helper" that runs node tools/server.js`, or `.claude/settings.json lets Claude run any command without asking (Bash(*))`. These files come with a clone or a pull. If you did not add them, open them and check before you go on; Claude is told the same and asks you before it runs something because of them. Nothing is blocked. You are told once per change: the next session in the same repository says nothing until one of these files changes, and a repository you have had for more than 14 days says nothing the first time.

To sign in later: open Terminal or PowerShell and type `codex login` (ChatGPT) or `agy` (Gemini).

### 1.5 Updates

When your admin releases a new version, a bar above the chat box shows **New version** with an **Update** button; you can also type `/update`.

1. Click **Update** and wait for the message that it is installed.
2. In the Claude desktop app (Mac, Windows, Linux), a question offers to close the app and open it again: choose **Reopen now** (sessions that are still working stop), or **Later** and do it yourself. Anywhere else, quit the Claude app completely and open it again.

A version is installed only when it carries the admin's signature. Your computer must be on the company network to download it. The previous version is kept in the `ai-worker.old` folder next to the plugin.

### 1.6 What your computer sends

Only a company package sends anything; a normal package sends nothing.

- **Sent to the company server:** your name, your Claude account email, a computer ID, IP addresses, how many sessions are open, working or waiting, tokens, cost, quota, how many tasks went to each assistant, the plugin version.
- **Sent by the connector for Codex, Cursor and Gemini CLI,** if you installed it (see 1.10): your name and email, a computer ID, and for each tool how many sessions are open, working or waiting.
- **Never sent:** chat content, questions, answers, file names, file contents, project names.

To stop sending from one computer, add `"sharing": { "enabled": false }` to `config.js` (see 1.7) and tell your admin.

### 1.7 Your settings

Two files in your user folder, under `.local/share/ai-worker/` (Windows: `%USERPROFILE%\.local\share\ai-worker\`):

| File | What you can change |
|---|---|
| `user.json` | Your name, your email, and `language` (`"en"` or `"vi"`) |
| `config.js` | Display names, `usdRate` (dollar to dong, used only in Vietnamese), each assistant on or off under `workers`, and `"askBeforeDestructive": false` to turn off the question before a command that destroys work |

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
| `/update` says the network you are on is not allowed to reach the company server | Nothing is wrong with your computer: the server answers only the networks your admin has added. Type `/update` again at the office, or ask your admin to add the network you are on |

### 1.10 Codex, Cursor and Gemini CLI

If you also work in Codex, Cursor or Gemini CLI, those sessions can show on the company board too. You do not need Claude Code for this.

1. **Where:** the unzipped folder your admin gave you. **Do:** double-click `INSTALL-Other-Tools-Mac.command` (Windows: `INSTALL-Other-Tools-Windows.bat`; Ubuntu: type `bash INSTALL-Other-Tools-Linux.sh` in Terminal). **Right result:** a window asks, for each tool it finds, whether to show it on the board.
2. **Do:** press Enter for yes or type `n` for no, for each tool. **Right result:** the window says `The board answered: received.`
3. **Codex only. Where:** Terminal. **Do:** type `codex`, then `/hooks`, and trust the seven hooks whose command ends in `ai-worker-hook.sh` (a hook is a small program the tool runs by itself at certain moments). **Right result:** `/hooks` lists them as trusted. Cursor and Gemini CLI need no such step: close and reopen them.

**What it sends:** your name and email, a computer ID, and for each tool how many sessions are open, working or waiting. Never what you type or what the tool answers.

**To remove it:** in Terminal type `bash ~/.local/share/ai-worker/connector/install.sh --uninstall`. The window says `Done. Codex, Cursor and Gemini CLI no longer send anything to the board.`

### 1.11 Cost and speed of an AI project or application your team built

If your team built an AI project or application that calls an LLM and needs a cost and performance report, the `ai-cost-report` skill measures it. Any provider works: Claude, GPT, Gemini, Grok, DeepSeek, Mistral, a model through OpenRouter, or one that runs on your own machine (Ollama, vLLM). The numbers come from the project itself: each LLM answer carries its token counts (`usage`, the number of pieces of text the provider bills), and a small meter adds them up for each request of a user, with the time it took. It never writes what the user asked, what the model answered, who the user is, or an error message. Nothing is sent to the board unless the project's server is given a key for it (see 2.6 and 3.8). Every step, also by hand and for other languages: [AI-PROJECTS.md](AI-PROJECTS.md).

1. **Where:** Claude Code, opened in the project's code folder. **Do:** type `/ai-worker:ai-cost-report` and say which project to measure. **Right result:** Claude finds where the project calls an LLM and shows the few lines it would add: one copied file (`ai_meter.py` for Python, `ai-meter.cjs` for Node; another language writes the same line by hand from `FORMAT.md`). Nothing changes until you say yes.
2. **Where:** the machine that runs the project. **Do:** run it as usual, with real users, for the period you report on. Trial runs: start it with `AI_METER_ENV=test` so they stay apart. **Right result:** a file `ai-meter.jsonl` next to it grows by one line per request.
3. **Where:** Claude Code. **Do:** give Claude the file and ask for the report, in Vietnamese or English, for the days you want. **Right result:** `ai-cost-report.html` (open it in a browser; **Print** saves it as PDF) and `ai-cost-report.csv` (opens in Excel or Google Sheets): number of requests, LLM calls and tokens per request, cost per request and per 1,000 requests, average, 95th percentile (the time 95 requests in 100 stay under) and slowest time, by model.

**What it cannot tell:** a request whose answer carried no token counts shows as "not measured", and a model with no price in the price file shows "no price"; neither is counted as zero. A model that runs on your own machines shows "runs on own machine, no API cost": its tokens and times are there, the machines' own cost is not. The price file holds list prices read from the pricing pages of Anthropic, OpenAI, Google and xAI on the day it says; for any other provider, or a price your company negotiated, ask Claude to put it in a price file of your own. "If the same tokens went to another model" is only an estimate; for a real comparison, run the project on the other model with `AI_METER_ENV=test` and make a report of those requests.

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

It updates by itself every second:

- **Status bar at the top:** how many people are working, waiting and idle, and warnings such as someone near their quota.
- **Diagram:** each person linked to Claude and the helper assistants; moving dots mean work is happening or being handed over. **Click a person** to see their numbers.
- **Heat map:** who used the most, and at what hour, over the past 24 hours.
- **Today's numbers, usage per assistant, an event log** (newest on top) **and a 24-hour chart.**
- **View mode:** switch between the diagram and the map of branches, in 2D or 3D.
- **Replay last 24 hours:** play back the day; **Back to now** returns to live.
- **Explain** shows what each colour and line means.
- **Detail board** (`/board`): the same numbers as a table, with the Plugin column showing which computers are not on the latest version. Below the table, **Use by week and month** starts with charts: the team's cost per week for the last 12 weeks and per month for up to 13 months, then a small row of columns for each office, all on one scale. A striped column is a week or month that is not whole: the current one, or the one the numbers start in. Point at a column, or tap it on a phone, to see its dates and exact amount. Under the charts, a table shows the cost of this week and this month for the whole team, each office and each person, next to last week and last month. ▲ and ▼ compare with the same number of days before, so a Wednesday is measured against Monday to Wednesday of last week. A dash means the server had no numbers yet for that time. Wall screens do not have this part.

Colours: green is working, yellow is waiting for an answer, light blue is idle, grey is offline.

A person often has several sessions at once. Someone waiting for an answer in one session while another session runs is shown yellow, but counted both as waiting and as working: they are in the **Waiting** and the **Working** tab of the small window, and in both numbers on the board, in Telegram and in the office_board tool. So "working" and "waiting" can add up to more than the people online.

A person who uses Codex, Cursor or Gemini CLI has one more line under their name with each tool they have open and what it is doing. For those tools, waiting means the tool asked for an approval or ended its turn with a question; their cost, tokens and quota are not known, so someone who uses only those tools has no cost on the board.

The board only knows about Claude Code on computers where the plugin is installed, and about Codex, Cursor and Gemini CLI on computers where the connector is installed. Chatting on claude.ai in a browser, the Chat tab of the Claude app and Claude Code sessions that run in the cloud are not counted, so a person who works there shows as idle or offline. Do not read the board as "who uses Claude the most".

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

On a network the board does not allow (a cafe, home), the icon is dimmed and its window says "This network may not reach the board". It stays paired and works again once you are back on an allowed network.

In **Settings** you can turn notifications on or off and choose how long a wait triggers one (5, 10, 15, 30 or 60 minutes; default 10), change the language, start at login, unpair, or remove the app. You get one notification per long wait, not one every minute.

**To update:** download the new installer from the board and install it over the old one. The pairing is kept.

### 2.4 Browser extension

For a manager who prefers the browser: a Chrome or Edge extension shows the number of people waiting on its icon, and a click opens the same small window.

1. Get the `AI-Worker-extension.zip` file from an admin (the **Extension for Chrome, Edge** button on the Admin page). Unzip it somewhere it will stay, for example Documents: deleting the folder breaks the extension.
2. Open `chrome://extensions` (Edge: `edge://extensions`), turn on **Developer mode**, click **Load unpacked**, choose the `AI-Worker-extension` folder.
3. Click the extension icon, type the address you open the board with (for example `https://board.company.com`), allow access to that one site, and read the 8-digit code to an admin.

**Correct result:** within a minute of the admin approving it, the icon shows the number waiting.

The extension holds no password, OTP or login cookie.

### 2.5 Ask Claude about the board

A manager can ask Claude about the team in their own words, typed or dictated, in any language: "who is waiting longest right now?", "which office spent the most this week?". Claude reads the board's numbers and answers.

1. In Claude Code on your computer, type `/ai-worker:board`. It shows an 8-digit code, good for 10 minutes.
2. Read the code to an admin of the board, who opens the Admin page, **Paired devices and keys**, types the code, clicks **View request**, checks that the type is "Claude plugin of a manager", then clicks **Approve**.
3. Type `/ai-worker:board` again.

**Correct result:** it says the computer is paired, and from the next message Claude answers questions about the team.

- **What Claude can read:** what a wall screen shows: each person's name, state, minutes waiting, cost today and over 7 days, quota and model, and the offices. Never an email or an IP.
- **Where it goes:** the numbers Claude reads become part of your conversation with Claude, like anything else you work on with it. The board server keeps no question and no answer.
- **To speak instead of typing:** type `/ai-worker:voice` once to set up your system's dictation (see 1.2), then use it in the Claude message box: the microphone key on a Mac, Windows key + H on Windows. Claude Code's own `/voice` does not list every language.
- **To stop:** type `/ai-worker:board unpair`, or an admin clicks **Revoke** on the Admin page. Away from the office network the board does not answer, and the pairing is kept.
- A computer that is not paired has no such tool, so nothing changes for staff.
- **From another AI tool:** Codex CLI, Cursor, Gemini CLI, or Claude Code without this plugin, can ask the same questions through the board's MCP endpoint. Open the page `/mcp/connect` of your board, read the code it shows to an admin, and paste the key it then gives into your tool. What that tool reads is sent to the company that makes it. Steps and limits: [INSTALL.md](INSTALL.md), section "Ask the board from an AI tool (MCP)".
- **From Telegram** (when your admin has turned it on): open the board's bot in Telegram, press **Start** and read the 8-digit code it shows to an admin. Once approved, tap **Who is waiting**, **Cost**, **Offices**, **Team** or **Quota**, or type a short question such as "who is waiting longest?". No AI reads the question: the bot gives one of a few fixed answers from the board's numbers. What the chat reads goes through Telegram and stays in the chat on your phone. Send `/stop` to disconnect. The bot never asks for your login code. Steps and limits: [INSTALL.md](INSTALL.md), section "Ask the board from Telegram".
- **The board inside Telegram** (when your admin has allowed your chat): tap **AI Worker** next to the message field to open the small window of the menu bar icon right in Telegram: who is waiting and working, the 7-day cost chart, quotas and costs. It opens on the office network. Steps: [INSTALL.md](INSTALL.md), section "The board's window inside Telegram".
- **A message when someone waits too long:** send `/alerts 10` to the bot (or 5, 15, 30, 60 minutes), or tick the box in the window's **Settings**. The bot then writes when someone has waited that long, at most once every 5 minutes and never at night; `/alerts off` stops it. Steps: [INSTALL.md](INSTALL.md), section "Messages when someone waits too long".

### 2.6 AI projects and applications

When the server has it turned on, the **AI projects** button on the home page, or **AI projects and applications** at the top of `/board`, opens `/projects`: what each project your team built measured, if it sends to the board.

1. **Where:** `/projects`. **Do:** pick the project, the first and last day (UTC) and **Real users**, then **Show**. **Right result:** turns, cost per turn and per 1,000 turns, average, 95th percentile and slowest time, by model and by day.
2. **Do:** **Open the print version** (a new tab; press Ctrl+P, ⌘P on a Mac, and choose **Save as PDF**) or **Download CSV**.

Each turn is kept 30 days; for older days the table at the bottom has the totals per day, kept 13 months. These are numbers the project measured, not a bill.

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

1. On the TV, open the board's address (the one your admin gives you, for example `https://board.company.com`). A smart TV shows an 8-digit code by itself; on a computer plugged into a TV, click **Wall screen: pair with a code** on the login page.
2. Scan the QR code on the TV with a phone on the company network, or type the code under **Paired devices and keys** on the Admin page.
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
- **Audit log:** logins, changes and refusals for the chosen month. Kept 12 months; the page shows the newest 300 lines. **Log check** above it says whether any line was changed or taken out of the database by hand, and shows the last fingerprint: note it down now and then to compare later.
- **Stopped by ai-worker:** how many times, across the team in the last 7 days, a key or password was kept from ChatGPT or Gemini, a commit or a risky command was asked about, or a page that tried to steer Claude was flagged. Counts only, never what it was.
- **Keys for AI tools not used for 30 days** are listed above the table in **Paired devices and keys**; revoke the ones nobody needs.
- **Computers and their keys** lists every staff computer that has its own key. When a computer is lost, stolen or its owner leaves, click **Revoke** on its row and enter your OTP: it stops sending at once, and the key in the install package cannot bring it back. **Let back** lets it enrol again.

### 3.7 Menu bar downloads

The **Menu bar icon** section offers the installers for managers (see 2.3). The server writes its own address into each file, so a manager only installs and pairs.

### 3.8 AI projects and applications

With `AI_PROJECTS=1` on the server (see INSTALL), the section **AI projects and applications** makes a key for each project: type its name, **Make a key**, enter your OTP. The two lines it shows once go into the environment of the project's own server, never into a web page or a phone app. The keys are listed, renamed and revoked in **Paired devices and keys**; revoking keeps what the project already sent, and the project shows as "(key revoked)" on the AI projects page. To remove a trial's numbers for good, click **Delete its numbers** beside its name in the same section, after its key is revoked. **Prices of your own** takes a price file in the shape of `skills/ai-cost-report/my-prices.example.json`, for a provider the price file does not have, a negotiated price, or a model on your own machine.

---

## Questions

- **Can a manager read what staff typed to Claude?** No. Chat content is never sent; the board only has numbers.
- **Someone uses Claude all day but the board shows them idle. Why?** They are probably on claude.ai in a browser or in the Chat tab of the app. Only Claude Code (the Code tab, the terminal, an editor) on a computer with the plugin is counted.
- **Does it work outside the office?** The plugin works anywhere. Sending numbers, the board and updates need the company network.
- **Do I need Gemini, ChatGPT or Gemma?** No. Everything works with Claude alone.
- **Is the cost real money?** It is the price at API rates. On a subscription plan it is for comparison only.
- **Where do I report a problem?** Take a screenshot and send it to your admin. For the open-source project, open an issue on GitHub; security problems go through [SECURITY.md](../SECURITY.md).
