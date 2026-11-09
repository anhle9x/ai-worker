[Tiếng Việt](chrome-extension-spec.vi.md) | English <!-- i18n-allow -->

# Chrome extension for managers: specification

What a browser extension for managers must do: show who is waiting for an answer without keeping the board open. Built in `extensions/manager/` with server routes `/ext/...`; the code shows what runs, this document wins on what it must do.

## Goal

A manager sees at a glance, from any tab, how many staff are waiting for Claude's answer or for their own reply, and opens the board in one click. The extension never gets more data than a wall screen already gets, and no staff computer changes.

## Not in scope

- **Tracking staff in their own browser** (claude.ai on the web, other sites). It would mean reading other sites' pages and watching staff browsers: a separate decision about data policy, not this extension.
- **Changing anything on the server's data:** no admin actions, no approving screens, no editing names. The extension only reads.
- **Email addresses, internal IPs, account names.** It gets the wall screen's view, which leaves these out (`role_view`, role `wall`). The popup shows what a wall screen and the menu bar window show, including quota and cost today.
- **Working outside the company network.** The server only answers that network; outside it the extension says so and waits.
- **Firefox, Safari, mobile browsers.** Chrome and Edge only, because both run the same extension format (Manifest V3).
- **Publishing on the Chrome Web Store.** It is installed by hand from a folder the IT department hands out.

## Who uses it

| Role | Uses | Can do |
|---|---|---|
| Manager | The extension's icon and its small window | See the five tabs of the menu bar window (Waiting, Working, Quota, Cost today, Settings); change notifications and language; unpair; open `/board` |
| Admin | `/admin` on the board | Approve or revoke a paired extension, like a wall screen |
| Server | `/ext/request-code`, `/ext/poll`, `/ext/state`, `/ext/mini`, `/ext/data`, `/ext/unpair` | Hand out a pairing code, a part of the wall view for the badge, the menu bar window's page and the wall view for the popup; revoke the key when the extension unpairs itself |

## What it must do

