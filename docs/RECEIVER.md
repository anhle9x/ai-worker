# The receiver in Go (optional, for large organisations)

[Tiếng Việt](RECEIVER.vi.md) | English <!-- i18n-allow -->

A small company does not need this page: the Python server takes every send itself. The receiver in `receiver/` is a second program, written with the Go standard library only, for an organisation with many thousands of computers. It takes the computers' sends on an address of its own over TLS, answers them at once, and hands them to the Python server in batches. Python stays the record: logins, roles, the board, the history and the SQLite files are unchanged.

**What this first stage does and does not do.** It takes sends correctly and gives Python the same records Python would have written itself; tests hold the two to that. It also serves the boards their live numbers, per branch or for the whole organisation, on `/live` (section 3, "The live feed"), and the board's page opens that feed when it is set up. On Linux with 4 vCPU and 8 GB it carries 40,000 computers sending `v: 2`, the format of the plugin from 0.50.15 on, even after a `kill -9` of the receiver and of Python (section 5). The plugin sends to the receiver only once the server tells it where (`ingestUrls`, "Which computers send to the receiver" below), so nothing changes until `RECEIVER_INGEST_URLS` is set.

## 1. How a send goes

| The send | What the receiver does |
|---|---|
| With the computer's own key (`awd1.…`), not due for renewal | Checks the key, cleans the send, puts it on the hours of today it holds for that computer, answers, and puts it on the one row that waits for Python for that computer |
| With the shared `INGEST_KEY`, with a key due for renewal (older than 30 days, or issued before `--rotate-device-secret`), or bytes the receiver is not sure Python reads the same way | Passes it to Python as it came, with the computer's real address; Python's answer goes back with the receiver's `boot` in place of Python's |

- The name and the account the computer claims are dropped; Python fills them from the person the computer enrolled as (`identities`).
- The receiver never trusts an `X-Forwarded-For` from the computer: it gives Python the address of the socket.
- The records of work handed to helpers, the IP history and the history of the board are written by Python, as for a send on `/ingest`. The board (`/data`) is kept 5 seconds instead of 0.5 (`VIEW_CACHE_SECONDS`), one build serves every role, and the old board is given while the next is built, as long as it is at most 15 seconds old, so a new name or branch shows 5 to 7 seconds later; the numbers come live from the receiver. The history of the board is written by the round that looks at everyone every 30 seconds, not after each batch, so a change comes into it up to 30 seconds later (`RECEIVER_FAST_APPLY=0` writes it after each batch again). A computer whose state only changed has its `devices` row written up to a minute later (every 30 seconds, and when the service stops), so after a `kill -9` the table may be a minute behind on what the computers are doing, never on who they are or what they spent; they all send again within seconds.
- A computer that Python asks for its whole book (`needFull`), one sent out of order, or a whole book sent again within an hour is handled exactly as Python does (`save_ingest`).
- The answer to a send has the same fields as Python's, with the receiver's own `boot`: rows not yet written are lost if the receiver stops, and a computer that sees `boot` change sends its latest hours again.

## 2. What the receiver copies from Python, and how they are kept the same

The cleaning of a send is the boundary of what reaches the board. The receiver copies it from `server/board/devices.py`: `clean_payload`, `clean_delegations`, `merge_hours`, `save_ingest`'s choices, money in whole `usdMicro`, and the totals per day of `add_up_hours`. Four details matter and are copied on purpose:

- the order of the keys of a JSON table, and a key that comes twice keeping its first place and its last value (a Python `dict`);
- a number without a dot or an exponent is a whole number, any other is a float, and the two stay apart;
- `round` rounds half to even (`math.RoundToEven`);
- hours are text keys, sorted by their number with a stable sort.

Anything the receiver is not sure Python reads the same way (a lone half of a UTF-16 pair, a byte order mark, NaN, a nesting deeper than 200) goes to Python as it came.

Three checks keep the two the same:

1. **The shared sample** `tests/contract/ingest-v2/cases.json`, played by the Python server (`server/test_contract.py`) and by the receiver (`receiver/internal/clean/contract_test.go`).
2. **A random test with Python as the judge**: `tests/contract/ingest-v2/fuzz_judge.py` makes random sends and cleans them with the server's own code; the Go test cleans the same bytes and must get the same, keys in the same order. `FUZZ_SEED` and `FUZZ_COUNT` change the seed and the number.
3. **While it runs**, the receiver hands `RECEIVER_CHECK_PERCENT` of the sends (default 1) to Python as they came as well; Python cleans them again and counts any difference (`checked`, `mismatches` in the policy below, and a line in the log).

