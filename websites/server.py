"""Two lab websites share one server; SITE_ROLE selects the identity."""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROLE = os.environ.get("SITE_ROLE", "good")
WEB_ROOT = Path(__file__).resolve().parent
SITES = {
    "good": {"site_id": "legitimate", "file": WEB_ROOT / "good" / "index.html"},
    "fake": {"site_id": "training-fake", "file": WEB_ROOT / "fake" / "index.html"},
}
if ROLE not in SITES:
    raise RuntimeError(f"SITE_ROLE không hợp lệ: {ROLE}")

SITE = SITES[ROLE]
PAGE = SITE["file"].read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(send_body=True)

    def do_HEAD(self):
        self.respond(send_body=False)

    def respond(self, send_body):
        if self.path == "/":
            status, body = 200, PAGE
            content_type = "text/html; charset=utf-8"
        elif self.path == "/health":
            status = 200
            body = json.dumps({"status": "ok", "site_id": SITE["site_id"]}).encode()
            content_type = "application/json; charset=utf-8"
        else:
            status, body = 404, b"Not found"
            content_type = "text/plain; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Lab-Site", SITE["site_id"])
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if send_body:
            self.wfile.write(body)
        # Keep health probes out of the experiment's HTTP access logs.
        if self.path != "/health":
            print(json.dumps({
                "time": datetime.now(timezone.utc).isoformat(),
                "site_id": SITE["site_id"],
                "client_ip": self.client_address[0],
                "method": self.command,
                "host": self.headers.get("Host"),
                "path": self.path,
                "status": status,
                "run_id": self.headers.get("X-Lab-Run-ID"),
                "branch_id": self.headers.get("X-Lab-Branch-ID"),
            }, ensure_ascii=False), flush=True)

    def log_message(self, format, *args):
        # Access logs use the structured JSON above.
        pass


if __name__ == "__main__":
    print(f"Serving {SITE['site_id']} on port 80", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
