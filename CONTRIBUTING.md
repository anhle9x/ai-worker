[Tiếng Việt](CONTRIBUTING.vi.md) | English <!-- i18n-allow -->

# Contributing

Thank you for helping. Bug reports, fixes, translations and documents are all welcome.

## Before you start

- **A bug:** open an issue with the form, and say the version and where it runs (plugin, server, installer, menu bar, extension).
- **A security problem:** do not open an issue; see [SECURITY.md](SECURITY.md).
- **A larger change:** open an issue first, so we agree on the approach before you write code.

## Rules of this repository

- **Two languages.** Code, comments and messages are in English, and every comment and docstring has an English line followed by a Vietnamese line. Vietnamese text lives only in comments, docstrings or `*.vi.*` files. Every document has an English `.md` and a Vietnamese `.vi.md`.
- **No outside library on the server.** The server uses Python's standard library only, Python 3.8 or newer. The optional receiver in `receiver/` uses Go's standard library only, and its cleaning copies the server's: change both ([docs/RECEIVER.md](docs/RECEIVER.md)).
- **No private data.** Never commit real names, emails, addresses, keys or company numbers. `packaging/check-clean.sh` checks this.
- **Every server path has a permission.** A new path goes into the route table in `server/webhook.py` and into the permission table in `server/test_webhook.py`.
- **A schema change is a new step.** Add a step to `DATA_STEPS` or `KEYS_STEPS` in `server/board/db.py`; never edit a step that has shipped.

## Checks to run

Run all twelve from the repository root before sending a change. GitHub Actions runs the same ones.

```bash
claude plugin test .
cd server && python3 -m unittest
```

```bash
python3 tests/connectors/test_connectors.py
python3 tests/appmeter/test_appmeter.py
node tests/extension/check-extension.js
node tests/check-map-layout.js
python3 tests/check-i18n.py
python3 tests/check-maps.py
python3 tests/check-frontmatter.py
bash tests/test-check-clean.sh
uvx ruff check .
```

```bash
cd receiver && go test ./...
```

The first block ends inside `server/`, so go back to the repository root before the second one. Without `uv`, the ruff check is `pipx run ruff check .`. The last block needs Go 1.22 or later and `python3`, and ends inside `receiver/`. `python3 tests/check-i18n.py --comments` also checks that every comment has an English line followed by a Vietnamese line.

`bash packaging/check-clean.sh` is not in this list: it looks for private data in the folder it runs in, so it belongs on what gets published. In a checkout that holds your own `packaging/company.json` it reports that file, and that is expected.

`web/ops.js`, `ops.css`, `ops3d.js` (and `i18n.js`, `ops.vi.js`) must be identical to the copies in `server/static/`; the packaging script checks this. `server/board/costreport.py`, `labels.json` and `prices.json` must be identical to `skills/ai-cost-report/report.py`, `labels.json` and `prices.json`; `server/test_projects.py` checks this. After editing `web/`, type `/reload-plugins` and then `/office` so the on-computer page picks up the new version.

How it is designed, with its specification, flow diagrams and the languages each part uses: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Bundled libraries and skills: see [THIRD-PARTY.md](THIRD-PARTY.md).

GitHub Actions runs every check on Ubuntu and Windows; what each one covers is in [docs/TEST-PLAN.md](docs/TEST-PLAN.md).

## Pull requests

Keep one change per pull request, fill in the template, and say how you checked it. By sending a pull request you agree that your work is published under the [MIT License](LICENSE).