Python also cleans every row again when it writes it, so its own cleaning stays the boundary.

The live numbers (`receiver/internal/live`) copy what the board makes of a person: `is_fresh`, `status_of`, and the parts of `group_by_person` and `_raw_data` behind `status`, `openSessions`, `working`, `waiting`, `delegating`, `tools`, `usdToday`, `tokensIn`, `tokensOut`, `tasks` and `updatedAt`. A fourth check holds them to it: `receiver/internal/ingest/live_test.go` runs the real Python server inside `tests/contract/ingest-v2/view_judge.py`, plays the shared sample through the receiver (moved to a few days ago, each run a person of its own), and after each step compares the receiver's rows with `role_view` from that server's memory, at the moment of the send, just before and after the computer goes offline, and on the next day; a second test does the same for every status, a connector with two tools and the totals of each branch.

## 3. Between the receiver and Python

The receiver calls the Python server on this machine (`RECEIVER_WEBHOOK`, default `http://127.0.0.1:8788`). The paths below exist only with `RECEIVER=1`, only for a direct call from this machine (no forwarding header) and only with the internal code from the file of secrets; anything else gets 404, as if the path were not there.

| Path | What |
|---|---|
| `POST /internal/rows` | A batch: `{"src", "boot", "seq", "rows": [...]}`. Each row is `{"k": ["m", device], "at": ms, "kind", "ip", "v", "stamp", "stamps"?, "raw"?}`: `kind` is `v1`, `hours`, `full` (what the receiver applied) or `delegations` (only the records of work, for a send whose numbers were not written); `v` is the cleaned send in the format it came in. Since protocol 2 (`proto` in the policy) a batch holds at most one row per computer: the sends of a computer between two batches are put together into one row, the newest state with every hour sent since (the newer send of an hour wins, an empty one still removes it, changed hours after a whole book go on that book) and the records of work of all of them, so Python writes once what it would have written send by send. Since protocol 3 each hour keeps the time of its send (`seq`, else `updatedAt`): `stamp` is the time of the row's main send (its whole book, or its first send of changed hours) and `stamps`, `{kind: {hour: time}}`, the time of each hour that came from another send, there or gone. Python writes each hour only over an older one (`board/order.py`), so an hour of an older send in the row never writes over a send that went straight to Python in between. A row without `stamp` (protocol 2) takes the time of its send for every hour. A row of kind `check` carries one send as it came (`raw`) and as the receiver cleaned it (`v`), for the third check only: Python compares them and writes nothing (at most 1,000 wait, past that they are dropped). Python writes the whole batch in one transaction, each row behind a savepoint of its own, and answers `{"ok", "seq", "needFull": [...], "unknown": [...], "incomplete": [...], "bad": [...]}`: `bad` names rows that failed and were left out alone (the receiver reads that computer's book again), `incomplete` computers whose person has no email or no name yet (the receiver passes on their next send that carries one, so Python fills it in and issues a key for the new person). The receiver keeps the batch until its `seq` is answered and sends that same batch again otherwise, never changed; the sends that come meanwhile wait for the next one. A batch with a `seq` already written is answered and not written twice. While Python does not answer, at most one row per computer waits, plus the batch on its way, and every send is still answered 200 |
| `POST /internal/ingest` | A send passed on as it came, at most 16 at once: past that the computer is told at once to come back (503 with `Retry-After`). The computer's `Authorization` is in `X-Receiver-Authorization` and its address in `X-Receiver-Client-Ip`; Python checks the key exactly as on `/ingest` |
| `GET /internal/policy?since=<seq>&boot=<boot>` | The numbered policy, asked every 15 seconds: revoked computers, `renewBefore`, the pace the computers are told, `SHARED_KEY_MODE`, the limits, and `written`, the computers Python wrote itself since `since` (the receiver drops the book it holds for them). `reset: true` after another start of Python: the receiver drops every book. `proto: 3` is the version of this protocol |
| `GET /internal/devices?after=<device>&limit=<n>` or `?device=<id>` | The hours of today and later of each computer, a page at a time when the receiver starts, or one computer's when it is needed: the receiver keeps no more. While the pages are read, the table of people is asked once so the boards have their rows, the batches wait until the books are loaded (Python writing them had no time left for the pages), and a computer whose book is not read yet is answered 503 `starting` with a `Retry-After` of 15 to 45 seconds instead of having its book asked alone, so Python is not asked tens of thousands of times while it gives the pages. Each record also has the state the live numbers need (`openSessions`, `working`, `waiting`, `delegating`, and `tools` for the connector), `seq`, the number of the computer's last send (the receiver's window of a minute compares it, as Python's does), and `stamps`, the time of the send that wrote each hour, so an older send reaching the receiver late never replaces a newer hour of the live numbers either; no name, email or address. `&whole=1` with `device` gives that computer's whole book, for the tests that compare the receiver with Python |
| `GET /internal/people?since=<seq>&boot=<boot>&limit=<n>` | The table of people (below): what changed since `since`, in the order of the changes, at most `limit` (5,000) at a time: `{"boot", "reset", "seq", "more", "people": [{"device", "row", "scope"}], "gone": [...]}`. Asked when the receiver starts and every 15 seconds, so a person who moves to another branch is in the right place within 10 to 25 seconds. While `more` is true the receiver asks again with `since=seq`, adding `&loading=1` while it loads the whole table after a `reset` (another start of Python, or a number Python can no longer answer from: it then drops the table it holds) |

