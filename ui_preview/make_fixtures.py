"""Generate attack/recovery job fixtures by rewriting the recorded live baseline job.

Source of truth for every event field is fixtures/jobs/baseline.json, captured from
GET /api/jobs/<id> on the deployed lab. Run: .venv\\Scripts\\python.exe ui_preview/make_fixtures.py
"""

import copy
import json
from pathlib import Path

JOBS = Path(__file__).resolve().parent / "fixtures" / "jobs"
BASELINE_RUN = "f6e5e807-65d2-42b3-b55f-26f42dcaf151"
ATTACK_RUN = "1c84eedb-14ed-41f3-a2e5-c5c8f2a706f5"
HTTP_KINDS = {"http.connecting", "http.connected", "http.request_sent", "http.response", "http.finished"}
GOOD_IP = "172.30.53.80"
FAKE_IP = "172.30.53.90"


def rewrite(value, run_id):
    if isinstance(value, dict):
        return {key: rewrite(item, run_id) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite(item, run_id) for item in value]
    if isinstance(value, str):
        return value.replace(BASELINE_RUN, run_id)
    return value


def attack_event(event, skipped_done):
    branch, kind, data = event["branch"], event["kind"], event.get("data") or {}
    if kind == "job.accepted":
        data["action"] = "attack"
    if kind == "mode.changed":
        data.update({"action": "attack", "attack": True})
    if branch == "secure" and kind in HTTP_KINDS:
        if skipped_done["secure"]:
            return None
        skipped_done["secure"] = True
        event["kind"] = "http.skipped"
        event["data"] = {"reason": "DNS_RCODE_SERVFAIL"}
        return event
    if branch == "secure" and kind == "dns.response":
        data.update({"rcode": "SERVFAIL", "answers": [], "ad": False})
    if branch == "secure" and kind == "validation.observed":
        data.update({"rcode": "SERVFAIL", "ad": False})
    if branch == "secure" and kind == "branch.completed":
        data.update({"interpretation": "blocked", "stop_reason": "DNS_RCODE_SERVFAIL"})
    if branch == "plain":
        if kind == "dns.response":
            data.update({"answers": [FAKE_IP], "ad": False})
        if kind == "http.response":
            data["site_id"] = "training-fake"
        if kind == "branch.completed":
            data.update({"interpretation": "accepted_fake", "stop_reason": None})
        if "ip" in data:
            data["ip"] = FAKE_IP
    event["data"] = data
    return event


def recovery_event(event):
    if event["kind"] == "job.accepted":
        event["data"]["action"] = "recovery"
    if event["kind"] == "mode.changed":
        event["data"].update({"action": "recovery", "attack": False})
    if event["kind"] == "dns.response" and event["branch"] == "secure":
        event["data"].update({"rcode": "NOERROR", "answers": [GOOD_IP], "ad": True})
    return event


def build(action, job_id, run_id):
    job = rewrite(json.loads((JOBS / "baseline.json").read_text(encoding="utf-8")), run_id)
    job.update({"job_id": job_id, "run_id": run_id, "action": action, "result_url": f"/api/runs/{run_id}"})
    skipped_done = {"secure": False}
    events = []
    for raw in job["events"]:
        event = copy.deepcopy(raw)
        event["job_id"] = job_id
        event["run_id"] = run_id
        event = attack_event(event, skipped_done) if action == "attack" else recovery_event(event)
        if event is not None:
            events.append(event)
    for index, event in enumerate(events, start=1):
        event["sequence"] = index
    job["events"] = events
    job["cursor"] = len(events)
    job["status"] = "completed"
    return job


def main():
    for name, spec in {
        "attack.json": build("attack", "mock-job-attack", ATTACK_RUN),
        "recovery.json": build("recovery", "mock-job-recovery", BASELINE_RUN),
    }.items():
        (JOBS / name).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        kinds = {event["kind"] for event in spec["events"]}
        print(f"{name}: {len(spec['events'])} events, http.skipped={'yes' if 'http.skipped' in kinds else 'no'}")


if __name__ == "__main__":
    main()
