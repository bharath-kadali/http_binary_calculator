# Binary HTTP — Protocol Spec v1

A minimal binary request/response protocol over a single, persistent TCP
connection. One socket, every request. `bcurl` (client) never opens a
second connection; `bserve` (server) never closes the connection after
answering.

## 1. Fixed frame header (12 bytes)

```
 0        1        2        3        4        5        6        7
+--------+--------+--------+--------+--------+--------+--------+--------+
|Version | Type   | Flags  | HdrCnt |      Header Block Length (u32)    |
+--------+--------+--------+--------+--------+--------+--------+--------+
|                        Body Length (u32)                              |
+--------+--------+--------+--------+--------+--------+--------+--------+
```

| Field                | Width  | Meaning                                            |
|----------------------|--------|-----------------------------------------------------|
| Version              | 1 byte | `0x01`. A receiver seeing a version it doesn't handle may reject the frame — versioning is orthogonal to the frame-type skip rule below. |
| Type                 | 1 byte | `1`=REQUEST, `2`=RESPONSE, `3`=ERROR. Anything else is unrecognised (see §4). |
| Flags                | 1 byte | Reserved, always `0` in v1. Bit 0 is earmarked for a pipelining "more responses follow" ack if that stretch goal is implemented. |
| Header Count         | 1 byte | Number of entries in the header block. |
| Header Block Length  | 4 bytes, big-endian | Exact byte length of the header block that follows. |
| Body Length          | 4 bytes, big-endian | Exact byte length of the body that follows the header block. |

**Why these widths, defended:** HTTP/2 packs its header into 24/8/8/31 bits
specifically because it multiplexes many streams over one connection and
needs a stream ID; bit-packing there buys header size at the cost of a
shift/mask on every read. This project has no multiplexing — one frame is
answered before the next is sent (pipelining is optional, and even then
frames are still strictly sequential per connection) — so there's no
stream ID to budget bits for, and every field is byte-aligned instead:
cheaper to parse correctly, at a cost of 3 extra bytes per frame, which is
noise next to a typical body. Body Length gets the full 4 bytes (up to 4
GiB) rather than HTTP/2's 24-bit (16 MiB) cap because this protocol has no
frame-splitting mechanism to fall back on for a larger single response —
truncating that field would silently cap the file size the protocol could
ever serve.

## 2. Header block

Each of the `HdrCnt` entries is:

```
name_id (1 byte)  [name_len (1 byte) + name (ascii)]  value_len (2 bytes, BE)  value (utf-8)
```

If `name_id` is in the **static table** below, the name is just that one
byte — nothing else is sent. If `name_id == 0xFF`, a length-prefixed raw
name follows (1-byte length, then that many ASCII bytes), for anything not
in the table. This is HPACK's first two tricks (a static table of common
names, and length-prefixing for the rest) without HPACK's dynamic table or
Huffman coding — those are real complexity for a marginal win at this
message size, and are left as a stretch goal.

**Static table (10 entries, chosen for the names this project actually
sends):**

| ID | Name           | ID | Name         |
|----|----------------|----|---------------|
| 0  | Method         | 5  | Connection    |
| 1  | Path           | 6  | Status        |
| 2  | Host           | 7  | User-Agent    |
| 3  | Content-Length | 8  | Accept        |
| 4  | Content-Type   | 9  | Date          |

Value length is 2 bytes (up to 65535 bytes) — generous for a header value,
cheap compared to the 4-byte body length.

## 3. Frame types

- **REQUEST** (client → server): headers `Method`, `Path`, `Host`
  required; body normally empty (GET only in v1 — no request body is
  defined).
- **RESPONSE** (server → client): headers include `Status` (as a decimal
  string: `200`, `400`, `404`, `405`), `Content-Length`, `Content-Type`;
  body is the payload.
- **ERROR**: reserved for a future out-of-band error not tied to a
  specific request (e.g. a connection-level problem); v1 servers report
  request failures as ordinary RESPONSE frames with a 4xx/5xx status
  instead, matching plain HTTP semantics.

Status codes used: `200` OK, `400` malformed frame, `404` path not found,
`405` method not GET.

## 4. Forward compatibility: the skip rule

**A receiver that gets a frame Type it does not recognise MUST skip it
cleanly and keep reading.** This works *because* Header Block Length and
Body Length live in the fixed header, outside any type-specific payload —
a receiver never needs to understand a frame's contents to know how many
bytes to discard: `skip(header_block_len + body_len)`, then read the next
fixed header. That's the whole mechanism, and it's what lets a v2 add new
frame types (a PING, a server push, whatever) that a v1 client or server
can simply skip over instead of crashing or hanging on. `bcurl` implements
this in its main read loop — see the `UNKNOWN frame type=... (skipped)`
case in `bcurl.py`.

## 5. Connection handling

Exactly one TCP connection per client run. The server keeps the socket
open across requests (pipelining — reading several REQUESTs before
answering any of them, then answering in order — is optional and not
required for `bcurl`, which sends one request and reads one response per
invocation). A malformed frame (fields that don't parse, or a length that
implies more bytes than the receiver is willing to buffer) gets a `400`
RESPONSE frame, not a silently dropped connection.

## 6. Worked example

`bcurl -v localhost:9000/index.html` against a server whose `www/`
contains a one-line `index.html` — see `ANNOTATED_HEXDUMP.md` for the
byte-by-byte breakdown of the exact REQUEST and RESPONSE frames this
produces.
