"""The offline preview must not masquerade as measurements or expose files."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[2]/"ui_preview/serve.py"
        spec=importlib.util.spec_from_file_location("ui_preview_under_test",path)
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
        cls.server=cls.module.ThreadingHTTPServer(("127.0.0.1",0),cls.module.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def get(self,path):
        return urllib.request.urlopen(self.base+path,timeout=5)
    def test_static_traversal_is_blocked(self):
        for path in ["/static/%2e%2e/%2e%2e/dashboard/app.py","/static/%2e%2e/serve.py"]:
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:self.get(path)
            self.assertEqual(error.exception.code,403)
    def test_preview_visibly_and_structurally_identifies_mock(self):
        with self.get('/') as r:html=r.read().decode('utf-8')
        self.assertIn('UI PREVIEW',html)
        self.assertIn('DỮ LIỆU PHÁT LẠI',html)
        for path in ['/api/state','/api/health']:
            with self.get(path) as r:self.assertEqual(json.load(r)['source'],'mock')
        run_id=self.module.LAB.jobs['baseline']['run_id']
        with self.get('/api/runs/'+run_id) as r:
            value=json.load(r);self.assertEqual(value['source'],'mock')
            self.assertIn(value['job_id'],[job['job_id'] for job in self.module.LAB.jobs.values()])
        with self.get('/api/runs/'+run_id+'/integrity') as r:
            value=json.load(r);self.assertFalse(value['verified']);self.assertEqual(value['status'],'preview_not_measured')
    def test_completed_poll_respects_cursor(self):
        job=self.module.LAB.jobs['baseline']
        with self.get(f"/api/jobs/{job['job_id']}?after={job['cursor']}") as r:self.assertEqual(json.load(r)['events'],[])
    def test_one_preview_job_at_a_time(self):
        lab=self.module.Lab()
        self.assertIsNotNone(lab.start_job('attack'))
        self.assertIsNone(lab.start_job('recovery'))
    def test_styles_and_font_are_available(self):
        for path in ['/static/css/kawaii.css','/static/fonts/nunito-OFL.txt']:
            with self.get(path) as r:self.assertEqual(r.status,200)

if __name__=='__main__':unittest.main()
