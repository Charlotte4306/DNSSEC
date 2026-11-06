"""Local Docker acceptance: python tools/acceptance.py [--faults]. No UI/SSH calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.app import create_app, single_server
from dashboard.config import REPO_ROOT, EVIDENCE_ROOT
from dashboard.services.docker_runner import DockerRunner
from dashboard.services.evidence_audit import audit_run


def require(condition, message):
    if not condition:
        raise RuntimeError(message)
    return True


def summarize_cases(cases, ready):
    counts={status:sum(row["status"]==status for row in cases) for status in ["PASS","FAIL","SKIP"]}
    partial=any(row["status"]=="SKIP" and row["id"]!="E08-UI" for row in cases)
    status="FAIL" if counts["FAIL"] or not ready else "PARTIAL" if partial else "PASS_WITH_UI_DEFERRED"
    return {"summary":counts,"status":status,"backend_passed":status=="PASS_WITH_UI_DEFERRED"}


class ObservedRunner(DockerRunner):
    def __init__(self):
        self.started = threading.Event()
        self.after_compare = None

    def compare(self, run_id):
        self.started.set()
        value = super().compare(run_id)
        callback, self.after_compare = self.after_compare, None
        if callback:
            callback()
        return value


class Acceptance:
    def __init__(self, faults):
        self.faults = faults
        self.runner = ObservedRunner()
        self.app = create_app(self.runner)
        self.client = self.app.test_client()
        self.folder = EVIDENCE_ROOT / ("acceptance-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8])
        self.folder.mkdir(parents=True)
        self.report = {"started_at": self.now(), "source": "local_real_docker_except_explicit_unit_cases",
                       "cases": [], "runs": {}, "ui_scope": "deferred_by_user", "report_directory": str(self.folder)}
        self.undo = []
        self.preflight_ready = False

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def check(self, code, description, operation, kind="live"):
        try:
            value = operation()
            require(value is not False, description)
            row = {"id": code, "description": description, "kind": kind, "status": "PASS"}
        except Exception as exc:
            row = {"id": code, "description": description, "kind": kind, "status": "FAIL", "error": str(exc)}
        self.report["cases"].append(row)
        print(f"{row['status']} {code}: {description}"+(" | "+row["error"] if "error" in row else ""), flush=True)
        return row["status"] == "PASS"

    def skip(self, code, reason):
        self.report["cases"].append({"id":code,"status":"SKIP","description":reason,"kind":"not_run"})

    def post(self, route, data=None, expected=200):
        response = self.client.post(route, json=data or {})
        require(response.status_code == expected, f"{route}: HTTP {response.status_code}, {response.json}")
        return response.json

    def scenario(self, phase):
        return self.post("/api/scenario", {"action":phase})

    def measure(self, phase, key=None):
        self.scenario(phase)
        data = self.post("/api/run")
        self.report["runs"][key or phase] = data["run_id"]
        return data

    def probe_bundle(self):
        code = ("import sys,json;sys.path.insert(0,'/app/lab');from dns_probe import probe;"
                "print(json.dumps({'authority':probe(server='authority'),"
                "'control':probe('control.demo.test',server='secure'),"
                "'negative':probe('not-present.demo.test',server='secure'),"
                "'tcp':probe(server='secure',tcp=True)}))")
        return self.runner.decode(self.runner.command(["exec","-T","client","python","-c",code]))

    def verify_run(self, data):
        report = audit_run(EVIDENCE_ROOT/data["run_id"])
        require(report["passed"], json.dumps([row for row in report["checks"] if row["status"]=="FAIL"]))
        require(self.client.get(f"/api/runs/{data['run_id']}/integrity").json["verified"], "API integrity failed")
        return True

    def preflight(self):
        require(not os.environ.get("DOCKER_HOST", "").startswith(("tcp:","ssh:")), "Remote Docker host is not allowed")
        endpoint = subprocess.check_output(["docker","context","inspect","--format","{{.Endpoints.docker.Host}}"], text=True, timeout=10).strip()
        require(endpoint.startswith(("unix:","npipe:")), "Use a local Unix/named-pipe Docker context")
        response = self.client.get("/api/health")
        require(response.status_code==200 and response.json["ready"], f"Local Docker health HTTP {response.status_code}: {response.json}")
        self.preflight_ready = True
        self.scenario("baseline")
        return True

    def unit_checks(self):
        host = subprocess.run([sys.executable,"-m","unittest","discover","-s","tests/dashboard","-v"],cwd=REPO_ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=90)
        host_text = host.stdout+host.stderr
        (self.folder/"host-unit.log").write_text(host_text,encoding="utf-8")
        require(host.returncode==0,"Host API/evidence unit tests failed; see host-unit.log")
        code = "import sys,unittest;s=unittest.defaultTestLoader.discover('/app/tests');r=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(s);sys.exit(not r.wasSuccessful())"
        client_text = self.runner.command(["exec","-T","client","python","-c",code],timeout=90,allowed=(0,1))
        (self.folder/"client-unit.log").write_text(client_text,encoding="utf-8")
        require("\nOK\n" in client_text.replace("\r\n","\n"), "Client DNS/HTTP tests failed; see client-unit.log")
        self.report["unit_tests"] = {"host": re.search(r"Ran (\d+) tests",host_text).group(1),
                                    "client": re.search(r"Ran (\d+) tests",client_text).group(1)}
        require("test_redirect_is_returned_without_second_request" in client_text and "test_blocks_external_ip_before_connection" in client_text,"Missing redirect/IP tests")
        require("test_servfail_without_correlated_logs_stays_generic" in host_text,"Missing generic SERVFAIL test")
        return True

    @staticmethod
    def good_pair(data):
        for name in ["plain","secure"]:
            r=data["results"][name]
            require(r["dns"]["rcode"]=="NOERROR" and r["dns"]["answers"]==["172.30.53.80"], name+" wrong DNS")
            require(r["http"]["status"]==200 and r["http"]["connected_ip"]=="172.30.53.80" and r["http"]["site_id"]=="legitimate",name+" wrong HTTP")
            require(r["evidence"]["http_corroborated"],name+" missing log")
        require(data["results"]["secure"]["dns"]["ad"] is True,"Secure AD missing")
        return True

    def positive(self):
        baseline=self.measure("baseline")
        self.check("T01","Baseline: both branches reach legitimate site; secure AD",lambda:self.good_pair(baseline))
        baseline_probes=self.probe_bundle()
        attack=self.measure("attack")
        plain,secure=attack["results"]["plain"],attack["results"]["secure"]
        self.check("T02","Plain accepts modified A, connects to .90, and matches access log",lambda:plain["dns"]["answers"]==["172.30.53.90"] and plain["http"]["connected_ip"]=="172.30.53.90" and plain["http"]["site_id"]=="training-fake" and plain["http"]["status"]==200 and plain["evidence"]["http_corroborated"])
        self.check("T03","Secure SERVFAIL has no usable IP, no HTTP, and no web access log",lambda:secure["dns"]["rcode"]=="SERVFAIL" and not secure["dns"]["answers"] and secure["http"]["attempted"] is False and secure["evidence"]["no_http_observed"] is True and secure["evidence"]["observed_request_count"]==0)
        proof=attack["evidence"]["proof"]
        self.check("T05","Saved proof: original .80, modified .90, nonempty unchanged RRSIG",lambda:proof is not None and proof["consistent_with_run"] and proof["data"]["rrsig_unchanged"] and proof["data"]["records"]["authority"]["answers"]==["172.30.53.80"] and proof["data"]["records"]["tamper"]["answers"]==["172.30.53.90"] and self.verify_run(attack))
        attack_probes=self.probe_bundle()
        self.check("T06","Control name still validates during attack",lambda:attack_probes["control"]["rcode"]=="NOERROR" and attack_probes["control"]["ad"] and attack_probes["control"]["answers"]==["172.30.53.80"])
        self.check("T07","Direct BIND retains original .80 during relay tampering",lambda:attack_probes["authority"]["answers"]==["172.30.53.80"] and attack_probes["authority"]["error"] is None)
        self.check("T08","Authenticated NXDOMAIN and consistent TCP/UDP results",lambda:baseline_probes["negative"]["rcode"]=="NXDOMAIN" and baseline_probes["negative"]["ad"] and baseline_probes["tcp"]["rcode"]==baseline["results"]["secure"]["dns"]["rcode"] and baseline_probes["tcp"]["answers"]==["172.30.53.80"] and baseline_probes["tcp"]["ad"] and attack_probes["tcp"]["rcode"]=="SERVFAIL")
        self.check("E08-API","Blocked run has no preview; old run is only reachable by its old ID",lambda:self.client.get(f"/api/runs/{attack['run_id']}/preview/secure").status_code==404 and self.client.get(f"/api/runs/{baseline['run_id']}/preview/secure").status_code==200)
        recovery=self.measure("recovery")
        self.check("T04","Recovery: both branches return to .80 with valid evidence",lambda:self.good_pair(recovery) and self.verify_run(recovery) and len({baseline["run_id"],attack["run_id"],recovery["run_id"]})==3)
        self.check("A01","Raw bodies, hashes, logs, proof and manifests agree for all phases",lambda:all(self.verify_run(data) for data in [baseline,attack,recovery]))
        self.check("A02","Attack context contains crypto failure, tagged as time-window context",lambda:"signature crypto failed" in attack["evidence"]["dns_context"] and attack["evidence"]["dns_context_correlation"]=="time_window_only_not_exact_run_id")
        (self.folder/"diagnostics.json").write_text(json.dumps({"baseline":baseline_probes,"attack":attack_probes},indent=2),encoding="utf-8")

    def wait_ready(self):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if self.runner.health()["ready"]: return
            time.sleep(0.5)
        raise RuntimeError("Local services did not recover within 30 seconds")

    def injected(self, action, service, operation):
        require((action,service) in {("stop","client"),("pause","tamper"),("stop","web-good"),("stop","plain")},"Unapproved fault target")
        self.runner.command([action,service])
        undo=("unpause" if action=="pause" else "start",service)
        self.undo.append(undo)
        try: return operation()
        finally:
            self.runner.command(list(undo))
            self.undo.remove(undo)
            self.wait_ready()
            self.scenario("recovery")

    def faults_suite(self):
        self.scenario("baseline")
        def unavailable():
            require(self.client.get("/api/health").status_code==503,"Missing service looked healthy")
            self.post("/api/run",expected=503)
            return True
        self.check("E01","Stopped client reports unavailable, never a successful new run",lambda:self.injected("stop","client",unavailable))
        self.scenario("baseline")
        def timeout():
            data=self.post("/api/run")
            self.report["runs"]["dns_timeout"]=data["run_id"]
            return all(r["dns"]["rcode"] is None and r["dns"]["ad"] is None and r["dns"]["error"] and not r["http"]["attempted"] for r in data["results"].values())
        self.check("E02","Paused relay causes real DNS timeout: unknown AD/rcode, no HTTP",lambda:self.injected("pause","tamper",timeout))
        self.scenario("baseline")
        def http_failure():
            data=self.post("/api/run");self.report["runs"]["http_failure"]=data["run_id"]
            return all(r["dns"]["rcode"]=="NOERROR" and r["http"]["attempted"] and r["http"]["error"] and r["http"]["status"] is None for r in data["results"].values()) and data["results"]["secure"]["dns"]["ad"]
        self.check("E03","Stopped HTTP server preserves successful DNS and reports HTTP error",lambda:self.injected("stop","web-good",http_failure))
        self.scenario("baseline")
        def flush_failure():
            response=self.post("/api/scenario",{"action":"attack"},expected=503)
            state=self.client.get("/api/state").json
            return state["actual_mode"]=="attack" and not state["ready_for_run"] and response["error"]["details"]["steps"]==[{"step":"set_mode","ok":True}]
        self.check("E04","Failed plain flush reports partial transition and actual relay mode",lambda:self.injected("stop","plain",flush_failure))
        def concurrent():
            self.scenario("baseline");self.runner.started.clear();responses=[]
            def work():
                with self.app.test_client() as client: responses.append(client.post("/api/run",json={}))
            thread=threading.Thread(target=work);thread.start()
            try:
                require(self.runner.started.wait(20),"Worker did not start")
                self.post("/api/scenario",{"action":"attack"},expected=409)
                self.post("/api/run",expected=409)
            finally: thread.join(90)
            require(not thread.is_alive(),"Measurement did not finish")
            require(len(responses)==1 and responses[0].status_code==200,"Concurrent measurement failed")
            data=responses[0].json;self.report["runs"]["concurrent"]=data["run_id"]
            return data["consistent"] and self.verify_run(data)
        self.check("E05","Real run rejects concurrent scenario/run with 409",concurrent)
        def external_change():
            self.scenario("baseline")
            self.runner.after_compare=lambda:self.runner.set_mode(True)
            data=self.post("/api/run");self.report["runs"]["external_change"]=data["run_id"]
            return not data["consistent"] and all(r["interpretation"]=="inconclusive" and r["http"]["preview_url"] is None for r in data["results"].values())
        self.check("E06","External CLI mode change within request invalidates result/preview",external_change)

    def finish(self):
        for undo in list(reversed(self.undo)):
            self.check("cleanup:"+undo[1],"Undo injected fault",lambda undo=undo:self.runner.command(list(undo)))
        if self.preflight_ready:
            def recover():
                self.wait_ready()
                data=self.measure("recovery","final_recovery")
                return self.good_pair(data) and self.verify_run(data)
            self.check("RECOVERY","Final measured recovery after all fault injections",recover)
        self.report["finished_at"]=self.now()
        expected={f"T{i:02d}" for i in range(1,9)} | {f"E{i:02d}" for i in range(1,8)} | {"E08-API","E08-UI","E09","UNIT","RECOVERY"}
        seen={row["id"] for row in self.report["cases"]}
        for code in sorted(expected-seen):
            self.skip(code,"Not executed because prerequisites or an earlier step did not complete")
        self.report.update(summarize_cases(self.report["cases"],self.preflight_ready))
        (self.folder/"report.json").write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding="utf-8")
        rows=["# DNSSEC acceptance report","",f"Status: {self.report['status']}","", "| Case | Type | Result | Description |", "|---|---|---|---|"]
        for row in self.report["cases"]:
            detail=(row["description"]+("; "+row["error"] if "error" in row else "")).replace("|","/").replace("\n"," ")
            rows.append(f"| {row['id']} | {row['kind']} | {row['status']} | {detail} |")
        rows.extend(["", "## Run IDs", ""]+[f"- {phase}: {run_id}" for phase,run_id in self.report["runs"].items()])
        rows.extend(["", "UI/UX checks are deferred. Unit/mock cases are labeled; live cases use actual Docker.", "SHA-256 is file integrity, not evidence authenticity. DNS validation logs are time-window context."])
        (self.folder/"report.md").write_text("\n".join(rows)+"\n",encoding="utf-8")
        print(json.dumps({"status":self.report["status"],"summary":self.report["summary"],"report":str(self.folder/"report.md")}),flush=True)

    def execute(self):
        try:
            if not self.check("PRECHECK","Local Docker services are ready",self.preflight): return
            units=self.check("UNIT","Host and client regression tests",self.unit_checks,kind="unit")
            if units:
                self.check("E07","Redirect and external-IP gate tests pass before extra connections",lambda:True,kind="unit; client-unit.log")
                self.check("E09","SERVFAIL without crypto log stays generic blocked",lambda:True,kind="unit; host-unit.log")
            self.check("POSITIVE","Execute T01-T08 and artifact checks",self.positive)
            if self.faults: self.faults_suite()
            else:
                for code in ["E01","E02","E03","E04","E05","E06"]: self.skip(code,"Not run; add --faults for actual local fault injection")
            self.skip("E08-UI","Visual stale/preview behavior deferred with UI/UX work; API part checked")
        except Exception as exc:
            self.check("SUITE_ERROR","Unexpected suite failure",lambda:require(False,str(exc)))
        finally: self.finish()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faults",action="store_true",help="Pause/stop only this local lab's services, then restore them")
    args=parser.parse_args()
    with single_server():
        suite=Acceptance(args.faults)
        suite.execute()
        raise SystemExit(0 if suite.report["backend_passed"] else 2 if suite.report["status"]=="PARTIAL" else 1)
