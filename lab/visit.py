"""HTTP-only stage: connect to a selected literal lab IP, not DNS yet."""
import argparse
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
from ipaddress import ip_address
import json
import hashlib
import time
import uuid

HOST = "www.demo.test"
TARGETS = {
    "good": {"ip": "172.30.53.80", "site_id": "legitimate"},
    "fake": {"ip": "172.30.53.90", "site_id": "training-fake"},
}
ALLOWED_IPS = {target["ip"] for target in TARGETS.values()}
MAX_BODY = 1024 * 1024


def visit(ip, run_id, branch_id, timeout=3, host=HOST):
    # Reject names and out-of-lab addresses before any network operation.
    if host not in [HOST, "control.demo.test"]:
        raise ValueError("HTTP Host must be a permitted lab name")
    address = str(ip_address(ip))
    if address not in ALLOWED_IPS:
        raise ValueError("Destination IP is outside the allowed lab targets")
    result = {
        "run_id": run_id,
        "branch_id": branch_id,
        "source": "direct_ip_without_dns",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "host_header": host,
        "destination_ip": address,
        "http": {
            "attempted": True,
            "request_sent": False,
            "connected_ip": None,
            "status": None,
            "site_id": None,
            "body": None,
            "error": None,
        },
    }
    start = time.monotonic()
    connection = HTTPConnection(address, port=80, timeout=timeout)
    try:
        connection.connect()
        result["http"]["connected_ip"] = connection.sock.getpeername()[0]
        connection.request("GET", "/", headers={
            "Host": host,
            "X-Lab-Run-ID": run_id,
            "X-Lab-Branch-ID": branch_id,
        })
        result["http"]["request_sent"] = True
        response = connection.getresponse()
        result["http"]["status"] = response.status
        result["http"]["site_id"] = response.getheader("X-Lab-Site")
        result["http"]["content_type"] = response.getheader("Content-Type")
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("HTTP response exceeds the 1 MiB lab limit")
        result["http"]["body"] = body.decode("utf-8")
        result["http"]["body_sha256"] = hashlib.sha256(body).hexdigest()
        # HTTPConnection does not automatically follow redirects.
    except (OSError, ValueError, HTTPException) as error:
        result["http"]["error"] = str(error)
    finally:
        connection.close()
    result["http"]["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["good", "fake", "both"], default="both")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    run_id = args.run_id or str(uuid.uuid4())
    targets = TARGETS if args.target == "both" else {args.target: TARGETS[args.target]}
    results = []
    for name, target in targets.items():
        result = visit(target["ip"], run_id, "direct-" + name)
        measured = result["http"]
        result["passed"] = (
            measured["error"] is None
            and measured["status"] == 200
            and measured["connected_ip"] == target["ip"]
            and measured["site_id"] == target["site_id"]
            and target["site_id"] in (measured["body"] or "")
        )
        results.append(result)
    print(json.dumps({"stage": "http_only", "results": results}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
