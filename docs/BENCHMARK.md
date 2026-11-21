[Tiếng Việt](BENCHMARK.vi.md) | English <!-- i18n-allow -->

# Benchmark

How many computers one board server carries, measured, what happens past that, and what to do when you need more. Every number here comes from [`tests/load/load_test.py`](../tests/load/load_test.py); run it on your own server to get yours.

## In short

| | Before (0.49.1) | After (next release) |
|---|---|---|
| Server work for one send, 300 computers | 79 ms | 0.5 ms |
| Server work for one send, 10,000 computers | (not measured, 1.3 s at 5,000) | 0.6 ms |
| Building the board, 10,000 computers | (not measured, 1.4 s at 5,000) | 164 ms, at most once every 2 s for each role |
| 300 computers sending every 10 s, 30 boards open | Falls over: answers take 19–24 s, 20% of sends and 33% of reads cut off | p95 5 ms for a send, 43 ms for a read, 0 errors, 10% of one core |
| Sends per second it can take, 300 computers | about 12 | 400–600 |
| When more arrives than it can take | Every request waits until all of them time out | Sends and people not logged in get 503 with `Retry-After` at once; people logged in still get the board |

**One send no longer costs more as the number of computers grows.** Before, each send and each read of the board cleaned the last 8 days of every computer again, so the work grew with every computer added. Now each computer's last send is cleaned once and kept in memory.

