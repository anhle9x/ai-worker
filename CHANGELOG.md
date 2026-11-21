# Changelog

Changes that matter to people who install or run AI Worker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Added
- An installer file for staff computers on Windows, `AI-Worker-Plugin.msi`, in place of unzipping the company package and running `INSTALL-Windows.bat`. It installs for the person only, with no admin rights, and has an entry in Settings > Apps. GitHub builds one file for everyone with a placeholder; the server fills in its own address, the send code and the update signing keys (from the newest release) when an admin downloads it from the new Admin section **Plugin for staff computers (Windows)**, so the send code never goes to GitHub and nobody builds a company zip by hand. Each download is written in the Admin log. The finish screen, and **Finish AI Worker setup** in the Start menu, run the same steps as `INSTALL-Windows.bat`; a plugin already updated by `/update` is kept, never replaced by the older one in the file. Uninstalling unregisters the plugin from Claude Code and deletes its folder with `company.json`; upgrading to a newer `.msi` does not. A copy the server did not fill installs a personal plugin. Fetch it with `bash packaging/windows-msi/fetch-msi.sh`; details in [docs/INSTALL.md](docs/INSTALL.md#plugin-installer-for-windows-msi). The file is not signed, so Windows shows "Windows protected your PC" the first time.
- `UNINSTALL-Windows.bat` in the zip package: double-click it and answer `y` to remove the plugin installed with `INSTALL-Windows.bat`. It unregisters the plugin from Claude Code and deletes the plugin folder with `company.json` and Claude Code's copy of it, with the same script as the `.msi`; the person's name and history stay. Until now the zip had no way to remove the plugin but typing commands and deleting the folder by hand.

## 0.50.3 - 2026-11-22

### Fixed
- On Windows, the connector for Codex, Cursor and Gemini CLI now keeps the computer's own key (`awd1.…`) even when the answer reaches it without a text `Content-Type` (a proxy that drops the header, for example). PowerShell then hands over the answer as bytes, and the connector looked for the key in them as if they were text, found nothing and kept sending with the shared key. It now reads the answer as UTF-8 either way, as the sh connector does.

## 0.50.2 - 2026-11-22

### Fixed
- The menu bar icon (macOS, Windows, Ubuntu) no longer forgets its pairing when the computer is on a network the board's proxy does not allow (a cafe, home, a phone's hotspot). The proxy's plain 403 page was taken for the board refusing the session: the icon dropped it and asked to pair again, while the server still counted the old pairing, so the account soon hit its limit of 2 computers. Now only an answer from the board itself drops the session; on a network that is not allowed the icon is dimmed and says "This network may not reach the board", and it works again as soon as the computer is back on an allowed one.

## 0.50.1 - 2026-11-21

### Fixed
- A computer whose plugin was older than 0.50.0 when the server went to 0.50.0 was shut out of the board: the server gave it a key of its own in the answer, the old plugin threw the key away, and from then on the server refused the shared key for it ("use this computer's own key"), even after the plugin was updated. Now a key the server gives binds nothing until the computer has sent with it once: until then the shared key still sends for it. A computer that has sent with its own key is held to it as before. When the server starts this version, the rows 0.50.0 wrote for keys it only gave are dropped once, so computers shut out that way send again by themselves; a computer an admin revoked stays revoked. A computer the server knows can still be revoked before it has used its key.
- The plugin no longer sends again every second or two while the server refuses its sends (401 or 403): it waits 30 seconds, then twice as long each time, up to 10 minutes, and goes back to its usual pace after a send goes through.
- The Admin page's list of computers and their keys shows a dash, not a date in 1970, for a computer revoked before it used a key, or whose key was dropped with `--rotate-device-secret --drop-old`.

## 0.50.0 - 2026-11-21

### Security
- When a session starts in a repository, the plugin reads the files that can make an AI coding tool run commands or act differently: hooks, helper programs, rules that let every command through, the mode that asks nothing and variables that send Claude's traffic elsewhere in `.claude/settings.json` and `settings.local.json`; MCP servers and their commands in `.mcp.json`; text aimed at an AI and commands that download and run a script or delete a folder in `CLAUDE.md`, `CLAUDE.local.md` and `AGENTS.md`; slash commands that run the shell, agents and skills with hooks, and the list of what a fresh clone adds under `.claude/`. What is new or changed since the last look is named to the person in one line (for example `.mcp.json declares an MCP server "helper" that runs node tools/server.js`) and to Claude for the session; nothing is blocked. Claude Code asks once whether to trust a folder without saying what is in it, and does not ask again when these files change in a pull. A repository first seen whose files are all older than 14 days is remembered without a word, and the home folder is left alone. Only fingerprints are kept, never a path or a file's text. The idea comes from the security notes of Tencent LoopForge.
- Each computer gets a key of its own (`awd1.…`) in the answer to its first send, kept in the plugin's store (the connector: a file only its user reads), and from then on only that key sends for it. The shared `INGEST_KEY` every package carries can no longer send as a computer that already has a key. A key is checked by its signature and never stored on the server; keys older than 30 days are renewed in the answer to a send, and last 90 days. The Admin page lists the computers with a key of their own (**Computers and their keys**): who each belongs to, when its key was issued, and a **Revoke** button (with the OTP typed again) that stops it at once, then **Let back** to let it enrol again. `webhook.py --revoke-device <id>` does the same from the command line. `SHARED_KEY_MODE` says what the shared key may still do: `allow` (the default), `known-only` (no new computers) or `off`. Updates still download with either key. `board.db` goes to schema version 5.
- A computer whose email or name is filled in after it got its key gets a new key in the answer, so its key names the person it belongs to now.
- `webhook.py --rotate-device-secret` makes a new secret to sign computer keys with, and every computer gets a new key at its next send; the old secret still checks keys until 90 days have passed. With `--drop-old` the old keys stop at once and every computer enrols again with the shared key, for a file of secrets that leaked. Run it with the webhook stopped.

