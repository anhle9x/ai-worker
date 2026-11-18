[Tiếng Việt](SECURITY.vi.md) | English <!-- i18n-allow -->

# Security policy

## Reporting a problem

Please do not open a public issue for a security problem: anyone could use it before it is fixed.

1. Report it privately on GitHub: the **Security** tab of this repository, then **Report a vulnerability**.
2. If that is not possible, send a direct message on Telegram to [t.me/anhle9x](https://t.me/anhle9x) and say you have a security report; details are then sent the way we agree.

Include what is affected (plugin, server, installer, menu bar), the version, and the steps to see the problem. Do not send real people's data.

## What happens next

- You get an answer within 7 days.
- A confirmed problem is fixed in the next release, and you are credited in the release notes unless you prefer not to be.
- Please keep it private until the fix is out, or 90 days at the latest.

## Supported versions

Only the newest release receives security fixes.

## What the project is designed against

AI Worker is designed to defend against these eight common web risks, from the OWASP Top 10 list of 2013. The code was reviewed with AI assistants and the main attacks were replayed on a test copy. No independent security firm has audited it, and no software can promise to have no flaws.

| Risk | What the product does | What remains |
|---|---|---|
| **Cross-Site Request Forgery (CSRF)** | The session cookie is `SameSite=Strict`. A request with a wrong `Origin` is refused, and admin changes also refuse a missing one. Sending numbers uses a key in a header, not a cookie | Older browsers without `SameSite` rely on the `Origin` check alone |
| **Cross-Site Scripting (XSS)** | Server pages escape values and page scripts insert data as text. Server pages send a Content-Security-Policy that allows scripts from the same site only | The policy allows inline styles. The on-computer page has no such policy; it shows only data from that computer |
| **Injection** | The server runs no shell commands, and its SQLite queries take values only as parameters, never as text joined into the query. File requests are checked against a fixed list or pattern. The plugin starts programs with a list of arguments. Text for ChatGPT goes through standard input, and Gemini is refused if it would start through a Windows `.cmd` or `.bat` launcher | A document can still try to steer a helper through the text it receives. ChatGPT runs in a read-only sandbox for this reason |
| **Broken authentication** | Each account has its own OTP key, and a code works once. Wrong tries are limited per IP and per account. Session tokens are random and expire; cookies are `HttpOnly`, and `Secure` over HTTPS. Changing accounts or TV screens needs the OTP code again | OTP is the only login factor, so keep the IP allow-list on. With Telegram login turned on, the bot token can sign anyone's login: keep it only in the server's env file |
| **Insecure direct object references** | Viewers and wall screens get one view filtered by role, with no way to ask for a record by ID. Actions on a chosen account or screen are for admins only | Viewers see everyone's numbers by design. Anyone with the shared send key can send under a name not yet tied to a device |
| **Missing function-level access control** | Every path is listed with its permission, and one gate checks them all. A path not listed is 404. A test pins what each role gets on each path. The server checks, it does not just hide buttons | A new path must be added to that table by whoever writes it |
| **Security misconfiguration** | There are no default accounts or keys, and the server will not start without `INGEST_KEY`. Behind Caddy it listens only inside the server. The service runs as its own user with limited rights; key and data files are private to it | You must set your own IP list, turn on HTTPS and keep the number of sudo users small |
| **Sensitive data exposure** | Chat content, file names and project names are never sent. Wall screens get no emails or internal IPs. TV sessions are stored as hashes, the log holds no keys, and files that look like secrets are recorded by name only. Totals per person per day (cost, tokens, tasks delegated) are shown to admins and viewers only | Without HTTPS the numbers travel unencrypted. The totals per day stay for up to 13 months with the person's name and account email, far longer than the 30 days of a computer's own row: tell staff, and delete a person's rows with `webhook.py --forget-usage` when that is needed. A copy of the database made before a schema upgrade sits next to it for 30 days. OTP keys sit unencrypted on the server, readable by the service and by sudo users. The install package holds the send key |

### What the plugin stops on the computer

- **Secrets leaving:** text for ChatGPT or Gemini that holds what looks like a key, a token or a password is not sent, whatever the permission mode. The check knows the shapes of common keys and `.env`-style settings; a secret with no recognisable shape can still pass.
- **Secrets in git:** before Claude runs `git commit`, the lines it adds are read the same way, and a commit that holds one is put to the person. A commit the person makes outside Claude is not checked.
- **Risky commands:** deleting a whole folder, `git reset --hard`, `git push --force`, `git clean`, running a downloaded script at once, turning off Gatekeeper, writing straight to a disk and `chmod 777` are put to the person in every mode.
- **Pages that try to steer Claude:** text from the web, a search or a browser that gives orders to an AI is flagged to Claude and to the person. It is found by wording, so a page that says the same thing differently passes; the result is never withheld.

On the server, the Admin page shows how many of these happened across the team in the last 7 days (counts only), points out keys for AI tools unused for 30 days, and checks that no line of the audit log was changed or taken out by hand. Each line carries the fingerprint of the one before; someone who can rewrite the whole database and its last fingerprint is not caught, so note the fingerprint shown on the page now and then.

### The connector for Codex, Cursor and Gemini CLI

The connector (`connectors/`) is optional and separate from the plugin. What to know before allowing it:

- **It runs as a hook inside another company's tool,** with the rights of the person who uses that tool. Each tool hands the hook its event, and that event holds the prompt or the answer. The hook reads the session id and whether the last message ends with a question mark; it stores and sends neither the prompt nor the answer. The whole hook is one short file you can read: `connectors/ai-worker-hook.sh` (Windows: `ai-worker-hook.ps1`).
- **It holds a second copy of the send key,** in `~/.local/share/ai-worker/connector/config`. On macOS and Linux only that account can read the file; on Windows it sits in the person's profile folder. The key gives the same rights as the plugin's copy: sending numbers, nothing else.
- **It changes other tools' settings.** The installer adds hooks to `~/.codex`, `~/.cursor` and `~/.gemini`, keeps a copy of each file it changes, and `--uninstall` takes the hooks out again. Codex runs them only after the person has reviewed and trusted them with `/hooks`; the installer never skips that step.
- **It has no signed update.** The connector does not update itself; a new version arrives only when someone runs its installer again from a package they trust.
- **What remains:** a person can send false counts under their own name, as with the plugin. Cursor, Gemini CLI and the Windows files have not been tried in the real tools yet.

### The MCP endpoint

The server has one read-only path, `/mcp`, where an AI tool that holds a key reads the board's numbers. What to know before approving a key:

- **It gives what a wall screen gets and nothing more:** names, states, cost and quota. Emails, IPs and device ids never go out, whatever the request asks.
- **Each key is approved by an admin,** with the 8-digit code flow of the TV screens and the OTP code entered again. The admin chooses whether the key reads each person or team and office totals only. The server stores a hash of the key; the Admin page shows its first characters.
- **A key opens `/mcp` only, and no other key opens `/mcp`:** not a wall screen's, an extension's or a plugin's key, the send key or a login session. Cookies are ignored there, and a request from a web page on another site is refused.
- **Limits:** 120 requests per key in 10 minutes, at most 50 keys, a message of at most 16 KB. Wrong keys count as probing, so an IP that keeps trying is blocked for 15 minutes. A key lapses after 30 days without use and after 1 year at most; revoking stops it at once, and a later use of it is written to the log.
- **Each read is logged for 3 months:** which key, which tool, which IP. The question a person asked never reaches the server.
- **The IP allow-list covers it.** With the Caddy template, `/mcp` answers only inside your networks. `MCP=0` takes the path away.

What remains:

- **What a tool reads goes to the company that makes the tool,** as part of the person's question: names and costs of colleagues, unless the key reads totals only. With totals, offices of fewer than 3 people share one row, but a team or a leftover group of one or two people still shows through the totals.
- **The key sits unencrypted on the person's computer,** in an environment variable or in the tool's settings file. Whoever copies it can read the same numbers from inside your networks until it is revoked.
- **The code says nothing about who is asking.** Someone on your network can ask for a code and try to get an admin to approve it. The approval card names the kind of key and the asking IP; approve only a code the person read to you themselves.
- **A name is text a staff member typed.** It could be written to steer the AI tool of whoever asks, and some of those tools can run commands. The server keeps only letters, digits and a few marks in a name, cuts it to 40 characters and tells the tool that names are data. That lowers the risk; it does not remove it.
- **Without HTTPS the key travels unencrypted,** like the rest of the board.
- **claude.ai and the Chat tab of Claude Desktop are off by default.** They connect from Anthropic's servers, so the allow-list refuses them. [docs/INSTALL.md](docs/INSTALL.md) shows how to let Anthropic's addresses reach `/mcp` and nothing else. Once you do, `/mcp` answers anyone who comes through claude.ai, and the key is the only thing in the way. Tried once, from the Chat tab of the Claude desktop app: it worked, and Claude called the tool without asking the person first, so the key's scope is what decides what goes out.
- **Tried in three places, all on macOS:** Claude Code 2.1.318, Codex CLI 0.164.0, and the Chat tab of the Claude desktop app through a claude.ai connector. Cursor, Gemini CLI, and every tool on Windows and Linux have not been tried yet.

### Asking the board from Telegram

Off unless the server's owner sets `TELEGRAM_ASK=1`. Then a second service, the bot process, asks Telegram for messages, and a person in a chat an admin approved gets answers from the board. What to know before turning it on:

- **This is the one part of the server that connects out, and only to Telegram.** The webhook still never does. The bot process runs under its own user, may reach only this machine, its DNS servers and Telegram's networks, and holds two secrets: the bot's token and the key of the one path it calls. It holds no database, no OTP key and no send key, and keeps nothing on disk.
- **The bot process decides nothing.** It hands each message to the webhook on the same machine; the webhook decides whether the chat is approved, what it may read and how often it may ask. That path, `/bot/telegram`, answers only a direct call from the same machine that shows the key: a request that came through the proxy gets 404, and a login or any other key gets 401.
- **Each chat is approved by an admin,** with the 8-digit code flow of the TV screens and the OTP code entered again. The card shows the person's Telegram name and number, and the board account that Telegram is linked to, if any. The admin chooses whether the chat reads each person or totals only. Only private chats are answered: in a group the bot says nothing and leaves.
- **It gives what a wall screen gets and nothing more,** as a few lines of text. No AI model reads the question. Emails, IPs and device ids never go out.
- **What stands for a chat is the person's Telegram number, which is no secret.** So it is taken on that one path only. It opens no page, no extension path and not `/mcp`, and the public pairing paths can neither take nor cancel a chat's code.
- **Limits:** 50 chats, 10 waiting for approval, 20 messages per chat in 10 minutes. A chat that is not approved is told so once an hour and otherwise gets no answer. A chat lapses after 30 days without use and after 1 year at most; `/stop` in the chat or Revoke on the Admin page ends it at once.
- **Each answer with numbers is logged for 3 months:** which chat and which command. The words a person typed are neither stored nor logged, by the webhook or by the bot process.

What remains:

- **Names and costs go through Telegram and stay in the chat.** Telegram is a third party. A chat with a bot is not end-to-end encrypted, and it shows on every device where the person is logged in to Telegram. A chat that reads totals only keeps people's names out of it; a team or a leftover group of one or two people still shows through the totals.
- **The phone.** Answers are sent so that Telegram's apps refuse to forward or save them, and the first line never names a person. On the phone this was tried on, Telegram's app refused a screenshot as well; that is how Telegram behaved on that device, not a promise. On a computer the screen can be captured, any screen can be photographed, and an unlocked phone in someone else's hands shows the chat.
- **The bot's token.** Whoever holds it can read what people send the bot from then on, and write to them in the bot's name, for example to ask for a login code; the bot itself never asks for one. They cannot read the board, because the server answers only approved chats and Telegram does not let a bot read back what it sent. The Admin page says when another program reads the same bot. Use a bot made for this, not the bot for logging in, whose token can sign a login.
- **Anyone can write to the bot:** its name is public. A stranger gets a pairing code and nothing else. Approve only a code the person read to you themselves.
- **A name is text a staff member typed.** In a chat it is only shown, never read by a model. The marks Telegram turns into links or commands are taken out of names. That makes a planted link harder to write, not impossible.
- **Telegram's networks may change.** The allow-list is Telegram's published list as read on 2026-11-16. If Telegram moves, the bot stops reaching it until you update `TELEGRAM_NETS`. `any` removes the limit, and that protection with it.
- **Used on one production server so far,** since 2026-11-17, with a chat that reads totals only. A chat that reads each person was tried there once, on 2026-11-17: the cost answer named the person with the highest cost and gave each office its own line. The waiting and quota answers with names in them were not seen, because nobody was waiting and nobody was near a quota.

### The window inside Telegram and the alerts

Both come on top of asking from Telegram, and both are off until turned on: the window with `TELEGRAM_APP=1` and an admin allowing each chat, the alerts by each chat itself (`/alerts`).

- **The window is a page of the board, under `/tg/`.** The person's phone or computer reaches the server itself over HTTPS; Telegram does not carry the numbers. With the template's Caddy block only the office networks get in. Letting `/tg/` in from anywhere is a separate decision that this project does not make for you.
- **What Telegram signs is checked before anything else.** Telegram puts a few signed fields after the `#` of the address, so they reach no log. The webhook checks them with a key the installer derives from the bot token: it checks a signature and cannot drive the bot. Fields older than 5 minutes are refused, and a wrong signature counts as probing.
- **Sessions live in memory only:** a random string kept as a hash, 1 hour after last use and 12 hours at most, 3 per chat, no cookie. The chat is found again on every call, so revoking it, `/stop`, or **Stop the window** ends every open window at once.
- **Only a chat an admin allows, one by one,** with the OTP code entered again. A chat that reads each person sees what a wall screen sees; a chat that reads totals only gets the team's counts and costs, added up on the server, and no name ever reaches it.
- **No script from another site runs in the window.** It does not load Telegram's script from telegram.org, and the page's `script-src 'self'` stays as it is.
- **The alerts are the bot writing without being asked.** Names and minutes in them go through Telegram and stay in the chat, like the answers. The first line names nobody, a chat that reads totals only gets the count alone, and a chat gets at most one message every 5 minutes, 6 an hour and 30 a day, none at night. Each is logged with how many people, never who.
- **Tried on one production server,** on 2026-11-18: the window on Android and Telegram Desktop, on the office network. Not yet on an iPhone, and the alerts not yet on a real chat.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
