[Tiếng Việt](TEST-PLAN.vi.md) | English <!-- i18n-allow -->

# Test plan

What is tested automatically on every push, what still needs a person, and the checklist before a release.

## 1. Automatic tests

GitHub Actions runs `.github/workflows/test-install.yml` on every push. A release is made only when every job is green.

| Job | Machine | Checks | Files |
|---|---|---|---|
| `code-check` | Ubuntu | Python lint (ruff); hook tests through the Claude Code CLI; over 100 server tests; the Chrome extension logic against a real local server | `ruff.toml`, `tests/*.test.ts(x)`, `server/test_webhook.py`, `tests/extension/check-extension.js` |
| `build` | Ubuntu | Package build; the private-data check; skill front matter; the two-language rules | `packaging/build.sh`, `tests/test-check-clean.sh`, `tests/check-frontmatter.py`, `tests/check-i18n.py` |
| `ubuntu` | Ubuntu | Installer on a clean machine, case by case; server install with systemd; menu bar script; the `.deb` installed and removed by apt; notification badge picture | `tests/linux/test-install.sh`, `tests/linux/test-server.sh`, `tests/menubar/test-menubar.sh`, `tests/menubar/test-deb.sh` |
| `windows` | Windows | Installer on a clean machine, case by case; icon next to the clock; notification badge picture | `tests/windows/test-install.ps1`, `tests/menubar/test-menubar.ps1` |
| `windows-app` | Windows | Build `AI Worker.exe` and `.msi`; install for one user without admin rights; pair; count waiting people; remove | `tests/menubar/test-windows-app.ps1` |

### What the tests cover

| Area | Covered by |
|---|---|
| Permission of every server path | `test_webhook.py` holds the full route table and fails if a path is added without a permission |
| Login, OTP, lockout after wrong codes, re-entering OTP for account actions | `test_webhook.py` |
| What each role receives (no email or IP for wall) | `test_webhook.py` |
| Pairing TV, menu bar and extension; revoke; expiry | `test_webhook.py`, `check-extension.js`, menu bar tests |
| A computer cannot send for another person; send limits | `test_webhook.py` |
| Cost by hour, no double count after reopening a session | `tests/cost.test.ts` |
| No prompt, chat or secret file content leaves the machine | `tests/activity.test.ts`, `tests/edits.test.ts`, `tests/team.test.ts`, `tests/office.test.tsx` |
| Helper assistants: Gemma model choice, safe arguments for Codex | `tests/workers.test.ts` |
| SQLite storage: moving the old JSON files in, schema version, file modes, many threads at once, backup, export back to JSON | `test_webhook.py` (`DatabaseStorage`), `tests/linux/test-server.sh` |
| Language choice and fallback | `tests/lang.test.ts` |
| No private word, address or key in the package | `tests/test-check-clean.sh` with `packaging/check-clean.sh` |

## 2. Run locally

```bash
python3 -m unittest test_webhook
```

Run it in `server/`. Correct result: `OK`.

```bash
npx -y @anthropic-ai/claude-code plugin test .
```

Run it at the repository root. Correct result: every test passes.

```bash
node tests/extension/check-extension.js
```

```bash
python3 tests/check-i18n.py
```

```bash
bash packaging/check-clean.sh
```

Correct result of the last one: `Clean.`

## 3. Checks that still need a person

Automatic tests use fake servers and fake browsers. Before a release that touches these parts, check by hand:

| Part | Machine | Check | Correct result |
|---|---|---|---|
| Plugin install | A real Mac and a real Windows PC | Run the installer, open Claude Code, type `/office` | The office page opens; the computer appears on the dashboard within 5 minutes |
| Update | A computer on the previous version | Wait for or force the update check, click **Update**, restart the app | The new version number shows in `/office` |
| Login with OTP | A real phone with Google or Microsoft Authenticator | Scan the QR on `/admin`, log in | Logged in; a wrong code 5 times locks for 15 minutes |
| TV screen | A real TV or a browser in full screen | Open `/tv`, approve the code on `/admin` | The board shows with no email or IP |
| macOS menu bar | A real Mac | Install the `.dmg` or `.zip`, pair | Icon shows the waiting count, notification arrives |
| Ubuntu menu bar | Ubuntu with X11 **and** Ubuntu with Wayland | Install the `.deb`, pair | Icon shows in the top bar on both |
| Chrome extension | Real Chrome | Load the extension, pair, open the popup | Popup and badge show the waiting count |
| Phone width | A phone or a 375 px window | Open the dashboard | Nothing overflows; buttons can be tapped |

## 4. Before a release

1. Every GitHub Actions job is green.
2. The checks in section 3 are done for every part this release changed.
3. `version` in `.claude-plugin/plugin.json` is raised, and `CHANGELOG.md` lists the changes.
   If the dashboard looks different, retake `assets/dashboard.png` and `assets/dashboard.vi.png` from a test server with made-up people, never a real one.
4. `bash packaging/release.sh` succeeds, and the signature is checked on one computer before the release goes out to everyone.
5. Write down in the site record what was released, when and by whom ([OPERATIONS.md](OPERATIONS.md), section 7).

## 5. Known gaps

- `hooks/register.tsx` and `web/ops.js` (copied to `server/static/ops.js`) have no direct tests of their own yet.
- No automatic test on a real Mac.
- No automatic test on Ubuntu Wayland; it is checked by hand.