**The limit of 300 computers (`MAX_DEVICES`) has not been raised yet.** A computer is one row: a person with a laptop, a desktop and Codex counts as three, so 300 computers is about 100 to 150 people. The code now carries far more, but the limit stays until the board is measured on a Linux server and large teams get a board page per branch (see [What is next](#what-is-next)).

## How it was measured

```bash
python3 tests/load/load_test.py --json load.json
```

```bash
python3 tests/load/load_test.py --scale 20,300,1000,3000,5000,10000
```

- The test starts the real server (`server/webhook.py`) on 127.0.0.1 in a temporary folder, in its own process, and talks to nothing else. It cannot be pointed at a real board.
- Each made-up computer sends what the plugin sends, in size and shape: 8 days of cost per hour, about 12 KB.
- Each open board reads `/data` every 10 seconds, as the page does.
- **office** runs: 20, 50, 150 and 300 computers, each sending every 10 seconds (three times the most the plugin does, which is every 30 seconds) or every 60 seconds (an ordinary day). One open board for every ten computers.
- **stress** runs: a fixed number of clients send, or read, again as soon as they get an answer, to find the ceiling.
- **scale**: past 300 computers the server refuses a new computer over HTTP, so this calls the server's own code in the same process and times one send and one build of the board.
- Each made-up computer enrols with the shared key and sends with its own key afterwards, as the plugin does. The stress and ceiling runs lift the limit of sends per computer (`INGEST_BURST`, `INGEST_PER_SECOND`), so they measure the server and not that limit.
- p95 means 95% of requests finished within that time.

Machine: a Mac with an Apple M-series chip, 15 cores, Python 3.15, server and test on the same computer.

## Results before the change (0.49.1)

| Computers | Every 10 s | Every 60 s |
|---|---|---|
| 20 | p95 16 ms, CPU 3% | p95 17 ms, CPU 1% |
| 50 | p95 30 ms, CPU 11% | p95 29 ms, CPU 3% |
| 150 | p95 236 ms, CPU 67% | p95 77 ms, CPU 20% |
| 300 | falls over (see above), CPU 100% | p95 494 ms, CPU 67% |

The stress runs topped out at about 12 requests a second whether 4, 16 or 32 clients asked: one core was full.

| Computers | 300 | 1,000 | 3,000 | 5,000 |
|---|---|---|---|---|
| One send | 79 ms | 293 ms | 821 ms | 1,339 ms |
| One build of the board | 81 ms | 312 ms | 861 ms | 1,446 ms |

A profile at 300 computers put about 90% of the time in cleaning again data that had already been cleaned when it arrived.

## Results after the change

**office**, sends and reads, all with 0 errors and 0 late sends:

| Computers | Every 10 s: send p95 / read p95 / CPU | Every 60 s: send p95 / read p95 / CPU |
|---|---|---|
| 20 | 5 ms / 6 ms / 0.6% | 5 ms / 7 ms / 0.3% |
| 50 | 5 ms / 12 ms / 1.8% | 5 ms / 12 ms / 0.4% |
| 150 | 5 ms / 27 ms / 4.9% | 5 ms / 26 ms / 1.7% |
| 300 | 5 ms / 43 ms / 9.5% | 5 ms / 43 ms / 3.2% |

Server memory stayed between 42 and 64 MB.

**stress**, 300 computers known:

| Clients | Sends per second | p95 | Note |
|---|---|---|---|
| 4 | 629 | 12 ms | |
| 16 | 416 | 54 ms | |
| 32 | 429 | 101 ms | 34 of 13,000 got 503: the server was busy and said so |

Reads of the board ran at 2,700 to 6,000 a second, since every open board of one role now shares one build every 2 seconds. The errors in those runs are the test's own: one Mac opening thousands of new connections a second runs out of local ports. The server returned no error.

**scale**, after the change and after the hours added up once and the rows kept per person:

| Computers | One send | First build of the board after the sends | Next builds | A read that finds the kept build |
|---|---|---|---|---|
| 20 | 0.63 ms | 1 ms | under 1 ms | under 0.01 ms |
| 300 | 0.58 ms | 8 ms | 4 ms | under 0.01 ms |
| 1,000 | 0.53 ms | 25 ms | 14 ms | under 0.01 ms |
| 3,000 | 0.61 ms | 69 ms | 47 ms | under 0.01 ms |
| 5,000 | 0.57 ms | 167 ms | 77 ms | under 0.01 ms |
| 10,000 | 0.63 ms | 241 ms | 164 ms | under 0.01 ms |

A send stays flat. The first build after many sends counts every person again; later builds count only the people who changed, plus the parts of the board every person shows in (the 24-hour chart of each row, the branches). At 10,000 computers the history round every 30 seconds takes about 31 ms and the daily count every 5 minutes about 250 ms, most of it writing the day's rows. The board is built at most once every 2 seconds for each role, whatever the number of open boards.

## Past 10,000 computers

Measured the same way (`--scale`), with `MAX_DEVICES` raised for the test:

| Computers | One send | Next builds of the board | Start (load and clean every computer) | Memory |
|---|---|---|---|---|
| 10,000 | 0.8 ms | 154 ms | 3.4 s | 1.5 GB |
| 30,000 | 0.7 ms | 596 ms | 11 s | 4.4 GB |
| 50,000 | 0.7 ms | 1.0 s | 19 s | 7.3 GB |
| 100,000 | 0.8 ms | 2.1 s | 40 s | 14.6 GB |

A send still costs the same. Memory does not: each computer's 8 days of hours kept as Python dicts take about 150 KB, so 100,000 computers need 14.6 GB and 40 seconds to start. This is the limit of the present design, not of a send.

The ceiling of one server process (`--ceiling`, 8 load processes):

| What | Answers per second | Server CPU |
|---|---|---|
| `/health` alone, the HTTP layer with nothing behind it | over 4,500 | about 65% of one core |
| Sends of 12 KB | 650 to 810 | about 95% of one core |
| Sends with 112 clients at once | 3,400 answered, 19,000 told 503 | the server stayed up |

The `/health` number is held down by the test itself: the server speaks HTTP/1.0, so every request is a new connection, and one computer opening thousands a second runs out of local ports. Caddy in front of the server would meet the same thing on Linux: without connections kept open between Caddy and the server, a few hundred new connections a second already use up its ports for a while.

100,000 computers sending every 30 seconds is about 3,300 sends a second, and 40 MB a second at 12 KB each. That is about five processes like this one on this Mac, and more on a small Linux server. So 100,000 computers need, in this order: a smaller send (only the hours that changed), a pace the server sets, a key per computer, the hours kept on disk with only the day totals in memory, connections kept open, and several processes that take sends. The plan and its measured goals are in [What is next](#what-is-next).

## What changed

- `DeviceCache` in `server/board/devices.py`: each computer's last send, cleaned once, kept in memory. The table is still the record: the cache is written together with it, loaded again when the server starts, and loaded again when another program such as `webhook.py --forget-device` changes the file (`PRAGMA data_version`).
- `hours_of` in `server/board/devices.py`: each computer's hours added up per local day once, when it is stored, and reused by the board, the history and the daily count instead of going through every hour of every computer each time. A local day is found by arithmetic, since the server's time zone is a fixed offset.
- `_person_row` in `server/board/devices.py`: each person's row of the board is kept until one of their computers sends or a moment that changes it comes: the next hour, the next local midnight, a computer going quiet, a connector's work going stale, a quota window resetting. A test compares kept rows with a fresh count across those moments.
- A send updates the rewind history of the person who sent only. The round every 30 seconds still looks at everyone, for computers that went quiet.
- `ViewCache` in `server/board/views.py`: the board is built at most once every `VIEW_CACHE_SECONDS` (default 2) for each role, and every board of that role gets the same bytes. A role never gets another role's build. A board asks every 10 seconds, so what it shows is at most 2 seconds older than before.
- `Load` and `Handler.shed` in `server/webhook.py`: past `BUSY_REQUESTS` (default 32) requests answered at once, a send or a request from someone not logged in gets 503 with `Retry-After: 30` at once. The plugin sends again at its next round. People logged in, devices with their own key and `/health` are still answered, and the log says once a minute how many were turned away.

## What these numbers do not show

- **A Linux server.** The board runs on Linux; a small cloud server is slower than this Mac. Run the test there before trusting these numbers for your size.
- **One address for many computers.** The test gives each computer its own address. A real office behind one public address shares the limit of 300 sends per address in 10 minutes: at one send every 30 seconds, about 15 busy computers behind one address reach it. This is a known limit until sends are counted per computer.
- **HTTPS and Caddy.** The test talks to the server directly, without TLS.
- **The test as the bottleneck.** The load comes from one Python process on the same computer. Past a few hundred requests a second the test, not the server, may be what tops out.

## Python, Rust or Go

Not a rewrite, for now. The measurements above show where the time went: cleaning the same data again and again, which a faster language would have done faster but still again and again. Fixed in Python, the server's own work for one send is about 0.5 ms. What is left is the HTTP layer of one Python process. Rust is memory-safe where C and C++ are not; Python already is. A rewrite would also give up what the server is built on: the standard library only, one command to install, code anyone in an IT team can read.

The signal to change: a sustained need above about 500 sends a second that more processes cannot meet. Even then only the part that takes sends would be rewritten, against shared test data that proves it cleans exactly as the Python one does. Go is the likelier choice there, for a single file to install.

## What is next

1. **Measure on Linux**, with a load generator in several processes and through Caddy with TLS.
2. **A board page per branch** for large teams, instead of every person in one answer.
3. **Raise `MAX_DEVICES`**, configurable, once 1 and 2 pass at that size.
4. **Past one process**, for organisations of 100,000 computers and more: a smaller send from the plugin (only the hours that changed), a pace the server sets, a key per computer, and several processes that take sends feeding one that serves people. This is planned, not built; it changes the format the plugin sends, so it is designed and measured before any of it ships.
