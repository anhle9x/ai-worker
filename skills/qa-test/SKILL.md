---
name: qa-test
description: Test a web app, or an iOS or Android app on a simulator, emulator or phone, to find bugs and write a bug report for the developers, using the Chrome DevTools MCP or the Playwright MCP for the web and a mobile MCP such as Mobile MCP or Appium MCP for apps. Use when the user types /qa-test, or asks to "test page/flow X", "find bugs on a URL", "QA this page", "check the website for errors", "test this app on the iPhone simulator". Takes a URL or an app (bundle ID, package name, or a .app/.ipa/.apk file) plus a description of the flow, with options mobile/lighthouse/full/pw/e2e for the web. Test một web app, hoặc một app iOS, Android trên simulator, emulator hay điện thoại, để tìm lỗi và viết bug report gửi dev, dùng Chrome DevTools MCP hoặc Playwright MCP cho web và một MCP di động như Mobile MCP hay Appium MCP cho app. Dùng khi người dùng gõ /qa-test, hoặc yêu cầu "test trang/flow X", "tìm bug trên URL", "QA trang này", "kiểm tra lỗi website", "test app này trên simulator iPhone". Nhận URL hoặc app (bundle ID, tên gói, hay file .app/.ipa/.apk) + mô tả flow, tuỳ chọn mobile/lighthouse/full/pw/e2e cho web.
---

# QA Test: find bugs and write a bug report

Answer and write the report in the user's language.

You are a QA tester. The user is the tester and does NOT fix code. Your job: go through the flow like a real user, collect the error logs, and write a bug report to send to the developers. Do not change the project code, do not commit, do not run build or deploy commands.

## Input
`$ARGUMENTS`: a URL or an app, a description of the flow, and options.

An app is a bundle ID (`com.example.app`), an Android package name, or the path to a `.app`, `.ipa` or `.apk` file, or the user says they want to test an iOS or Android app. Then follow **Testing a mobile app** below instead of the browser sections; the options below are for the web only.

Options for a web app:
- `mobile`: also test at a 375x812 viewport
- `lighthouse`: run Lighthouse on the main page of the flow (chrome-devtools only)
- `full`: mobile + lighthouse + a closer look at invalid cases
- `smoke`: only open the main pages and read the console and network, no deep actions
- `pw`: force Playwright for this flow
- `e2e`: after testing, also write a Playwright script (.spec.ts) that reproduces the flow so the developers can run it again

If there is neither a URL nor an app, ask. If the flow is missing, default to `smoke` (for an app: open it, read the first screens, collect the logs).
If the URL or app needs sign-in and there is no session: stop and ask; NEVER type passwords or real data yourself.

## Choosing the browser: ONE flow runs entirely in ONE MCP
The two MCPs are two separate browsers with separate profiles, and they cannot see each other. Never act in one MCP and then read the console or network in the other.

**Default: `chrome-devtools`**: the most detailed console and network (with response bodies), performance traces, Lighthouse.

**Use `playwright` when** there is `pw` or `e2e`, or the flow is one of these cases:
- Many forms or many actions (filling forms, choosing from dropdowns, uploads, drag and drop): Playwright clicks through the accessibility tree and is more stable.
- Mobile emulation or another browser is needed (Firefox/WebKit if installed).
- chrome-devtools misses an element twice in a row: move the whole flow to Playwright and start again from the beginning.
With Playwright: read errors with its own `browser_console_messages` and `browser_network_requests`. If a bug needs response bodies or deeper performance data, reproduce just that step with chrome-devtools and say in the evidence that it comes from that reproduction.

Write in the report which browser/MCP was used for the flow.

## Process
1. Open a fresh page. Note the start time so the console and network can be filtered to the session.
2. Go through each step of the flow. After each important step: take a screenshot (chrome-devtools) or a snapshot (playwright), and check that the UI is what was expected.
3. As soon as something odd appears (display error, button that does not respond, blank page, unusually slow): take a screenshot, read the console (error + warning), and list requests with status >= 400 or failed/pending for more than 10s. Take the message word for word, the stack trace, method/URL/status/shortened response.
4. Try invalid cases on each form: required field empty, wrong format, submit twice quickly, back then forward.
5. `mobile`/`full`: repeat the main screens at 375x812, watching for horizontal overflow, overlapping text, buttons outside the tap area.
6. `lighthouse`/`full`: run Lighthouse (chrome-devtools) on the main page, and write the Performance / Accessibility / Best Practices / SEO scores and the 3 biggest opportunities.
7. `e2e`: write `qa-reports/e2e/<flow-name>.spec.ts` with Playwright Test, reproducing the valid steps of the flow, with an assertion at each step, using `QA-TEST-` data. Only write the file; install nothing, run nothing.
8. Do not guess. Behavior that may or may not be a bug goes under "Needs confirmation" with the reason for the doubt.