### The file of secrets

With `RECEIVER=1` the Python server writes `KEYS_DIR/receiver-secrets.json` (or `RECEIVER_SECRETS_FILE`) at every start and at every `--rotate-device-secret`: written to a temporary file and renamed, readable by the server's account only (0600).

```json
[
 {"kid": "…", "alg": "HS256", "org": "…", "secret": "…", "since": 0},
 {"kid": "internal", "alg": "internal", "secret": "…"},
 {"kid": "…", "alg": "ticket", "secret": "…"}
]
```

The signing secrets come newest first; an older one stays while a key it signed may still be alive. The last one signs the tickets of the live feed (below): a secret of its own, never a computer key's, so a ticket cannot be used as a key or a key as a ticket; `--rotate-device-secret` turns it too. The receiver reads the file again when it changes, and when a key names a `kid` it does not know (at most every 10 seconds). Whoever holds this file can make a key for any computer and send numbers as it, but cannot read any data: keep it on the server, and run the receiver as the same account as the webhook.

### Rows and scopes

The receiver sends the board live numbers per branch. For that, each person on the board has the code of their row, and the board can be read one branch at a time:

- **The code of a row** (`row` on each person of `/data`, only with `RECEIVER=1`): 12 characters, an HMAC of the person (`person_key`: the account and the name) with the same secret as the wall's code for an email (`wall_alias_secret` in the keys database) under another label. It is the same for every role, after a restart and in every process, and gives back neither the email nor the name, so the live numbers can be put on the right row without the wall ever seeing an email. People are joined on this code, never on the `pid` inside a computer's key.
- **The live numbers** (`receiver/internal/live`): the receiver keeps each computer's state as its last send left it (the time, the session counts, the connector's counts per tool, the tasks being handed to helpers) and its totals per local day, and adds them up at a given second into one row per code, as the board does: `row`, `branch` (its scope), `status`, `openSessions`, `working`, `waiting`, `delegating`, `tools`, `usdToday` (rounded as the board rounds it, with `usdMicroToday` beside it), `tokensIn`, `tokensOut`, `tasks`, `updatedAt`; and per branch the fields of `branchTotals`. A computer is on a row only once the table of people names it. When Python writes a computer itself (a send passed on, `written` in the policy, a row it left out or did not take), the receiver reads that computer's record again after the next batch or policy, unless rows of it still wait, so the live numbers never go back to an older state; after another start of Python it reads every book again, except the books of computers whose rows still wait here: those are read once the rows are written, and such a computer is told to come back meanwhile, so the book read never lacks hours this side already took. The live feed below sends these numbers to the boards.
- **The table of people**: each computer → (the code of its person's row, the scope that row is in: the id of its branch, or `""` for none). Python builds it from what the board shows, at most every `RECEIVER_PEOPLE_SECONDS`, when the receiver asks; every change has a number of its own. It holds no name, no email and no address.
- **`/data?scope=`** (any logged-in role, with or without `RECEIVER`): `scope=org` is the whole organisation, with `branchTotals` (for each branch and `""`: people, online, working, waiting, open sessions, cost today, tokens; a person waiting in one session while another runs is counted in both working and waiting) and its people only while there are 500 or fewer; `scope=branch:<id>` is one branch (`branch:` alone: the people in no branch), 500 people a page in the order of their names, `&page=<n>` from 0, with `page`, `pages`, `peopleTotal` and `pageNames` (the first and last name of each page). Both are cut from the same view of the same role as plain `/data`, which stays as it was: without `RECEIVER` and with any number of people, it is byte for byte what it was before.

### The live feed

The board gets its numbers from the receiver as they change, instead of asking the Python server every second. Python still says who may see what: names, emails and addresses still come only from `/data`, and the feed carries only numbers and the code of each row.

1. **The ticket.** The board's page asks the Python server `POST /sse/ticket` with `{"scope": "org"}` or `{"scope": "branch:<id>"}` (any scope `/data?scope=` takes; every role that may read `/data` may read every scope). Only a logged-in session, only from the board's own page (the `Origin` must be there and be the board's), only with `RECEIVER=1` and both `RECEIVER_LIVE_URL` and `RECEIVER_BOARD_ORIGIN` set; otherwise 404. The answer is `{"ticket", "scope", "expiresAt", "live", "snap"}`. A ticket is `awt1.<kid>.<role>.<scope in base64url>.<sid>.<expiry in seconds>.<signature>`, an HMAC-SHA256 with the tickets' secret of the file of secrets. It lives 5 minutes. The `sid` is made from the session with that secret: it gives back neither the session nor the name.
2. **The feed.** The page opens `GET <RECEIVER_LIVE_URL>/live?t=<ticket>&scope=<scope>` with `EventSource`, or `GET …/live/snap?…` for the same numbers once as JSON. The receiver checks the signature, the expiry, that the scope asked is the ticket's, that the `Origin` is `RECEIVER_BOARD_ORIGIN` (which only the answer lets read it), and that the session is still open; otherwise 401 or 403, or 503 while it has no policy from Python yet.
3. **The events.** `hello` (`scope`, `role`, `expiresAt`, `beatMs`, `tickMs`), then `snap` with the whole scope, then every second at most `d` with the rows that changed, each with its whole value, and `gone`, the codes of the rows that left. A branch carries its people's rows (`rows`, the fields of the live numbers above); the whole organisation carries the totals of each branch only (`branches`, the fields of `branchTotals`). A quiet feed gets a comment every 15 seconds so proxies keep it open. At the end of the ticket the receiver sends `bye` (`{"why": "expired"}`) and closes: the page asks a new ticket and opens again, and gets the whole scope again.
4. **Logging out.** The receiver asks the policy every 15 seconds; it names in `endedSessions` the sessions given a ticket that still lives but are no longer open (logged out, expired, their account or TV screen removed, their role changed). The receiver ends their feeds with `bye` (`{"why": "ended"}`) at the next tick, so a feed is cut within about 20 seconds of logging out. `boardOrigins` in the policy is the board's origin.
5. **Built once, read by every board.** Each second the receiver adds up every computer once, and builds each scope that a board reads (or asked on `/live/snap` in the last 30 seconds) once, for every board of that scope: the JSON of each row is made once, and a board keeps only the number of the last change it sent. A board that reads slowly therefore holds no queue: it gets, when it can take it, what changed since; one write may wait 10 seconds, after which the feed is cut. A board further behind than the rows that left two minutes ago gets the whole scope again. At most 5,000 feeds are open at once (503 past that).
6. **Timeouts.** A send has 30 seconds to be read and answered (`ReadTimeout`, `WriteTimeout`); a feed sets its own deadlines in their place, so it is not cut at 30 seconds.
7. **The board's page** (`server/static/page.js`, drawn by `ops.js`). At start it asks a ticket for its scope: a 404 (no `RECEIVER`, or no `RECEIVER_LIVE_URL` and `RECEIVER_BOARD_ORIGIN`: a small company) and the page asks plain `/data` every second as it always did. Otherwise it reads one scope at a time, chosen in a picker at the top of the list (**Whole organisation**, each branch, **Not in a branch**, and the page of a branch of more than 500 people, offered by its first and last name) and kept in the address (`?scope=branch:<id>&page=<n>`), so a reload or a TV screen stays on it. The whole organisation shows the totals of each branch: one card per branch in place of the diagram, one row per branch in the list, the counts and the cost of the organisation added up from them; a card or a row opens that branch. A branch shows its people as the board always did. The page asks `/data?scope=` every 20 seconds for the names and the rest of the board (the 24-hour charts, the events, the models), opens the feed with its ticket, and puts the numbers of each `d` over the person with the same `row` (or the branch with the same `id`); a row of the feed that is not on the page is left out, and a row in `gone` loses its numbers until the next `/data` says whether the person is still there. On `bye` it asks a new ticket and opens again; on an error it waits 1 second, then twice as long each time, at most 30. While the whole organisation still lists its people (500 or fewer) the page keeps asking `/data?scope=org` every second and opens no feed, since the feed of the whole organisation carries only the totals of the branches.

With `RECEIVER_LIVE_URL` set, the board's pages allow that address in `connect-src` of their `Content-Security-Policy`; without it they are as before. The feed goes straight to the receiver, not through Caddy. The tickets are held to the same format by a shared sample (`tests/contract/ticket/cases.json`, made by the server, checked by `receiver/internal/feed`), and the receiver also checks tickets that the server's own code gave (`keys_judge.py`).

## 4. Settings

On the Python server (`/etc/ai-worker.env`):

| Setting | What |
|---|---|
| `RECEIVER` | `1` opens the paths above and writes the file of secrets. Empty: off |
| `RECEIVER_SECRETS_FILE` | Where the file goes; empty is `receiver-secrets.json` in `KEYS_DIR` |
| `RECEIVER_CHECK_PERCENT` | Percent of sends the receiver also hands over as they came, for the third check (default 1) |
| `RECEIVER_PEOPLE_SECONDS` | How often at most the table of people is built again, in seconds (default 5; the receiver asks every 15) |
| `RECEIVER_LIVE_URL` | The receiver's address as the boards reach it, for example `https://ingest.example.com`: it goes into the tickets' answer and the pages' `connect-src`. Empty: no live feed |
| `RECEIVER_BOARD_ORIGIN` | The board's own address, for example `https://board.example.com`: the only page the receiver lets open the feed. Empty: no live feed |

On the receiver (its environment):

| Setting | What |
|---|---|
| `RECEIVER_LISTEN` | `IP:port` to listen on. Required, and the IP must be said: the receiver never listens on every address by default |
| `RECEIVER_TLS_CERT`, `RECEIVER_TLS_KEY` | The certificate (full chain) and its private key, as files. Read again when they change, so a renewal needs no restart |
| `RECEIVER_SECRETS_FILE` | The file of secrets above. Required |
| `RECEIVER_WEBHOOK` | The Python server on this machine; only `http://127.0.0.1:…`, `http://[::1]:…` or `http://localhost:…` |
| `RECEIVER_BATCH_MS` | How often the rows go to Python: 1000 (the default) for a small organisation, 5000 to 10000 for a large one |
| `RECEIVER_MEMORY_MB` | Memory the receiver keeps under, given to Go's runtime: by default 40% of the machine's memory (about 3 GB on 8 GB), leaving the rest to Python; `0` for none. A `GOMEMLIMIT` already set is kept Out of it, a quarter bounds the bodies being read and cleaned (16 bytes for each byte of a body) and 35% the rows waiting for Python, a whole book kept encoded; past either a send is answered 503 with a `Retry-After` of 5 to 15 seconds. When the memory still in use (the heap live at the last collection and the stacks, not the garbage waiting to be collected) passes 80% of it, every new send is refused until under 70%, since Go only aims at the limit. |
| `RECEIVER_MAX_CONNECTIONS` | Computers connected at once; past it a send is answered 503 with a `Retry-After` of 30 to 90 seconds and its connection closed, and the log says once a minute how many were refused. By default the memory limit over 64 KB a connection (about 48,000 on 8 GB); `0` for no ceiling. Boards' live feeds and `/health` are let through |
| `RECEIVER_SENDS_PER_SECOND` | Sends the machine is to answer each second, by default 2,500 a processor (measured: 4 processors filled at 20,000 a second with Python beside them). Past it, the answer's `minGapMs` asks every computer to send less often: the connections open over this number, in whole seconds, at most 120; for example 5 seconds with 50,000 computers on 4 processors. The live numbers then come that much later. `0` keeps the server's gap |

When Python is slower than the computers send, the beat stretches by itself: the next batch goes only once Python has answered the last one, the sends of one computer meanwhile wait as one row, and the batches stay in the order of the computers' ids. `GET /health` on the receiver says how many rows wait (`queued`), how long the oldest has waited (`waitSeconds`), and `behind: true` once that passes 60 seconds, also written once to the log. The numbers on the boards still come live from the receiver.

The receiver speaks HTTP/1.1 only (HTTP/2 costs more here), waits at most 10 seconds for the headers of a request, reads at most 256 KB of a body, and keeps an idle connection 5 minutes, a little longer than a quiet computer's 4 minutes between sends.

### Which computers send to the receiver

- `RECEIVER_INGEST_URLS` lists up to 4 `https` addresses of the receiver. Empty (the default): every computer sends to the webhook, as before.
- Which computers are told: `RECEIVER_INGEST_DEVICES` (their ids, comma separated) and `RECEIVER_INGEST_PERCENT` (0 to 100, by a stable hash of the id, so raising it only adds computers). Start with a few computers of the IT team, then 5, 25, 100, with `RECEIVER_CHECK_PERCENT=100` while trying.
- The server tells a chosen computer only when it sends `v: 2` (a send of `v: 1` carries the whole book of 8 days, and ran the receiver out of memory at 40,000 computers, section 7), in its answer to a send made with the computer's own key (`ingestUrls`, `ingestTtlMs`, [DATA-MODEL.md](DATA-MODEL.md)); the shared key never goes to the receiver. The plugin keeps the address `RECEIVER_INGEST_TTL_SECONDS` (default an hour, moved by up to a fifth), then asks `GET /ingest/route?v=2` on the webhook, which writes nothing (without `?v=2` the answer is always an empty list); an empty list sends it back to the webhook.
- The plugin trusts an address only over `https`, without a path, and on the webhook's own host, under the webhook's parent domain (`ingest.example.com` beside `board.example.com`, never a public suffix such as `com.vn`), or listed in the package's `sharing.ingestHosts`. The certificate is a public one for that name (section 5).
- When the receiver cannot be reached, answers without `Retry-After`, or refuses the key, the plugin sends to the webhook instead: that send after a wait under 30 seconds at random, so a whole office that lost the receiver together reaches the webhook spread out, and the next ones there for about a minute, doubling up to ten, each spread by up to half. When the webhook itself does not answer, or answers 5xx without `Retry-After`, the sends wait 5 seconds, doubling up to 5 minutes, spread the same way. A busy receiver (429 or 503 with `Retry-After`) is waited for, never poured onto the webhook it shields.
- To turn it off slowly, empty the settings: the computers come back within one time of keeping the address. At once: stop the receiver, and they come back on their next send.
- A computer that sent straight to the webhook while an older row of it waited in a batch keeps the newer hours: each hour of the row keeps the time of its send, and Python writes none over a newer one, even after it started again (its records of work handed to helpers are still logged).

## 5. Setting it up

**How big a server.** Measured on Linux (Hetzner CPX32: 4 vCPU, 8 GB) with the receiver and Python on the same machine, fake computers keeping a connection open and sending every 2 seconds (each send changing money: the worst case), and the boards reading the live feed and `/data` ([BENCHMARK.md](BENCHMARK.md#on-linux-with-the-go-receiver)):

| Computers connected at once | Server | Measured |
|---|---|---|
| up to 40,000 | 4 vCPU, 8 GB | live numbers p99 1.5 s, CPU 56%, memory 6.0 GB; the receiver asks for a send every 4 s |
| about 50,000 | 4 vCPU, 8 GB | live numbers p99 1.7 s, CPU 67%, memory 6.4 GB; a send every 5 s; Python's tables and `/data` up to a minute behind (`behind`) |
| 40,000 sending `v: 2` as the plugin of 0.50.15 does, the receiver then Python killed with `kill -9` | 4 vCPU, 8 GB | about 12,850 sends a second taken, p99 0.15 to 0.4 s; the receiver back to full speed about 2.5 minutes after its restart; the money of every person the same as the computers held, to the micro-dollar, right after the run (receiver 0.50.16, 2026-11-25) |
| more than about 49,500 | 4 vCPU, 8 GB | the rest are told to come back (503, `RECEIVER_MAX_CONNECTIONS`), nothing lost |
| 40,000 as above, Caddy with TLS on the same machine in front of Python (the boards and the sends that fall back go through it) | 4 vCPU, 8 GB | the same as without Caddy while nothing fails; memory up to 7.4 of 7.7 GB (Caddy 0.2 to 0.5 GB). After a `kill -9` of the receiver and of Python, Python wrote about 10 times slower with too little memory left to cache its database, so the board's tables and `/data` fell up to 10 minutes behind; the live numbers stayed on time and no money taken was lost (2026-11-25). With Caddy on the machine, take 16 GB for 40,000 computers |
| 100,000 | 8 vCPU, 16 GB | not measured: the ceilings scale with memory and processors, Python's writes do not |

Computers that are idle send every 4 minutes, so an organisation counts here by the computers working at once, not by those installed.

Where it listens was decided with the design: a **second public IP on the same server, port 443 of that IP**. The receiver and Python stay on one machine, so the file of secrets and the internal paths stay local; port 443 gets through company proxies; moving the receiver to a machine of its own later is a change of DNS.

1. At the server's provider, add a second public IP to the server.
2. In the Caddyfile, add `default_bind <first IP>` so Caddy keeps to the first IP. Caddy's automatic HTTP-to-HTTPS server does not follow that option, so also add an empty `http://` site bound to the first IP (see caddyserver.com/docs/caddyfile/options).
3. Add a DNS A record for `ingest.<your domain>` pointing to the second IP.
4. Get a certificate for that name with an outside tool, checked over DNS (nobody listens on port 80 of the second IP).
5. Open port 443 of the second IP in the firewall.
6. Build the receiver (`cd receiver && go build -o /opt/ai-worker/ai-worker-receiver .`), set `RECEIVER=1`, `RECEIVER_LIVE_URL=https://ingest.<your domain>` and `RECEIVER_BOARD_ORIGIN=https://<the board's domain>` in `/etc/ai-worker.env` and restart the webhook, then run the receiver with systemd as the `ai-worker` account with `AmbientCapabilities=CAP_NET_BIND_SERVICE`, never as root. In the unit, `MemoryMax=` a little above `RECEIVER_MEMORY_MB` and `OOMScoreAdjust=500`, so if memory still runs out the kernel kills the receiver, which restarts in seconds, and never the Python server. Run `install.sh` again after setting `RECEIVER=1`: the webhook's own ceiling goes from 1 GB to 45% of the machine, since Python then holds the books of every computer (2 to 3.5 GB at 100,000); `WEBHOOK_MEMORY_MB` in the env file sets it by hand.
7. Once every computer has its own key, set `SHARED_KEY_MODE` to `known-only` or `off`.

Not known yet: whether your provider gives a second IP, and at what price (otherwise port 8443, then measure how many computers it stops).

### Trying it with a few computers

Before the whole organisation, try it for about a week with a few computers of the IT team. Nothing changes for the others.

1. The server on 0.50.16 or later, and the plugin on 0.50.15 or later on the computers chosen (`/update` on each): an older plugin sends `v: 1` and is never sent to the receiver.
2. Set up the receiver as in steps 1 to 6 above, and check from a computer in the office that `https://ingest.<your domain>/health` answers.
3. Find the ids of the computers chosen on the Admin page, **Computers and their keys** (`device-` and 16 letters and digits).
4. Add to `/etc/ai-worker.env`, then restart the webhook:

```bash
RECEIVER_INGEST_URLS=https://ingest.<your domain>
RECEIVER_INGEST_DEVICES=device-aaaaaaaaaaaaaaaa,device-bbbbbbbbbbbbbbbb
RECEIVER_CHECK_PERCENT=100
```

```bash
sudo systemctl restart ai-worker-webhook
```

5. Each computer chosen moves to the receiver after its next send to the webhook, within a few minutes while Claude Code is open. What to watch for a week:
   - the board shows these computers' numbers as before, and the Admin page shows no yellow line about the receiver being behind;
   - `sudo journalctl -u ai-worker-webhook | grep "cleaned differently"` finds nothing: with `RECEIVER_CHECK_PERCENT=100` every send is checked against Python's own cleaning (section 2);
   - the receiver's log (`sudo journalctl -u ai-worker-receiver`, or the name you gave its unit) has no line about the memory limit or about books it could not load.
6. To go back: empty `RECEIVER_INGEST_URLS` and restart the webhook, and the computers come back within `RECEIVER_INGEST_TTL_SECONDS` (an hour by default); at once: stop the receiver, and they come back on their next send.
7. Then widen with `RECEIVER_INGEST_PERCENT`: 5, 25, 100, a few days each, keeping `RECEIVER_INGEST_DEVICES`. At 100, set `RECEIVER_CHECK_PERCENT` back to 1.

## 6. Turning the signing secret

```bash
sudo systemctl stop ai-worker-webhook
```

```bash
sudo -u ai-worker env DATA_DIR=/opt/ai-worker/data KEYS_DIR=/opt/ai-worker/keys RECEIVER=1 python3 /opt/ai-worker/webhook.py --rotate-device-secret
```

```bash
sudo systemctl start ai-worker-webhook
```

A new secret signs every key from then on, and every computer gets a new key at its next send; the old secret still checks keys until 90 days have passed. If the file of secrets leaked, add `--drop-old`: the old keys stop at once and every computer enrols again with the shared key, so `SHARED_KEY_MODE` must not be `off` while they do. The receiver reads the new file by itself.

## 7. Known limits of this stage

- **The sizes of section 5 hold for sends of `v: 2` only**, which the plugin sends from 0.50.15 on, once the server answers that it reads it. A send of `v: 1` carries the whole book of 8 days: measured at 40,000 computers on 4 vCPU and 8 GB, the receiver took about 800 sends a second where the computers wanted about 20,000. So the server tells the receiver's address only to computers that send `v: 2` (section 4), and a computer still on an older plugin stays on the webhook.
- The receiver does not check the list of computers let send from any network (`OFFICE_NETS`, [INSTALL.md](INSTALL.md#sending-from-outside-the-office-chosen-computers)): the batches it writes through `/internal/rows` do not pass the webhook's check. Keep the receiver's address reachable from the office networks only.
- How big a server is in section 5. What is left at about 50,000 computers on 4 vCPU is Python's writes: with boards reading `/data` it writes about 1,650 rows a second there (5,100 with none), so its tables and the board's `/data` fall up to a minute behind while the live numbers stay on time. Before the ceilings the receiver ran out of memory at about 60,000 connections and was killed again after each start.
- When Python writes slower than the computers send, the rows wait at the receiver, one per computer, and nothing is lost; past a minute the receiver's `/health` says `behind` and the Admin page shows it in yellow. If it lasts, the machine is too small for the organisation: measured in a VM of 4 vCPU, Python writes about 10,000 rows a second with no board open and about half that with boards reading `/data` all the time.
- The table of people is built from the whole board each time the receiver asks: what that costs at 100,000 computers is measured with the rest on Linux.
- The live feed adds up every computer once a second, instead of keeping the sums up to date as the sends come. Measured on a Mac with an M-series chip at 100,000 computers, 500 people a branch: one pass 83 ms; one second with every branch and the whole organisation read by a board 175 ms in all, half of it making the JSON of the rows. The measurement on Linux (4 vCPU) decides whether the sums must be kept as the sends come.
- On the page of the whole organisation without its people, the 24-hour charts, the models and the quotas are empty: they are counted per person, so they show on the page of each branch.
- An amount above a billion dollars in one hour, sent only as `usd`, is held to the cent differently by Python when it cleans the row again; the third check reports it.
- The receiver holds of each computer only the time of its last send and its hours of today, as three numbers an hour: measured at 100,000 computers with all 24 hours each, 261 MB of Go's heap (about 2.6 KB a computer; 739 MB taken from the system). The whole book is Python's.
