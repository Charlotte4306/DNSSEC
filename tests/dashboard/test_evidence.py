"""Faults in saved evidence must fail audit, even when file hashes are rewritten."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_api import FakeRunner
from dashboard.app import create_app
from dashboard.services.docker_runner import APIError
from dashboard.services.evidence_audit import audit_run
from dashboard.services.evidence_integrity import verify_manifest


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = FakeRunner()
        self.app = create_app(self.runner, self.temp.name)
        self.client = self.app.test_client()

    def run_phase(self, phase="baseline"):
        response = self.client.post("/api/scenario", json={"action": phase})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/run", json={})
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json
        return result, Path(self.temp.name)/result["run_id"]

    def rewrite_manifest_for(self, folder, filename):
        manifest = json.loads((folder/"checksums.json").read_text())
        manifest["files"][filename] = hashlib.sha256((folder/filename).read_bytes()).hexdigest()
        (folder/"checksums.json").write_text(json.dumps(manifest))

    def test_proof_manifest_and_offline_audit_for_three_phases(self):
        for phase in ["baseline", "attack", "recovery"]:
            with self.subTest(phase=phase):
                result, folder = self.run_phase(phase)
                self.assertTrue((folder/"proof.json").is_file())
                self.assertEqual(json.loads((folder/"proof.json").read_text()), result["evidence"]["proof"])
                self.assertTrue(self.client.get(result["evidence"]["integrity_url"]).json["verified"])
                report = audit_run(folder)
                self.assertTrue(report["passed"], report)

    def test_changed_preview_refused_by_api_and_audit(self):
        result, folder = self.run_phase()
        (folder/"preview-plain.html").write_text("changed content")
        self.assertFalse(verify_manifest(folder, result["run_id"])["verified"])
        self.assertEqual(self.client.get(result["results"]["plain"]["http"]["preview_url"]).status_code, 409)
        self.assertFalse(audit_run(folder)["passed"])

    def test_missing_artifact_is_not_complete_evidence(self):
        result, folder = self.run_phase()
        (folder/"http-access.json").unlink()
        integrity = self.client.get(result["evidence"]["integrity_url"]).json
        self.assertEqual(integrity["status"], "mismatch")
        self.assertFalse(integrity["verified"])

    def test_manifest_path_traversal_rejected_without_reading_target(self):
        result, folder = self.run_phase()
        manifest = json.loads((folder/"checksums.json").read_text())
        manifest["files"]["../../outside.json"] = "0"*64
        (folder/"checksums.json").write_text(json.dumps(manifest))
        integrity = verify_manifest(folder, result["run_id"])
        self.assertEqual(integrity["status"], "invalid_manifest")
        self.assertEqual(integrity["files"], [])

    def test_legacy_run_without_manifest_is_unverifiable_but_readable(self):
        result, folder = self.run_phase()
        (folder/"checksums.json").unlink()
        self.assertEqual(self.client.get("/api/runs/"+result["run_id"]).status_code, 200)
        self.assertEqual(verify_manifest(folder,result["run_id"])["status"], "unavailable")
        self.assertFalse(audit_run(folder)["passed"])

    def test_legacy_invalid_json_is_reported_as_corrupt(self):
        result, folder = self.run_phase()
        (folder/"checksums.json").unlink()
        (folder/"result.json").write_text("{broken")
        response=self.client.get("/api/runs/"+result["run_id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json["error"]["code"],"EVIDENCE_CORRUPT")

    def test_hashes_do_not_hide_body_mismatch(self):
        result, folder = self.run_phase()
        worker = json.loads((folder/"worker.json").read_text())
        worker["results"]["plain"]["http"]["body"] = "different body"
        (folder/"worker.json").write_text(json.dumps(worker))
        self.rewrite_manifest_for(folder,"worker.json")
        self.assertTrue(verify_manifest(folder,result["run_id"])["verified"])
        failed = [row["id"] for row in audit_run(folder)["checks"] if row["status"] == "FAIL"]
        self.assertIn("plain_body_hash", failed)

    def test_logs_from_another_run_fail_even_with_valid_file_hash(self):
        result, folder = self.run_phase()
        logs = json.loads((folder/"http-access.json").read_text())
        logs[0]["run_id"] = "another-run"
        (folder/"http-access.json").write_text(json.dumps(logs))
        self.rewrite_manifest_for(folder,"http-access.json")
        failed = [row["id"] for row in audit_run(folder)["checks"] if row["status"] == "FAIL"]
        self.assertIn("log_identity", failed)

    def test_proof_failure_is_saved_as_missing_evidence_not_fabricated(self):
        with patch.object(self.runner,"proof",side_effect=APIError("PROOF_UNAVAILABLE","Missing proof")):
            result, folder = self.run_phase()
        self.assertIsNone(result["evidence"]["proof"])
        self.assertFalse((folder/"proof.json").exists())
        self.assertTrue(verify_manifest(folder,result["run_id"])["verified"])
        self.assertFalse(audit_run(folder)["passed"])

    def test_servfail_without_correlated_logs_stays_generic(self):
        result, folder = self.run_phase("attack")
        secure = result["results"]["secure"]
        self.assertEqual(secure["interpretation"],"blocked")
        self.assertFalse(secure["http"]["attempted"])
        self.assertNotIn("signature crypto failed", result["evidence"]["dns_context"])
        self.assertEqual(result["evidence"]["dns_context_correlation"],"time_window_only_not_exact_run_id")

    def test_incomplete_write_never_publishes_a_completed_run(self):
        self.client.post("/api/scenario",json={"action":"baseline"})
        with patch("dashboard.services.evidence_service.write_manifest",side_effect=OSError("disk failure")):
            with patch.object(self.app.logger,"exception"):
                response = self.client.post("/api/run",json={})
        self.assertEqual(response.status_code,500)
        directories=list(Path(self.temp.name).iterdir())
        self.assertEqual(len(directories),1)
        self.assertFalse((directories[0]/"result.json").exists())
        self.assertEqual(self.client.get("/api/runs/"+directories[0].name).status_code,404)


if __name__ == "__main__":
    unittest.main()
