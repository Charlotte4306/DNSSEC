"""Callbacks are tied to real socket/probe boundaries, not UI timers."""
import io
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lab"))
from visit import visit
from browse import browse
import api_worker


class ProgressTests(unittest.TestCase):
    @patch("visit.HTTPConnection")
    def test_connected_emitted_only_after_connect_and_before_request(self,factory):
        events=[];conn=factory.return_value
        def connected(): self.assertEqual([k for k,d in events],["http.connecting"])
        conn.connect.side_effect=connected
        conn.sock.getpeername.return_value=("172.30.53.80",80)
        def request(*args,**kwargs): self.assertEqual(events[-1][0],"http.connected")
        conn.request.side_effect=request
        conn.getresponse.return_value.status=200
        conn.getresponse.return_value.read.return_value=b"legitimate"
        conn.getresponse.return_value.getheader.return_value="legitimate"
        visit("172.30.53.80","test","plain",on_event=lambda *e:events.append(e))
        self.assertEqual([k for k,d in events],["http.connecting","http.connected","http.request_sent","http.response","http.finished"])

    @patch("visit.HTTPConnection")
    def test_connection_refused_never_emits_connected_or_request(self,factory):
        events=[];factory.return_value.connect.side_effect=ConnectionRefusedError("refused")
        visit("172.30.53.80","test","plain",on_event=lambda k,d:events.append(k))
        self.assertEqual(events,["http.connecting","http.error","http.finished"])

    @patch("browse.visit")
    @patch("browse.probe")
    def test_servfail_and_timeout_never_visit_http(self,probe,visitor):
        for error,rcode in [(None,"SERVFAIL"),("timeout",None)]:
            probe.return_value={"name":"www.demo.test","rcode":rcode,"error":error,"ad":False,"answers":[]}
            events=[]
            result=browse(resolver="secure",on_event=lambda k,d:events.append(k))
            self.assertFalse(result["http"]["attempted"])
            self.assertNotIn("http.connected",events)
            self.assertIn("http.skipped",events)
            self.assertEqual(events[-1],"branch.completed")
        visitor.assert_not_called()

    @patch("api_worker.snapshot",return_value={"attack":False,"changed_at":"unit"})
    def test_concurrent_branches_output_valid_ndjson_shared_run_id(self,snapshot):
        barrier=threading.Barrier(2)
        def branch(name,run_id,resolver,on_event=None):
            barrier.wait(timeout=2)
            for i in range(30): on_event("dns.started",{"i":i,"message":"Tiếng Việt"})
            return {"dns":{"error":None},"http":{"error":None}}
        output=io.StringIO()
        with patch("api_worker.browse",side_effect=branch),patch.object(sys,"argv",["worker","compare","--events","--run-id","unit-run"]),patch("sys.stdout",output):
            self.assertEqual(api_worker.main(),0)
        lines=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(lines),61)
        self.assertEqual({r["run_id"] for r in lines},{"unit-run"})
        self.assertEqual({r['branch'] for r in lines[:-1]},{'plain','secure'})
        self.assertEqual(lines[-1]['type'],'result')

if __name__=="__main__":unittest.main()
