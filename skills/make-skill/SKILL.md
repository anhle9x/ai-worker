---
name: make-skill
description: Turn a document, a procedure or a way of working the user describes into a new skill for Claude, as a draft the user reviews before it is switched on. Use when the user types /make-skill, or asks to make a skill, to teach Claude a procedure of their team, or to turn a document into a skill. Biến một tài liệu, một quy trình hay một cách làm việc mà người dùng mô tả thành một skill mới cho Claude, dưới dạng bản nháp để người dùng xem lại trước khi bật. Dùng khi người dùng gõ /make-skill, nhờ tạo skill, nhờ dạy Claude quy trình của phòng mình, hoặc nhờ biến một tài liệu thành skill.
---

# Make a skill from a document

Answer the user in their language. Write the new skill in the language of its source: a Vietnamese procedure gives a Vietnamese skill.

A skill is a short instruction file that Claude follows each time a certain kind of job comes up, so the job is done the same way without the user explaining it again. This skill writes one from what the user gives, keeps it as a draft, and switches it on only when the user says yes.

## Steps

1. **Get the source.** It is a file the user names, text they pasted, or their own description of how the job is done. If there is none, ask one question: which job should Claude do the same way every time? Read the whole source before writing anything.

2. **Check the source for secrets before anything else.** Look for:
   - passwords, and lines such as `PASSWORD=`, `SECRET=`, `TOKEN=`, `API_KEY=` followed by a value;
   - keys and tokens: a long random string, or one that starts with `sk-`, `ghp_`, `xox`, `AKIA`, or follows the word `Bearer`;
   - a private key block (`-----BEGIN ... PRIVATE KEY-----`), the content of a `.env` file, an address with a password inside it (`user:password@host`).

   If you find one, stop. Tell the user where it is (the file and the line, never the value itself) and ask whether to leave that part out. A secret never goes into a skill, not even shortened.

3. **Leave personal data out.** A skill names roles, not people: "the chief accountant", not a name with a phone number, an ID number or a salary. Keep the name of a system or a form when the job needs it. Say in your summary what you left out.

4. **Decide whether this is a skill.** It is one when the job comes back again and again, has steps or rules, and has a clear point where it is done. If the source is a single fact (a deadline, a phone number), say that a skill is the wrong place for it and stop. If it holds several different jobs, name them, ask which one to start with, and make that one only.

5. **Pick a name.** Lower case, plain ASCII letters with hyphens, two to four words, starting with what it does: `monthly-expense-report`, `reply-supplier-email`. Look in the `skills` folder inside the `.claude` folder of the user's home folder: if the name is taken there, pick another or ask.

6. **Write the draft** to `~/.local/share/ai-worker/skill-drafts/<name>/SKILL.md`. A draft there is not active: Claude does not use it yet. Use this frame:

   ```
   ---
   name: <name>
   description: "<What it does, in one sentence>. Use when <the words people here really say when they need it>."
   ---

   # <Title>

   ## When to use it, and when not

   ## Steps
   1. <Where to do it, what to do, what the right result looks like>

   ## Rules
   - <Each must and must-not from the source>

   ## Result
   <What comes out: its format, its file name, where it is saved>

   ## Example
   <One short made-up example, with no real name or figure>

   ## Source
   Written from <file name or "the user's description"> on <yyyy-mm-dd>. Review it when the source changes.
   ```

   Rules for the draft:
   - Write the whole skill in the language of the source, the headings of the frame and the words "Use when" too. Only the `name` stays plain ASCII.
   - Only what the source says. Do not invent a step, a number or a rule. Where the source leaves a gap, do not fill it: list it as a question for the user.
   - The description decides when Claude picks the skill, so put in it the words the user's team really uses, in their language. Keep it inside double quotes.
   - Short beats complete: under 150 lines. Do not copy the source word for word.

7. **Show the user the draft**, in this order: its name, when it will be used, the steps as a short list, what you left out and why, and your open questions. Then ask one question with these choices: switch it on, change something, keep it as a draft.

8. **Switch it on only after a clear yes.** Copy the draft folder to `skills/<name>/` inside the `.claude` folder of the user's home folder. If a skill of that name is already there, ask before replacing it. Then tell the user:
   - it works in new sessions: open a new session if this one does not show it;
   - how to call it: type `/<name>`, or just ask for the job in their own words;
   - how to remove it: delete that folder.

9. **Say where it lives.** The skill is on this computer only. To give it to the whole team, the user sends the folder to their admin, who can put it in the company package. Do not upload or send it anywhere yourself.

## Limits

- Never switch a skill on, and never replace an existing one, without the user saying yes to that exact step.
- Never put a password, a key, a token or personal data in a skill, and never repeat one in your answer.
- Do not send the source or the draft to Gemini or ChatGPT.
- Do not change the skills that came with the plugin.
