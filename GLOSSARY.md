# AI Worker

AI Worker measures how a team uses AI tools: a plugin on each computer sends its numbers to the board, which adds them up per person, office and day. The words below name the things the code and the docs keep coming back to.

## Sending numbers

**Send**:
One message of a computer's numbers to the board, on `/ingest` or through the Go receiver.
_Avoid_: post, upload, report

**Hour**:
The numbers of one computer for one clock hour and one kind (`ledger`, `tasks`, `blocks`), stored as one row of `device_hours`.
_Avoid_: bucket, slot

**Book**:
All the hours the board holds of one computer.
_Avoid_: history, record (a record is the computer's state without its hours)

**Whole book**:
A send that carries every hour of the computer's book, so an hour it leaves out is gone.
_Avoid_: full sync, snapshot

**Changed hours**:
A send that carries only the hours that changed since the last one the board took; an hour not sent stays as it is, an empty one removes it.
_Avoid_: delta, diff, patch

**Row**:
What the Go receiver hands the board for one computer in a batch: one or several sends put together.
_Avoid_: record, entry

## Order of sends

**Stamp**:
The time a send is ordered by: its `seq` when the plugin numbers its sends, else its `updatedAt`. Each hour keeps the stamp of the send that wrote it (`sent_at`).
_Avoid_: timestamp, version

**Older hour**:
An hour of a send left as it was because the hour held was written by a send with a newer stamp; counted on the Admin page.
_Avoid_: stale hour, rejected hour, conflict
