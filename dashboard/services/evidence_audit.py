"""Offline consistency checks of raw worker, summary, body hashes, and web logs."""
import hashlib
import json
from pathlib import Path
from dashboard.services.evidence_integrity import verify_manifest


def audit_run(folder):
    folder = Path(folder)
    checks = []
    def check(code, condition, detail):
        checks.append({"id": code, "status": "PASS" if condition else "FAIL", "detail": detail})
    integrity = verify_manifest(folder, folder.name)
    check("artifact_integrity", integrity["verified"], integrity["status"])
    if not integrity["verified"]:
        return {"run_id": folder.name, "passed": False, "checks": checks, "integrity": integrity}
    try:
        result = json.loads((folder/"result.json").read_text(encoding="utf-8"))
        worker = json.loads((folder/"worker.json").read_text(encoding="utf-8"))
        logs = json.loads((folder/"http-access.json").read_text(encoding="utf-8"))
        check("run_identity", result["run_id"] == worker["run_id"] == folder.name, "Raw data and summary share the directory run_id")
        check("mode_consistency", result["consistent"] is True and worker["consistent"] is True,
              "A run with changing mode cannot establish a stable-scenario result")
        check("collection_complete", not result["evidence"]["collection_errors"], "Unavailable logs/proof are missing evidence, not zero requests")
        check("log_identity", all(row.get("run_id") == folder.name and row.get("branch_id") in {"plain", "secure"} for row in logs), "No logs from other runs/unknown branches")
        for name in ["plain", "secure"]:
            raw, summary = worker["results"][name], result["results"][name]
            http = raw["http"]
            check(name+"_identity", raw["run_id"] == folder.name and raw["branch_id"] == raw["resolver"] == name,
                  "Raw branch belongs to this run")
            check(name+"_dns_summary", all(summary["dns"].get(k) == raw["dns"].get(k) for k in ["rcode", "ad", "answers", "error"]), "Summary preserves measured DNS")
            check(name+"_http_summary", all(summary["http"].get(k) == http.get(k) for k in ["attempted", "request_sent", "connected_ip", "status", "site_id", "error"]), "Summary preserves measured HTTP")
            body = http.get("body")
            if body is not None:
                sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
                check(name+"_body_hash", sha == http.get("body_sha256") == summary["http"].get("body_hash"), "Recompute raw HTTP body hash")
            records = [row for row in logs if row.get("branch_id") == name]
            if not http["attempted"]:
                check(name+"_no_http", not records and not http["request_sent"] and body is None and http["status"] is None and http["connected_ip"] is None,
                      "Worker did not try HTTP; no server access log in the collected window")
                check(name+"_no_preview", summary["http"].get("preview_url") is None and not (folder/f"preview-{name}.html").exists(), "No stored HTML or preview for a branch that did not send HTTP")
            elif http["status"] == 200:
                expected_site = {"172.30.53.80": "legitimate", "172.30.53.90": "training-fake"}.get(http["connected_ip"])
                check(name+"_destination", raw["dns"]["answers"] == [http["connected_ip"]] and http["site_id"] == expected_site and expected_site is not None,
                      "Connected exactly to the permitted DNS answer with matching site identity")
                matched = [row for row in records if row.get("host") == worker["target"] and row.get("method") == "GET" and row.get("path") == "/" and row.get("status") == http["status"] and row.get("site_id") == http["site_id"]]
                check(name+"_access_log", len(records) == len(matched) == 1, "Exactly one corroborating GET for this branch")
            if name == "secure" and http["attempted"]:
                check("secure_requires_ad", raw["dns"]["rcode"] == "NOERROR" and raw["dns"]["ad"] is True, "Secure branch requires authenticated DNS before HTTP")
        proof = result["evidence"].get("proof")
        check("proof_saved", proof is not None and (folder/"proof.json").is_file(), "A/RRSIG evidence is saved inside the run")
        if proof:
            check("proof_revision", proof.get("consistent_with_run") is True and proof["revision"] == result["scenario_revision"], "Proof and measurement share a stable revision; queries are separate")
            proof_data = proof["data"]
            signatures = {}
            for name in ["authority", "tamper"]:
                lines = [line for line in proof_data["records"][name]["raw"].splitlines() if " RRSIG A " in line]
                signatures[name] = "\n".join(lines)
            check("nonempty_rrsig_unchanged", bool(signatures["authority"]) and signatures["authority"] == signatures["tamper"] and proof_data["rrsig_unchanged"] is True,
                  "Compare actual nonempty RRSIG A text, not hashes of empty strings")
            check("rrsig_hash", hashlib.sha256(signatures["authority"].encode()).hexdigest() == proof_data["rrsig_sha256"], "Recompute RRSIG evidence hash")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        check("evidence_schema", False, str(exc))
    return {"run_id": folder.name, "passed": all(row["status"] == "PASS" for row in checks), "checks": checks, "integrity": integrity,
            "limits": "This checks file/data consistency; it does not independently validate DNSSEC signatures or authenticate the host."}
