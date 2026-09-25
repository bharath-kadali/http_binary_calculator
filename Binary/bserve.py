#!/usr/bin/env python3
"""
bserve - minimal reference implementation of Track 1, used here ONLY to
exercise bcurl.py against something real and to produce a genuine, correct
hexdump for SPEC.md. Not the deliverable - you said you already have your
own server. Swap this out for yours; the wire format is what has to match.

Usage:
    ./bserve.py ROOT PORT
"""

import socket
import sys
import struct
import os

VERSION = 1
TYPE_REQUEST = 1
TYPE_RESPONSE = 2
TYPE_ERROR = 3
FIXED_HEADER_LEN = 12

STATIC_TABLE = {
    0: "Method", 1: "Path", 2: "Host", 3: "Content-Length",
    4: "Content-Type", 5: "Connection", 6: "Status",
    7: "User-Agent", 8: "Accept", 9: "Date",
}
NAME_TO_ID = {v: k for k, v in STATIC_TABLE.items()}
CUSTOM_NAME_MARKER = 0xFF


def encode_headers(headers):
    out = bytearray()
    for name, value in headers:
        vbytes = value.encode("utf-8")
        if name in NAME_TO_ID:
            out += bytes([NAME_TO_ID[name]])
        else:
            nbytes = name.encode("ascii")
            out += bytes([CUSTOM_NAME_MARKER, len(nbytes)]) + nbytes
        out += struct.pack("!H", len(vbytes)) + vbytes
    return len(headers), bytes(out)


def decode_headers(block, count):
    headers = []
    i = 0
    for _ in range(count):
        name_id = block[i]; i += 1
        if name_id == CUSTOM_NAME_MARKER:
            nlen = block[i]; i += 1
            name = block[i:i + nlen].decode("ascii"); i += nlen
        else:
            name = STATIC_TABLE.get(name_id, f"X-Unknown-{name_id}")
        (vlen,) = struct.unpack("!H", block[i:i + 2]); i += 2
        value = block[i:i + vlen].decode("utf-8"); i += vlen
        headers.append((name, value))
    return headers


def build_frame(ftype, headers, body=b""):
    count, header_block = encode_headers(headers)
    fixed = struct.pack("!BBBBII", VERSION, ftype, 0, count, len(header_block), len(body))
    return fixed + header_block + body


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            if len(buf) == 0:
                return None
            raise ConnectionError("peer closed mid-frame")
        buf += chunk
    return bytes(buf)


def read_frame(sock):
    fixed = recv_exact(sock, FIXED_HEADER_LEN)
    if fixed is None:
        return None
    try:
        version, ftype, flags, count, header_block_len, body_len = struct.unpack("!BBBBII", fixed)
    except struct.error:
        return "MALFORMED", None, None, None
    header_block = recv_exact(sock, header_block_len)
    body = recv_exact(sock, body_len)
    if header_block is None or body is None:
        return "MALFORMED", None, None, None
    headers = decode_headers(header_block, count) if ftype == TYPE_REQUEST else None
    return ftype, flags, headers, body


def status_response(status, text=""):
    body = text.encode("utf-8")
    headers = [
        ("Status", str(status)),
        ("Content-Length", str(len(body))),
        ("Content-Type", "text/plain"),
    ]
    return build_frame(TYPE_RESPONSE, headers, body)


def handle(conn, root):
    with conn:
        while True:
            try:
                result = read_frame(conn)
            except ConnectionError:
                return
            if result is None:
                return  # clean close, no partial frame in flight
            if result[0] == "MALFORMED":
                conn.sendall(status_response(400, "malformed frame"))
                return
            ftype, flags, headers, body = result
            if ftype != TYPE_REQUEST:
                conn.sendall(status_response(400, "expected REQUEST frame"))
                continue
            hmap = dict(headers)
            method = hmap.get("Method", "")
            path = hmap.get("Path", "")
            if method != "GET":
                conn.sendall(status_response(405, "only GET is supported"))
                continue
            local = os.path.join(root, path.lstrip("/"))
            if not os.path.isfile(local):
                conn.sendall(status_response(404, "not found"))
                continue
            with open(local, "rb") as f:
                data = f.read()
            ctype = "text/html" if path.endswith(".html") else "text/plain"
            resp_headers = [
                ("Status", "200"),
                ("Content-Length", str(len(data))),
                ("Content-Type", ctype),
            ]
            conn.sendall(build_frame(TYPE_RESPONSE, resp_headers, data))


def main(argv):
    if len(argv) != 2:
        print("usage: bserve.py ROOT PORT", file=sys.stderr)
        return 2
    root, port = argv[0], int(argv[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen()
        print(f"bserve listening on :{port}, root={root}", file=sys.stderr)
        while True:
            conn, addr = srv.accept()
            handle(conn, root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