### Changed
- Someone waiting for an answer in one session while another session runs is counted both as waiting and as working, instead of waiting only. The small window of the menu bar icon, the browser extension and the window inside Telegram list them in the **Waiting** and the **Working** tab, so "1 waiting · 0 working" no longer shows while a session runs; the board's counts and rings, the totals of each branch (in the server and the Go receiver), Telegram's `/team`, and the office_board tool (plugin and server, now version 1.1.0) count them the same way. Their dot stays yellow, and the alert for a long wait is unchanged. The Admin page's list of computers shows both, for example "waiting for reply (1) · working (2)". Because one person can be in both, working plus waiting can be more than the people online: the office_board tool and Telegram say so.
- A new plugin install makes a device id of 16 letters and digits from secure randomness, as the connector already did, instead of 8 from `Math.random`, so a million computers do not get the same id by chance. An id made before is kept, so no computer shows twice.
- The code that stands for an email on the wall display stays the same after the server restarts: it is made with a secret kept in the keys database instead of one made afresh at every start.
- Money is added up in whole millionths of a dollar (`usdMicro`) on the server, so totals are exact whatever the order of the hours and computers. A total can differ from before by less than a millionth of a dollar per hour; the stored rows keep `usd` beside `usdMicro`.
- A change shows on the board within a few seconds. The plugin sends a second after its numbers or state change (a turn starts or ends, Claude waits for an answer), at most once every 2 seconds, instead of only at its 30-second heartbeat; the sessions on one computer share what was last sent, so they do not send the same change twice. The board asks every second while it is on screen (every 10 seconds in a background tab) and draws only what changed, and the server keeps a build for each role half a second (`VIEW_CACHE_SECONDS`, now 0.5). Measured on the demo: a change reaches the page 0.15 to 0.3 s after the server gets it.
- Sends are limited per computer instead of per address: each computer may send 20 times at once, then once a second. Before, 300 sends per address in 10 minutes stopped an office of about 15 busy computers behind one public address. The limit of 10 new computers per address a day stays.
- The board's server keeps every computer's last send in memory, cleaned once, instead of cleaning every computer's 8 days of numbers again at each send and each read of the board. A send now takes about the same time with 20 computers as with 10,000 (about 0.5 ms of the server's own work on a Mac with an M-series chip, against 79 ms at 300 computers and 1.3 s at 5,000 before). The table stays the record: the cache is written with it and loaded again at start, and when another program such as `webhook.py --forget-device` changes the file.
- Each computer's hours are added up per day once, when it sends, and each person's row of the board is kept until one of their computers sends or a moment that changes it comes (the next hour, midnight, a computer going quiet, a quota resetting). Building the board for 10,000 computers takes 164 ms instead of 898 ms, the history round every 30 seconds 31 ms, and the daily count every 5 minutes no longer goes through every hour of every computer.
- A send now updates the rewind history of the person who sent only; the round every 30 seconds still looks at everyone, for computers that went quiet.
- When more requests are being answered at once than `BUSY_REQUESTS` (default 32), a send or a request from someone not logged in gets 503 with `Retry-After: 30` at once instead of waiting behind the others until everything times out; a body over 16 KB is not even read. The plugin sends again at its next round; people logged in, devices with their own key and `/health` are still answered, and the log says once a minute how many were turned away.
- The board's server keeps each computer's hour book in rows of its own instead of one block of JSON in the computer's row: `board.db` goes to schema version 6, with the tables `device_hours` (one row per hour and kind, the key starting with the hour) and `device_days` (one row per computer per local day). The upgrade moves the books in at the first start, in one transaction, after copying the database to `board.db.schema-5.bak`, the way back (docs/OPERATIONS.md, section 5). A send writes only the hours that changed and the days they fall in, and the computer's row only when more than its time changed, at least once a minute; the memory holds each computer without its book, with its days and its last 48 hours. Measured on a Mac with an M-series chip at 10,000 computers: a send of changed hours 0.12 ms instead of 0.46, a batch from the receiver 13,000 rows a second instead of 2,400 with 0.14 KB of WAL a row instead of 12, a start 1.3 s instead of 3.8, and 434 MB of memory instead of 1,630. At 100,000 computers the server starts in 14.7 s with 3.5 GB of memory; a v: 1 send of the whole book takes 6.2 ms there, as its 8 days of hours are read from all over the table. The board, the history, the daily totals and `--export-json` give the same as before. Changing `TZ_OFFSET` counts the days again at the next start.
- The board's numbers are built at most once every `VIEW_CACHE_SECONDS` (default 2) for each role, and every open board of that role gets the same answer. A board asks every 10 seconds, so what it shows is at most 2 seconds older than before. `VIEW_CACHE_SECONDS=0` builds them for every request, as before.

### Added
- An optional receiver written in Go (`receiver/`, Go standard library only) for organisations with many thousands of computers: it takes the sends of computers that have a key of their own on an address of its own over TLS (HTTP/1.1 only, a renewed certificate read again without a restart, the address to listen on always said), cleans them exactly as the server does, answers at once and hands them to the server in numbered batches; any other send it passes to the server as it came, with the computer's real address. A small company does not need it, and no plugin sends to it yet. On the server, `RECEIVER=1` opens the paths it uses on the same machine (`/internal/rows`, `/internal/ingest`, `/internal/policy`, `/internal/devices`, 404 to anything else) and writes the file of secrets it reads (`KEYS_DIR/receiver-secrets.json`, 0600). The receiver and the server are held to the same results by the shared sample, a random test with the server's code as the judge, and, while it runs, the server cleaning again `RECEIVER_CHECK_PERCENT` of the sends (default 1). This stage does not yet reach 100,000 computers within 5 seconds. Details: docs/RECEIVER.md.
- The Go receiver and the server speak version 2 of their internal protocol (`proto: 2` in the policy): a batch holds at most one row per computer, its sends since the last batch put together as the server would have written them one by one; the third check comes in rows of its own (`check`), compared and never written; a batch on its way is never changed, so sent again it is the same batch. The receiver keeps of each computer only the time of its last send and its hours of today, three numbers an hour, and loads only those from the server (`/internal/devices`; `whole=1` gives one computer's whole book, for tests): measured at 100,000 computers with 24 hours each, 261 MB of Go's heap. While the server does not answer, every send is still answered 200 and at most one row per computer waits. The shared sample is now also played through the receiver into the real Python server, which must end with the books and days it expects.
- `/data?scope=org` gives the whole organisation with the totals of each branch (people, online, working, waiting, open sessions, cost today, tokens), and its people only while there are 500 or fewer; `/data?scope=branch:<id>` gives one branch, 500 people a page in the order of their names (`&page=`). Both are cut from the same view of the same role as `/data`, which is unchanged. With `RECEIVER=1` each person of `/data` also has `row`, the code of their row: an HMAC of the person with the wall's secret under another label, the same for every role and after a restart, which gives back no email or name; the Go receiver reads which row and which branch each computer is on, only what changed since the last time, from `/internal/people` every 15 seconds, so a person who moves to another branch is in the right place within 10 to 25 seconds (`RECEIVER_PEOPLE_SECONDS`, default 5, is how often at most the server builds that table again). Details: docs/RECEIVER.md, section 3.
- The Go receiver keeps each computer's state (its sessions, the connector's tools, the tasks being handed to helpers) besides today's totals, and adds them up per person's row and per branch exactly as the board does: status, sessions, working, waiting, cost and tokens today, tasks. A test runs the real server and checks, after each step of the shared sample and for every status, that the receiver's rows and branch totals are what the board says at the same second. `/internal/devices` now also gives that state, with no name, email or address. These are the numbers the live feed to the boards will carry; nothing is sent to a board yet. Details: docs/RECEIVER.md, sections 2 and 3.
- The Go receiver serves the boards their live numbers on `/live` (server-sent events) and `/live/snap` (the same once, as JSON): for one branch its people's rows, for the whole organisation the totals of each branch, only numbers and row codes, the same for every role. Each second it adds up every computer once and builds each scope that is read once for every board of it; after `hello` and the whole scope it sends only the rows that changed (`d`, with `gone`), and a comment every 15 seconds when quiet. A board that reads slowly holds no queue and is cut after one write waits 10 seconds; a feed is not cut by the 30-second timeouts of a send. A logged-in board gets a ticket from `POST /sse/ticket` on the server (5 minutes, signed with a secret of its own in the file of secrets, turned with `--rotate-device-secret`); the receiver checks its signature, its end, its scope and the board's `Origin`, and ends within about 20 seconds the feed of a session logged out, as the policy names it (`endedSessions`). Two new settings on the server, `RECEIVER_LIVE_URL` and `RECEIVER_BOARD_ORIGIN`, turn it on and add the receiver to the pages' `connect-src`; without them, and without `RECEIVER`, nothing changes. Measured on a Mac with an M-series chip at 100,000 computers with every branch read: 175 ms of work a second. Details: docs/RECEIVER.md, section 3, "The live feed".
- With the live feed set up, the board's page reads one scope at a time, chosen at the top of its list: the whole organisation, one branch, or the page of a branch of more than 500 people, kept in the address (`?scope=`, `&page=`) for a reload or a TV screen. The whole organisation shows one card and one row per branch with its totals, opening that branch; a branch shows its people. The numbers come from the feed as they change, put on each person by the code of their row, and `/data?scope=` is asked every 20 seconds for the names and the rest of the board; at the end of a ticket or after an error the page asks a new one and opens the feed again. Without the feed (`POST /sse/ticket` answers 404, as for a small company) the page asks `/data` every second as before, and so does the page of a whole organisation of 500 people or fewer. Details: docs/RECEIVER.md, section 3, "The live feed".
- `/ingest` reads a second format, `v: 2`, for the plugin to come: the state in full and only the hours that changed, each sent as its whole value and replacing that hour, or the whole book with `full: true`. Both formats keep the same record, so the board, the history and the daily totals are the same whichever a computer sends; a shared sample (`tests/contract/ingest-v2/`) holds them to that, for this server and for a receiver written in another language later. The answer to every send now also says which formats the server reads (`accepts`), the pace it wants (`minGapMs`, `stateGapMs`, `maxGapMs`: 2 seconds, 2 seconds, 4 minutes by default, set with `INGEST_MIN_GAP_MS`, `INGEST_STATE_GAP_MS`, `INGEST_MAX_GAP_MS`), whether it needs the whole book (`needFull`) and a new `boot` value at each start; older plugins ignore these. Sends of one computer at the same moment are now merged one at a time. Details: docs/DATA-MODEL.md, "Format v: 2".
- `MAX_DEVICES` in `/etc/ai-worker.env` sets how many computers the board accepts (default 300, at most 200,000). Measure before raising it: `docs/BENCHMARK.md` shows memory growing by about 150 KB per computer.
- `tests/load/load_test.py`, a load test of the board's server: it starts the real server on 127.0.0.1 in a temporary folder and plays computers that send and people who keep the board open, at 20 to 300 computers and two rhythms, then pushes it to its ceiling, from several load processes; `--scale` measures past 300 computers, with memory and start time, and `--ceiling` finds what one server process answers. Results and what they mean: `docs/BENCHMARK.md`.

