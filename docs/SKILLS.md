[Tiếng Việt](SKILLS.vi.md) | English <!-- i18n-allow -->

# Skills and rules

**Every skill comes with the plugin.** Three are for everyday work: `meeting-notes`, `lesson-generator`, `handoff`. The others are for people who write code or run systems: testing, coding, security and UI, `write-spec` for specifications, `draw-flow` for Mermaid diagrams. The plugin also ships the `planner` assistant, the rules for technical work, and the guidance and security rules (on only in the company package). Type `/ai-worker:help` in a session to see the list on your computer.

**The tools some of those skills need are a separate step, for people who write code.** In the unzipped package, open the `setup` folder and double-click `INSTALL-DevTools-Mac.command` or `INSTALL-DevTools-Windows.bat`, after installing the plugin. It installs Node 20.19 or newer, registers Playwright and Chrome DevTools, and asks whether to also download `stageshow` and `video-shotcraft`. Windows uses `winget` to install Python, Chrome and ffmpeg when missing. A Mac can install those three only if Homebrew is writable; otherwise the installer lists at the end what is still missing. Without this step the skills are still there; `qa-test`, `qa-site` and `browser-testing-with-devtools` cannot drive a browser.

`video-shotcraft` uses Remotion, which has its own license, and some audio of unclear source: check before making videos for the company.

Sources and licenses of the skills: `skills/SOURCES.md`. The skills written by others are kept as their authors wrote them.

## Every skill

| Skill | For | What it does | Author | License |
|---|---|---|---|---|
| `meeting-notes` | Everyone | Turns rough meeting notes into minutes: decisions, actions with an owner and a deadline | Muse (alapha888/agent-skills-en) | MIT |
| `lesson-generator` | Everyone | Builds a short multi-lesson course with flashcards and quizzes | Elvis Saravia, DAIR.AI | MIT |
| `handoff` | Everyone | Writes the handoff note so the next session can carry on | This project | MIT |
| `qa-test` | Coding and systems | Tests one web flow and writes a bug report | This project | MIT |
| `qa-site` | Coding and systems | Tests a whole web project, flow by flow, into one report | This project | MIT |
| `write-spec` | Coding and systems | Writes a specification: goal, scope, roles, numbered requirements | This project | MIT |
| `draw-flow` | Coding and systems | Draws how a system really works as checked Mermaid diagrams | This project | MIT |
| `browser-testing-with-devtools` | Coding and systems | Tests pages through Chrome DevTools: DOM, console, network | Addy Osmani | MIT |
| `interview-me` | Coding and systems | Asks one question at a time until the real need is clear | Addy Osmani | MIT |
| `ui-ux-pro-max` | Coding and systems | Interface and UX guidance with searchable styles and palettes | Next Level Builder | MIT |
| `tdd` | Coding and systems | Test-driven development, red-green-refactor | Matt Pocock | MIT |
| `diagnosing-bugs` | Coding and systems | A loop for hard bugs and slowdowns | Matt Pocock | MIT |
| `codebase-design` | Coding and systems | Vocabulary for designing deep modules | Matt Pocock | MIT |
| `domain-modeling` | Coding and systems | Builds the project's glossary and decision records | Matt Pocock | MIT |
| `improve-codebase-architecture` | Coding and systems | Finds where the code can be deepened and reports it | Matt Pocock | MIT |
| `grilling` | Coding and systems | Stress-tests a plan or idea with hard questions | Matt Pocock | MIT |
| `security-audit` | Coding and systems | Security review of code, APIs and services | Cloudflare, Inc. | MIT |

`stageshow` and `video-shotcraft` are not in this repository; the tools installer offers to download them.
