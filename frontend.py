#!/usr/bin/env python3
"""Tiny HTTP wrapper that fronts mcp-atlassian with a probe-friendly `/` handler.

Central Station's default app template hardcodes a Kubernetes liveness probe of
`httpGet path=/ port=http`. mcp-atlassian serves `/mcp` (streamable-http) but
returns 404 for `/`, so the probe always fails and kubelet kills the pod
before it accepts MCP traffic.

This wrapper:
  * listens on $PORT (default 3000),
  * returns 200 on `/` (kubelet probe),
  * transparently proxies every other path/method to mcp-atlassian on
    $PORT + 1000.
"""
from __future__ import annotations
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn

PORT = int(os.environ.get("PORT", "3000"))
BACKEND_PORT = PORT + 1000
BACKEND_HOST = "127.0.0.1"


def start_backend() -> subprocess.Popen[bytes]:
    """Spawn the real mcp-atlassian on BACKEND_PORT. The wrapper passes argv[1:]
    through (the sooperset image's default args minus --port, which we
    override) and replaces the port argument with our backend port."""
    args = [a for a in sys.argv[1:] if a not in ("--port", str(PORT))]
    # Drop the original --port and its value (already filtered above as best-effort).
    cleaned: list[str] = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a == "--port":
            skip_next = True
            continue
        cleaned.append(a)
    cmd = ["mcp-atlassian"] + cleaned + ["--port", str(BACKEND_PORT)]
    print(f"frontend: starting backend: {' '.join(cmd)}", flush=True)
    return subprocess.Popen(cmd)


def wait_for_backend(timeout: int = 30) -> bool:
    """Block until BACKEND_PORT accepts connections, or the timeout expires."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Suppress noisy access logs.
        return

    def _proxy(self) -> None:
        url = f"http://{BACKEND_HOST}:{BACKEND_PORT}{self.path}"
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))
        headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
        req = urllib.request.Request(url, data=body, method=self.command, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                while chunk := resp.read(8192):
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except (urllib.error.URLError, ConnectionError) as e:
            self.send_error(502, f"upstream error: {e}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK\n")
            return
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()


class ThreadingServer(ThreadingMixIn, ThreadingHTTPServer):
    daemon_threads = True


def main() -> int:
    backend = start_backend()
    if not wait_for_backend(60):
        print("frontend: backend did not become ready within 60s", file=sys.stderr)
        backend.terminate()
        return 1
    print(f"frontend: listening on {PORT}, proxying to {BACKEND_HOST}:{BACKEND_PORT}", flush=True)
    server = ThreadingServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
