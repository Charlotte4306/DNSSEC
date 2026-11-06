"""Resolve with the chosen lab server, then HTTP to that exact answer IP."""
import argparse
from datetime import datetime, timezone
import json
import re
import uuid
from dns_probe import probe, NAMES, SERVERS
from visit import visit, ALLOWED_IPS


def validate_run_id(run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("run_id must contain 1-80 letters, digits, underscores or hyphens")
    return run_id


def browse(name="www.demo.test", run_id=None, resolver="authority", on_event=None):
    if name not in NAMES or resolver not in ["authority", "plain", "secure"]:
        raise ValueError("Unknown lab name or resolver")
    run_id = validate_run_id(run_id or str(uuid.uuid4()))
    started = datetime.now(timezone.utc).isoformat()
    def emit(kind, data):
        if on_event is not None: on_event(kind, data)
    emit("dns.started", {"name": name, "server": SERVERS[resolver]})
    dns = probe(name, server=resolver)
    emit("dns.error" if dns["error"] else "dns.response", {key: dns.get(key) for key in ["rcode", "ad", "answers", "error", "elapsed_ms"]})
    if resolver == "secure" and not dns["error"]:
        emit("validation.observed", {"rcode": dns["rcode"], "ad": dns["ad"], "source": "resolver_response_not_internal_crypto_steps"})
    result = {"run_id": run_id, "branch_id": resolver, "resolver": resolver,
              "requested_at": started, "stage": "dns_to_http", "dns": dns,
              "http": {"attempted": False, "request_sent": False, "connected_ip": None,
                       "status": None, "site_id": None, "body": None,
                       "body_sha256": None, "content_type": None, "elapsed_ms": None,
                       "error": None},
              "stop_reason": None, "interpretation": "inconclusive"}
    if dns["error"]:
        result["stop_reason"] = "DNS_TRANSPORT_ERROR"
    elif dns["rcode"] != "NOERROR":
        result["stop_reason"] = "DNS_RCODE_" + str(dns["rcode"])
        result["interpretation"] = "blocked"
    elif resolver == "secure" and not dns["ad"]:
        result["stop_reason"] = "SECURE_REQUIRES_AUTHENTICATED_DATA"
    elif len(dns["answers"]) != 1 or dns["answers"][0] not in ALLOWED_IPS:
        result["stop_reason"] = "DNS_ANSWER_NOT_SINGLE_ALLOWED_IPV4"
    else:
        options = {"host": name}
        if on_event is not None: options["on_event"] = emit
        measured = visit(dns["answers"][0], run_id, resolver, **options)
        result["http"].update(measured["http"])
        http = result["http"]
        if http["error"]:
            result["stop_reason"] = "HTTP_ERROR"
        elif http["status"] != 200:
            result["stop_reason"] = "HTTP_STATUS_" + str(http["status"])
        elif http["connected_ip"] != dns["answers"][0]:
            result["stop_reason"] = "CONNECTED_IP_MISMATCH"
        elif http["site_id"] == "training-fake" and http["connected_ip"] == "172.30.53.90":
            result["interpretation"] = "accepted_fake"
        elif http["site_id"] == "legitimate" and http["connected_ip"] == "172.30.53.80":
            result["interpretation"] = "validated" if resolver == "secure" else "reached_legitimate_unvalidated"
        else:
            result["stop_reason"] = "UNEXPECTED_SITE_ID"
    if not result["http"]["attempted"]:
        emit("http.skipped", {"reason": result["stop_reason"]})
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    emit("branch.completed", {"interpretation": result["interpretation"], "stop_reason": result["stop_reason"]})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=NAMES, default=NAMES[0])
    parser.add_argument("--resolver", choices=["authority", "plain", "secure"], default="authority")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    result = browse(args.name, args.run_id, args.resolver)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["http"]["status"] == 200 and not result["http"]["error"] else 1)
