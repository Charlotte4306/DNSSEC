"""Read bounded NDJSON from a fixed Docker command; never execute caller commands."""
import json
import queue
import subprocess
import tempfile
import threading
import time
from dashboard.config import REPO_ROOT
from dashboard.services.docker_runner import APIError

KINDS={"dns.started","dns.response","dns.error","validation.observed","http.connecting","http.connected","http.request_sent","http.response","http.error","http.finished","http.skipped","branch.completed"}


def stream_compare(run_id, on_event):
    command=["docker","compose","--project-directory",str(REPO_ROOT),"exec","-T","client",
             "timeout","--kill-after=2s","25s","python","-u","/app/lab/api_worker.py","compare","--name","www.demo.test","--run-id",run_id,"--events"]
    messages=queue.Queue(maxsize=64)
    stopping=threading.Event()
    with tempfile.TemporaryFile() as errors:
        try:
            process=subprocess.Popen(command,cwd=REPO_ROOT,stdout=subprocess.PIPE,stderr=errors,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except OSError as exc:
            raise APIError("DOCKER_UNAVAILABLE","Không chạy được Docker CLI.") from exc
        def read():
            try:
                while not stopping.is_set():
                    line=process.stdout.readline(8*1024*1024+1)
                    while not stopping.is_set():
                        try: messages.put(line,timeout=.2);break
                        except queue.Full: pass
                    if not line: break
            except Exception as exc:
                if not stopping.is_set():
                    try: messages.put(exc,timeout=.2)
                    except queue.Full: pass
        reader=threading.Thread(target=read,daemon=True);reader.start()
        result=None;count=0;deadline=time.monotonic()+35
        try:
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0: raise APIError("WORKER_TIMEOUT","Worker hết thời gian xử lý.",504)
                try: line=messages.get(timeout=min(remaining,1))
                except queue.Empty: continue
                if isinstance(line,Exception): raise line
                if not line: break
                if len(line)>8*1024*1024: raise ValueError("NDJSON line too large")
                record=json.loads(line.decode("utf-8"))
                if record.get("run_id")!=run_id: raise ValueError("Different run_id in event stream")
                if result is not None: raise ValueError("Unexpected data after terminal result")
                if record.get("type")=="event":
                    if record.get("kind") not in KINDS or record.get("branch") not in {"plain","secure"} or not isinstance(record.get("data"),dict) or not isinstance(record.get("timestamp"),str):
                        raise ValueError("Invalid worker event")
                    count+=1
                    if count>128: raise ValueError("Too many worker events")
                    on_event(record)
                elif record.get("type")=="result": result=record["result"]
                else: raise ValueError("Invalid stream record")
            exit_code=process.wait(timeout=5)
            if exit_code in {124,137}: raise APIError("WORKER_TIMEOUT","Worker bị dừng sau giới hạn thời gian.",504)
            if exit_code not in {0,1} or result is None: raise ValueError("No valid terminal worker result")
            return result
        except (ValueError,KeyError,TypeError,UnicodeError) as exc:
            raise APIError("INVALID_WORKER_OUTPUT","Luồng sự kiện worker không hợp lệ.",502) from exc
        finally:
            stopping.set()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=3)
            reader.join(timeout=2)
            process.stdout.close()