| ID | Requirement | Where |
|---|---|---|
| F1 | On first use the extension asks for the board's address and shows a pairing code; it holds no password, no TOTP secret and no login cookie | `popup.js` (form), `startPairing` in `extensions/manager/core.js`; `/ext/request-code` in `Handler.tv_pair` |
| F2 | The extension works only after an admin approves its code in `/admin`, the same way a wall screen is approved | `TvPairing`, `Handler.tv_pair` (`/ext/request-code`, `/ext/poll`) in `server/webhook.py` |
| F3 | An admin can revoke the extension in `/admin`; within one minute it shows "not paired" and asks to pair again | `checkBoard` in `extensions/manager/core.js` (401 → not paired); `PERM_DEVICE_KEY` in `Handler.gate` |
| F4 | The icon's badge shows how many people are waiting for a reply; no badge when nobody is. The toolbar icon is a one-colour G, dark on a light toolbar and light on a dark one; the store, the extensions page and notifications use the blue G | `badgeFor` in `extensions/manager/core.js`, `setBadge` and `toolbarIcon` in `background.js`, `offscreen.js` (the `offscreen` permission, only to watch the light or dark mode) |
| F5 | The small window lists the people who are waiting or working, by the short name the wall screen shows, with how long they have waited. The popup shows the server's `waitingSince` (from `WaitTracker`, through `/ext/data`); the badge and notifications count from the first time the extension saw them waiting, since `/ext/state` sends no start time | Badge and notifications: `trackWaits` in `extensions/manager/core.js`, `ext_state` in `server/webhook.py`. Popup: the menu bar window (five tabs, drawn drop-downs and confirm card): `showMini` and `window.MiniApi` in `popup.js`, the copies in `extensions/manager/mini/`, `get_ext_mini` / `get_ext_data` (`page_mini(True, browser=True)`, `role_view`) in `server/webhook.py`; `render` in `popup.js` only when the board is older or cannot give the page |
| F6 | When a person has waited more than the set time, the manager gets one browser notification per wait, not one per minute | `dueNotifications` in `extensions/manager/core.js` |
| F7 | The manager can turn notifications off and set the wait time; the choice survives a browser restart | `cleanSettings`, `saveSettings` in `extensions/manager/core.js` (`chrome.storage.local`); the popup's Settings tab saves through `MiniApi.save` in `popup.js` |
| F8 | One click on "Open board" opens `/board` in a new tab, where the normal login applies | `MiniApi.openLink` in `popup.js` (`boardPath` in `core.js`), `openBoard` in `extensions/manager/background.js` for notifications |
| F9 | When the server cannot be reached (outside the network, server down), the badge turns grey and the window says so; it never shows old numbers as current | `checkBoard`, `badgeFor` in `extensions/manager/core.js` |
| F10 | The extension asks the browser for access to the board's address only, not to all sites. The board must be https; plain http only to `localhost` or `127.0.0.1`, for testing | `optional_host_permissions` in `extensions/manager/manifest.json`, `requestAccess` in `popup.js`, `normalizeBoardUrl` in `core.js` |
| F13 | "Unpair this browser", and pairing again over an old key, revoke the key on the server too (best effort; if the board cannot be reached the row stays in `/admin` for an admin to revoke) | `forget`, `startPairing` in `extensions/manager/core.js`; `Handler.ext_unpair` (`/ext/unpair`) in `server/webhook.py` |
| F11 | Words in the extension follow the browser's language, English or Vietnamese; the popup's Settings tab can choose another, kept in this browser, and the notifications, the icon's title and the pairing screen follow that choice too | `extensions/manager/_locales/en`, `_locales/vi`; `tx` in `server/webhook.py` for the popup (`/ext/mini?lang=`), `chosenLang` and `MiniApi.setLang` in `popup.js`, `pickLang` in `core.js`, `loadLang` in `background.js` |
| F12 | The server's audit log shows when an extension paired, was revoked, or asked with a revoked key, with the same detail as for a screen | `AuditLog`, `RevokedKeys`, `Handler.note_revoked_key` in `server/webhook.py` (field `kind: extension`) |

## Limits

| Limit | Value |
|---|---|
| How often it asks the server | Once a minute (every 5 seconds only while the popup shows a pairing code) |
| Default wait before a notification | 10 minutes (choices 5, 10, 15, 30, 60) |
| How long a pairing lasts | As for a screen: 30 days, renewed while used (`TV_SESSION_SECONDS`), up to a fixed ceiling (`TV_CEILING_SECONDS`); a change of network keeps it and is written to the audit log (`TvStore.touch`) |
| Pairing code valid for | 10 minutes (`TV_CODE_SECONDS`) |
| Browsers | Chrome and Edge, Manifest V3 |
| Data it can read | The wall view only (`role_view` with role `wall`) |
| Outside libraries | None |

## How it pairs

The extension uses the TV pairing flow (`TvPairing`, `TvStore`), but through `/ext/request-code` and `/ext/poll`: the pending key and the session travel in the JSON reply and the `Authorization` header, never in a cookie. A cookie would land in the manager's own browser and replace their login to the board. Requests are sent with `credentials: "omit"`. A paired extension reads `/ext/state` for its badge, which answers only people waiting or working, by wall name, with no email, IP or cost. Its popup is the menu bar window: it reads `/ext/mini` (the page, as layout and words only; no script from the board runs) and `/ext/data` (exactly `/data` for a wall screen), both with the same key, and runs its own copy of `mini.js`. The copies in `extensions/manager/mini/` must equal `server/static/mini.*`, and its `logo-black.png` and `logo-white.png` must equal `server/menubar/icons/generic-black.png` and `generic-white.png`; `node tests/extension/check-extension.js` fails when they differ.

In `/admin` the request card says "browser extension" and the TV screens table marks the row, so an admin can tell a laptop from a TV. Extensions count toward the limit of 20 screens (`TV_MAX`).

After 5 minutes without an answer from the server, the extension starts counting waits again, since it cannot know whether a wait went on.
