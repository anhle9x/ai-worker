# Changelog

Changes that matter to people who install or run AI Worker. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Added
- `python3 server/demo.py` shows the board on your own computer with 12 made-up people in 4 offices: no server, no install. It prints the address, the account and the 6-digit code to log in with, keeps everything in a temporary folder that is deleted when it stops, and ignores the settings of a real board.

### Changed
- The README shows nine pictures of the board in one row that scrolls sideways.

### Fixed
- On Windows, stopping `server/demo.py` left its sample data behind while saying it was deleted: the databases are now closed first, and the message says so if the folder could not be removed. The README gives the Windows command, `py server\demo.py`.
- On the maps, an office's label could cover another label, another office's pin or the list of offices in the corner, and could be pushed out of the frame. Each label now takes a free place beside its own pin, on the left when the right is taken, and stays inside the frame.

## 0.31.3 - 2026-11-14

### Fixed
- The flat (2D) map on the board stayed blank: it never started drawing. The 2.5D map and the globe were not affected.

### Added
- The README has a "Screens" section with seven pictures of the board, all with made-up people and numbers.

## 0.31.2 - 2026-11-13

### Fixed
- In a session with no folder chosen, asking in plain words for a whole project to be looked over made Claude ask for a folder and then stop, instead of naming the command to type. The rule now tells it to name `/ai-worker:improve-codebase-architecture` first, before asking for a folder or reading any file.

## 0.31.1 - 2026-11-13

### Changed
- Nobody has to remember a skill's name. `/ai-worker:help` now says so at the top of the skills, and marks the one skill that runs only when its name is typed (`improve-codebase-architecture`, which reads a whole project).
- When someone asks in their own words for the structure of a whole project to be looked over, Claude names the command to type instead of doing that long scan itself. A remark about one function, file or module is helped with at once, as before.

## 0.31.0 - 2026-11-13

### Changed
- The Dev pack is gone as a separate plugin: its 14 skills (testing, coding, security, UI, specifications, diagrams), the `planner` assistant and the rules for technical work now come with the plugin itself, so every computer has them and they update with it. Their names start with `ai-worker:` instead of `ai-worker-dev:`. If you had installed the Dev pack, remove the `ai-worker-dev` plugin, or its skills show twice.
- The tools some of those skills need (Node, Playwright, Chrome DevTools) are still a separate step for people who write code: `INSTALL-DevTools-Mac.command` or `INSTALL-DevTools-Windows.bat`, in the `setup` folder of the package. They replace `INSTALL-Dev-*`.
- `/ai-worker:help` reads as a short list in plain words, in two groups: skills for everyday work, and skills for people who write code or run systems.

## 0.30.0 - 2026-11-13

### Added
- `/ai-worker:help` lists what the plugin gives on the computer it runs on: its commands, the skills it ships, which helper assistants (Gemma, ChatGPT, Gemini) that computer has, whether the Dev pack is installed and whether numbers are sent to the company server. Until now nothing showed this.

## 0.29.1 - 2026-11-13

### Fixed
- In a session that has not started yet, the app did not list `/office`, `/office-pane` or `/update` and said `/office isn't a command here`, because the plugin only declared them once a session was running. They are now also declared as files, so the list shows `ai-worker:office`, `ai-worker:office-pane` and `ai-worker:update` from the start. The short names work as before.

## 0.29.0 - 2026-11-13

### Added
- The question that offers to close and reopen the Claude desktop app after `/update` now also appears on Windows and on Linux (the `claude-desktop` package for Ubuntu and Debian), not only on a Mac. On Windows the app is asked to end the way Windows asks at sign-out, because closing its window only hides it in the tray. Tried with the real app on Windows; on Linux only against a stand-in package so far, not the real app.

### Fixed
- The messages and guides told Windows users to close every window to quit the Claude app. That only hides the app in the tray: it keeps running. They now say to right-click the Claude icon next to the clock and choose Exit.

## 0.28.1 - 2026-11-13

### Changed
- Nothing new to use. This version exists so that a computer on 0.28.0 has an update to install: that is the only way to see the question that offers to reopen the Claude app.

## 0.28.0 - 2026-11-13

### Added
- After `/update` or the Update button installs a new version, the Claude desktop app on a Mac offers to close and open again on its own. It asks first, because sessions that are still working stop. Elsewhere (Windows, Linux, a terminal, an editor) the message still asks you to quit and reopen by hand.

## 0.27.2 - 2026-11-13

### Fixed
- The warning shown when a session's context is 60% or 80% full now points to `/handoff`. The plugin looked for the skill only in `~/.claude/skills/handoff`, not in its own folder where it ships, so the warning never mentioned it.

## 0.27.1 - 2026-11-12

### Fixed
- Closing a session's detail card on the board (× or Esc) keeps it closed. The session stayed selected, so the card came back with the next data refresh a few seconds later.

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
