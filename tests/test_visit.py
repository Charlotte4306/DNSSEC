import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from visit import visit


class VisitTests(unittest.TestCase):
    @patch("visit.HTTPConnection")
    def test_blocks_external_ip_before_connection(self, factory):
        with self.assertRaises(ValueError):
            visit("8.8.8.8", "run", "plain")
        factory.assert_not_called()

    @patch("visit.HTTPConnection")
    def test_rejects_hostname_before_connection(self, factory):
        with self.assertRaises(ValueError):
            visit("www.demo.test", "run", "plain")
        factory.assert_not_called()

    @patch("visit.HTTPConnection")
    def test_connects_to_ip_and_preserves_host_header(self, factory):
        conn = factory.return_value
        conn.sock.getpeername.return_value = ("172.30.53.80", 80)
        response = conn.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key: {"X-Lab-Site": "legitimate", "Content-Type": "text/html"}.get(key)
        response.read.return_value = b"legitimate"
        result = visit("172.30.53.80", "run-123", "plain")
        factory.assert_called_once_with("172.30.53.80", port=80, timeout=3)
        self.assertEqual(conn.request.call_args.kwargs["headers"]["Host"], "www.demo.test")
        self.assertEqual(conn.request.call_args.kwargs["headers"]["X-Lab-Run-ID"], "run-123")
        self.assertEqual(result["http"]["connected_ip"], "172.30.53.80")
        self.assertIsNone(result["http"]["error"])
        conn.close.assert_called_once()

    @patch("visit.HTTPConnection")
    def test_connection_failure_does_not_claim_request_sent(self, factory):
        conn = factory.return_value
        conn.connect.side_effect = ConnectionRefusedError("connection refused")
        result = visit("172.30.53.80", "run", "plain")
        self.assertFalse(result["http"]["request_sent"])
        self.assertIsNone(result["http"]["status"])
        self.assertIsNotNone(result["http"]["error"])
        conn.request.assert_not_called()
        conn.close.assert_called_once()

    @patch("visit.HTTPConnection")
    def test_redirect_is_returned_without_second_request(self, factory):
        conn = factory.return_value
        conn.sock.getpeername.return_value = ("172.30.53.80", 80)
        response = conn.getresponse.return_value
        response.status = 302
        response.getheader.return_value = None
        response.read.return_value = b"redirect"
        result = visit("172.30.53.80", "run", "plain")
        self.assertEqual(result["http"]["status"], 302)
        conn.request.assert_called_once()


    @patch("visit.HTTPConnection")
    def test_protocol_failure_is_reported(self, factory):
        from http.client import BadStatusLine
        conn = factory.return_value
        conn.sock.getpeername.return_value = ("172.30.53.80", 80)
        conn.getresponse.side_effect = BadStatusLine("invalid HTTP")
        result = visit("172.30.53.80", "run", "plain")
        self.assertTrue(result["http"]["request_sent"])
        self.assertIsNone(result["http"]["status"])
        self.assertIsNotNone(result["http"]["error"])

    @patch("visit.MAX_BODY", 4)
    @patch("visit.HTTPConnection")
    def test_response_size_limit(self, factory):
        conn = factory.return_value
        conn.sock.getpeername.return_value = ("172.30.53.80", 80)
        conn.getresponse.return_value.status = 200
        conn.getresponse.return_value.getheader.return_value = "legitimate"
        conn.getresponse.return_value.read.return_value = b"12345"
        result = visit("172.30.53.80", "run", "plain")
        self.assertIsNone(result["http"]["body"])
        self.assertIn("limit", result["http"]["error"])


if __name__ == "__main__": unittest.main()
