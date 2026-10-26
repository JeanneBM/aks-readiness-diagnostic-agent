"""Disposable readiness fixture. It deliberately does not access real dependencies."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

PORT = int(os.environ.get("PORT", "8080"))
PATH = os.environ.get("READY_PATH", "/ready")
DEPENDENCY = os.environ.get("SIMULATE_DEPENDENCY_FAILURE", "false") == "true"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/live":
            self.send_response(200)
        elif self.path == PATH:
            if DEPENDENCY:
                print("Dependency check failed: inventory", flush=True)
            self.send_response(503 if DEPENDENCY else 200)
        else:
            self.send_response(404)
        self.end_headers()
        self.wfile.write(b"fixture\n")


if __name__ == "__main__":
    print(f"Listening on 0.0.0.0:{PORT}", flush=True)
    print(f"Readiness endpoint: {PATH}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