### Fixed
- A record of work handed to a helper whose `tool` was a list or a table instead of text stopped the rest of that send's handling with an error; it is now dropped like any other bad record.

## 0.49.1 - 2026-11-20

### Fixed
- The board's top bar no longer cuts its title to "AI WORKER // AGEN…" or breaks the line under it in two when the bar is crowded (more buttons, or a window a little over 1500 pixels wide): the end of the title and the line under it show only when they fit whole, and are hidden otherwise.

## 0.49.0 - 2026-11-20

### Security
- The check before a risky command reads a backslash the way the shell does. `rm -rf x\" ~/work \"node_modules` was read as one harmless word ending in `node_modules` and ran without being put to the person; the same escaped quote could hide `| sh` after a download.
- The secret check before `git commit` also reads what a `git add` earlier in the same command will stage. In `git add . && git commit`, the most common form, the check ran before the add and saw nothing new. A `git commit` written as `/usr/bin/git`, `env git`, `sudo git` or `NAME=value git` is now seen too.
- The board's login refuses a form sent from a page on another site. Such a page, opened by anyone in the office, could send five wrong codes from that person's browser and lock everyone behind the office's IP out of login for 15 minutes.
- The Python and Go meters no longer follow a redirect from the board's address. The Python meter carried the project's key to wherever the redirect pointed, another host or plain http included.
- The OTP secrets are sealed in `accounts.db` with a key that `install.sh` makes once in `/etc/ai-worker-otp.key`, root only, and hands to the webhook through systemd (`LoadCredential`). A copy of `keys/` or of a backup of `/opt` no longer logs anyone in. The webhook seals the secrets already there at its first start and rewrites the file so no plain copy stays in it; without the right key it does not start, and says why. The running service and sudo users can still open them.
- No copy of an OTP secret is left in plain text where it is not needed: `install.sh` takes the names the webhook has imported out of `OTP=` in `/etc/ai-worker.env` and starts it again, `manage-otp.sh --rescue` writes the new admin straight into the database instead of that line, the copy of `accounts.db` made before a schema upgrade is deleted after 7 days instead of 30, `keys/legacy-json/accounts.json` from before SQLite is deleted 30 days after it was moved in, and deleted rows of `accounts.db` are overwritten.

### Changed
- `accounts.db` goes to schema version 2, so an older version refuses it. To go back, run `sudo bash manage-otp.sh --unseal` first (docs/OPERATIONS.md, section 5). `manage-otp.sh --forget-sealed` removes the accounts whose sealed secret no key on the server opens, for when the OTP key is lost for good.
- Keep a copy of `/etc/ai-worker-otp.key` somewhere safe, apart from your backups of `/opt/ai-worker`: without it nobody can log in.

## 0.48.1 - 2026-11-20

### Fixed
- The **By model** table of an AI project's report fits its frame on a computer screen: the Cost and Price checked columns were hidden past the right edge on the board's **AI projects** page and in the print version seen on screen. The printed A4 page was already right.
- On the **AI projects** page, the boxes that pick the project and the environment show their whole text: a long project name, or "Real users (prod)" in Vietnamese, was cut short.

### Changed
- In Vietnamese, the Admin page writes days as DD/MM/YYYY in the audit log, the log check line, the reads by AI tools and Telegram chats, and the work handed to AI helpers. English keeps YYYY-MM-DD.
- README: the pictures of the report, the **AI projects** page and Telegram were taken again, so the numbers in them agree.

## 0.48.0 - 2026-11-20

### Changed
- On the Admin page, the section **TV screens** is now **Paired devices and keys**: it has long held menu bar icons, browser extensions, Telegram chats and the keys of AI tools and AI projects as well as TVs. The connect page, the Telegram bot, the plugin, the browser extension and the guides use the new name.
- README: on a phone the row of pictures opens on the cost and performance report straight away, with no empty space to its left, the Telegram picture is the fourth instead of the last and now shows the bot's chat beside the board's window, a new picture shows the page that connects an AI tool to the board over MCP, and the opening names SOPs where it speaks of turning a team's procedures into skills.

## 0.47.7 - 2026-11-20

### Changed
- In Vietnamese, the cost and performance report of an AI project or application writes days as DD/MM/YYYY (for example 19/11/2026): the report the `ai-cost-report` skill makes, the print version and the board's **AI projects** page. English keeps YYYY-MM-DD, and so do the CSV, the file names and `--from`/`--to`.
- The README's row of pictures starts with the cost and performance report (A4) and the **AI projects** page, adds the window inside Telegram, and shows the Admin page with what ai-worker stopped, the log check and AI tool keys left unused. The opening now also names turning a team's procedures into skills.

## 0.47.6 - 2026-11-20

### Changed
- The README opens with what AI Worker does in one line (cost and speed of AI from the whole team to the AI products you build, passwords and API keys kept from leaking, all on your own server), then the points that set it apart: the live board, the cost and speed report for your own AI projects, the skills that work out of the box, nothing of the work read, and free for the whole team. The title is now just "AI Worker". In English and Vietnamese.

## 0.47.5 - 2026-11-19

### Fixed
- The C/C++ meter (`ai_meter.h`) did not build with gcc on Linux when warnings are errors: gcc warned that the turn's time might not fit its buffer. The buffer now has room for every field at its widest. The project's own CI (`tests/appmeter`) had failed on this since 0.46.0; the other meters passed.

## 0.47.4 - 2026-11-19

### Changed
- The architecture drawing in the README (light and dark, English and Vietnamese) shows your team's AI project or application sending its own counts to the server with a key of its own, the server keeping its turns, and the AI projects page with the report, the PDF and the CSV. Its text for screen readers says the same.

## 0.47.3 - 2026-11-19

### Added
- An admin can delete the numbers of an AI project or application whose key was revoked, for example a trial: **Delete its numbers** beside its name in **AI projects and applications** on the Admin page, with the OTP code. It is refused while the key still works, and the audit log records the project and how many turns and daily rows went. On `/projects`, such a project now reads "(key revoked)" next to its name.

### Changed
- The README puts two features with the ones that set AI Worker apart: measuring the AI projects your team builds (cost and performance in one report) and the guardrails on every computer with their record on the server. They replace two lines further down. The architecture document shows an AI project in the drawing of the parts, has a main flow for measuring one, from the meter to the report, and says where the meters live.
- On `/projects`, **Download the report** is now **Open the print version**: the report opens in a new tab instead of being saved as an HTML file, so saving it as a PDF (Ctrl+P, ⌘P on a Mac, then Save as PDF) leaves nothing else in the downloads folder. The CSV is still a download. The bar at the top of the print version also says to untick the browser's own headers and footers, which only repeat the date and the title the report already prints. The guides say the same.

