import socket

HOST = "127.0.0.1"
PORT = 8080


def read_response(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        data += sock.recv(4096)

    header, data = data.split(b"\r\n\r\n", 1)
    headers = header.decode().split("\r\n")
    content_length = 0

    for line in headers[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            if name.lower() == "content-length":
                content_length = int(value.strip())

    while len(data) < content_length:
        data += sock.recv(4096)

    body = data[:content_length]
    return headers[0], body.decode()


requests = [
    "GET /add?a=2&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "GET /sub?a=10&b=4 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "GET /mul?a=6&b=7 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "GET /div?a=6&b=2 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "GET /div?a=1&b=0 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "GET /pow?a=2&b=8 HTTP/1.1\r\nHost: localhost\r\n\r\n",
    "POST /add HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n",
    "GET /add?a=9&b=1 HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
]

with socket.create_connection((HOST, PORT)) as sock:
    print("ONE TCP CONNECTION")
    for i, request in enumerate(requests, 1):
        sock.sendall(request.encode())
        status, body = read_response(sock)
        print(f"{i}. {status}  body={body!r}")
