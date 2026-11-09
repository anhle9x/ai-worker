[Tiếng Việt](PERMISSIONS.vi.md) | English <!-- i18n-allow -->

# Permission model

Who can see and do what on the dashboard server. The rules live in one place: the route table at the end of `server/webhook.py` (`GET_ROUTES`, `POST_ROUTES`) and the gate `Handler.gate`. A path that is not in the table answers 404. The test `test_webhook.py` holds a copy of the table and fails if the two differ.

## 1. Who is calling

| Caller | Proves itself with | Role on the server |
|---|---|---|
| Employee computer (plugin) | `INGEST_KEY` in the `Authorization` header | None: may only send numbers and download signed updates |
| Admin | Account name + 6-digit OTP, then a session cookie (8 hours) | `admin` |
| Manager | Account name + OTP, session cookie (8 hours) | `viewer` |
| Wall account | Account name + OTP, session cookie (7 days) | `wall` |
| TV screen | Pairing key approved by an admin (30 days, renewed while used) | `wall` |
| Menu bar icon | Pairing key, approved by a manager with their own account and OTP, at most 2 computers per account | Always `wall` |
| Browser extension | Pairing key in the `Authorization` header, approved by an admin | Always `wall` |

The server does not trust the IP of a request unless the request comes through the local proxy (`TRUST_PROXY`). The office IP allow-list is enforced by Caddy or nginx in front, not by the webhook.

## 2. What each role sees

| Data | `admin` | `viewer` | `wall` |
|---|---|---|---|
| 3D office, status, cost, tasks, quota | Yes | Yes | Yes |
| Email | Yes | Yes | No: replaced by a short code that changes at each restart |
| Name that is an email or IP | Yes | Yes | No: shown as "Device xxxxxx" |
| Internal IPs, accounts typed by staff | Yes | Yes | No |
| Team plan spend | Yes | Yes | No |
| Computer groups with no name | Yes | No | No |
| Text board `/board` | Yes | Yes | No |
| `/admin` page and installers | Yes | No | No |

The fields each role receives are fixed in `server/board/views.py` (`COMMON_FIELDS_BY_ROLE`, `PERSON_FIELDS_BY_ROLE`). A field not listed there is never sent.

## 3. What each role can do

| Action | Path | Who | Extra check |
|---|---|---|---|
| Send numbers | `POST /ingest` | Computer with `INGEST_KEY` | The computer stays tied to the person of its first send |
| Download an update | `GET /releases/...` | Computer with `INGEST_KEY` | The computer checks the signature before installing |
| Name locations, mark the sales team, load the Team CSV | `POST /locations`, `/team-sale`, `/team-csv` | `admin` | Same-origin request |
| Create, delete, change role of accounts; end sessions | `POST /admin/accounts`, `/admin/sessions` | `admin` | Re-enter OTP, valid 5 minutes |
| Approve, rename, revoke TV screens and extensions | `POST /admin/tv-*` | `admin` | Re-enter OTP, valid 5 minutes |
| Reload a TV screen | `POST /admin/tv-reload` | `admin` | Same-origin request |
| Approve own menu bar icon | `POST /mini/pair` | Account with role `admin` or `viewer` | That account's OTP |

## 4. Guards

- **At least one admin:** the server refuses to delete or demote the last admin.
- **Wrong OTP:** 5 wrong codes from one address in 15 minutes lock that address. 20 wrong codes on one account in 15 minutes lock that account, so a stranger cannot lock the whole site.
- **Account limit:** 200 accounts, 20 TV screens, 300 computers.
- **Every refusal and every change is written to the audit log** (table `audit` in `board.db`), with who, role, IP and path. CSV content is not copied into it.
- **If every admin is lost:** someone with sudo on the server runs `sudo bash manage-otp.sh --rescue <name>` in the `server/` folder. See [USER-GUIDE.md](USER-GUIDE.md).