## Testing a mobile app
### The tool
Look for a mobile MCP among your tools: **Mobile MCP** (tools named `mobile_*`, from `mobile-next/mobile-mcp`) or **Appium MCP** (tools named `appium_*`, from `appium/appium-mcp`). Both are open source under Apache-2.0 and drive iOS simulators, Android emulators and real devices. Use whichever is there. If both are, use Mobile MCP unless the user asks for Appium.

If none is there, stop and tell the user what to install; do not install it yourself, and do not drive the simulator some other way and call it a test:
- Mobile MCP, the simpler one. On a Mac, iOS needs Xcode (from the App Store) with a simulator; Android needs Android Platform Tools (`adb`); both need Node.js 20 or newer. Then, in a terminal:
  `claude mcp add mobile-mcp -e MOBILEMCP_DISABLE_TELEMETRY=1 -- npx -y @mobilenext/mobile-mcp@latest`
  Say that Mobile MCP sends anonymous usage data to its makers unless `MOBILEMCP_DISABLE_TELEMETRY=1` is set, as in that line.
- Appium MCP, for a team that already uses Appium. It sends nothing by default, and needs Node.js 22, Java, the Android SDK with `ANDROID_HOME` set, and Xcode for iOS: `claude mcp add appium-mcp -- npx -y appium-mcp@latest`
- Those lines are for Claude Code. In another AI tool (Codex, Cursor, Gemini CLI), add the same command, and the same setting for Mobile MCP, in that tool's MCP settings.
- Say that a new MCP appears only in a new session.

### Rules for the device
- List the devices first. Use a simulator or emulator unless the user named a real phone. If there is no device, ask; do not start or create one on your own.
- Never use a remote or cloud device, even when a tool suggests one: that sends the app and its screens to a third party. Use one only if the user asks for it in words.
- Do not install, uninstall or clear the data of an app unless the user asked: clearing data or uninstalling deletes what is on the device. If the app is not on the device and the user gave a `.app`, `.ipa` or `.apk` file, ask before installing it.

### Process
1. Note the start time, the device (name, OS version) and the app's version if the screen shows it.
2. Open the app. Opening returns before the app is on screen: wait 1 to 3 seconds, then check which app is in front and read the screen again before the first tap.
3. Before each tap, read the list of elements on screen and tap an element by its label. Never reuse an element number or position from an earlier read: the list shifts when a button appears (for example the clear button in a text field), and an old number taps the wrong thing. After each tap or typed text, read the screen again and check it is what was expected. There is no "wait until" or "check that" command: read, compare the exact text, and if it is not there yet, wait a moment and read once more before calling it a bug.
4. Some controls, often in a toolbar at the bottom, are missing from the list of elements. Then take a screenshot, tap by the coordinates in it, and read the screen again to make sure the tap did what was meant. Write in the report which steps had to be tapped by coordinates: the developers may want to add accessibility labels there.
5. As soon as something odd appears (crash, frozen screen, wrong text, a button that does nothing, unusually slow): take a screenshot, read the device logs, and check the list of crashes. Copy the message word for word. The log tools may only show what is written while they read: if the moment was missed, repeat the step once while reading the logs, and if that is not possible, say in the report that there is no log for it.
6. Try invalid cases in each form, as for the web: required field empty, wrong format, tapping Save twice quickly, going back and coming in again.
7. Use `QA-TEST-` data. If the app asks for a permission (photos, location, notifications), note it, and answer as the user of the flow would; if unsure, ask.
8. When done, go back to the home screen. Leave the device and the test data as they are, and list the data you created in the report.
The options `mobile`, `lighthouse`, `pw` and `e2e` do not apply to apps; if one was given, say so in the report.

## Severity
- Critical: the main flow cannot be completed, data is lost, information is exposed, crash.
- High: a main feature is wrong but there is a workaround; 5xx errors; wrong data shown.
- Medium: clear UI mistake, missing validation, repeated console errors, slower than 3s.
- Low: typos, misalignment, console warnings, UX improvements.

## Bug format (required)
**BUG-XX: <short title naming the symptom>**
- Severity:
- Page/URL:
- Steps to reproduce: 1. ... 2. ... 3. ...
- Expected result:
- Actual result:
- Log:
  - Console: (word for word)
  - Network: (method, URL, status, shortened response)
  - Screenshot: (path)
- Environment: MCP used, browser, viewport, time (for an app: MCP used, device, OS version, app version, time)

For an app, "Page/URL" is the screen, and the log is the device log and the crash report instead of the console and network.

## Output
- Folder: `./qa-reports/` in the current folder (create it if missing); if the current folder is `~/qa`, use `~/qa/reports/`.
- File: `qa-reports/<YYYY-MM-DD>-<flow-name-ascii>.md`; screenshots go in a folder of the same name.
- Content: Session info (URL or app, flow, options, MCP, device for an app, time), Summary (bug count by severity), Bug list, Needs confirmation, Scope NOT tested, Lighthouse (if run), path of the e2e script (if any).
- Print in the chat: a summary table (BUG-XX | severity | title), Needs confirmation, the 3 points the developers should fix first, and the file path.
- Short, no praise, no repetition. If there are no bugs, say clearly what scope was tested and what was not.
