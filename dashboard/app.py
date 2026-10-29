"""Host-side API only. Start one process; UI integration stays on dashboard-layout."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException
from dashboard.config import EVIDENCE_ROOT, REPO_ROOT, TARGET
from dashboard.services.docker_runner import APIError, DockerRunner
from dashboard.services.evidence_service import EvidenceStore
from dashboard.services.scenario_service import LabService


def create_app(runner=None, evidence_root=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=4096, JSON_SORT_KEYS=False)
    service = LabService(runner or DockerRunner(), EvidenceStore(evidence_root or EVIDENCE_ROOT))
    app.extensions["lab"] = service

    @app.before_request
    def local_requests_only():
        host = urlsplit("http://" + request.host).hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise APIError("INVALID_HOST", "API chỉ phục vụ localhost.", 403)
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                raise APIError("INVALID_ORIGIN", "Chỉ chấp nhận thao tác cùng origin.", 403)
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                raise APIError("INVALID_ORIGIN", "Không nhận thao tác từ website khác.", 403)
            if not request.is_json:
                raise APIError("JSON_REQUIRED", "Gửi Content-Type: application/json và JSON object.", 415)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(APIError)
    def api_error(exc):
        return jsonify(error={"code": exc.code, "message": exc.message, "details": exc.details}), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error={"code": exc.name.upper().replace(" ", "_"), "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def internal_error(exc):
        app.logger.exception("Dashboard operation failed")
        return jsonify(error={"code": "INTERNAL_ERROR", "message": "Backend gặp lỗi; xem terminal. Không có kết quả mới được xác nhận."}), 500

    def body(allowed=()):
        data = request.get_json()
        if not isinstance(data, dict) or set(data) - set(allowed):
            raise APIError("INVALID_INPUT", "JSON phải là object và chỉ chứa các trường được phép.", 400)
        return data

    @app.get("/")
    def index():
        return jsonify(service="DNSSEC lab API", source="live", ui_connected=False,
                       note="Frontend được nối trên feature/dashboard-layout.", endpoints=["/api/health", "/api/state"])

    @app.get("/api/health")
    def health():
        value = service.runner.health()
        return jsonify(value), 200 if value["ready"] else 503

    @app.get("/api/state")
    def state():
        return jsonify(service.state())

    @app.post("/api/scenario")
    def scenario():
        data = body({"action"})
        if data.get("action") not in ("baseline", "attack", "recovery"):
            raise APIError("INVALID_SCENARIO", "action phải là baseline, attack hoặc recovery.", 400)
        return jsonify(service.scenario(data["action"]))

    @app.post("/api/run")
    def run():
        data = body({"target"})
        if data.get("target", TARGET) != TARGET:
            raise APIError("INVALID_TARGET", "Chỉ nhận www.demo.test.", 400)
        return jsonify(service.run())

    @app.post("/api/proof")
    def proof():
        body()
        return jsonify(service.proof())

    @app.get("/api/runs/<run_id>")
    def result(run_id):
        return jsonify(service.store.get(run_id))

    @app.get("/api/runs/<run_id>/preview/<branch>")
    def preview(run_id, branch):
        response = Response(service.store.preview(run_id, branch), content_type="text/html; charset=utf-8")
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        return response

    return app


@contextmanager
def single_server():
    """One CLI server per checkout, including different ports. No reloader/workers."""
    lock_file = REPO_ROOT / "evidence" / "dashboard-api.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_file.open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("API server đang chạy cho checkout này. Dừng server cũ trước.") from exc
        yield
    finally:
        handle.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with single_server():
        create_app().run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=True)
