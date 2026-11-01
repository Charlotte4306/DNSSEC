"""UI-only preview server for the DNSSEC dashboard.

Replays recorded fixtures so the live UI assets in this folder can be edited without
Docker, BIND or the Flask backend. app.js / motion.js / css / html are byte copies of
what itscharlotte.tech serves; all substitution happens here.

    .venv/Scripts/python.exe ui_preview/serve.py --port 18790

baseline job+run are recorded from the deployed lab. attack and recovery job events are
rewritten from the baseline recording by make_fixtures.py; their run results come from
evidence/runs. Treat attack/recovery timelines as reconstruction, not measurement.
"""

import argparse
import json
import mimetypes
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
PREVIEW_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
REVEAL_MS = 160
SETTLE_MS = 400
ACTION_MODE = {"baseline": "normal", "recovery": "normal", "attack": "attack"}


def load_json(*parts):
    return json.loads((FIXTURES / Path(*parts)).read_text(encoding="utf-8"))


class Lab:
    """Single source of truth for the mock: state follows the last completed job."""

    def __init__(self):
        self.lock = threading.Lock()
        self.health = load_json("health.json")
        self.proof = load_json("proof.json")
        self.jobs = {action: load_json("jobs", f"{action}.json") for action in ("baseline", "attack", "recovery")}
        self.runs = {}
        for job in self.jobs.values():
            self.runs[job["run_id"]] = load_json("runs", job["run_id"], "result.json")
        job = self.jobs["baseline"]
        run = self.runs[job["run_id"]]
        self.state = {
            "source": "live",
            "ready_for_run": True,
            "busy": False,
            "active_job_id": None,
            "last_error": None,
            "actual_mode": "normal",
            "mode_snapshot": {"attack": False, "changed_at": run["scenario_before"]["changed_at"]},
            "revision": run["scenario_revision"],
            "last_run_id": run["run_id"],
            "last_task": {"action": "job:baseline", "job_id": job["job_id"], "run_id": run["run_id"],
                          "status": "completed", "requested_at": job["requested_at"],
                          "finished_at": job["finished_at"]},
        }
        self.running = None

    def start_job(self, action):
        if action not in self.jobs:
            raise ValueError(action)
        with self.lock:
            if self.running:
                return self.running
            self.state["busy"] = True
            self.running = {"action": action, "job": self.jobs[action], "began": time.monotonic(), "done": False}
            self.state["active_job_id"] = self.jobs[action]["job_id"]
            self.state["last_task"] = {"action": f"job:{action}", "job_id": self.jobs[action]["job_id"],
                                       "run_id": self.jobs[action]["run_id"], "status": "running",
                                       "requested_at": datetime.now(timezone.utc).isoformat(), "finished_at": None}
            return self.running

    def poll_job(self, job_id, after):
        with self.lock:
            job = next((item["job"] for item in [self.running] if item and item["job"]["job_id"] == job_id), None)
            if job is None:
                for stored in self.jobs.values():
                    if stored["job_id"] == job_id:
                        job = stored
                if job is None:
                    return None
                return {"job": job, "events": job["events"], "cursor": job["cursor"], "status": "completed"}
            elapsed = (time.monotonic() - self.running["began"]) * 1000
            revealed = min(len(job["events"]), max(1, int(elapsed / REVEAL_MS) + 1))
            finished = revealed == len(job["events"]) and elapsed >= len(job["events"]) * REVEAL_MS + SETTLE_MS
            if finished and not self.running["done"]:
                self.running["done"] = True
                self._settle(job)
            status = "completed" if finished else "running"
            if finished and self.running:
                self.state["busy"] = False
                self.state["active_job_id"] = None
                self.running = None
            return {"job": job, "events": [e for e in job["events"] if e["sequence"] > after and e["sequence"] <= revealed],
                    "cursor": revealed, "status": status}

    def _settle(self, job):
        run = self.runs[job["run_id"]]
        self.state["revision"] = run["scenario_revision"]
        self.state["actual_mode"] = ACTION_MODE.get(job["action"], "normal")
        self.state["mode_snapshot"] = {"attack": job["action"] == "attack", "changed_at": run["scenario_revision"]}
        self.state["last_run_id"] = run["run_id"]
        self.state["last_task"] = {**self.state["last_task"], "status": "completed",
                                   "finished_at": datetime.now(timezone.utc).isoformat()}


