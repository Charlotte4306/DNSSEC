"""Integration tests: run inside the client with both websites healthy."""
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from visit import visit, TARGETS


class WebIntegrationTests(unittest.TestCase):
    def test_both_sites_return_correct_identity_and_body(self):
        for name, target in TARGETS.items():
            with self.subTest(site=name):
                result = visit(target["ip"], "integration-" + str(uuid.uuid4()), name)
                http = result["http"]
                self.assertIsNone(http["error"])
                self.assertTrue(http["request_sent"])
                self.assertEqual(http["connected_ip"], target["ip"])
                self.assertEqual(http["status"], 200)
                self.assertEqual(http["site_id"], target["site_id"])
                self.assertIn(target["site_id"], http["body"])
                self.assertEqual(len(http["body_sha256"]), 64)

    def test_http_routes(self):
        for target in TARGETS.values():
            for method, path, expected in [("GET", "/health", 200), ("GET", "/missing", 404), ("HEAD", "/", 200)]:
                with self.subTest(ip=target["ip"], method=method, path=path):
                    conn = HTTPConnection(target["ip"], timeout=3)
                    try:
                        conn.request(method, path, headers={"Host": "www.demo.test"})
                        response = conn.getresponse()
                        body = response.read()
                        self.assertEqual(response.status, expected)
                        self.assertEqual(response.getheader("X-Lab-Site"), target["site_id"])
                        if path == "/health":
                            self.assertEqual(json.loads(body)["status"], "ok")
                        if method == "HEAD":
                            self.assertEqual(body, b"")
                    finally:
                        conn.close()


if __name__ == "__main__": unittest.main()
