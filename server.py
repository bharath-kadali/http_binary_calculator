import signal
import socket
import sys
from urllib.parse import urlsplit, parse_qs

HOST = "0.0.0.0"
DEFAULT_PORT = 8080
MAX_HEADER_BYTES = 16 * 1024
READ_CHUNK = 4096
IDLE_TIMEOUT = 10


STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    413: "Payload Too Large",
    505: "HTTP Version Not Supported",
}


def response(status, body="", close=False, extra_headers=None):
    body_bytes = body.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status} {STATUS_TEXT[status]}",
        f"Content-Length: {len(body_bytes)}",
        "Content-Type: text/plain; charset=utf-8",
        "Connection: close" if close else "Connection: keep-alive",
    ]
    if extra_headers:
        headers.extend(extra_headers)
    return ("\r\n".join(headers) + "\r\n\r\n").encode() + body_bytes


def recv_request(conn, buffer):
    """
    Read exactly one HTTP request from a persistent TCP stream.

    Returns:
      (request_bytes, remaining_buffer)
    or (None, remaining_buffer) on clean EOF.
    """
    while b"\r\n\r\n" not in buffer:
        chunk = conn.recv(READ_CHUNK)
        if not chunk:
            return None, buffer
        buffer += chunk
        if len(buffer) > MAX_HEADER_BYTES:
            raise ValueError("headers too large")

    header_end = buffer.index(b"\r\n\r\n") + 4
    head = buffer[:header_end]
    lines = head.decode("iso-8859-1").split("\r\n")

    if not lines or not lines[0]:
        raise ValueError("empty request line")

    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("malformed header")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    try:
        content_length = int(headers.get("content-length", "0"))
    except ValueError:
        raise ValueError("bad content-length")

    if content_length < 0 or content_length > 1024 * 1024:
        raise ValueError("invalid content-length")

    total = header_end + content_length
    while len(buffer) < total:
        chunk = conn.recv(READ_CHUNK)
        if not chunk:
            raise ValueError("incomplete request body")
        buffer += chunk

    return buffer[:total], buffer[total:]


def calculate(path):
    parsed = urlsplit(path)
    operation = parsed.path.lstrip("/")

    if operation not in {"add", "sub", "mul", "div"}:
        return 404, "Not Found"

    params = parse_qs(parsed.query, keep_blank_values=True)
    if "a" not in params or "b" not in params:
        return 400, "Missing a or b"

    try:
        a = float(params["a"][0])
        b = float(params["b"][0])
    except (ValueError, TypeError):
        return 400, "a and b must be numbers"

    if operation == "add":
        result = a + b
    elif operation == "sub":
        result = a - b
    elif operation == "mul":
        result = a * b
    else:
        if b == 0:
            return 400, "Division by zero"
        result = a / b

    # Return integers without a trailing ".0".
    if result.is_integer():
        return 200, str(int(result))
    return 200, str(result)


def handle_client(conn, addr):
    conn.settimeout(IDLE_TIMEOUT)
    buffer = b""

    try:
        while True:
            try:
                request, buffer = recv_request(conn, buffer)
            except socket.timeout:
                # Optional stretch: idle timeout.
                conn.sendall(response(408, "Request Timeout", close=True))
                return
            except ValueError as exc:
                conn.sendall(response(400, str(exc), close=True))
                return

            if request is None:
                return

            head = request.split(b"\r\n\r\n", 1)[0]
            lines = head.decode("iso-8859-1").split("\r\n")
            method, target, version = lines[0].split(" ", 2)

            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.strip().lower()] = value.strip()

            if version != "HTTP/1.1":
                conn.sendall(response(505, "HTTP/1.1 required", close=True))
                return

            if "host" not in headers:
                conn.sendall(response(400, "Host header required", close=True))
                return

            wants_close = headers.get("connection", "").lower() == "close"

            if method != "GET":
                conn.sendall(response(405, "Method Not Allowed", close=wants_close,
                                      extra_headers=["Allow: GET"]))
                if wants_close:
                    print(f"[{addr}] Client requested connection close")
                    return
                continue

            status, body = calculate(target)
            conn.sendall(response(status, body, close=wants_close))

            if wants_close:
                return

    except (ConnectionResetError, BrokenPipeError, socket.timeout):
        return
    finally:
        conn.close()
        print(f"[{addr}] Connection closed")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, port))
        server.listen(20)
        server.settimeout(1.0)

        stop_requested = False

        def _shutdown_handler(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGINT, _shutdown_handler)

        print(f"Calculator server listening on 0.0.0.0:{port}")
        print(f"Idle timeout: {IDLE_TIMEOUT}s")

        try:
            while True:
                if stop_requested:
                    break
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    if stop_requested:
                        break
                    continue
                print(f"connection from {addr}")
                handle_client(conn, addr)

        except KeyboardInterrupt:
            pass
        finally:
            print("\nServer stopped.")


if __name__ == "__main__":
    main()
