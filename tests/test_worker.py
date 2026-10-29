import sys
from pathlib import Path
from unittest.mock import patch
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from browse import browse
from api_worker import compare

class WorkerGateTests(unittest.TestCase):
    @patch("browse.visit")
    @patch("browse.probe")
    def test_secure_servfail_never_calls_http_or_fallback(self, probe, visit):
        probe.return_value = {"error": None, "rcode": "SERVFAIL", "ad": False, "answers": []}
        r = browse(run_id="unit-blocked", resolver="secure")
        self.assertFalse(r["http"]["attempted"])
        self.assertIsNone(r["http"]["body"])
        visit.assert_not_called()
        probe.assert_called_once_with("www.demo.test", server="secure")

    @patch("browse.visit")
    @patch("browse.probe")
    def test_secure_rejects_noerror_without_ad(self, probe, visit):
        probe.return_value = {"error": None, "rcode": "NOERROR", "ad": False, "answers": ["172.30.53.80"]}
        r = browse(resolver="secure")
        self.assertEqual(r["stop_reason"], "SECURE_REQUIRES_AUTHENTICATED_DATA")
        visit.assert_not_called()

    @patch("browse.visit")
    @patch("browse.probe")
    def test_plain_fetches_exact_dns_ip(self, probe, visit):
        probe.return_value = {"error": None, "rcode": "NOERROR", "ad": False, "answers": ["172.30.53.90"]}
        visit.return_value = {"http": {"attempted": True, "status": 200, "error": None,
            "site_id": "training-fake", "connected_ip": "172.30.53.90"}}
        r = browse(run_id="unit-fake", resolver="plain")
        visit.assert_called_once_with("172.30.53.90", "unit-fake", "plain", host="www.demo.test")
        self.assertEqual(r["interpretation"], "accepted_fake")

    @patch("browse.visit")
    @patch("browse.probe")
    def test_http_failure_keeps_successful_dns_result(self, probe, visit):
        probe.return_value = {"error": None, "rcode": "NOERROR", "ad": True, "answers": ["172.30.53.80"]}
        visit.return_value = {"http": {"attempted": True, "status": None, "error": "refused"}}
        r = browse(resolver="secure")
        self.assertEqual(r["dns"]["rcode"], "NOERROR")
        self.assertEqual(r["stop_reason"], "HTTP_ERROR")

    @patch("browse.visit")
    @patch("browse.probe")
    def test_bad_run_id_fails_before_network(self, probe, visit):
        with self.assertRaises(ValueError): browse(run_id="bad\r\nheader")
        probe.assert_not_called(); visit.assert_not_called()

    @patch("api_worker.browse")
    @patch("api_worker.snapshot")
    def test_concurrent_mode_change_marks_results_inconclusive(self, snapshot, browse):
        snapshot.side_effect = [{"attack": False}, {"attack": True}]
        browse.side_effect = lambda *args: {"interpretation": "validated"}
        r = compare(run_id="mode-race")
        self.assertFalse(r["consistent"])
        self.assertTrue(all(x["interpretation"] == "inconclusive" for x in r["results"].values()))

    @patch("browse.visit")
    @patch("browse.probe")
    def test_blocked_run_does_not_reuse_previous_page(self, probe, visit):
        probe.side_effect = [
            {"error": None, "rcode": "NOERROR", "ad": True, "answers": ["172.30.53.80"]},
            {"error": None, "rcode": "SERVFAIL", "ad": False, "answers": []}]
        visit.return_value = {"http": {"status": 200, "error": None, "body": "old page",
            "site_id": "legitimate", "connected_ip": "172.30.53.80"}}
        first = browse(resolver="secure")
        second = browse(resolver="secure")
        self.assertEqual(first["http"]["body"], "old page")
        self.assertIsNone(second["http"]["body"])
        self.assertFalse(second["http"]["attempted"])
        self.assertEqual(visit.call_count, 1)
