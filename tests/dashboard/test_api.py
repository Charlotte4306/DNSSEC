"""Host-side API tests; intentionally outside the container's unit-test discovery."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from dashboard.app import create_app
from dashboard.services.docker_runner import APIError, DockerRunner
from dashboard.services.evidence_service import EvidenceStore, sanitize_preview


class FakeRunner:
    def __init__(self):
        self.mode = {"attack": False, "changed_at": "initial"}
        self.calls, self.rows = [], []
        self.fail_flush = False
        self.changed = False
        self.missing_logs = False
        self.log_failure = False
        self.malformed = False
        self.http_error = False
        self.dns_error = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.wait = False

    def health(self):
        return {"ready": True, "source": "live", "services": {}}

    def snapshot(self):
        return deepcopy(self.mode)

    def set_mode(self, active):
        self.calls.append(("mode", active))
        self.mode = {"attack": active, "changed_at": str(len(self.calls))}

    def flush(self, resolver):
        self.calls.append(("flush", resolver))
        if self.fail_flush:
            raise APIError("DOCKER_COMMAND_FAILED", "Flush failed")

    def compare(self, run_id):
        self.calls.append(("compare", run_id))
        self.entered.set()
        if self.wait:
            if not self.release.wait(5):
                raise RuntimeError("Test did not release fake worker")
        before = deepcopy(self.mode)
        results = {}
        self.rows = []
        for branch in ["plain", "secure"]:
            blocked = branch == "secure" and self.mode["attack"]
            stopped = blocked or self.dns_error
            ip = "172.30.53.90" if self.mode["attack"] else "172.30.53.80"
            site = "training-fake" if self.mode["attack"] else "legitimate"
            failed_http = self.http_error and not stopped
            body = None if stopped or failed_http else "<h1>" + site + "</h1><script>alert(1)</script>"
            results[branch] = {
                "run_id": run_id, "branch_id": branch, "resolver": branch,
                "dns": {"name": "www.demo.test", "rcode": None if self.dns_error else "SERVFAIL" if blocked else "NOERROR",
                        "ad": None if self.dns_error else branch == "secure" and not blocked,
                        "answers": [] if stopped else [ip], "error": "timeout" if self.dns_error else None},
                "http": {"attempted": not stopped, "request_sent": not stopped and not failed_http,
                         "connected_ip": None if stopped or failed_http else ip,
                         "status": None if stopped or failed_http else 200,
                         "site_id": None if stopped or failed_http else site, "body": body,
                         "body_sha256": hashlib.sha256(body.encode()).hexdigest() if body else None,
                         "error": "connection refused" if failed_http else None},
                "interpretation": "inconclusive" if self.dns_error or failed_http else "blocked" if blocked else "accepted_fake" if self.mode["attack"] else "validated" if branch == "secure" else "reached_legitimate_unvalidated"
            }
            if not stopped and not failed_http:
                self.rows.append({"run_id": run_id, "branch_id": branch, "method": "GET", "path": "/",
                                  "host": "www.demo.test", "status": 200, "site_id": site})
        if self.changed:
            self.mode = {"attack": not self.mode["attack"], "changed_at": "outside-change"}
        result = {"run_id": run_id, "target": "www.demo.test", "consistent": True,
                  "scenario_before": before, "scenario_after": before, "results": results}
        if self.malformed:
            result["run_id"] = "wrong-id"
        return result

    def web_logs(self, since):
        if self.log_failure:
            raise APIError("DOCKER_TIMEOUT", "Logs unavailable", 504)
        return [] if self.missing_logs else deepcopy(self.rows)

    def dns_logs(self, since):
        return "time-window context only"

    def proof(self):
        return {"rrsig_unchanged": True, "records": {}}


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = FakeRunner()
        self.app = create_app(self.runner, self.temp.name)
        self.app.testing = True
        self.client = self.app.test_client()

    def post(self, endpoint, data=None):
        return self.client.post(endpoint, json=data or {})

    def prepare(self, action="baseline"):
        response = self.post("/api/scenario", {"action": action})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_requires_preparation_and_flushes_both(self):
        self.assertEqual(self.post("/api/run").status_code, 409)
        self.prepare()
        self.assertEqual(self.runner.calls[-3:], [("mode", False), ("flush", "plain"), ("flush", "secure")])
        self.assertTrue(self.client.get("/api/state").json["ready_for_run"])

    def test_baseline_attack_recovery_and_no_stale_preview(self):
        for action, expected in [("baseline", "legitimate"), ("attack", "training-fake"), ("recovery", "legitimate")]:
            self.prepare(action)
            response = self.post("/api/run")
            self.assertEqual(response.status_code, 200, response.json)
            data = response.json
            self.assertEqual(data["source"], "live")
            self.assertEqual(data["results"]["plain"]["http"]["site_id"], expected)
            self.assertTrue(data["results"]["plain"]["evidence"]["http_corroborated"])
            self.assertNotIn("body", data["results"]["plain"]["http"])
            self.assertEqual(self.client.get("/api/runs/" + data["run_id"]).json, data)
            preview = self.client.get(data["results"]["plain"]["http"]["preview_url"])
            self.assertEqual(preview.status_code, 200)
            self.assertNotIn("<script", preview.text)
            self.assertIn("sandbox", preview.headers["Content-Security-Policy"])
            if action == "attack":
                secure = data["results"]["secure"]
                self.assertFalse(secure["http"]["attempted"])
                self.assertIsNone(secure["http"]["preview_url"])
                self.assertTrue(secure["evidence"]["no_http_observed"])
                self.assertEqual(self.client.get(f"/api/runs/{data['run_id']}/preview/secure").status_code, 404)
            folder = Path(self.temp.name) / data["run_id"]
            self.assertTrue((folder / "worker.json").exists())
            self.assertIn("body", json.loads((folder / "worker.json").read_text())["results"]["plain"]["http"])

    def test_flush_failure_is_partial_and_not_ready(self):
        self.runner.fail_flush = True
        response = self.post("/api/scenario", {"action": "attack"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"]["details"]["steps"], [{"step": "set_mode", "ok": True}])
        state = self.client.get("/api/state").json
        self.assertEqual(state["actual_mode"], "attack")
        self.assertFalse(state["busy"])
        self.assertFalse(state["ready_for_run"])
        self.assertEqual(self.post("/api/run").status_code, 409)

    def test_busy_rejects_mutations_but_state_remains_readable(self):
        self.prepare()
        self.runner.wait = True
        responses = []
        def run():
            with self.app.test_client() as client:
                responses.append(client.post("/api/run", json={}).status_code)
        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(self.runner.entered.wait(2))
            self.assertTrue(self.client.get("/api/state").json["busy"])
            for endpoint, data in [("/api/run", {}), ("/api/scenario", {"action": "attack"}), ("/api/proof", {})]:
                self.assertEqual(self.post(endpoint, data).status_code, 409)
        finally:
            self.runner.release.set()
            thread.join(5)
        self.assertEqual(responses, [200])
        self.assertFalse(self.client.get("/api/state").json["busy"])

    def test_external_mode_change_does_not_publish_preview(self):
        self.prepare()
        self.runner.changed = True
        response = self.post("/api/run")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["consistent"])
        for result in response.json["results"].values():
            self.assertEqual(result["interpretation"], "inconclusive")
            self.assertIsNone(result["http"]["preview_url"])

    def test_dns_and_http_errors_preserve_stage(self):
        for kind in ["dns_error", "http_error"]:
            self.prepare()
            setattr(self.runner, kind, True)
            data = self.post("/api/run").json
            result = data["results"]["secure"]
            self.assertEqual(result["interpretation"], "inconclusive")
            self.assertEqual(result["http"]["attempted"], kind == "http_error")
            self.assertEqual(result["dns"]["rcode"], "NOERROR" if kind == "http_error" else None)
            self.assertIsNone(result["http"]["preview_url"])
            setattr(self.runner, kind, False)

    def test_missing_access_logs_downgrades_verified_result(self):
        self.prepare("attack")
        self.runner.missing_logs = True
        result = self.post("/api/run").json["results"]["plain"]
        self.assertEqual(result["observed_interpretation"], "accepted_fake")
        self.assertEqual(result["interpretation"], "inconclusive")

    def test_log_collection_failure_is_not_zero_requests(self):
        self.prepare("attack")
        self.runner.log_failure = True
        data = self.post("/api/run").json
        self.assertTrue(data["evidence"]["collection_errors"])
        self.assertIsNone(data["results"]["secure"]["evidence"]["no_http_observed"])

    def test_wrong_worker_identity_is_rejected_and_lock_released(self):
        self.prepare()
        self.runner.malformed = True
        self.assertEqual(self.post("/api/run").status_code, 502)
        self.assertFalse(self.client.get("/api/state").json["busy"])

    def test_target_action_and_command_injection_rejected(self):
        for endpoint, data in [("/api/run", {"target": "example.com"}),
                               ("/api/run", {"command": "docker ps"}),
                               ("/api/scenario", {"action": "attack; echo x"}),
                               ("/api/scenario", {"action": ["attack"]})]:
            self.assertEqual(self.post(endpoint, data).status_code, 400)
        self.assertEqual(self.runner.calls, [])

    def test_json_origin_and_host_guards(self):
        self.assertEqual(self.client.post("/api/run", data="{}").status_code, 415)
        self.assertEqual(self.client.post("/api/run", json={}, headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/state", headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/run", data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/run", json=[]).status_code, 400)

    def test_missing_runs_bad_branches_and_traversal(self):
        self.assertEqual(self.client.get("/api/runs/missing").status_code, 404)
        with self.assertRaises(APIError):
            EvidenceStore(self.temp.name).path("../outside")
        self.prepare()
        data = self.post("/api/run").json
        self.assertEqual(self.client.get(f"/api/runs/{data['run_id']}/preview/other").status_code, 400)

    def test_last_run_survives_proof_and_page_does_not_load_mock(self):
        self.prepare()
        data = self.post("/api/run").json
        self.post("/api/proof")
        state = self.client.get("/api/state").json
        self.assertEqual(state["last_task"]["action"], "proof")
        self.assertEqual(state["last_run_id"], data["run_id"])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('/static/js/app.js', page.text)
        self.assertNotIn('mock-data.js', page.text)
        self.assertEqual(self.client.get('/static/js/mock-data.js').status_code, 404)

    def test_proof_is_real_runner_output_and_health_failure(self):
        self.assertTrue(self.post("/api/proof").json["proof"]["rrsig_unchanged"])
        self.runner.health = lambda: {"ready": False, "services": {}}
        self.assertEqual(self.client.get("/api/health").status_code, 503)


class RunnerTests(unittest.TestCase):
    def test_timeout_and_missing_docker_are_json_errors(self):
        runner = DockerRunner()
        for error, status in [(FileNotFoundError(), 503), (subprocess.TimeoutExpired("docker", 1), 504)]:
            with patch("dashboard.services.docker_runner.subprocess.run", side_effect=error):
                with self.assertRaises(APIError) as result:
                    runner.snapshot()
                self.assertEqual(result.exception.status, status)

    def test_measured_error_exit_one_preserves_worker_json(self):
        result = subprocess.CompletedProcess([], 1, '{"measured": true}', '')
        with patch("dashboard.services.docker_runner.subprocess.run", return_value=result) as called:
            self.assertTrue(DockerRunner().compare("test-run")["measured"])
            self.assertFalse(called.call_args.kwargs["shell"])
            self.assertIsInstance(called.call_args.args[0], list)

    def test_adjacent_json_access_logs_preserve_both_branches(self):
        line = 'web-good-1 | {"run_id":"r","branch_id":"plain"}{"run_id":"r","branch_id":"secure"}\nweb-good-1 | \n'
        with patch.object(DockerRunner, "command", return_value=line):
            rows = DockerRunner().web_logs("2026-10-29T00:00:00Z")
        self.assertEqual([row["branch_id"] for row in rows], ["plain", "secure"])

    def test_preview_removes_active_content_and_network_sources(self):
        hostile = '<head><style>LEAK_CSS</style></head><h1>Visible</h1><script>bad()</script><img src="https://evil" onerror="bad()"><iframe src="https://evil"></iframe><form action="https://evil"><input></form><a href="javascript:bad()">Link</a><p style="background:url(https://evil)">Text</p>'
        clean = sanitize_preview(hostile, "legitimate")
        for forbidden in ["<script", "<iframe", "<img", "<form", "<input", "https://evil", "javascript:", "onerror", "LEAK_CSS", "bad()"]:
            self.assertNotIn(forbidden, clean)
        self.assertIn("<h1>Visible</h1>", clean)


if __name__ == "__main__":
    unittest.main()
