[Tiếng Việt](employee-notice.vi.md) | English <!-- i18n-allow -->

# Employee notice template

Fill in the parts in [brackets], have your legal or HR contact review it, and give it to staff **before** installing AI Worker on their computers. This is a template, not legal advice.

---

**Subject: AI usage dashboard on company computers**

From [date], [company] will install the AI Worker plugin for Claude Code on [which computers or teams].

**Why:** to [see how AI tools are used and what they cost, plan quotas, ...].

**What is sent to the company server:**
- Your name, your Claude account email, a computer ID, and your computer's internal and public IP address; the server keeps the internal addresses each computer used in the last 30 days
- The email you typed when the plugin was installed, if you typed one
- A hardware mark: your computer's own id after a one-way hash, which cannot be turned back into the id. It only tells the board that a reinstalled plugin is the same computer, and is never shown
- Number of open sessions, and whether Claude is working or waiting for you
- [Only if the connector for Codex, Cursor and Gemini CLI is installed] For each of those tools: how many sessions are open, working or waiting for you
- Tokens used, estimated cost, number of tasks given to each assistant, and quota used
- The AI models and assistants in use, which kinds of helper assistants Claude is running and how many, and the plugin version

**What is never sent:** chat content, prompts, file names or file contents.

**Who can see it:** [admin names or roles] see everything. [Viewer roles] see [what they see]. Wall screens do not show email or IP addresses. Totals by week and by month are shown to [admins and viewers] only. [Only if asking the board from Telegram is on] Managers whose Telegram chat an admin approved can read [team and office totals / each person's name as a wall screen shows it, state, minutes waiting, cost and quota] in that chat; those answers pass through Telegram's servers, a company outside [company]. [Only if the window inside Telegram is on] The same managers can open the board's small window inside Telegram, on the company network; those numbers go from the company server to their phone or computer, not through Telegram. [Only if the bot's alerts are on] A manager whose chat turned them on also gets a message when someone has waited longer than a few minutes for Claude, naming who [if the chat reads each person]; these messages pass through Telegram too.

**How long it is kept:** the server keeps the latest numbers of each computer, with tokens and cost per hour for the last 8 days, until 30 days after that computer last sent. From those it adds up one total per person per day (cost, tokens, tasks given to each assistant, and your office that day, next to your name and account email) and keeps these daily totals for up to 13 months, so that use can be compared by week, by month and with the same month a year before. The log of logins and admin actions is kept for 12 months. Backup copies the company makes follow [backup retention period]. [Anything your company keeps for longer or shorter.]

**Where it is stored:** [server, location]. The data is [not] shared with [anyone outside the company].

**How it is used:** [for example: for planning and cost only, not for performance review]. If this changes, you will be told first.

**Questions, or to see or correct your data:** contact [name, email].

---
