"""One asynchronous lab job; short polling reads events without running Docker."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from dashboard.services.docker_runner import APIError


def now(): return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self,lab):
        self.lab=lab
        self.root=lab.store.directory/"_jobs"
        self.lock=threading.RLock()
        self.jobs={}
        self.active=None

    def folder(self,job_id):
        try:
            if str(uuid.UUID(job_id))!=job_id: raise ValueError()
        except (ValueError,TypeError,AttributeError) as exc:
            raise APIError("INVALID_JOB_ID","job_id không hợp lệ.",400) from exc
        path=self.root/job_id
        if path.is_symlink(): raise APIError("INVALID_JOB_ID","Không nhận thư mục symlink.",400)
        return path

    def persist(self,job):
        value={key:value for key,value in job.items() if key not in {"events","clock"}}
        folder=self.folder(job["job_id"])
        temp=folder/"state.tmp"
        temp.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
        temp.replace(folder/"state.json")

    def record(self,job,kind,branch=None,data=None,timestamp=None,source="supervisor"):
        with self.lock:
            if len(job["events"])>=256: raise APIError("EVENT_LIMIT","Số sự kiện vượt giới hạn.",502)
            if time.monotonic()-job["clock"]>180: raise APIError("JOB_TIMEOUT","Tác vụ vượt ngân sách thời gian.",504)
            event={"sequence":len(job["events"])+1,"job_id":job["job_id"],"run_id":job["run_id"],
                   "kind":kind,"branch":branch,"timestamp":timestamp or now(),"received_at":now(),
                   "source":source,"data":data or {}}
            with (self.folder(job["job_id"])/"events.jsonl").open("a",encoding="utf-8") as output:
                output.write(json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n")
            job["events"].append(event)

    def start(self,action):
        self.lab.reserve("job:"+action)
        job_id,run_id=str(uuid.uuid4()),str(uuid.uuid4())
        job={"job_id":job_id,"run_id":run_id,"action":action,"source":"live","status":"running",
             "requested_at":now(),"finished_at":None,"result_url":None,"error":None,"events":[],"clock":time.monotonic()}
        try:
            with self.lock:
                self.folder(job_id).mkdir(parents=True,exist_ok=False)
                self.jobs[job_id]=job;self.active=job_id
                for key in list(self.jobs):
                    if len(self.jobs)<=64: break
                    if self.jobs[key]["status"]!="running": del self.jobs[key]
                self.persist(job)
                self.record(job,"job.accepted",data={"action":action})
            with self.lab.meta_lock:
                self.lab.task.update(job_id=job_id,run_id=run_id)
            threading.Thread(target=self.execute,args=(job,),daemon=True,name="dnssec-job").start()
        except Exception as exc:
            with self.lock:
                self.active=None
                job.update(status="failed",error={"code":"JOB_START_FAILED","message":str(exc)})
            self.lab.release(exc)
            raise
        return self.get(job_id,0)

    def execute(self,job):
        error=None
        outcome="completed"
        measured_url=None
        emit=lambda *args,**kwargs:self.record(job,*args,**kwargs)
        try:
            self.lab._scenario_operation(job["action"],emit)
            result=self.lab._run_operation(job["run_id"],emit,job["job_id"])
            measured_url=f"/api/runs/{job['run_id']}"
            if any(r["dns"].get("error") or r["http"].get("error") for r in result["results"].values()):
                raise APIError("MEASUREMENT_FAILED","Phép đo gặp lỗi DNS hoặc HTTP; giữ dữ liệu quan sát được để đối chiếu.",502)
            self.record(job,"job.completed",data={"result_url":f"/api/runs/{job['run_id']}"})

        except Exception as exc:
            error=exc
            outcome="failed"
            with self.lock:
                job.update(error={"code":getattr(exc,"code","INTERNAL_ERROR"),"message":str(exc)})
            try: self.record(job,"job.failed",data=job["error"])
            except Exception: pass
        finally:
            with self.lock:
                job["finished_at"]=now()
                try:
                    journal=self.folder(job["job_id"])/"events.jsonl"
                    job["events_sha256"]=hashlib.sha256(journal.read_bytes()).hexdigest()
                    job.update(status=outcome,result_url=measured_url)
                    self.persist(job)
                except Exception as exc:
                    error=error or exc
                    job.update(status="failed",result_url=None,error={"code":"JOB_EVIDENCE_FAILED","message":"Không lưu được nhật ký tác vụ."})
                self.active=None
            self.lab.release(error)

    def get(self,job_id,after):
        if type(after) is not int or not 0<=after<=256:
            raise APIError("INVALID_CURSOR","after phải là số nguyên từ 0 đến 256.",400)
        with self.lock:
            folder=self.folder(job_id)
            job=self.jobs.get(job_id)
            if job is None:
                try:
                    metadata=folder/"state.json";journal=folder/"events.jsonl"
                    if metadata.is_symlink() or journal.is_symlink() or metadata.stat().st_size>65536 or journal.stat().st_size>1024*1024: raise ValueError("Invalid journal files")
                    job=json.loads(metadata.read_text(encoding="utf-8"))
                    if job["job_id"]!=job_id: raise ValueError("Job identity mismatch")
                    job["events"]=[json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
                    if len(job["events"])>256 or any(e["sequence"]!=i+1 or e["job_id"]!=job_id or e["run_id"]!=job["run_id"] for i,e in enumerate(job["events"])): raise ValueError("Invalid journal sequence")
                    if job["status"]=="running":
                        job.update(status="interrupted",error={"code":"JOB_INTERRUPTED","message":"API đã khởi động lại; không tự chạy lại tác vụ cũ."},finished_at=now(),result_url=None)
                        job["events_sha256"]=hashlib.sha256(journal.read_bytes()).hexdigest()
                        self.persist(job)
                except FileNotFoundError as exc: raise APIError("JOB_NOT_FOUND","Không tìm thấy tác vụ.",404) from exc
                except (ValueError,KeyError,TypeError) as exc: raise APIError("JOB_EVIDENCE_CORRUPT","Nhật ký tác vụ không hợp lệ.",409) from exc
            if job["status"]!="running":
                journal=folder/"events.jsonl"
                if not journal.is_file() or journal.is_symlink() or hashlib.sha256(journal.read_bytes()).hexdigest()!=job.get("events_sha256"):
                    raise APIError("JOB_EVIDENCE_CORRUPT","Nhật ký tác vụ đã thay đổi.",409)
            if after>len(job["events"]): raise APIError("INVALID_CURSOR","Cursor vượt số sự kiện của tác vụ.",400)
            snapshot={k:deepcopy(v) for k,v in job.items() if k not in {"clock","events"}}
            snapshot.update(events=deepcopy(job["events"][after:]),cursor=len(job["events"]))
            return snapshot
