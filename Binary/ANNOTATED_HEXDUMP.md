# Annotated hexdump — one complete request/response

Captured verbatim from:

```
$ ./bcurl.py -v localhost:9000/index.html
```

against a server whose `www/index.html` contains:
```
<html><body><h1>hello</h1></body></html>
```

## REQUEST frame (61 bytes, sent by bcurl)

```
00000000  01 01 00 04 00 00 00 31 00 00 00 00 00 00 03 47  |.......1.......G|
00000010  45 54 01 00 0b 2f 69 6e 64 65 78 2e 68 74 6d 6c  |ET.../index.html|
00000020  02 00 0e 6c 6f 63 61 6c 68 6f 73 74 3a 39 30 30  |...localhost:900|
00000030  30 07 00 09 62 63 75 72 6c 2f 31 2e 30           |0...bcurl/1.0|
```

| Bytes    | Value                     | Meaning                                  |
|----------|---------------------------|-------------------------------------------|
| `01`             | Version            | `1` |
| `01`             | Type               | `1` = REQUEST |
| `00`             | Flags              | unused in v1 |
| `04`             | Header Count       | 4 header entries follow |
| `00 00 00 31`    | Header Block Length| `0x31` = 49 bytes |
| `00 00 00 00`    | Body Length        | 0 — GET has no body |
| `00` `00 03` `47 45 54`             | Header 1 | id `0`=**Method**, len 3, value `"GET"` |
| `01` `00 0b` `2f 69 6e 64 65 78 2e 68 74 6d 6c` | Header 2 | id `1`=**Path**, len 11, value `"/index.html"` |
| `02` `00 0e` `6c 6f 63 61 6c 68 6f 73 74 3a 39 30 30 30` | Header 3 | id `2`=**Host**, len 14, value `"localhost:9000"` |
| `07` `00 09` `62 63 75 72 6c 2f 31 2e 30` | Header 4 | id `7`=**User-Agent**, len 9, value `"bcurl/1.0"` |
| *(none)* | Body | 0 bytes |

`12` (fixed header) `+ 49` (header block) `+ 0` (body) `= 61` bytes total. ✓

## RESPONSE frame (76 bytes, received by bcurl)

```
00000000  01 02 00 03 00 00 00 17 00 00 00 29 06 00 03 32  |...........)...2|
00000010  30 30 03 00 02 34 31 04 00 09 74 65 78 74 2f 68  |00...41...text/h|
00000020  74 6d 6c 3c 68 74 6d 6c 3e 3c 62 6f 64 79 3e 3c  |tml<html><body><|
00000030  68 31 3e 68 65 6c 6c 6f 3c 2f 68 31 3e 3c 2f 62  |h1>hello</h1></b|
00000040  6f 64 79 3e 3c 2f 68 74 6d 6c 3e 0a              |ody></html>.|
```

| Bytes    | Value                     | Meaning                                  |
|----------|---------------------------|-------------------------------------------|
| `01`             | Version            | `1` |
| `02`             | Type               | `2` = RESPONSE |
| `00`             | Flags              | unused in v1 |
| `03`             | Header Count       | 3 header entries follow |
| `00 00 00 17`    | Header Block Length| `0x17` = 23 bytes |
| `00 00 00 29`    | Body Length        | `0x29` = 41 bytes |
| `06` `00 03` `32 30 30`             | Header 1 | id `6`=**Status**, len 3, value `"200"` |
| `03` `00 02` `34 31`                | Header 2 | id `3`=**Content-Length**, len 2, value `"41"` |
| `04` `00 09` `74 65 78 74 2f 68 74 6d 6c` | Header 3 | id `4`=**Content-Type**, len 9, value `"text/html"` |
| bytes 35–75 (41 bytes) | Body | `<html><body><h1>hello</h1></body></html>\n` |

`12` (fixed header) `+ 23` (header block) `+ 41` (body) `= 76` bytes total. ✓
Note: `Status: 200`, so `bcurl` writes the 41 body bytes to stdout and exits `0`.

## Cross-checked failure modes

`bcurl` was also run against:
- a missing path → server replies `Status: 404`, `bcurl` prints `not found`
  to stdout and **exits 1**.
- a non-GET request (sent directly, bypassing `bcurl`, to exercise the
  server side) → `Status: 405`.
- a server that emits an unrecognised frame type (`99`) before the real
  RESPONSE → `bcurl` logs `UNKNOWN frame type=99 (skipped)` to stderr,
  discards exactly `header_block_len + body_len` bytes per the fixed
  header, and still correctly reads and returns the RESPONSE that follows.
