# Calculator HTTP Server and Client

This project is a small Python example of a basic HTTP calculator service. It includes:

- a server that listens for HTTP requests and performs arithmetic
- a client that sends example requests and prints the responses

The server supports simple calculator operations over HTTP GET requests:

- `/add?a=...&b=...`
- `/sub?a=...&b=...`
- `/mul?a=...&b=...`
- `/div?a=...&b=...`

It returns plain text responses and includes basic validation for bad input, unsupported routes, and division by zero.

## Project structure

```text
calculator/
├── HTTP/
│   ├── server.py
│   └── client.py
└── README.md
```

## How the server works

The server in `HTTP/server.py` creates a TCP socket and listens on `0.0.0.0:8080` by default.

### Request handling flow

1. The server accepts a client connection.
2. It reads raw bytes from the socket until it receives a full HTTP request.
3. It parses:
   - the request line (`GET /add?a=2&b=3 HTTP/1.1`)
   - headers such as `Host` and `Connection`
   - the request body if present
4. It validates the request:
   - only `GET` is accepted
   - `HTTP/1.1` is required
   - `Host` is required
   - payload size is limited
5. It extracts the operation name from the URL path and reads query parameters `a` and `b`.
6. It performs the calculation.
7. It builds an HTTP response with:
   - a status code
   - a plain-text body
   - a `Content-Length` header
   - a `Connection` header
8. It sends the response back to the client.

### Supported operations

The `calculate()` function parses the URL path and query string:

- `add` -> `a + b`
- `sub` -> `a - b`
- `mul` -> `a * b`
- `div` -> `a / b`

If the result is a whole number, the server returns it without a trailing `.0`.

### Example valid requests

```http
GET /add?a=2&b=3 HTTP/1.1
Host: localhost

GET /div?a=10&b=2 HTTP/1.1
Host: localhost
```

### Example responses

```http
HTTP/1.1 200 OK
Content-Length: 1
Content-Type: text/plain; charset=utf-8
Connection: keep-alive

5
```

## How the client works

The client in `HTTP/client.py` connects to the server and sends a list of HTTP requests.

### Request/response flow

1. It creates a socket connection to `127.0.0.1:8080`.
2. It sends a raw HTTP request string.
3. It reads from the socket until it receives the end of the headers (`\r\n\r\n`).
4. It parses the response headers and locates `Content-Length`.
5. It reads exactly that many bytes from the body.
6. It prints the status line and response body.

This client sends multiple requests in one TCP connection to demonstrate how HTTP requests and responses can be reused over a persistent socket.

## Running the project

### Start the server

From the project folder, run:

```bash
python HTTP/server.py
```

Or specify a custom port:

```bash
python HTTP/server.py 8081
```

### Run the client

In another terminal, run:

```bash
python HTTP/client.py
```

The client will send example requests such as:

- `GET /add?a=2&b=3 HTTP/1.1`
- `GET /sub?a=10&b=4 HTTP/1.1`
- `GET /mul?a=6&b=7 HTTP/1.1`
- `GET /div?a=6&b=2 HTTP/1.1`
- `GET /div?a=1&b=0 HTTP/1.1`
- `GET /pow?a=2&b=8 HTTP/1.1`

## Error handling

The server includes basic HTTP error handling for:

- unknown routes (`404 Not Found`)
- missing query parameters (`400 Bad Request`)
- invalid numbers (`400 Bad Request`)
- division by zero (`400 Bad Request`)
- unsupported methods (`405 Method Not Allowed`)
- unsupported HTTP version (`505 HTTP Version Not Supported`)
- timeouts (`408 Request Timeout`)

## Notes

This is a minimal educational implementation of an HTTP server and client. It is intentionally simple and does not include full browser-style features such as HTML pages, complex routing, or a production-grade framework.

The focus is to show how raw socket programming, HTTP parsing, and simple request/response handling work together.
