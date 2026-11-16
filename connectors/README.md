[Tiếng Việt](README.vi.md) | English <!-- i18n-allow -->

# Connector for Codex, Cursor and Gemini CLI

Lets a person who works in Codex, Cursor or Gemini CLI show on the AI Worker board: sessions open, working and waiting, per tool. It does not need Claude Code or the AI Worker plugin.

Installing and removing it: [docs/INSTALL.md](../docs/INSTALL.md#codex-cursor-and-gemini-cli-on-the-board). This page is for people who want to read what it does, or write a connector for another tool.

## Files

| File | Does |
|---|---|
| `ai-worker-hook.sh` | The hook on macOS and Linux. Needs sh, awk, sed, grep and curl or wget |
| `ai-worker-hook.ps1` | The same hook on Windows, in PowerShell |
| `install.sh`, `install.ps1` | Ask which tools to show, add the hooks to each tool's settings, remove them with `--uninstall` |
| `merge-hooks.js` | Adds or removes our hooks in a JSON settings file without touching the rest. Runs with `osascript` on macOS, Node elsewhere; `install.ps1` does the same in PowerShell |

Tests: `python3 tests/connectors/test_connectors.py`.

## How far it is tested

| | State |
|---|---|
| The sh hook and installer | Pass the tests with sample events and a temporary home folder, on macOS and on Ubuntu (GitHub's test machine) |
| Codex CLI | In a real Codex CLI 0.164.0 session on macOS the start, prompt, stop, interrupt and end hooks ran, and a question from Codex showed on a sample board as waiting. The approval and tool hooks have not been seen in a real session yet |
| Cursor, Gemini CLI | Written from their documentation; not tried inside the real tools |
| Windows (`.ps1`) | Pass the same tests on Windows (GitHub's test machine, Windows PowerShell); not tried inside a real tool on Windows |

If you try one of the untested rows, please open an issue with what you saw, working or not.

## What each tool's event means here

The tool runs `ai-worker-hook.sh <tool> <event>` and hands it the event as JSON on standard input.

| Ours | Codex | Gemini CLI | Cursor | The session becomes |
|---|---|---|---|---|
| `start` | `SessionStart` | `SessionStart` | `sessionStart` | idle, if it is new |
| `prompt` | `UserPromptSubmit` | `BeforeAgent` | `beforeSubmitPrompt` | working |
| `ask` | `PermissionRequest` | `Notification` | none | waiting: the tool wants an approval |
| `tool` | `PostToolUse` | `AfterTool` | none | working again, if it was waiting for an approval |
| `reply` | none | none | `afterAgentResponse` | unchanged; notes whether the reply ends with a question mark |
| `stop` | `Stop`, `Interrupt` | `AfterAgent` | `stop` | waiting if the last message ends with a question mark, else idle |
| `end` | `SessionEnd` | `SessionEnd` | `sessionEnd` | removed |

From the event the hook reads the session id (`session_id`, or `conversation_id` in Cursor) and, for `reply` and `stop`, whether the last message (`last_assistant_message`, `prompt_response`, `text`) ends with a question mark. It answers the tool before it does anything else: nothing for Codex, `{}` for Gemini CLI and Cursor, `{"continue":true}` for Cursor's `beforeSubmitPrompt`. It never blocks or changes what the tool does. Codex sends no `Stop` when the person cuts a turn short with Esc (seen in a real session), which is why `Interrupt` is hooked as well.

## Files on the computer

All in `~/.local/share/ai-worker/connector/`:

| File | Holds |
|---|---|
| `config` | `url`, `key` (the send key), `name`, `account`; readable by that account only |
| `device` | The random id `device-...` of this connector |
| `sessions` | One line per open session: tool, session id, state, time of its last event, a mark |
| `sent`, `last-error` | When the board last accepted a report, or how it last refused one |
| `report.json` | The last report sent |

## The report

One `POST <board>/ingest` with `Authorization: Bearer <send key>` and this JSON body, sent when the counts change and at most every 5 minutes while they do not:

```json
{
  "v": 1,
  "device": "device-k3v9x1q7m2p8c4zt",
  "name": "An",
  "account": "an@example.com",
  "updatedAt": 1794816190000,
  "openSessions": 2,
  "working": 1,
  "waiting": 1,
  "tools": {
    "codex": { "openSessions": 1, "working": 0, "waiting": 1 },
    "cursor": { "openSessions": 1, "working": 1, "waiting": 0 }
  }
}
```

| Field | Rule |
|---|---|
| `v` | Always `1` |
| `device` | `device-` and 1 to 40 of `a-z0-9`. The server ties it to the first `name` and `account` it was sent with; another name later is refused with 409 |
| `name`, `account` | As the board shows the person. Use the same pair as the AI Worker plugin on that computer, or the person shows as two rows |
| `updatedAt` | Time of the report, in milliseconds |
| `tools` | The table that marks a connector report. Keys the server knows: `codex`, `cursor`, `gemini`; any other key is dropped. `{}` means no session is open |
| `openSessions`, `working`, `waiting` | The totals, for a server older than this feature. A current server adds them up from `tools` itself |

The server counts a report for 2 hours after `updatedAt`, and its `working` for 30 minutes: a turn that fails sends no event, so send again while work goes on. Answers: 200 accepted; 400 not a report; 401 wrong key; 409 the device belongs to another name; 413 too large; 429 too many sends or new devices from this address; 507 the device limit is reached.

## A connector for another tool

The server takes tool names from a fixed list, `CONNECTOR_TOOLS` in `server/board/settings.py`, so a new tool is a change in three places: that list, the names in `TOOL_NAMES` (`server/board/pages.py` and `server/static/ops.js`), and the event table in `install.sh` and `install.ps1`. Keep the rule that makes this safe to install: send counts only, never the prompt, the answer, a file name, a folder or a project name.
