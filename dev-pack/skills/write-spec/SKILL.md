---
name: write-spec
description: Write or update a specification for a system, feature or tool, with a goal, what is not in scope, who uses it, numbered requirements and limits, so a reader can tell what must be built and whether it is done. Use when the user types /write-spec, asks for a spec, a specification or requirements, or wants an existing system written down before changing it. Viết hoặc cập nhật đặc tả cho một hệ thống, tính năng hay công cụ, gồm mục tiêu, ngoài phạm vi, người dùng, yêu cầu có mã và giới hạn, để người đọc biết phải làm gì và thế nào là xong. Dùng khi người dùng gõ /write-spec, nhờ viết spec, đặc tả, yêu cầu, hoặc muốn ghi lại một hệ thống đang có trước khi sửa.
---

# Write a spec

Answer and write the spec in the user's language.

Purpose: someone who was not in this conversation reads the spec and can tell what must be built, what must not, and whether each part is finished. A spec says what and why. How the parts fit together belongs in a design document; use the `draw-flow` skill for its diagrams.

## Input
`$ARGUMENTS`: what the spec is about. It describes one of two things:
- **A system that exists:** the code is the evidence. The spec records what it does today.
- **Something new:** the user is the evidence. The spec records what they want.

## How to do it
1. **Read first.** In a project, read the README, the existing documents and the code that matters. If a spec already exists, update it; do not create a second one.
2. **Fill the five sections** from what you read. Ask only what you cannot find, one question at a time, each with your best guess attached. If the user cannot yet say who it is for or why they want it, use the `interview-me` skill first.
3. **Write it in the frame below.** Anything still unknown is marked `[to confirm]`.
4. **Check it** against the checklist below and fix what fails.
5. **Save it** where the project keeps its documents, or as `docs/SPEC.md` if there is no such place. If the project keeps documents in two languages, write both.
6. **Report in a few lines:** where it was saved, how many requirements it has, every `[to confirm]`, and any code that looked like a mistake.

## The five sections
- **Goal:** one to three sentences on who gets what, and the price they refuse to pay. No features here. If the goal could describe any product, it is too vague.
- **Not in scope:** things a reader would reasonably expect but will not get, including risks the system knowingly leaves open. Say why when it is not obvious. This section stops arguments later, so it is never empty; if you find nothing, ask.
- **Who uses it:** one row per role, never a real person's name. A screen or another system that acts on its own counts as a role. "Can do" is what separates the roles.
- **What it must do:** one behavior per row.
  - The ID is `F` plus a number. IDs stay fixed: a removed requirement leaves its number unused, so other documents can keep pointing at them.
  - The wording is something a person could check and answer yes or no.
  - It says what happens, not how it is built.
  - It covers failure as well as success: what happens when a check fails or an answer never comes.
  - "Where" is the function or file you opened and saw doing this, or `not built`. Never write a location you did not open. Avoid line numbers: they go stale.
  - It records what a reader would object to losing, not every branch of the code. Past about 20 rows, merge rows that are one rule, or split the spec.
  - Code that looks like a mistake is not a requirement. Leave it out and tell the user in your report (step 6).
- **Limits:** numbers the system enforces, how long data is kept, and fixed conditions such as platform, budget or "no outside libraries". Each value comes from the code or the user. Do not repeat what a requirement already says.

## Frame
```markdown
# <Name>: specification

<One line: what this is. One line: which wins if this document and the code disagree. For a system that exists, the code shows what runs today and the document gets corrected. For something new, the spec wins until the user changes it.>

## Goal

<Who gets what, and the price they refuse to pay.>

## Not in scope

- <What a reader might expect, and why it is left out.>

## Who uses it

| Role | Uses | Can do |
|---|---|---|
| Admin | Dashboard, `/admin` | Change accounts and settings |
| Viewer | Dashboard, `/board` | See the numbers; change nothing |

## What it must do

| ID | Requirement | Where |
|---|---|---|
| F1 | Without a server the tool still works on one computer | `src/start.ts` |
| F2 | A failed permission question counts as no, and nothing is sent | `not built` |

## Limits

| Limit | Value |
|---|---|
| Size of one upload | 256 KB |
| Wrong logins | 5 per account in 15 minutes |
| Action log kept for | 12 months |
```

## Weak and strong requirements
| Weak | Strong | What changed |
|---|---|---|
| Logins must be secure | Five wrong codes in 15 minutes block the account | It can be tested |
| Updates are checked properly | A computer installs an update only with a valid signature | It says what must be true |
| Use a Redis cache | A repeated search answers within one second | It says what, not how |
| Handle errors well | If sending fails, the tool tries again and warns once the problem lasts | It says what the person sees |

## Checklist
- Does the goal name who benefits?
- Could each requirement be answered yes or no, by someone who did not write it?
- Does each "Where" point to something you opened, or say `not built`?
- Does each role appear in at least one requirement, and does each requirement serve a role?
- Do any two requirements contradict each other, or contradict "Not in scope"?
- Is every number traceable to the code or the user?

## Limits
- Do not invent numbers, names or dates. Mark them `[to confirm]`.
- If the code and what the user says disagree, write down both and ask which is right.
- Do not write passwords, keys, tokens, real names or internal addresses into a spec.
- Do not send a draft with internal names or figures to Gemini or ChatGPT.
- Do not change code while writing a spec. If you find a bug, report it separately.
