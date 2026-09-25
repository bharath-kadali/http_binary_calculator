#!/usr/bin/env python3
"""
bcurl - Track 2 client for the binary-HTTP course project.

Usage:
    ./bcurl.py [-v] host[:port]/path

Example:
    ./bcurl.py -v localhost:9000/index.html

Behaviour (per the spec, see SPEC.md):
  - Opens exactly one TCP connection.
  - Builds one binary REQUEST frame and sends it.
  - Reads frames from the socket. Any frame whose Type it does not
    recognise is skipped cleanly (using the length fields in the fixed
    header) rather than treated as an error - this is what lets a v2
    server add new frame types without breaking this client.
  - On the first RESPONSE (or ERROR) frame, writes the body to stdout
    exactly (Body Length bytes, not "until EOF").
  - With -v, hexdumps every frame - the one it sends and every one it
    reads, including skipped/unknown ones - to stderr, so stdout stays
    exactly the response body.
  - Exits non-zero if the response status is 4xx or 5xx.
  - Never opens a second connection, no matter what it reads.
"""

import socket
import sys
import struct

# ---------------------------------------------------------------------------
# Wire format (see SPEC.md for the full writeup and rationale)
# ---------------------------------------------------------------------------

VERSION = 1

TYPE_REQUEST = 1
TYPE_RESPONSE = 2
TYPE_ERROR = 3
# Any other type value is unrecognised by this client and must be skipped.

FIXED_HEADER_LEN = 12  # version(1) type(1) flags(1) header_count(1) header_block_len(4) body_len(4)

STATIC_TABLE = {
    0: "Method",
    1: "Path",
    2: "Host",
    3: "Content-Length",
    4: "Content-Type",
    5: "Connection",
    6: "Status",
    7: "User-Agent",
    8: "Accept",
    9: "Date",
}
NAME_TO_ID = {v: k for k, v in STATIC_TABLE.items()}
CUSTOM_NAME_MARKER = 0xFF


# ---------------------------------------------------------------------------
# Header block encode / decode
# ---------------------------------------------------------------------------

def encode_headers(headers):
    """headers: list of (name, value) str pairs -> (count, header_block_bytes)"""
    out = bytearray()
    for name, value in headers:
        vbytes = value.encode("utf-8")
        if name in NAME_TO_ID:
            out += bytes([NAME_TO_ID[name]])
        else:
            nbytes = name.encode("ascii")
            if len(nbytes) > 255:
                raise ValueError("header name too long for length-prefixed encoding")
            out += bytes([CUSTOM_NAME_MARKER, len(nbytes)]) + nbytes
        if len(vbytes) > 0xFFFF:
            raise ValueError("header value too long (max 65535 bytes)")
        out += struct.pack("!H", len(vbytes)) + vbytes
    return len(headers), bytes(out)


def decode_headers(block, count):
    headers = []
    i = 0
    for _ in range(count):
        name_id = block[i]
        i += 1
        if name_id == CUSTOM_NAME_MARKER:
            nlen = block[i]
            i += 1
            name = block[i:i + nlen].decode("ascii")
            i += nlen
        else:
            name = STATIC_TABLE.get(name_id, f"X-Unknown-{name_id}")
        (vlen,) = struct.unpack("!H", block[i:i + 2])
        i += 2
        value = block[i:i + vlen].decode("utf-8")
        i += vlen
        headers.append((name, value))
    return headers


# ---------------------------------------------------------------------------
# Frame encode / decode
# ---------------------------------------------------------------------------

def build_frame(ftype, headers, body=b""):
    count, header_block = encode_headers(headers)
    fixed = struct.pack(
        "!BBBBII",
        VERSION,
        ftype,
        0,               # flags - unused (reserved for pipelining ack in v2)
        count,
        len(header_block),
        len(body),
    )
    return fixed + header_block + body


def recv_exact(sock, n):
    """Read exactly n bytes or raise - never trust a short recv() on a
    binary framed protocol; there is no EOF-terminated body here."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(
                f"peer closed with {len(buf)}/{n} bytes of frame still owed"
            )
        buf += chunk
    return bytes(buf)


def read_frame(sock):
    """Read one complete frame off the wire and return
    (ftype, flags, headers, body, raw_bytes)."""
    fixed = recv_exact(sock, FIXED_HEADER_LEN)
    version, ftype, flags, count, header_block_len, body_len = struct.unpack(
        "!BBBBII", fixed
    )
    header_block = recv_exact(sock, header_block_len)
    body = recv_exact(sock, body_len)
    raw = fixed + header_block + body
    headers = None
    if ftype in (TYPE_REQUEST, TYPE_RESPONSE, TYPE_ERROR):
        headers = decode_headers(header_block, count)
    return ftype, flags, headers, body, raw


# ---------------------------------------------------------------------------
# Hexdump (verbose mode -> stderr, so stdout is always exactly the body)
# ---------------------------------------------------------------------------

def hexdump(label, data, out=sys.stderr):
    print(f"--- {label} ({len(data)} bytes) ---", file=out)
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        hex_part = f"{hex_part:<47}"
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{off:08x}  {hex_part}  |{ascii_part}|", file=out)
    print(file=out)


# ---------------------------------------------------------------------------
# URL parsing: "host[:port]/path"
# ---------------------------------------------------------------------------

def parse_target(target):
    if "://" in target:
        target = target.split("://", 1)[1]
    if "/" in target:
        hostport, _, path = target.partition("/")
        path = "/" + path
    else:
        hostport, path = target, "/"
    if ":" in hostport:
        host, port_s = hostport.split(":", 1)
        port = int(port_s)
    else:
        host, port = hostport, 80
    return host, port, path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv):
    verbose = False
    args = []
    for a in argv:
        if a == "-v":
            verbose = True
        else:
            args.append(a)

    if len(args) != 1:
        print("usage: bcurl.py [-v] host[:port]/path", file=sys.stderr)
        return 2

    host, port, path = parse_target(args[0])

    headers = [
        ("Method", "GET"),
        ("Path", path),
        ("Host", f"{host}:{port}"),
        ("User-Agent", "bcurl/1.0"),
    ]
    request = build_frame(TYPE_REQUEST, headers)

    # Exactly one connection, for the life of the process.
    with socket.create_connection((host, port)) as sock:
        if verbose:
            hexdump("REQUEST frame (sent)", request)
        sock.sendall(request)

        while True:
            ftype, flags, hdrs, body, raw = read_frame(sock)

            if ftype not in (TYPE_REQUEST, TYPE_RESPONSE, TYPE_ERROR):
                # Unknown frame type: the fixed header already told us
                # its total length, so we can discard it cleanly and
                # keep reading - required for a future v2 to be able to
                # introduce new frame types without breaking this client.
                if verbose:
                    hexdump(f"UNKNOWN frame type={ftype} (skipped)", raw)
                continue

            if verbose:
                label = "RESPONSE" if ftype == TYPE_RESPONSE else "ERROR"
                hexdump(f"{label} frame (received)", raw)

            header_map = dict(hdrs)
            status = int(header_map.get("Status", "0"))

            sys.stdout.buffer.write(body)
            sys.stdout.buffer.flush()

            if 400 <= status < 600:
                return 1
            return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
