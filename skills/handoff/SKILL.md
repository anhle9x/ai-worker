---
name: handoff
description: Write or update the handoff note of the work in progress so the next session can continue without asking again. Use when the user types /handoff, says "handoff" or "ghi bàn giao", or when the context is nearly full and a new session is about to open. Ghi hoặc cập nhật ghi chú bàn giao của việc đang làm để phiên sau làm tiếp mà không phải hỏi lại. Dùng khi người dùng gõ /handoff, nói "ghi bàn giao", hoặc khi context sắp đầy và sắp mở phiên mới.
---

# Write a handoff note

Answer and write the note in the user's language.

Purpose: a new session (which cannot see this conversation) reads the note and carries on without asking again.

## How to do it
1. Pick the task name (kebab-case, ASCII only, for example `monthly-report`). If the user wrote a name after the command, use it.
2. The note lives at `~/.local/share/ai-worker/handoff/<task-name>.md`, on this computer. If it exists, read it and update it; do not create a duplicate. At the start of a new session, when the user says to continue a task, read that task's note first.
3. Write it in the frame below. Only summaries and decisions; do not copy documents word for word.
4. Tell the user in one line: where it was saved, and the name of the note.

## Note frame
```
# Handoff: <task name>

**Updated:** <yyyy-mm-dd>

## Where things stand
- Main file, version, how far the work has gone.

## Decided
- Each decision with a short reason, including what the user rejected, so it is not proposed again.

## Tried and failed
- What was tried, and why it failed.

## Still open
- Next steps in priority order; which ones wait for the user to do or decide.

## Constraints
- What must not be touched, and what must not be sent outside.
```

## Limits
- Do not write passwords, keys, tokens or sensitive figures; only write "it is in file X".
- Do not send the content of the note to Gemini or ChatGPT.
- Write dates in absolute form (2026-10-30), never "today" or "next week".
