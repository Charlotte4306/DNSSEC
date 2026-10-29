"""DNS -> the exact answer IP -> HTTP. No DNSSEC validation at this stage."""
import argparse
import json
import uuid
from dns_probe import probe, NAMES
from visit import visit, ALLOWED_IPS


def browse(name="www.demo.test", run_id=None):
    run_id = run_id or str(uuid.uuid4())
    dns = probe(name)
    result = {"run_id": run_id, "stage": "unsigned_dns_to_http", "dns": dns,
              "http": {"attempted": False, "request_sent": False,
                       "connected_ip": None, "status": None, "error": None},
              "stop_reason": None}
    if dns["error"] or dns["rcode"] != "NOERROR":
        result["stop_reason"] = "DNS query failed or returned a non-success rcode"
    elif len(dns["answers"]) != 1 or dns["answers"][0] not in ALLOWED_IPS:
        result["stop_reason"] = "DNS must return exactly one allowed lab IPv4 address"
    else:
        measured = visit(dns["answers"][0], run_id, "authority", host=name)
        result["http"] = measured["http"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=NAMES, default=NAMES[0])
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    result = browse(args.name, args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["http"]["status"] == 200 and not result["http"]["error"] else 1)
