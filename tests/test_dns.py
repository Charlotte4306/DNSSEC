"""Integration with real BIND, plus unit checks of the HTTP gate."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from dns_probe import probe
from browse import browse


class DNSIntegrationTests(unittest.TestCase):
    def test_authoritative_A_udp_and_tcp(self):
        for tcp in [False, True]:
            with self.subTest(tcp=tcp):
                r = probe(tcp=tcp)
                self.assertIsNone(r["error"])
                self.assertEqual(r["rcode"], "NOERROR")
                self.assertEqual(r["answers"], ["172.30.53.80"])
                self.assertTrue(r["aa"])
                self.assertFalse(r["ad"])

    def test_negative_answers(self):
        self.assertEqual(probe("not-present.demo.test")["rcode"], "NXDOMAIN")
        nodata = probe(rdtype="AAAA")
        self.assertEqual(nodata["rcode"], "NOERROR")
        self.assertEqual(nodata["answers"], [])

    def test_dns_to_http_really_reaches_good_site(self):
        r = browse(run_id="dns-integration-good")
        self.assertEqual(r["http"]["connected_ip"], r["dns"]["answers"][0])
        self.assertEqual(r["http"]["status"], 200)
        self.assertEqual(r["http"]["site_id"], "legitimate")

    @patch("browse.visit")
    def test_live_nxdomain_never_calls_http(self, visit):
        r = browse("not-present.demo.test")
        self.assertEqual(r["dns"]["rcode"], "NXDOMAIN")
        self.assertFalse(r["http"]["attempted"])
        visit.assert_not_called()


class DNSGateTests(unittest.TestCase):
    @patch("browse.visit")
    @patch("browse.probe")
    def test_failures_block_http(self, probe_mock, visit_mock):
        for rcode, error, answers in [("SERVFAIL", None, []), (None, "timeout", []),
                                      ("NOERROR", None, ["8.8.8.8"]),
                                      ("NOERROR", None, [])]:
            with self.subTest(rcode=rcode, error=error, answers=answers):
                probe_mock.return_value = {"rcode": rcode, "error": error, "answers": answers}
                r = browse()
                self.assertFalse(r["http"]["attempted"])
                self.assertIsNotNone(r["stop_reason"])
        visit_mock.assert_not_called()


if __name__ == "__main__": unittest.main()
