"""Local upstream proxy for fork scenarios.

anvil takes its fork URL on the command line, and the agent has shell access
in the workspace — `ps` would show the Alchemy key. So the key stays HERE:
a loopback HTTP server forwards JSON-RPC bodies to the real upstream, and
anvil forks from http://127.0.0.1:<port> instead. The upstream URL never
appears in argv, the workspace, or results.
"""
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_proxy(upstream_url):
    """Start a loopback JSON-RPC forwarder. Returns (server, local_url);
    call server.shutdown() when done."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            req = urllib.request.Request(
                upstream_url, data=body,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = resp.read()
            except Exception:  # noqa: BLE001 - upstream hiccup; anvil retries
                self.send_error(502)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep the harness output clean
            pass

    class QuietServer(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # anvil drops keep-alive sockets constantly; that's not an error
            import sys
            exc = sys.exception()
            if isinstance(exc, (ConnectionError, BrokenPipeError, TimeoutError)):
                return
            super().handle_error(request, client_address)

    srv = QuietServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
