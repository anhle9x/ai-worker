# Changelog

Changes that matter to people who install or run AI Worker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## 0.27.0 - 2026-11-10

### Added
- The Admin page offers the manager browser extension for Chrome and Edge. `packaging/build-extension.sh` zips `extensions/manager` into `server/menubar/`, `install.sh` copies it, and an "Extension for Chrome, Edge" button appears for admins. See [docs/INSTALL.md](docs/INSTALL.md).

### Changed
- The menu bar downloads on the Admin page are one button per system. macOS and Windows open a small menu that lists the files by name, the recommended one first (`AI-Worker.dmg`, `AI-Worker.msi`); the downloaded file keeps that name.

### Fixed
- The browser extension gets its pairing code right after "Allow". Chrome closes the extension's window while it asks for access, so the address had to be entered twice.

## 0.26.1 - 2026-11-09

### Fixed
- The 3D globe on the management board draws the land, borders and grid again, and flies down to Vietnam when it opens. The 2.5D map flies to a branch again too.
- The login page no longer stops with a script error, so pairing a wall screen with a code works again.

## 0.26.0 - 2026-11-09

### Added
- Log in with Telegram (optional, off until a bot is set up). Each person links once from the detail board after entering the 6-digit code; after that, "Log in with Telegram" goes to Telegram's login page and back. The login page loads nothing from Telegram, and the server never calls Telegram: it only checks Telegram's signature with the bot token. The name and code keep working, and admin changes still ask for the code. See [docs/INSTALL.md](docs/INSTALL.md).
- Admins see who linked Telegram on `/admin` and can unlink it; reissuing a key or moving an account to the wall role unlinks it too.

### Changed
- The installers open the office page in the browser at the end, before the first Claude Code session.
- With Telegram on, the name box on the login page no longer takes focus, so the browser's saved-password list does not open over the buttons.

## 0.25.0 - 2026-11-09

### Changed
- The server keeps its data in SQLite: `data/board.db` for the numbers and `keys/accounts.db` for accounts. At the first start it moves the old JSON files in and keeps them in `legacy-json/`. See [docs/DATA-MODEL.md](docs/DATA-MODEL.md).
- Backups use SQLite's own backup instead of copying the folder. See [docs/OPERATIONS.md](docs/OPERATIONS.md), section 4.
- The server code is split into `server/board/`; `install.sh` installs the folder.
- The public keys that sign updates live in `~/.ai-worker-keys/allowed_signers`, outside git. `build.sh` and `release.sh` copy them into the package, and `release.sh` stops when there is no key.
- The installers no longer ask to download Gemma when the model is already on the computer.

### Added
- `webhook.py --export-json <folder>` writes the data back as the old JSON files, to go back to 0.24 without losing changes.
- `webhook.py --forget-device <device id>` frees a computer to be used by someone else.
- A full document set in `docs/`: user guide, install, operations, data design, permissions, test plan, components.
- Contributing guide, code of conduct, support page, issue and pull request forms.
- CI checks the Python code with ruff and runs the server and extension tests.

### Fixed
- The plugin made computer ids starting with `may-`, which the server has refused since 0.24.0, so every send got error 400. New ids start with `device-`, and an old id keeps its ending.
- The server limit of 300 computers counts the database again; since the move to SQLite it counted nothing.

### Upgrading
Copy `/opt/ai-worker` aside first, then run `sudo bash install.sh`. The service log shows `migrated JSON files into ...` once. Change any backup job that copies `data/` to the SQLite backup command.

## 0.24.0 - 2026-11-04

The last version that kept the server data in JSON files. Changes before the repository was published are not listed.
