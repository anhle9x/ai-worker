[Tiếng Việt](SKILLS.vi.md) | English <!-- i18n-allow -->

# Skills and rules

**The common pack, built into the plugin:** `meeting-notes`, `lesson-generator`, `handoff`, and the guidance and security rules (on only in the company package).

**The technical pack `ai-worker-dev`, for developers and the IT team, installed separately:**
```bash
bash packaging/build-dev-pack.sh
```
This makes `dist/AI-Worker-Dev-<version>.zip`. Unzip it and double-click `INSTALL-Dev-Mac.command` or `INSTALL-Dev-Windows.bat`. The pack has the skills for testing, coding, security and UI, `write-spec` for specifications, `draw-flow` for Mermaid diagrams, the `planner` assistant and the session-splitting rule.

The installer installs Node 20.19 or newer, registers Playwright and Chrome DevTools, and asks whether to also download `stageshow` and `video-shotcraft`. Windows uses `winget` to install Python, Chrome and ffmpeg when missing. A Mac can install those three only if Homebrew is writable; otherwise the installer lists at the end what is still missing.

`video-shotcraft` uses Remotion, which has its own license, and some audio of unclear source: check before making videos for the company.

Sources and licenses of the skills: `skills/SOURCES.md`, `dev-pack/skills/SOURCES.md`.

## Every skill

| Skill | Pack | What it does | Author | License |
|---|---|---|---|---|
| `meeting-notes` | Plugin | Turns rough meeting notes into minutes: decisions, actions with an owner and a deadline | Muse (alapha888/agent-skills-en) | MIT |
| `lesson-generator` | Plugin | Builds a short multi-lesson course with flashcards and quizzes | Elvis Saravia, DAIR.AI | MIT |
| `handoff` | Plugin | Writes the handoff note so the next session can carry on | This project | MIT |
| `qa-test` | Developer pack | Tests one web flow and writes a bug report | This project | MIT |
| `qa-site` | Developer pack | Tests a whole web project, flow by flow, into one report | This project | MIT |
| `write-spec` | Developer pack | Writes a specification: goal, scope, roles, numbered requirements | This project | MIT |
| `draw-flow` | Developer pack | Draws how a system really works as checked Mermaid diagrams | This project | MIT |
| `browser-testing-with-devtools` | Developer pack | Tests pages through Chrome DevTools: DOM, console, network | Addy Osmani | MIT |
| `interview-me` | Developer pack | Asks one question at a time until the real need is clear | Addy Osmani | MIT |
| `ui-ux-pro-max` | Developer pack | Interface and UX guidance with searchable styles and palettes | Next Level Builder | MIT |
| `tdd` | Developer pack | Test-driven development, red-green-refactor | Matt Pocock | MIT |
| `diagnosing-bugs` | Developer pack | A loop for hard bugs and slowdowns | Matt Pocock | MIT |
| `codebase-design` | Developer pack | Vocabulary for designing deep modules | Matt Pocock | MIT |
| `domain-modeling` | Developer pack | Builds the project's glossary and decision records | Matt Pocock | MIT |
| `improve-codebase-architecture` | Developer pack | Finds where the code can be deepened and reports it | Matt Pocock | MIT |
| `grilling` | Developer pack | Stress-tests a plan or idea with hard questions | Matt Pocock | MIT |
| `security-audit` | Developer pack | Security review of code, APIs and services | Cloudflare, Inc. | MIT |

`stageshow` and `video-shotcraft` are not in this repository; the developer pack installer offers to download them.
