"""One mutation/measurement at a time; snapshots detect external mode changes."""
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
import uuid
from dashboard.config import TARGET
from dashboard.services.docker_runner import APIError
from dashboard.services.evidence_service import match_logs


def now():
    return datetime.now(timezone.utc).isoformat()


class LabService:
    def __init__(self, runner, store):
        self.runner, self.store = runner, store
        self.lock = threading.Lock()
        self.meta_lock = threading.Lock()
        self.busy, self.task, self.last_error = False, None, None
        self.prepared = None

    def state(self):
        with self.meta_lock:
            info = {"busy": self.busy, "last_task": deepcopy(self.task), "last_error": deepcopy(self.last_error)}
            prepared = deepcopy(self.prepared)
        try:
            snapshot = self.runner.snapshot()
            info.update(source="live", actual_mode="attack" if snapshot["attack"] else "normal",
                        revision=snapshot["changed_at"], mode_snapshot=snapshot,
                        ready_for_run=prepared == snapshot and not info["busy"])
        except APIError as exc:
            info.update(source="live", actual_mode="unknown", revision=None, ready_for_run=False,
                        error={"code": exc.code, "message": exc.message})
        return info

    def exclusive(self, action, operation):
        if not self.lock.acquire(blocking=False):
            raise APIError("LAB_BUSY", "Lab đang xử lý tác vụ khác. Chờ tác vụ kết thúc.", 409)
        with self.meta_lock:
            self.busy, self.last_error = True, None
            self.task = {"action": action, "requested_at": now(), "status": "running"}
        try:
            value = operation()
            with self.meta_lock:
                self.task.update(status="completed", finished_at=now())
            return value
        except Exception as exc:
            with self.meta_lock:
                self.prepared = None
                self.last_error = {"code": exc.code if isinstance(exc, APIError) else "INTERNAL_ERROR", "message": str(exc)}
                self.task.update(status="failed", finished_at=now())
            raise
        finally:
            with self.meta_lock:
                self.busy = False
            self.lock.release()

    def scenario(self, action):
        def operation():
            steps = []
            # Invalidate readiness before changing relay; failed flush must not look ready.
            with self.meta_lock:
                self.prepared = None
            try:
                self.runner.set_mode(action == "attack")
                steps.append({"step": "set_mode", "ok": True})
                for resolver in ["plain", "secure"]:
                    self.runner.flush(resolver)
                    steps.append({"step": "flush_" + resolver, "ok": True})
                snapshot = self.runner.snapshot()
                if snapshot["attack"] != (action == "attack"):
                    raise APIError("MODE_MISMATCH", "Relay khác chế độ vừa yêu cầu.", 409)
            except APIError as exc:
                exc.details.update(steps=steps, requested_action=action, ready_for_run=False)
                raise
            with self.meta_lock:
                self.prepared = snapshot
            return {"source": "live", "action": action, "actual_mode": "attack" if snapshot["attack"] else "normal",
                    "revision": snapshot["changed_at"], "steps": steps, "ready_for_run": True}
        return self.exclusive("scenario:" + action, operation)

    def run(self):
        def operation():
            before = self.runner.snapshot()
            with self.meta_lock:
                prepared = deepcopy(self.prepared)
            if before != prepared:
                raise APIError("SCENARIO_NOT_PREPARED", "Chọn kịch bản qua API để đổi mode và xóa cache trước khi đo.", 409)
            run_id, started = str(uuid.uuid4()), now()
            with self.meta_lock:
                self.task["run_id"] = run_id
            worker = self.runner.compare(run_id)
            self.validate_worker(worker, run_id)
            after = self.runner.snapshot()
            consistent = worker["consistent"] and before == worker["scenario_before"] == worker["scenario_after"] == after
            if not consistent:
                with self.meta_lock:
                    self.prepared = None
            rows, context, errors = [], "", []
            for kind, getter in [("http_access", lambda since: self.collect_web_logs(worker, since)), ("dns_context", self.runner.dns_logs)]:
                try:
                    value = getter(started)
                    if kind == "http_access": rows = value
                    else: context = value
                except APIError as exc:
                    errors.append({"source": kind, "code": exc.code, "message": exc.message})
            matching, corroboration = match_logs(worker, rows)
            if any(error["source"] == "http_access" for error in errors):
                for evidence in corroboration.values():
                    evidence.update(no_http_observed=None, observed_request_count=None, http_corroborated=None)
            result = deepcopy(worker)
            result.update(source="live", requested_at=started, finished_at=now(), consistent=consistent,
                          scenario_revision=before["changed_at"], scenario_after=after,
                          evidence={"http_access": matching, "collection_errors": errors,
                                    "dns_context": context, "dns_context_correlation": "time_window_only_not_exact_run_id",
                                    "log_window_start": started,
                                    "note": "SERVFAIL không tự chứng minh lỗi chữ ký; log DNS chỉ là ngữ cảnh theo thời gian."})
            for branch, measured in result["results"].items():
                measured["scenario_revision"] = before["changed_at"]
                measured["evidence"] = corroboration[branch]
                measured["evidence"]["dns_file"] = f"{run_id}/worker.json"
                measured["http"]["preview_url"] = None
                body = measured["http"].pop("body", None)
                measured["http"]["body_available"] = body is not None
                measured["http"]["body_hash"] = measured["http"].get("body_sha256")
                if consistent and measured["http"]["status"] == 200 and not measured["http"]["error"] and body is not None:
                    measured["http"]["preview_url"] = f"/api/runs/{run_id}/preview/{branch}"
                # Preserve the worker's observation separately from evidence strength.
                measured["observed_interpretation"] = measured["interpretation"]
                if (not consistent
                    or (measured["http"]["status"] == 200 and not corroboration[branch]["http_corroborated"])
                    or (not measured["http"]["attempted"] and corroboration[branch]["observed_request_count"])):
                    measured["interpretation"] = "inconclusive"
            self.store.save(run_id, result, worker, matching, context)
            return result
        return self.exclusive("run", operation)

    def collect_web_logs(self, worker, since):
        # Bounded log-visibility wait, not a fabricated request count.
        expected = {branch for branch, result in worker["results"].items() if result["http"].get("request_sent")}
        deadline = time.monotonic() + 2
        while True:
            rows = self.runner.web_logs(since)
            observed = {row.get("branch_id") for row in rows if row.get("run_id") == worker["run_id"]}
            if expected <= observed or time.monotonic() >= deadline:
                return rows
            time.sleep(0.15)

    @staticmethod
    def validate_worker(worker, run_id):
        # Explicit checks remain active under python -O.
        def require(condition):
            if not condition:
                raise ValueError("Worker schema mismatch")
        try:
            require(worker["run_id"] == run_id and worker["target"] == TARGET)
            require(type(worker["consistent"]) is bool)
            require(set(worker["results"]) == {"plain", "secure"})
            require(isinstance(worker["scenario_before"], dict) and isinstance(worker["scenario_after"], dict))
            for branch, measured in worker["results"].items():
                require(measured["run_id"] == run_id and measured["branch_id"] == measured["resolver"] == branch)
                require(measured["dns"]["name"] == TARGET)
                require(isinstance(measured["dns"]["answers"], list))
                require(type(measured["http"]["attempted"]) is bool)
                require(type(measured["http"]["request_sent"]) is bool)
                require(isinstance(measured["interpretation"], str))
                for key in ["status", "site_id", "connected_ip", "body", "error"]:
                    require(key in measured["http"])
                if not measured["http"]["attempted"]:
                    require(measured["http"]["body"] is None and measured["http"]["status"] is None
                            and measured["http"]["connected_ip"] is None and not measured["http"]["request_sent"])
        except (KeyError, TypeError, ValueError) as exc:
            raise APIError("INVALID_WORKER_OUTPUT", "Kết quả worker không khớp lần chạy hoặc schema.", 502) from exc

    def proof(self):
        def operation():
            before = self.runner.snapshot()
            proof = self.runner.proof()
            after = self.runner.snapshot()
            if before != after:
                raise APIError("MODE_CHANGED", "Mode đã đổi trong lúc lấy bằng chứng.", 409)
            return {"source": "live", "revision": before["changed_at"], "requested_at": now(), "proof": proof}
        return self.exclusive("proof", operation)
