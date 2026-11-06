"""Background orchestration tests with a clearly isolated fake lab runner."""
import hashlib
import json
import time
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from test_api import FakeRunner
from dashboard.app import create_app
from dashboard.services.job_service import JobManager
from dashboard.services.docker_runner import APIError


class EventRunner(FakeRunner):
    def compare_events(self, run_id, callback):
        callback({"kind":"dns.started","branch":"plain","timestamp":"2026-10-29T00:00:00+00:00","data":{"name":"www.demo.test"}})
        return self.compare(run_id)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runner=EventRunner();self.app=create_app(self.runner,self.temp.name);self.app.testing=True
        self.client=self.app.test_client();self.jobs=self.app.extensions["jobs"]

    def wait(self,job_id):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            value=self.jobs.get(job_id,0)
            if value["status"]!="running":
                while self.app.extensions["lab"].busy and time.monotonic()<deadline: time.sleep(.001)
                return value
            time.sleep(.002)
        self.fail("Job did not finish")

    def start(self,action="baseline"):
        response=self.client.post("/api/jobs",json={"action":action})
        self.assertEqual(response.status_code,202,response.json)
        return response.json

    def test_sequence_cursor_persistence_checksum_and_no_docker_on_read(self):
        value=self.wait(self.start()["job_id"])
        self.assertEqual(value["status"],"completed",value)
        self.assertEqual([e["sequence"] for e in value["events"]],list(range(1,value["cursor"]+1)))
        self.assertTrue(any(e["source"]=="worker" for e in value["events"]))
        self.assertEqual({e["run_id"] for e in value["events"]},{value["run_id"]})
        with patch.object(self.runner,"snapshot",side_effect=AssertionError("Progress must not run Docker")),patch.object(self.runner,"compare",side_effect=AssertionError()):
            self.assertEqual(self.client.get(f"/api/jobs/{value['job_id']}?after={value['cursor']}").json["events"],[])
            self.assertEqual(JobManager(self.app.extensions["lab"]).get(value["job_id"],0),value)
        journal=self.jobs.folder(value["job_id"])/"events.jsonl"
        self.assertEqual(hashlib.sha256(journal.read_bytes()).hexdigest(),value["events_sha256"])
        result=self.client.get(value["result_url"])
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["job_id"],value["job_id"])

    def test_same_lock_rejects_all_overlapping_mutations(self):
        self.runner.wait=True
        job=self.start()
        self.addCleanup(self.runner.release.set)
        self.assertTrue(self.runner.entered.wait(2))
        for endpoint,payload in [("/api/jobs",{"action":"attack"}),("/api/run",{}),("/api/scenario",{"action":"recovery"}),("/api/proof",{})]:
            self.assertEqual(self.client.post(endpoint,json=payload).status_code,409,endpoint)
        self.assertEqual(self.client.get('/api/jobs/'+job['job_id']).status_code,200)
        self.runner.release.set();self.assertEqual(self.wait(job["job_id"])["status"],"completed")

    def test_flush_failure_is_failed_without_success_result(self):
        self.runner.fail_flush=True
        value=self.wait(self.start()["job_id"])
        self.assertEqual(value["status"],"failed")
        self.assertIsNone(value["result_url"])
        self.assertEqual(value["events"][-1]["kind"],"job.failed")
        self.assertFalse(any(e["kind"]=="job.completed" for e in value["events"]))
        self.assertFalse(self.app.extensions["lab"].busy)

    def test_timeout_is_failed_and_sealed(self):
        with patch.object(self.runner,"compare_events",side_effect=APIError("WORKER_TIMEOUT","Timed out",504)):
            value=self.wait(self.start()["job_id"])
        self.assertEqual(value["status"],"failed")
        self.assertEqual(value["error"]["code"],"WORKER_TIMEOUT")
        self.assertIsNone(value["result_url"])
        self.assertEqual(len(value["events_sha256"]),64)

    def test_http_error_keeps_measured_dns_but_job_is_failed(self):
        self.runner.http_error=True
        value=self.wait(self.start()["job_id"])
        self.assertEqual(value["status"],"failed")
        self.assertEqual(value["error"]["code"],"MEASUREMENT_FAILED")
        result=self.client.get(value["result_url"]).json
        self.assertEqual(result["results"]["secure"]["dns"]["ad"],True)
        self.assertEqual(result["results"]["secure"]["http"]["error"],"connection refused")

    def test_dns_timeout_keeps_observation_and_failed_status(self):
        self.runner.dns_error=True
        value=self.wait(self.start()["job_id"])
        self.assertEqual(value["status"],"failed")
        result=self.client.get(value["result_url"]).json
        self.assertFalse(result["results"]["secure"]["http"]["attempted"])

    def test_corruption_rejected_in_memory_and_after_restart(self):
        value=self.wait(self.start()["job_id"])
        journal=self.jobs.folder(value["job_id"])/"events.jsonl"
        journal.write_text(journal.read_text(encoding="utf-8")+"{}\n",encoding="utf-8")
        self.assertEqual(self.client.get('/api/jobs/'+value['job_id']).status_code,409)
        with self.assertRaises(APIError): JobManager(self.app.extensions["lab"]).get(value["job_id"],0)

    def test_restart_marks_unfinished_job_interrupted_never_restarts(self):
        import uuid
        job_id=str(uuid.uuid4());folder=self.jobs.folder(job_id);folder.mkdir(parents=True)
        (folder/'events.jsonl').write_text('',encoding='utf-8')
        (folder/'state.json').write_text(json.dumps({"job_id":job_id,"run_id":str(uuid.uuid4()),"status":"running","result_url":None}),encoding='utf-8')
        value=JobManager(self.app.extensions['lab']).get(job_id,0)
        self.assertEqual(value['status'],'interrupted')
        self.assertEqual(self.runner.calls,[])

    def test_invalid_id_cursor_target_and_action(self):
        self.assertEqual(self.client.get('/api/jobs/not-a-uuid').status_code,400)
        value=self.wait(self.start()["job_id"])
        for cursor in ['-1','1.2','999','256','bad','١']:
            self.assertEqual(self.client.get(f"/api/jobs/{value['job_id']}?after={cursor}").status_code,400,cursor)
        self.assertEqual(self.client.post('/api/jobs',json={'action':'attack','target':'example.com'}).status_code,400)
        self.assertEqual(self.client.post('/api/jobs',json={'action':'unknown'}).status_code,400)

if __name__=="__main__":unittest.main()
