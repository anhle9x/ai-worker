[Tiếng Việt](menu-bar-spec.vi.md) | English <!-- i18n-allow -->

# Menu bar icon for managers: specification

An icon in the macOS menu bar, the Windows notification area and the Ubuntu top bar: managers see who is waiting for an answer, and a click opens a small window. Built and running; the code shows what runs today, and this document gets corrected when they disagree. The small window is the `/mini` page on the server, shared by every system.

## Goal

A manager sees in the menu bar, even with the browser closed, how many people are waiting and who has waited long, and opens the board in one click. The interface is designed once, on the server. The icon never gets more data than a wall screen, and no outside library is added, except Microsoft's WebView2 SDK for the Windows window (see `THIRD-PARTY.md`).

## Not in scope

- **Emails, internal IPs, full names.** The icon and its window get the wall screen's view (`role_view`, role `wall`).
- **Changing data on the server**, other than this computer's own notification settings and unpairing it.
- **Working outside the company network.** The server only answers that network.
- **Staff computers.** The icon is for managers; staff computers install nothing new.
- **A signed macOS app.** The app has an ad-hoc signature, so the first launch needs "Open Anyway" once. An Apple Developer ID removes that step; `build.sh` already takes one.

## Who uses it

| Role | Uses | Can do |
|---|---|---|
| Manager | The icon and the `/mini` window | See counts and lists, change notifications, language and start at login, unpair, remove the app, pair their own computer with their account and OTP |
| Admin | `/admin` | Download the installers, pair a computer by entering its code, see who paired which computer, revoke one |
| Server | `/mini`, `/mini/pair`, `/mini/state`, `/mini/handoff`, `/mini/settings`, `/mini/unpair`, `/data`, pairing routes | Serve the window, check the OTP, hand out one-time codes, serve the wall view |

## What it must do

| ID | Requirement | Where |
|---|---|---|
| F1 | `/mini` fits a window of about 360 wide: name and update time, five tabs (Waiting, Working, Quota, Cost today, Settings), the list, "Open board"; it follows light or dark mode | `page_mini` in `server/webhook.py`, `server/static/mini.js`, `mini.css` |
| F2 | Waiting shows how long each person has waited; Quota shows every window the account reports, so a plan without a 5-hour limit simply has none | `WaitTracker`, `mini.js` |
| F3 | A manager pairs their own computer: the icon opens `/mini/pair` with the code after `#`, the manager enters their account and 6-digit code, and nobody else has to approve | `mini_self_pair`, `TvPairing.self_approve` |
| F4 | Self-pairing checks the OTP with the same limits as logging in, accepts only viewer or admin accounts, only a request from the same IP, and at most `MENUBAR_PER_ACCOUNT` computers per account | `mini_self_pair`, `LoginGate.check_otp` |
| F5 | Deleting an account, moving it to the wall role, or ending its sessions removes the computers it paired | `TvStore.revoke_owner` |
| F6 | An admin can still pair a computer by entering the code it shows, the way wall screens are paired | `TvPairing`, `/admin` |
| F7 | The icon: the logo alone, the logo with the count, the logo in blue `#1A56C8` when someone waited past the limit, faded when the server cannot be reached, a key while not paired | `main.swift`, `ai-worker.1m.py`, `ai-worker-tray.ps1`, `ai-worker-indicator.py` |
| F8 | macOS: a native app shows the window under the icon; the window cannot be dragged loose, has a blurred background, and takes the height of the page | `server/menubar/macos-app/main.swift` |
| F9 | Ubuntu: an AppIndicator icon in a .deb the server builds with its address inside (the Argos script still works); Windows: the app `AI Worker.exe` (C#, .NET Framework 4.8) in the notification area, installed for the user from `AI Worker.msi` (no admin rights; installing over a running copy closes it first, without a reboot); it opens `/mini` in a small borderless window of its own (WebView2), like the Mac's, falls back to a compact Edge window when WebView2 fails, encrypts its session with DPAPI and takes over from the older PowerShell icon (`ai-worker-tray.ps1`, still served as the fallback .zip) | `ai-worker-indicator.py`, `menubar_deb`, `ai-worker.1m.py`, `windows-app/Program.cs`, `AIWorker.wxs`, `menubar-popup.cs`, `ai-worker-tray.ps1` |
| F10 | The window takes the computer's session through a one-time code that lives `MINI_HANDOFF_SECONDS` and works once | `MiniHandoff`, `get_mini` |
| F11 | Someone waiting past the set time gives one operating system notification per wait, not one per minute. On Windows a click on the notification opens the window, through an `ai-worker-open:` link registered under `HKCU\Software\Classes` | `main.swift`, `remind`, `ToNotify`, `Notify-Long` |
| F12 | Settings on every system: notification on or off and its delay (kept on the server for this computer), language, start at login (macOS app: on after the first launch), unpair, remove the app (macOS: unpair, Trash, quit; Windows and Ubuntu: unpair, then remove the app) | `mini.js`, `TvStore.set_mini_settings`, `main.swift`, `ai-worker-tray.ps1`, `ai-worker-indicator.py` |
| F13 | When the server cannot be reached the icon fades and the window says so; old numbers are never shown as current | `main.swift`, scripts |
| F14 | The Admin page gives "Download for macOS", "Download for macOS (.dmg)" when `build.sh` left one next to the app, "Download for Windows (.msi)" when `server/menubar/AI-Worker.msi` is there (the server fills its own address into the package), "Download for Windows" or "Windows, old installer (.zip)" for the PowerShell icon, and "Download for Ubuntu (.deb)"; with `MENUBAR_MAC_APP` set, macOS gets the app built for this server, otherwise the SwiftBar installer | `get_menubar_installer`, `menubar_msi`, `menubar_zip`, `admin.js` |
| F15 | The macOS app follows the Mac's language unless built for one. The window uses the language chosen in Settings, kept in a `lang` cookie; the Windows and Ubuntu icons open `/mini?…&lang=`, so the window and the tray menu match | `main.swift`, `tx`, `get_mini`, `mini.js` |
| F16 | The admin's list of screens names a menu bar computer "Menu bar on Mac/Windows/Linux", shows who paired it by themselves, and does not report a page version for it | `device_label`, `admin.js` |

## Limits

| Limit | Value |
|---|---|
| How often the icon asks the server | Once a minute |
| Default wait before a notification | 10 minutes (5, 10, 15, 30 or 60) |
| Computers one account may pair by itself | 2 (`MENUBAR_PER_ACCOUNT`) |
| One-time code for the window | 90 seconds, single use |
| How long a pairing lasts | 30 days, renewed while used, at most 1 year |
| Data the icon can read | The wall view only |
| macOS app | macOS 13 or newer, Apple silicon and Intel, built with `swiftc` from Apple's Command Line Tools |
| Ubuntu | Python 3 with python3-gi, GTK, WebKit2GTK and the AppIndicator library, installed by apt from the .deb; Chrome or Chromium recommended |
| Windows | .NET Framework 4.8 (built into Windows 10 and 11) and the WebView2 Runtime; without WebView2 the window opens in a compact Edge window. The fallback .zip needs only the built-in PowerShell |

## Building the macOS app

On a Mac with Apple's Command Line Tools (`xcode-select --install`), once per company:

```bash
bash server/menubar/macos-app/build.sh https://your-board-address auto "AI Worker"
```

This writes the board's address into the app before signing it and makes `server/menubar/macos-app/dist/AI-Worker-menu-bar-mac-app.zip`. Copy the zip to the server and set `MENUBAR_MAC_APP` to its path. People who only use the app need nothing installed.
