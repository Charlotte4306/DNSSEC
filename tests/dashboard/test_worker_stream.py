"""Validate framed worker output; no Docker required for these protocol tests."""
import io
import json
import unittest
from unittest.mock import patch
from dashboard.services.worker_stream import stream_compare
from dashboard.services.docker_runner import APIError

class Process:
    def __init__(self,records,code=0):
        self.stdout=io.BytesIO(b"".join((json.dumps(r)+"\n").encode() if isinstance(r,dict) else r for r in records));self.code=code
    def wait(self,timeout=None): return self.code
    def poll(self): return self.code

class WorkerStreamTests(unittest.TestCase):
    def test_valid_stream_event_then_terminal(self):
        records=[{"type":"event","run_id":"test","kind":"dns.started","branch":"plain","timestamp":"2026-10-29T00:00:00Z","data":{}},{"type":"result","run_id":"test","result":{"run_id":"test"}}]
        events=[]
        with patch('dashboard.services.worker_stream.subprocess.Popen',return_value=Process(records)):
            self.assertEqual(stream_compare('test',events.append),{'run_id':'test'})
        self.assertEqual(len(events),1)

    def test_invalid_or_truncated_stream_is_never_accepted(self):
        terminal={"type":"result","run_id":"test","result":{}}
        for records in [[b'{"type":'],[],[{"type":"result","run_id":"other","result":{}}],[terminal,terminal],[{"type":"event","run_id":"test","kind":"not-real","branch":"plain","timestamp":"now","data":{}}]]:
            with self.subTest(records=records),patch('dashboard.services.worker_stream.subprocess.Popen',return_value=Process(records)):
                with self.assertRaises(APIError) as caught:stream_compare('test',lambda e:None)
                self.assertEqual(caught.exception.code,'INVALID_WORKER_OUTPUT')

    def test_container_timeout_has_explicit_failed_code(self):
        with patch('dashboard.services.worker_stream.subprocess.Popen',return_value=Process([],124)):
            with self.assertRaises(APIError) as caught:stream_compare('test',lambda e:None)
        self.assertEqual(caught.exception.code,'WORKER_TIMEOUT')

if __name__=='__main__':unittest.main()
