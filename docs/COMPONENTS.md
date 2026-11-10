[Tiếng Việt](COMPONENTS.vi.md) | English <!-- i18n-allow -->

# Components and versions

Every part of AI Worker, where it runs, what it needs and which version is pinned. Licenses of outside code are in [THIRD-PARTY.md](../THIRD-PARTY.md).

## 1. Parts we build

| Part | Runs on | Language | Version |
|---|---|---|---|
| Plugin (hooks, `/office`, skills) | Staff computers, inside Claude Code | TypeScript | `version` in `.claude-plugin/plugin.json` (now 0.27.0) |
| Dashboard server (webhook) | Linux server | Python, standard library only; data in SQLite | Same as the plugin release |
| 3D office page | Browser | JavaScript, three.js | Same as the plugin release |
| Menu bar icon | macOS, Windows, Ubuntu | Python (SwiftBar on Mac, Ubuntu), Swift app (`macos-app/`), PowerShell and C# (Windows) | Built by the server for each download |
| Manager browser extension | Chrome | JavaScript | `version` in `extensions/manager/manifest.json` (now 0.1.0) |
| Installers | macOS, Windows, Linux | Bash, PowerShell | Inside the package |

## 2. What each machine needs

| Machine | Needs | Installed by |
|---|---|---|
| Server | Linux with systemd, Python 3.8 or newer with its built-in `sqlite3` module, Caddy or nginx for HTTPS | IT, by hand; then `server/install.sh` |
| Staff computer | Claude Code (desktop app or CLI), a Claude account | The staff member |
| Staff computer, optional helpers | Ollama with a Gemma model, Codex CLI (ChatGPT), Antigravity CLI `agy` (Gemini) | The installer asks |
| Developer pack | Node 20.19 or newer, Python, Chrome, ffmpeg | The developer pack installer (`winget` on Windows, Homebrew on Mac) |
| Ubuntu menu bar | `python3`, `python3-gi`, `python3-gi-cairo`, GTK 3, AyatanaAppIndicator3 (or AppIndicator3), WebKit2 4.1 (or 4.0) | `apt`, from the `.deb` dependencies |
| macOS menu bar without the built app | SwiftBar | `install-mac.command`, from Homebrew or its GitHub release |
| Windows menu bar | WebView2 runtime (built into Windows 10 and 11) | Windows |

## 3. Pinned outside code

| Component | Version | Where |
|---|---|---|
| three.js | r186 | `web/three.js`, `server/static/three.js` |
| qrcode-generator | 2.0.4 | `server/static/qrcode.js` |
| Microsoft WebView2 SDK | 1.0.4314.35 | `server/menubar/webview2/` |
| Natural Earth boundaries | | `server/static/land.json` |
| `stageshow`, `video-shotcraft` (optional downloads) | Pinned commit | The installer |

## 4. Tools used to check the code

| Tool | Version | Used in |
|---|---|---|
| Claude Code CLI (`plugin test`) | 2.1.319 | GitHub Actions, `code-check` |
| ruff | 0.17.4, rules in `ruff.toml` | GitHub Actions, `code-check` |
| TypeScript (`tsc`) | run locally only | Developer computer |
| GitHub runners | `ubuntu-latest`, `windows-latest` | `.github/workflows/test-install.yml` |

## 5. When to update

- **Server Python:** follows the server's OS updates; the webhook uses no outside package.
- **Pinned outside code:** check the source for security fixes each release; update the version here and in THIRD-PARTY.md together.
- **Claude Code CLI in CI:** raise the pinned version when a new Claude Code changes the plugin format.
