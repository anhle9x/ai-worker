[Tiếng Việt](SECURITY.vi.md) | English <!-- i18n-allow -->

# Security policy

## Reporting a problem

Please do not open a public issue for a security problem: anyone could use it before it is fixed.

1. Report it privately on GitHub: the **Security** tab of this repository, then **Report a vulnerability**.
2. If that is not possible, send a direct message on Telegram to [t.me/anhle9x](https://t.me/anhle9x) and say you have a security report; details are then sent the way we agree.

Include what is affected (plugin, server, installer, menu bar), the version, and the steps to see the problem. Do not send real people's data.

## What happens next

- You get an answer within 7 days.
- A confirmed problem is fixed in the next release, and you are credited in the release notes unless you prefer not to be.
- Please keep it private until the fix is out, or 90 days at the latest.

## Supported versions

Only the newest release receives security fixes.

## What the project is designed against

AI Worker is designed to defend against these eight common web risks, from the OWASP Top 10 list of 2013. The code was reviewed with AI assistants and the main attacks were replayed on a test copy. No independent security firm has audited it, and no software can promise to have no flaws.

| Risk | What the product does | What remains |
|---|---|---|
| **Cross-Site Request Forgery (CSRF)** | The session cookie is `SameSite=Strict`. A request with a wrong `Origin` is refused, and admin changes also refuse a missing one. Sending numbers uses a key in a header, not a cookie | Older browsers without `SameSite` rely on the `Origin` check alone |
| **Cross-Site Scripting (XSS)** | Server pages escape values and page scripts insert data as text. Server pages send a Content-Security-Policy that allows scripts from the same site only | The policy allows inline styles. The on-computer page has no such policy; it shows only data from that computer |
| **Injection** | The server runs no shell commands, and its SQLite queries take values only as parameters, never as text joined into the query. File requests are checked against a fixed list or pattern. The plugin starts programs with a list of arguments. Text for ChatGPT goes through standard input, and Gemini is refused if it would start through a Windows `.cmd` or `.bat` launcher | A document can still try to steer a helper through the text it receives. ChatGPT runs in a read-only sandbox for this reason |
| **Broken authentication** | Each account has its own OTP key, and a code works once. Wrong tries are limited per IP and per account. Session tokens are random and expire; cookies are `HttpOnly`, and `Secure` over HTTPS. Changing accounts or TV screens needs the OTP code again | OTP is the only login factor, so keep the IP allow-list on |
| **Insecure direct object references** | Viewers and wall screens get one view filtered by role, with no way to ask for a record by ID. Actions on a chosen account or screen are for admins only | Viewers see everyone's numbers by design. Anyone with the shared send key can send under a name not yet tied to a device |
| **Missing function-level access control** | Every path is listed with its permission, and one gate checks them all. A path not listed is 404. A test pins what each role gets on each path. The server checks, it does not just hide buttons | A new path must be added to that table by whoever writes it |
| **Security misconfiguration** | There are no default accounts or keys, and the server will not start without `INGEST_KEY`. Behind Caddy it listens only inside the server. The service runs as its own user with limited rights; key and data files are private to it | You must set your own IP list, turn on HTTPS and keep the number of sudo users small |
| **Sensitive data exposure** | Chat content, file names and project names are never sent. Wall screens get no emails or internal IPs. TV sessions are stored as hashes, the log holds no keys, and files that look like secrets are recorded by name only | Without HTTPS the numbers travel unencrypted. OTP keys sit unencrypted on the server, readable by the service and by sudo users. The install package holds the send key |

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
