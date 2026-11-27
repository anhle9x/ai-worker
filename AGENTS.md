# Notes for AI coding agents

Read this before changing anything in this repository. People read [CONTRIBUTING.md](CONTRIBUTING.md); this file is the short version for agents.

## What this is

A Claude Code plugin (`.claude-plugin/`, `hooks/`, `skills/`, `web/`) on each employee's computer, a connector for Codex, Cursor and Gemini CLI that needs no Claude Code (`connectors/`), a dashboard server (`server/`) on one Linux machine, and an optional receiver in Go for large organisations (`receiver/`, [docs/RECEIVER.md](docs/RECEIVER.md)). Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Data: [docs/DATA-MODEL.md](docs/DATA-MODEL.md). Permissions: [docs/PERMISSIONS.md](docs/PERMISSIONS.md).

## Do not move

`.claude-plugin/`, `hooks/` and `skills/` must stay at the root: Claude Code loads the plugin from there. Installers and self-update rely on the other folder names too.

## Rules

- Every comment and docstring: an English line, then a Vietnamese line. Vietnamese only in comments, docstrings or `*.vi.*` files. Each document has `.md` and `.vi.md`.
- The receiver in `receiver/` uses the Go standard library only. Its cleaning copies `server/board/devices.py`: change both, then run `python3 tests/contract/ingest-v2/make_cases.py` if a case changed.
- The server uses the Python standard library only (Python 3.8+). Data is in SQLite through `server/board/db.py`; a schema change is a new step, never an edit of a shipped one. SQL takes values only as parameters.
- A new server path goes into the route table in `server/webhook.py` and the permission table in `server/test_webhook.py`.
- `web/ops.js`, `ops.css`, `ops3d.js`, `i18n.js`, `ops.vi.js` must equal their copies in `server/static/`.
- `server/board/costreport.py`, `labels.json`, `prices.json` must equal `skills/ai-cost-report/report.py`, `labels.json`, `prices.json` (`server/test_projects.py` checks).
- Never commit real names, emails, IPs, domains, keys or company numbers. Use `board.example.com` and `example.com`.
- The employee's computer never sends chat content, prompts, file names or project names. Keep it that way.
- `connectors/ai-worker-hook.sh` and `connectors/ai-worker-hook.ps1` do the same thing, as do `install.sh` and `install.ps1`: change both. The hook runs with sh, awk, sed, grep and curl or wget only: no Python, no Node.

## Checks

Run all twelve before calling a change done. CI runs the same checks, except that of the server's tests it runs only the modules named in `.github/workflows/test-install.yml`: the whole `cd server && python3 -m unittest` runs only on your computer, so run it there.

```bash
claude plugin test .
```

```bash
cd server && python3 -m unittest
```

```bash
python3 tests/connectors/test_connectors.py
```

```bash
python3 tests/appmeter/test_appmeter.py
```

```bash
node tests/extension/check-extension.js
```

```bash
node tests/check-map-layout.js
```

```bash
python3 tests/check-i18n.py
```

```bash
python3 tests/check-maps.py
```

```bash
python3 tests/check-frontmatter.py
```

```bash
bash tests/test-check-clean.sh
```

```bash
uvx ruff check .
```

```bash
cd receiver && go test ./...
```

Without `uv`, the ruff check is `pipx run ruff check .`. The last one needs Go 1.22 or later and `python3`: the receiver's tests run the Python server as the judge.

When you change `hooks/` or `tests/*.ts(x)`, also run the type check on your computer; CI cannot, since it needs the type files Claude Code writes to `.claude-plugin/types` (see `docs/ARCHITECTURE.md`):

```bash
npx -y -p typescript@5.9.3 tsc -p tsconfig.json
```

`bash packaging/check-clean.sh` is not in this list: it looks for private data in the folder it runs in, so it belongs on what gets published. In a checkout that holds your own `packaging/company.json` it reports that file, and that is expected.
