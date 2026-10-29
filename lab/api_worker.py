"""JSON CLI for later dashboard integration; no HTTP API/server here."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import uuid
from browse import browse, validate_run_id
from dns_probe import NAMES

def snapshot():
    return json.loads(Path("/state/mode.json").read_text())

def compare(name="www.demo.test", run_id=None):
    run_id = validate_run_id(run_id or str(uuid.uuid4()))
    before = snapshot()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {server: executor.submit(browse, name, run_id, server) for server in ["plain", "secure"]}
        results = {server: future.result() for server, future in futures.items()}
    after = snapshot()
    consistent = before == after
    if not consistent:
        for result in results.values(): result["interpretation"] = "inconclusive"
    return {"schema_version": 1, "run_id": run_id, "target": name,
            "scenario_before": before, "scenario_after": after,
            "consistent": consistent, "results": results}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["compare", "visit"])
    parser.add_argument("--resolver", choices=["plain", "secure"], default="secure")
    parser.add_argument("--name", choices=NAMES, default=NAMES[0])
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    try:
        if args.action == "compare":
            result = compare(args.name, args.run_id)
            success = result["consistent"] and all(not r["dns"]["error"] and not r["http"]["error"] for r in result["results"].values())
        else:
            result = browse(args.name, args.run_id, args.resolver)
            success = not result["dns"]["error"] and not result["http"]["error"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # A measured DNS refusal is a valid result, not a failed CLI execution.
        return 0 if success else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

if __name__ == "__main__": raise SystemExit(main())