## 0.47.2 - 2026-11-19

### Changed
- The report people download (**Download the report** on `/projects`, and the HTML file the `ai-cost-report` skill makes) is now made for paper: always white, A4 portrait, with the project's name, the days, the environment and when it was made at the top, the line saying these are numbers the project measured and not a bill in bold, the totals in four columns, and tables that shrink their text and wrap instead of being cut at the edge. A table's heading repeats on each page, no row or heading is split from its table, the price sources stay with the closing line, and each page carries the report's name and its page number. Opened in a browser, the same file reads as a light document page: larger text and a wider sheet on a computer, the full width of a phone with the totals in two columns, and only the widest table (by model) scrolling inside its own box, never the page. A bar at the top, not printed, says how to save it as a PDF (the board serves the file without scripts, so there is no print button). The `/projects` page keeps its own look.

### Fixed
- On `/projects`, the arrow of the project and environment pickers sat on the edge of the box; it now sits inside, with room around it.

## 0.47.1 - 2026-11-19

### Changed
- The cost and speed report of an AI project or application (on the board's `/projects` and in the file the skill makes) takes AI Worker's own colours: dark blue with a cyan accent in dark mode, teal on light, cards and tables on panels, the totals in four even columns (two on a phone), and the picker as one panel with a clear button. Notes that leave numbers out (not measured, no price, longer prompts cost more) stand out in amber; notes that only explain do not.
- When no turn was measured in the chosen days and environment, the report says so in one line instead of cards and tables full of dashes.

## 0.47.0 - 2026-11-19

### Added
- A meter for Java 11+ and every JVM language (Kotlin, Scala, Groovy), `skills/ai-cost-report/meter/AiMeter.java`: one file in package `aimeter`, standard library only. Java has no JSON reader of its own, so the file carries a small one: `record` reads the provider's answer as JSON text, or as a `Map` already parsed by Jackson or Gson, like the Python meter, including xAI's reasoning tokens outside `completion_tokens`; `count` takes numbers by hand. `meter.turn(t -> ...)` writes `timeout` or `error` and rethrows; sending to the board goes in batches in the background with `java.net.http`, only over HTTPS or to the same machine.
- A test for it in `tests/appmeter/test_appmeter.py`, skipped without a working JDK: built with `--release 11 -Xlint:all -Werror`, it reads the same sample answers as Python with the same counts, refuses what is not whole-number JSON, and sends the same lines to a board started by the test.

### Changed
- The AI projects guide (`docs/AI-PROJECTS.md` and `.vi.md`) has a section for Java, Kotlin and other JVM languages, with a short Spring Boot example, and one for React, Next.js and other web front ends: no meter in the browser, the meter goes where the server calls the LLM (Route Handlers, API routes, Server Actions, Express), with what to do on a serverless host and how to measure the time the user sees without a key in the page. The download links point to `v0.47.0`.
- The `ai-cost-report` skill, README and the skills list name Java and Kotlin, and the skill says how to meter a React or Next.js project.

## 0.46.0 - 2026-11-19

### Added
- Meters for more languages in `skills/ai-cost-report/meter/`, each one file to copy with nothing to install: `AiMeter.cs` (C#, .NET 6+) and `aimeter.go` (Go 1.21+) read the providers' answers and can send to the board like the Python and Node meters; `ai_meter.rs` (Rust) and `ai_meter.h` (C99 and C++) write the file from token counts the project passes in. `ai-meter.d.cts` gives TypeScript the types of `ai-meter.cjs`. On Linux, `ai_meter.h` turns on POSIX itself when it is included first, so `-std=c99` builds with glibc.
- Tests for each new meter in `tests/appmeter/test_appmeter.py`, skipped on a machine without the language's tools: the Go and C# meters read the same sample answers as Python with the same counts and send the same lines to a board started by the test; the Rust, C99 and C++11 meters (built with every warning an error) write lines the report reads, with `null` when a call is not measured and `other` for a bad provider name; the TypeScript types accept the guide's code under `--strict`, it runs, and wrong calls are refused.

### Changed
- The AI projects guide (`docs/AI-PROJECTS.md` and `.vi.md`) has a table of the meters by language, the copy and download command for each, and a section for each of JavaScript, TypeScript, C#, Go, Rust and C/C++ in step 3, with the code to add and what each one cannot do (Rust and C/C++ take token counts by hand and only write the file). A project in another language (Java, PHP, Ruby...) is told plainly what to write instead, with one whole line as an example.
- The `ai-cost-report` skill lists every meter file and how to use each one; README and the skills list name the languages.

## 0.45.4 - 2026-11-19

### Changed
- Wherever the guides asked for the board's address (the AI projects guide, the meter's format, the server's README, the settings template, the install and user guides), they now say it is the domain you open the board with and give an example; the SSH command in the Telegram setup names the SSH user and the server's IP or name.

## 0.45.3 - 2026-11-19

### Added
- A guide for the people who build an AI project or application, `docs/AI-PROJECTS.md` (and `.vi.md`): every step to measure it, by Claude or by hand, with or without a board, for Python, Node or any other language. README, the documents index, the user guide, the install guide, the components list, the operations guide and the server's README point to it or now mention AI projects and applications.
- `/ai-worker:help` says in plain words what `ai-cost-report` does.

### Fixed
- On `/projects`, the link at the top went back to the detail board even when you came from the home page's **AI projects** button. It now offers both: **◂ Dashboard** (the home page) and **Detail board**.
- The user guide said the meter sends nothing to the board; since 0.45.0 it does when the project's server is given a key.

## 0.45.2 - 2026-11-19

### Added
- The home page has an **AI projects** button next to **Detail board**, for admins and viewers when the server has `AI_PROJECTS=1`; it opens `/projects`. The wall display does not show it.

## 0.45.1 - 2026-11-19

### Fixed
- The steps that turn on AI projects and applications in INSTALL named the wrong service: restart `ai-worker-webhook` after adding `AI_PROJECTS=1`.

## 0.45.0 - 2026-11-19

### Added
- AI projects and applications on the board, off unless the server has `AI_PROJECTS=1`. An admin makes a key for each project on the Admin page (with the OTP code, shown once); the project's own server sends what its `ai-cost-report` meter measured to `/projects/ingest`. Admins and viewers open **AI projects and applications** from `/board`, pick a project and days, and read or download the same report as the skill makes, as HTML (prints to PDF) or CSV. The key only sends, is refused from a browser, and opens nothing else; each turn is cleaned by the report's own code, an unknown field dropped and a turn sent twice kept once; 120 sends per key in 10 minutes, 100,000 turns a day. Turns are kept 30 days, totals per day 13 months; cost is worked out when someone looks, from the price file and prices an admin may paste for providers it does not have. The wall display, the MCP endpoint and Telegram do not get these numbers.
- The meters in `skills/ai-cost-report/meter/` can also send to the board: set `AI_METER_URL` and `AI_METER_KEY` on the project's server. They send in batches in the background, drop the oldest turn when 1,000 are waiting, give up after one more try, never make the project wait, and send the key only over HTTPS or to the same machine. The file is still written.
- `aiworker.caddy` has a commented block that lets one outside IP, such as a project on a cloud server, reach `/projects/ingest` and nothing else.

### Changed
- The server's database moves to schema version 4 (two tables for AI projects and applications). The server copies the database before upgrading, as for every schema change. The server installer also copies `server/board/*.json` (the price file and the report's words).

## 0.44.0 - 2026-11-19

### Added
- A new skill, `ai-cost-report`, measures the cost and speed of an AI project or application your team built, for a cost and performance report. It works with any LLM provider: it reads the answers of Anthropic, OpenAI, Gemini, xAI Grok, Bedrock, Cohere, Ollama, the Vercel AI SDK and every API that copies OpenAI's shape (DeepSeek, Mistral, Groq, OpenRouter, vLLM...), and takes the numbers by hand for any other. A small meter goes into the project (one file to copy for Python or Node, with no package to install, or a documented line format for any other language) and writes one line per user request to a file on that machine: times, and the token counts the provider returned, per model. It never writes a question, an answer, a user id or an error message, and nothing goes to the board. The skill turns the file into an HTML page that prints to PDF and a CSV: requests, LLM calls and tokens per request, cost per request and per 1,000 requests, average, 95th percentile and slowest time, by model. Prices come from a price file that names each provider's pricing page and the day it was read (Anthropic, OpenAI, Google, xAI), plus a price file of your own for any other provider or a negotiated price. A model with no price says so instead of a guess, a model that runs on your own machines counts no API cost, and tokens the project did not get are shown as not measured, never as zero.
- The installer for Codex, Cursor and Gemini CLI copies `ai-cost-report` too, so 17 skills in all.

## 0.43.0 - 2026-11-19

### Added
- On the office page, the cost chart's time range menu has a date range: pick the first and the last day, like the dates of a return flight, and **Show** draws just those days; **Last 7 days** goes back to the usual view. Only days this computer has cost for can be picked.

### Fixed
- On the office page, the cost chart drew nothing when **Columns** was chosen: a name left over from renaming the code stopped it at the first column.
- On a phone, the dates under the cost chart ran into each other. The chart now writes only as many as fit side by side.

## 0.42.0 - 2026-11-19

### Added
- Each piece of work Claude hands to ChatGPT, Gemini or Gemma leaves a record in the server's chained audit log: who, which helper, how long the prompt and the answer were, whether a secret stopped it, what the check of the answer found, and a fingerprint of the prompt. Never the prompt or the answer: the fingerprint is salted with a value kept on the computer, so the server cannot guess a short prompt by trying likely texts. The Admin page lists the month's records with totals; admins only. The records go only to a server, never into a common folder.
- The answer of ChatGPT, Gemini or Gemma is read before Claude uses it: a key or a password in it, text aimed at an AI (a helper that searched the web can bring back a page's orders), and commands in it that cannot be undone. When something is found, Claude is told beside the answer not to copy the secret, not to follow the text and not to run the command unless you ask after seeing it, and you see a short notice. The answer still reaches Claude whole. The Admin page counts these with the other stops.

### Changed
- The server's database moves to schema version 3 (one small table that keeps the audit log from writing the same record twice). The server copies the database before upgrading, as for every schema change.

## 0.41.0 - 2026-11-18

### Added
- A Telegram chat that reads totals only can open the board's window inside Telegram too, once an admin clicks **Allow the window**. The server adds the numbers up itself and sends only the team's counts and costs, never a person: the big number, the 7-day chart and the small numbers are there, and each tab shows one line of totals with a note that nobody is named.

### Changed
- The architecture drawing in the README is drawn again: it shows the window inside Telegram on its own path, what the plugin stops on the computer, what may leave for ChatGPT or Gemini, the chained audit log and what the Admin page counts.

## 0.40.0 - 2026-11-18

### Added
- Before Claude runs `git commit`, the lines the commit adds are read for keys, tokens and passwords. A commit that holds one is put to you first, whatever the permission mode, naming the file and line but never the value: once in git, a secret stays in the history and goes wherever the repository is pushed.
- A web page, a search result or a browser page that speaks to an AI instead of its reader ("ignore your previous instructions", "do not tell the user", "send the API keys to…", text hidden in characters nobody can see) is flagged: Claude is told, beside the result, that it is the page's text and not your request, and you see a short notice. The result itself still reaches Claude whole.
- The Admin page points out keys for AI tools (the MCP endpoint) that nobody has used for 30 days, so a key left in an old config file can be revoked.
- Each line of the server's audit log carries the fingerprint of the line before it. The Admin page says whether any line was changed or taken out of the database by hand, and shows the last fingerprint to note down. Someone who can rewrite the whole database and its last fingerprint is not caught this way.
- The Admin page shows how many times ai-worker stopped something across the team in the last 7 days: secrets not sent, commits asked about, risky commands asked about, pages that tried to steer Claude. Counts only, never what it was; admins and viewers only.

## 0.39.1 - 2026-11-18

### Fixed
- A password or key written as a `.env` setting in the middle of a line (`review: DB_PASSWORD=…`), or in JSON (`"DB_PASSWORD": "…"`) or YAML (`DB_PASSWORD: '…'`), was sent to ChatGPT or Gemini, because the check looked for such a name only at the start of a line. It is now caught anywhere in the line. Reads of the environment (`os.getenv(…)`, `process.env.X`, `${{ secrets.X }}`) still pass.

### Changed
- Past 80% of the context, Claude is told too, not only the person: beside the person's next message, once per climb, it is asked to finish what that message asks, then write a handoff note and suggest a new session in one line. A compaction at the limit makes the person wait one to two minutes and drops detail; a fresh session does neither. If the person carries on here, so does Claude.

## 0.39.0 - 2026-11-18

### Added
- Text for ChatGPT or Gemini is read before it leaves the computer: if it holds what looks like a secret (a private key, an AWS, GitHub, GitLab, Slack, OpenAI, Anthropic, Google, Stripe or Telegram bot key or token, a JSON web token, a password in a connection string, or a password or key in a `.env` line), it is not sent, whatever the permission rule or mode. Claude is told what was found and on which line, never the value, so it can take it out and send again. The same check covers a separate ai-workers server (`mcp__ai-workers__ask_chatgpt` and the like). Placeholders and the providers' own documentation examples pass.
- Four more kinds of shell command are put to a person before they run, like a folder delete: a downloaded script run at once (`curl … | sh`, `bash <(curl …)`, `iwr … | iex`), turning off macOS's check on downloaded apps (`xattr -d com.apple.quarantine`, `spctl --master-disable`), writing straight to a disk or erasing one (`dd of=/dev/…`, `mkfs`, `diskutil eraseDisk`), and opening a file to every user and program (`chmod 777`, `chmod o+w`).

## 0.38.0 - 2026-11-18

### Added
- The Telegram bot can write first: a message when someone has waited for an answer longer than the chat chose. Each chat turns it on for itself with `/alerts 10` (`/baocho 10`; 5, 15, 30 or 60 too) or in the window's settings, and it is off until then. Each wait is told once, several go in one message, at most one message every 5 minutes, 6 an hour and 30 a day, none from 19:00 to 07:00. The first line names nobody; a chat that reads totals only gets the count alone; a chat allowed the window gets a button that opens it. Each message is logged with how many people, never who. See [INSTALL.md](docs/INSTALL.md).

## 0.37.0 - 2026-11-18

### Added
- The board's small window can open inside Telegram, as a Telegram Mini App: the number of people waiting, the 7-day cost chart and the tabs of the menu bar icon, from the bot's menu button. Off unless `TELEGRAM_APP=1` and `TELEGRAM_APP_URL` are set; then an admin allows each chat that reads each person, with **Allow the window** on the Admin page. The numbers go from the board to Telegram's built-in browser over HTTPS, not through Telegram's servers, so the window opens on the networks the proxy lets in (your offices, by default). The webhook checks what Telegram signs with a key the installer derives from the bot token, and keeps sessions in memory only; revoking the chat, `/stop`, or **Stop the window** ends them at once. Not yet tried in Telegram's own apps. See [INSTALL.md](docs/INSTALL.md).

### Changed
- `qa-test` finds the app by the name the user gives: it lists the apps on the device and picks the one that matches, and shows the list only when none or several do. Nobody has to know a bundle ID.

## 0.36.0 - 2026-11-18

### Added
- `qa-test` also tests iOS and Android apps on a simulator, an emulator or a phone, through a mobile MCP: Mobile MCP or Appium MCP, both open source. The skill installs nothing: when no such MCP is there, it names the one line to run, with Mobile MCP's usage data switched off. It never uses a cloud device unless asked, and asks before installing an app or clearing its data. Tried with Mobile MCP 1.0.17 on an iPhone 18 Pro simulator with iOS 27.2.

## 0.35.1 - 2026-11-17

### Changed
- The window under the menu bar icon shows three more numbers under the chart: today's tokens, open sessions, and tasks handed to Gemini, ChatGPT and Gemma in the last 24 hours. All three come from what `/data` already holds: nothing new is collected or sent. The tabs no longer show a tooltip that repeats the name written under them. As before, the browser extension shows the change after it is installed again from the Admin page.

## 0.35.0 - 2026-11-17

### Changed
- The window under the menu bar icon, round two: the tabs carry their names under the icons; when nobody is waiting, today's cost takes the place of the big number, so the window always opens on a number worth reading; the big number is always in the accent colour; and Open board is a small button on the right instead of a wide filled bar. The menu bar apps get it from the server; as with 0.34.0, the browser extension shows it after it is installed again from the Admin page.

### Added
- A chart of the whole team's cost on each of the last 7 days in the window under the menu bar icon, today in full colour, with a dashed line at the average. For it, `/data` gives every role, the wall role included, `teamDays`: one team total per day for the last 7 days, with no person and no office. It is the one part of the daily totals a wall reader gets; everything per person or per office stays with admins and viewers ([PERMISSIONS.md](docs/PERMISSIONS.md)).

## 0.34.0 - 2026-11-17

### Changed
- The window under the menu bar icon, and the same window in the manager browser extension, has a new look: the number of people waiting for an answer in large type at the top, with how many are working and today's cost under it; the tabs as one segmented control; short bars next to each wait and each cost; one accent colour, with red kept for a quota close to its limit; and Open board as the one filled button. The menu bar apps on macOS, Windows and Ubuntu show the page the server sends, so they get the new look as soon as the server is updated, with nothing to install again. The browser extension carries its own copy: a manager sees the new look after installing the extension again from the Admin page.
- On the Admin page, the line under **TV screens** says that every 8-digit code is approved there (TV screens, menu bar icons, browser extensions, Telegram chats and AI tools), and the code box no longer says the code is on the TV. The section keeps its name, which older plugins and the bot point admins to.
- On `/mcp/connect`, "Claude Code" and "Gemini CLI" stay whole when the subtitle wraps.

## 0.33.3 - 2026-11-17

### Added
- The board links to `/mcp/connect`, the page where a person asks for a key for their AI tool: a **Connect an AI tool** button on `/board` for admins and view-only accounts, and the link with a **Copy link** button next to the code box under **TV screens** on the Admin page. Wall displays do not show it, and with `MCP=0` neither appears.

### Changed
- The page `/mcp/connect` and the hint on the Admin page name Claude Code, not Claude, among the AI tools that can connect: claude.ai is off by default.

## 0.33.2 - 2026-11-17

### Changed
- The contributor guide and the test plan list all ten checks to run before a change is done, the same ten as `AGENTS.md`.
- The description of the `ui-ux-pro-max` skill says to load it before writing or changing interface code, in English and Vietnamese. On a computer with many skills installed, a request to redesign a page was often done without it.

### Fixed
- The "How it works" diagram in the README said employee computers send counts only. It now says what is sent (the name, the account and a few details about the computer, with the counts) and shows the two ways to read the board that 0.33.0 added: AI tools over MCP and a Telegram chat.

## 0.33.1 - 2026-11-17

### Changed
- The documents say how far asking from Telegram has been tried: a chat that reads each person was tried once with the real Telegram on a production server. The cost answer named a person; the waiting and quota answers with names were not seen.
- The Vietnamese install guide uses the same words for the demo's sample people as the rest of the Vietnamese documents.

## 0.33.0 - 2026-11-17

### Added
- **Use by week and month.** The detail board (`/board`) has a new part below the table: the cost of this week and this month for the whole team, each office and each person, next to last week and last month, with the month's tokens and delegated tasks. ▲ and ▼ compare with the same number of days before. Admins and viewers see it; wall screens, the menu bar, the browser extension, a manager's plugin and the MCP endpoint do not. The server adds up the hours the computers already send into one total per person per day: no computer sends anything new, and nothing has to be reinstalled on them.
- **Charts of use by week and month.** Above that table the detail board draws the team's cost per week for the last 12 weeks and per month for up to 13 months, and one small row of columns per office on a shared scale. A week or month that is not whole (the current one, or the one the numbers start in) is striped; hover, tab to or tap a column for its dates and exact amount. Drawn by the server as plain HTML: no script and no library. On a server that has just been upgraded the charts start with a few columns and fill up week by week.
- `webhook.py --forget-usage <email or name>` deletes one person's totals per day.
- `python3 server/demo.py` comes with half a year of sample history, so the new part has a last week and a last month to compare with and its charts have columns to draw.
- **Ask the board from any AI tool that speaks MCP.** The server has a read-only path, `/mcp`, with one tool that gives what `/ai-worker:board` gives in Claude Code: who is working, who is waiting and for how long, cost and quota, never an email or an IP. A person asks for a key on the new page `/mcp/connect`; an admin approves their 8-digit code on the Admin page and chooses what the key may read: each person, or team and office totals only. A key opens `/mcp` and nothing else, lapses after 30 days without use, may ask 120 times in 10 minutes, and each read is logged for 3 months under "Reads by AI tools". `MCP=0` in `/etc/ai-worker.env` takes the path away. Tried in Claude Code and Codex CLI on macOS; the lines for Cursor and Gemini CLI follow their documentation and have not been tried. claude.ai and the Chat tab of Claude Desktop are off by default; `docs/INSTALL.md` shows how to let them in, and that was tried once from the Chat tab of the Claude desktop app. What a tool reads is sent to the company that makes the tool: see `SECURITY.md`.
- **Ask the board from a Telegram chat (optional, off by default).** For managers who do not write code: tap **Who is waiting**, **Cost**, **Offices**, **Team** or **Quota** in a chat with a bot, or type a short question, and get the answer from the board's numbers, in English or Vietnamese. No AI model reads the question, so it costs nothing and needs no API key. An admin approves each chat with its 8-digit code on the Admin page and chooses what it may read: each person, or team and office totals only. A separate service, `ai-worker-telegram`, talks to Telegram and may reach nothing else; the webhook itself still never connects out, and nothing is opened towards the Internet. Turn it on with `TELEGRAM_ASK=1` and a bot made for this; `docs/INSTALL.md` has the steps. What a chat reads goes through Telegram, a third party, and stays in the chat. Tried with the real Telegram by hand on macOS and on one production server, with a chat that reads totals only.

### Changed
- **The server keeps a person's numbers for longer.** One total per person per day (cost, tokens, tasks delegated, the office that day, with name and account email) now stays for up to 13 months. Before, a person's numbers were gone 30 days after their computer last sent. Tell your staff before you upgrade: the [employee notice template](docs/employee-notice.md) has the new wording.
- **First change of the database layout** (`board.db` goes from schema version 1 to 2). At its first start the new server copies `board.db` to `board.db.schema-1.bak` next to it before it changes anything, and stops without changing anything if the copy cannot be made. An older server refuses the upgraded database; going back with the copy is in [docs/OPERATIONS.md](docs/OPERATIONS.md), section 5. The server deletes the copy after 30 days.
- In a private copy of the repository, the two Windows jobs of the GitHub Actions workflow run only when a push changes what they test (installers, the connector, the menu bar app, their tests, the plugin's manifest) or when the workflow is started by hand. They were about three quarters of the minutes of each run. In a public repository they still run on every push.
- The README has a roadmap of what is done and what comes next, and its feature list names the new ways to ask the board and the use by week and month.

### Fixed
- The connector's installer no longer replaces or removes a skill in `~/.agents/skills/` that you changed after it was copied there. It keeps the skill, says so, and tells you how to get the package's version again. Skills copied by 0.32.0 carry no mark: one that differs from the package is kept on a later install, and `--uninstall` still removes them.
- On macOS, the connector's installer run without its language file printed nothing and read its messages aloud, because it took the system's `say` program for its own. It now prints them in English.

## 0.32.0 - 2026-11-16

### Added
- **Codex, Cursor and Gemini CLI on the board.** A connector (`connectors/`) lets a person who works in one of these tools show on the board: sessions open, working and waiting, per tool. It needs no Claude Code, Python or Node. The package has `INSTALL-Other-Tools-*` installers, which ask about each tool, add hooks to that tool's own settings without touching the rest, and can be undone with `--uninstall`. Waiting means the tool asked for an approval or ended its turn with a question. Tokens, cost and quota are not known for these tools. Update the server first: an older server does not name the tool and shows the person as offline after 12 minutes. Tried inside a real Codex CLI session on macOS, and tested with sample events on macOS, Ubuntu and Windows; Cursor and Gemini CLI are written from documentation, and neither they nor any tool on Windows has been tried for real yet.
- The board names the tools a person has open, next to their name, on the dashboard and the detail board.
- The connector's installer can copy 16 of the plugin's skills to `~/.agents/skills/`, which Codex, Cursor and Gemini CLI read.
- `python3 server/demo.py` prints its send key, so a connector can be tried against the demo, and three of its sample people use another tool.

### Changed
- A report from the connector counts for 2 hours instead of 12 minutes, because the connector sends only when something happens in a tool; its "working" is believed for 30 minutes, because a turn that fails sends no event.
- `AGENTS.md` lists ten checks: the connector tests are new.
- The README says the plugin also runs in the Claude Code extension for VS Code: checked on macOS, where the commands and skills load the same as in the desktop app.

## 0.31.17 - 2026-11-16

### Changed
- The README opens with what sets AI Worker apart: the live board of who is waiting, and a rollout a whole office can use without a Team or Enterprise plan or device management. A new section says when another tool fits better.

## 0.31.16 - 2026-11-15

### Changed
- `AGENTS.md` lists all nine checks to run before a change is done. `packaging/check-clean.sh` is explained apart from them: it belongs on what gets published.

## 0.31.15 - 2026-11-15

### Fixed
- A skill written by `make-skill` now tells Claude to answer in the language you write in: one made from a Vietnamese procedure could open its answer in English.
- Switching a draft on moves it out of the drafts folder instead of leaving a second copy there.

## 0.31.14 - 2026-11-15

### Added
- `make-skill` checks its own draft before showing it: the description says when to use the skill and, where it could be taken for another job, what it is not for; each step says where, what and what the right result looks like; no secret or personal data got in; the file stays short. What it cannot fix without guessing it asks you about.

### Changed
- Six skills say more clearly when they are the right one, so Claude picks them at the right moment. `browser-testing-with-devtools` and `lesson-generator` now say when to use them. `domain-modeling`, `draw-flow`, `qa-site` and `ui-ux-pro-max` now say what they are not for and which skill to use instead. Only the descriptions changed, not what the skills do.

## 0.31.13 - 2026-11-14

### Added
- A new session is told which handoff notes are on the computer: the names and dates of the newest five. Asked to continue one of those tasks, Claude reads its note first; asked only to continue, it asks which one. The plugin gives names and dates, never a note's text, and adds nothing on a computer with no note.

### Changed
- A command that destroys work now carries the plain-words warning as its description, so the app's permission box shows it: the box shows a command's own description, not the reason a plugin gives. What Claude wrote for the command follows the warning.

## 0.31.12 - 2026-11-14

### Fixed
- The question before a command that destroys work did not appear in the app's automatic permission mode: the command went to the automatic approval, which let it run. The plugin now marks such a command as one a person must answer, in the app's own permission box, in every mode; where nobody can be asked it is refused.

## 0.31.11 - 2026-11-14

### Added
- A question before a shell command that destroys work. When Claude is about to delete a whole folder, run `git reset --hard`, `git push --force` or `git clean`, and a rule or the permission mode already lets the command through, the plugin asks the person in plain words first; on a no, or with nobody to answer, the command does not run. Build folders and the system's temporary folder are left alone. `"askBeforeDestructive": false` in `config.js` turns it off. It reads the command as text, so it is a safety net for the common forms, not a guarantee.

### Changed
- Text for ChatGPT or Gemini is now asked about in every permission mode. A mode that asks nothing used to let it go out without a question; only an allow rule the person set for that assistant skips the question now.

## 0.31.10 - 2026-11-14

### Added
- When a long conversation is compacted, the plugin also tells the summarizer what the work depends on: the user's standing instructions, the decisions and their reasons, what failed, what is still open, and the exact file paths, commands and versions. After an automatic compaction a note tells the person that nothing broke and no new session is needed.

## 0.31.9 - 2026-11-14

### Added
- A new everyday skill, `/ai-worker:make-skill`: it turns a document or a team's procedure into a new skill for Claude. It refuses a source that holds a password, a key or a token, leaves personal data out, keeps the skill as a draft on the computer, and switches it on only after the user says yes.

### Changed
- `/update` on a network the company server refuses now says so in plain words: the network is not allowed, nothing is wrong with the computer, try again at the office or ask the admin to add the network. It used to say "server returned 403". The code is still shown at the end, for the admin.

## 0.31.8 - 2026-11-14

### Added
- `/ai-worker:voice` helps people speak instead of typing, in Vietnamese too. It opens the settings page of the computer's own dictation (Keyboard on a Mac, Language & region on Windows) and shows the few steps to do once. Telling Claude "I want to speak instead of typing" points to the same command. The plugin changes no setting and brings no speech recognition of its own.

### Changed
- The example question shown after `/ai-worker:board` pairs, and in the README and the user guide, is now "who is waiting longest right now?". The board knows who is waiting at this moment and for how long, not who waited earlier in the day.

## 0.31.7 - 2026-11-14

### Added
- A manager can ask Claude about the team in their own words. `/ai-worker:board` pairs the manager's computer with the company board: it shows an 8-digit code, an admin approves it on the Admin page, and from then on Claude reads the board when asked ("who has waited longest today?"). Claude gets what a wall screen shows, names, states, cost and quota, never an email or an IP. `/ai-worker:board unpair` or **Revoke** on the Admin page ends it. A computer that is not paired carries no such tool.
- The Admin page names a Claude plugin apart from TV screens and browser extensions, in the pairing request, the list and the audit log.

### Changed
- The rule for the `planner` assistant: a session that already runs on Opus or a stronger model plans a big decision itself, instead of asking whether to call the planner.

## 0.31.6 - 2026-11-14

### Changed
- A branch appears on the board's map and in its list once a computer there has sent numbers. A branch that is only declared, with no computer yet, stays on the Admin page and off the map and the wall display.
- On a map with many offices there is not room for every office's label. A label is now shown only where it covers no other label, no pin, not the list of offices and not the map's own buttons, and stays near its pin; the others are hidden and their pins still open the office. Offices near their quota limit or with people waiting are given their label first. With a few offices nothing changes.

## 0.31.5 - 2026-11-14

### Fixed
- On the maps, two offices close together had one pin right on top of the other, so a click always opened the same office. Pins that meet are now drawn side by side, and each opens its own office.

## 0.31.4 - 2026-11-14

### Added
- `python3 server/demo.py` shows the board on your own computer with 12 made-up people in 4 offices: no server, no install. It prints the address, the account and the 6-digit code to log in with, keeps everything in a temporary folder that is deleted when it stops, and ignores the settings of a real board. Checked on macOS, Linux and Windows; the README gives the commands for each, with the two `winget` lines that install Git and Python on Windows when they are missing.

### Changed
- The README shows nine pictures of the board in one row that scrolls sideways.

### Fixed
- On the maps, an office's label could cover another label, another office's pin or the list of offices in the corner, and could be pushed out of the frame. Each label now takes a free place beside its own pin, on the left when the right is taken, and stays inside the frame.

## 0.31.3 - 2026-11-14

### Fixed
- The flat (2D) map on the board stayed blank: it never started drawing. The 2.5D map and the globe were not affected.

### Added
- The README has a "Screens" section with seven pictures of the board, all with made-up people and numbers.

## 0.31.2 - 2026-11-13

### Fixed
- In a session with no folder chosen, asking in plain words for a whole project to be looked over made Claude ask for a folder and then stop, instead of naming the command to type. The rule now tells it to name `/ai-worker:improve-codebase-architecture` first, before asking for a folder or reading any file.

## 0.31.1 - 2026-11-13

### Changed
- Nobody has to remember a skill's name. `/ai-worker:help` now says so at the top of the skills, and marks the one skill that runs only when its name is typed (`improve-codebase-architecture`, which reads a whole project).
- When someone asks in their own words for the structure of a whole project to be looked over, Claude names the command to type instead of doing that long scan itself. A remark about one function, file or module is helped with at once, as before.

## 0.31.0 - 2026-11-13

### Changed
- The Dev pack is gone as a separate plugin: its 14 skills (testing, coding, security, UI, specifications, diagrams), the `planner` assistant and the rules for technical work now come with the plugin itself, so every computer has them and they update with it. Their names start with `ai-worker:` instead of `ai-worker-dev:`. If you had installed the Dev pack, remove the `ai-worker-dev` plugin, or its skills show twice.
- The tools some of those skills need (Node, Playwright, Chrome DevTools) are still a separate step for people who write code: `INSTALL-DevTools-Mac.command` or `INSTALL-DevTools-Windows.bat`, in the `setup` folder of the package. They replace `INSTALL-Dev-*`.
- `/ai-worker:help` reads as a short list in plain words, in two groups: skills for everyday work, and skills for people who write code or run systems.

## 0.30.0 - 2026-11-13

### Added
- `/ai-worker:help` lists what the plugin gives on the computer it runs on: its commands, the skills it ships, which helper assistants (Gemma, ChatGPT, Gemini) that computer has, whether the Dev pack is installed and whether numbers are sent to the company server. Until now nothing showed this.

## 0.29.1 - 2026-11-13

### Fixed
- In a session that has not started yet, the app did not list `/office`, `/office-pane` or `/update` and said `/office isn't a command here`, because the plugin only declared them once a session was running. They are now also declared as files, so the list shows `ai-worker:office`, `ai-worker:office-pane` and `ai-worker:update` from the start. The short names work as before.

## 0.29.0 - 2026-11-13

### Added
- The question that offers to close and reopen the Claude desktop app after `/update` now also appears on Windows and on Linux (the `claude-desktop` package for Ubuntu and Debian), not only on a Mac. On Windows the app is asked to end the way Windows asks at sign-out, because closing its window only hides it in the tray. Tried with the real app on Windows; on Linux only against a stand-in package so far, not the real app.

### Fixed
- The messages and guides told Windows users to close every window to quit the Claude app. That only hides the app in the tray: it keeps running. They now say to right-click the Claude icon next to the clock and choose Exit.

## 0.28.1 - 2026-11-13

### Changed
- Nothing new to use. This version exists so that a computer on 0.28.0 has an update to install: that is the only way to see the question that offers to reopen the Claude app.

## 0.28.0 - 2026-11-13

### Added
- After `/update` or the Update button installs a new version, the Claude desktop app on a Mac offers to close and open again on its own. It asks first, because sessions that are still working stop. Elsewhere (Windows, Linux, a terminal, an editor) the message still asks you to quit and reopen by hand.

## 0.27.2 - 2026-11-13

### Fixed
- The warning shown when a session's context is 60% or 80% full now points to `/handoff`. The plugin looked for the skill only in `~/.claude/skills/handoff`, not in its own folder where it ships, so the warning never mentioned it.

## 0.27.1 - 2026-11-12

### Fixed
- Closing a session's detail card on the board (× or Esc) keeps it closed. The session stayed selected, so the card came back with the next data refresh a few seconds later.

## 0.27.0 - 2026-11-10

### Added
- The Admin page offers the manager browser extension for Chrome and Edge. `packaging/build-extension.sh` zips `extensions/manager` into `server/menubar/`, `install.sh` copies it, and an "Extension for Chrome, Edge" button appears for admins. See [docs/INSTALL.md](docs/INSTALL.md).

### Changed
- The menu bar downloads on the Admin page are one button per system. macOS and Windows open a small menu that lists the files by name, the recommended one first (`AI-Worker.dmg`, `AI-Worker.msi`); the downloaded file keeps that name.

### Fixed
- The browser extension gets its pairing code right after "Allow". Chrome closes the extension's window while it asks for access, so the address had to be entered twice.

## 0.26.1 - 2026-11-09

### Fixed
- The 3D globe on the management board draws the land, borders and grid again, and flies down to Vietnam when it opens. The 2.5D map flies to a branch again too.
- The login page no longer stops with a script error, so pairing a wall screen with a code works again.

## 0.26.0 - 2026-11-09

### Added
- Log in with Telegram (optional, off until a bot is set up). Each person links once from the detail board after entering the 6-digit code; after that, "Log in with Telegram" goes to Telegram's login page and back. The login page loads nothing from Telegram, and the server never calls Telegram: it only checks Telegram's signature with the bot token. The name and code keep working, and admin changes still ask for the code. See [docs/INSTALL.md](docs/INSTALL.md).
- Admins see who linked Telegram on `/admin` and can unlink it; reissuing a key or moving an account to the wall role unlinks it too.

### Changed
- The installers open the office page in the browser at the end, before the first Claude Code session.
- With Telegram on, the name box on the login page no longer takes focus, so the browser's saved-password list does not open over the buttons.

## 0.25.0 - 2026-11-09

### Changed
- The server keeps its data in SQLite: `data/board.db` for the numbers and `keys/accounts.db` for accounts. At the first start it moves the old JSON files in and keeps them in `legacy-json/`. See [docs/DATA-MODEL.md](docs/DATA-MODEL.md).
- Backups use SQLite's own backup instead of copying the folder. See [docs/OPERATIONS.md](docs/OPERATIONS.md), section 4.
- The server code is split into `server/board/`; `install.sh` installs the folder.
- The public keys that sign updates live in `~/.ai-worker-keys/allowed_signers`, outside git. `build.sh` and `release.sh` copy them into the package, and `release.sh` stops when there is no key.
- The installers no longer ask to download Gemma when the model is already on the computer.

### Added
- `webhook.py --export-json <folder>` writes the data back as the old JSON files, to go back to 0.24 without losing changes.
- `webhook.py --forget-device <device id>` frees a computer to be used by someone else.
- A full document set in `docs/`: user guide, install, operations, data design, permissions, test plan, components.
- Contributing guide, code of conduct, support page, issue and pull request forms.
- CI checks the Python code with ruff and runs the server and extension tests.

### Fixed
- The plugin made computer ids starting with `may-`, which the server has refused since 0.24.0, so every send got error 400. New ids start with `device-`, and an old id keeps its ending.
- The server limit of 300 computers counts the database again; since the move to SQLite it counted nothing.

### Upgrading
Copy `/opt/ai-worker` aside first, then run `sudo bash install.sh`. The service log shows `migrated JSON files into ...` once. Change any backup job that copies `data/` to the SQLite backup command.

## 0.24.0 - 2026-11-04

The last version that kept the server data in JSON files. Changes before the repository was published are not listed.
