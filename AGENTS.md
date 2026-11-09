# Notes for AI coding agents

Read this before changing anything in this repository. People read [CONTRIBUTING.md](CONTRIBUTING.md); this file is the short version for agents.

## What this is

A Claude Code plugin (`.claude-plugin/`, `hooks/`, `skills/`, `web/`) on each employee's computer, and a dashboard server (`server/`) on one Linux machine. Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Data: [docs/DATA-MODEL.md](docs/DATA-MODEL.md). Permissions: [docs/PERMISSIONS.md](docs/PERMISSIONS.md).

## Do not move

`.claude-plugin/`, `hooks/` and `skills/` must stay at the root: Claude Code loads the plugin from there. Installers and self-update rely on the other folder names too.

## Rules

- Every comment and docstring: an English line, then a Vietnamese line. Vietnamese only in comments, docstrings or `*.vi.*` files. Each document has `.md` and `.vi.md`.
- The server uses the Python standard library only (Python 3.8+). Data is in SQLite through `server/board/db.py`; a schema change is a new step, never an edit of a shipped one. SQL takes values only as parameters.
- A new server path goes into the route table in `server/webhook.py` and the permission table in `server/test_webhook.py`.
- `web/ops.js`, `ops.css`, `ops3d.js`, `i18n.js`, `ops.vi.js` must equal their copies in `server/static/`.
- Never commit real names, emails, IPs, domains, keys or company numbers. Use `board.example.com` and `example.com`.
- The employee's computer never sends chat content, prompts, file names or project names. Keep it that way.

## Checks

```bash
claude plugin test .
```

```bash
cd server && python3 -m unittest test_webhook
```

```bash
node tests/extension/check-extension.js
```

```bash
python3 tests/check-i18n.py
```

```bash
bash packaging/check-clean.sh
```
