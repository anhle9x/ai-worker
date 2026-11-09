# Changelog

Changes that matter to people who install or run AI Worker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Changed
- The server keeps its data in SQLite: `data/board.db` for the numbers and `keys/accounts.db` for accounts. At the first start it moves the old JSON files in and keeps them in `legacy-json/`. See [docs/DATA-MODEL.md](docs/DATA-MODEL.md).
- Backups use SQLite's own backup instead of copying the folder. See [docs/OPERATIONS.md](docs/OPERATIONS.md), section 4.
- The server code is split into `server/board/`; `install.sh` installs the folder.

### Added
- `webhook.py --export-json <folder>` writes the data back as the old JSON files, to go back to 0.24 without losing changes.
- `webhook.py --forget-device <device id>` frees a computer to be used by someone else.
- A full document set in `docs/`: user guide, install, operations, data design, permissions, test plan, components.
- Contributing guide, code of conduct, support page, issue and pull request forms.
- CI checks the Python code with ruff and runs the server and extension tests.

### Upgrading
Copy `/opt/ai-worker` aside first, then run `sudo bash install.sh`. The service log shows `migrated JSON files into ...` once. Change any backup job that copies `data/` to the SQLite backup command.

## 0.24.0 - 2026-11-04

The last version that kept the server data in JSON files. Changes before the repository was published are not listed.
