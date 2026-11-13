# Third-party components

AI Worker's own code is under the MIT License in [LICENSE](LICENSE). These parts come from others and keep their own licenses.

## Libraries and data

| Component | Where | Author | License |
|---|---|---|---|
| three.js | `web/three.js`, `server/static/three.js` | three.js authors | MIT, `web/three.LICENSE` |
| qrcode-generator 2.0.4 | `server/static/qrcode.js` | Kazuhiko Arase | MIT, stated in the file |
| Microsoft.Web.WebView2 1.0.4314.35 (WebView2 SDK) | `server/menubar/webview2/` | Microsoft | BSD-style, `server/menubar/webview2/LICENSE.txt` |
| Natural Earth boundaries | `server/static/land.json` | Natural Earth | Public domain |

## Skills in the plugin

| Skill | Source | Author | License |
|---|---|---|---|
| `meeting-notes` | alapha888/agent-skills-en | Muse | MIT, `skills/meeting-notes/LICENSE` |
| `lesson-generator` | dair-ai/dair-academy-plugins | Elvis Saravia and DAIR.AI | MIT, `skills/lesson-generator/LICENSE` |

## Skills for people who write code or run systems

| Skill | Source | Author | License |
|---|---|---|---|
| `browser-testing-with-devtools`, `interview-me` | addyosmani/agent-skills | Addy Osmani | MIT, `LICENSE` in each folder |
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | Next Level Builder | MIT, `LICENSE` in the folder |
| `tdd`, `diagnosing-bugs`, `codebase-design`, `domain-modeling`, `improve-codebase-architecture`, `grilling` | see `skills/SOURCES.md` | Matt Pocock | MIT, `LICENSE` in each folder |
| `security-audit` | see `skills/SOURCES.md` | Cloudflare, Inc. | MIT, `LICENSE` in the folder |

## Optional download, not included

`stageshow` (benjitaylor/skills) is not in this repository. The tools installer (`setup/INSTALL-DevTools-*`) offers to download it at a pinned commit. Its code is MIT, but its app icons are not covered by that license, so check them before you use or redistribute them.

`video-shotcraft` (Vincentwei1021/video-shotcraft) is not in this repository either. The tools installer (`setup/INSTALL-DevTools-*`) offers to download it at a pinned commit. Its code is under the Apache License 2.0 (`LICENSE` in its repository). It uses Remotion, which has its own license and may require a paid company license, and some of its audio files have an unclear source.

SwiftBar (swiftbar/SwiftBar) is not in this repository. When the server has no built macOS app (`MENUBAR_MAC_APP` not set), "Download for macOS" gives `server/menubar/install-mac.command`, which installs SwiftBar from Homebrew or its official GitHub release. SwiftBar is under the MIT License (`LICENSE` in its repository).