LAB = Lab()


class Handler(BaseHTTPRequestHandler):
    lab = LAB

    def log_message(self, *args):
        pass

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path, content_type=None, extra_headers=()):
        if not path.is_file():
            return self.send_json({"error": {"code": "NOT_FOUND", "message": "Không tìm thấy tài nguyên."}}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        return self.route("GET")

    def do_HEAD(self):
        return self.route("HEAD")

    def do_POST(self):
        return self.route("POST")

    def route(self, method):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        try:
            if path == "/":
                return self.send_file(ROOT / "index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self.send_file(ROOT / unquote(path).lstrip("/"))
            if path == "/api/health":
                return self.send_json(self.lab.health)
            if path == "/api/state":
                with self.lab.lock:
                    return self.send_json({**self.lab.state, "source": "live"})
            if path == "/api/jobs" and method == "POST":
                action = (self.read_json().get("action") or "").strip()
                if action not in self.lab.jobs:
                    return self.send_json({"error": {"code": "INVALID_ACTION", "message": f"Kịch bản không có fixture: {action}"}}, 400)
                return self.send_json({"job_id": self.lab.start_job(action)["job"]["job_id"], "source": "live"})
            if path.startswith("/api/jobs/"):
                after = int((query.get("after") or ["0"])[0])
                job = self.lab.poll_job(unquote(path.rsplit("/", 1)[-1]), after)
                if job is None:
                    return self.send_json({"error": {"code": "JOB_NOT_FOUND", "message": "Không có tác vụ mock này."}}, 404)
                record = job["job"]
                return self.send_json({"source": "live", "job_id": record["job_id"], "run_id": record["run_id"],
                                       "action": record["action"], "status": job["status"], "events": job["events"],
                                       "cursor": job["cursor"], "events_sha256": record.get("events_sha256"),
                                       "result_url": record["result_url"], "requested_at": record["requested_at"],
                                       "finished_at": record["finished_at"] if job["status"] == "completed" else None,
                                       "error": None})
            if path == "/api/proof" and method == "POST":
                with self.lab.lock:
                    return self.send_json({"source": "live", "requested_at": datetime.now(timezone.utc).isoformat(),
                                           "revision": self.lab.state["revision"], "consistent_with_run": True,
                                           "proof": self.lab.proof["data"]})
            if path.startswith("/api/runs/"):
                return self.run_route(path, method)
            if path in {"/api/run", "/api/scenario"} and method == "POST":
                return self.send_json({"error": {"code": "UNSUPPORTED", "message": "Bản UI này chỉ dùng /api/jobs."}}, 404)
            return self.send_json({"error": {"code": "NOT_FOUND", "message": f"Không có {path}."}}, 404)
        except ValueError as exc:
            return self.send_json({"error": {"code": "BAD_REQUEST", "message": str(exc)}}, 400)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise ValueError("Body phải là JSON hợp lệ.") from None
        return value if isinstance(value, dict) else {}

    def run_route(self, path, method):
        parts = [unquote(part) for part in path.split("/") if part][2:]
        run_id = parts[0] if parts else None
        if len(parts) == 1:
            run = self.lab.runs.get(run_id)
            return self.send_json(run) if run else self.send_json({"error": {"code": "RUN_NOT_FOUND", "message": run_id}}, 404)
        if len(parts) == 2 and parts[1] == "integrity":
            stored = FIXTURES / "runs" / run_id / "integrity.json"
            return self.send_file(stored, "application/json; charset=utf-8")
        if len(parts) == 3 and parts[1] == "preview" and parts[2] in {"plain", "secure"}:
            return self.send_file(FIXTURES / "runs" / run_id / "preview" / f"{parts[2]}.html",
                                  "text/html; charset=utf-8", [("Content-Security-Policy", PREVIEW_CSP)])
        return self.send_json({"error": {"code": "NOT_FOUND", "message": path}}, 404)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18790)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"UI preview (mock, no backend): http://{args.host}:{args.port}/  fixtures={FIXTURES.name}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
