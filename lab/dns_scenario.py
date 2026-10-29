"""DNS-only comparison; resolver-to-HTTP integration belongs to the next feature."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
from dns_probe import probe

STATE = Path("/state/mode.json")

def set_mode(active):
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps({"attack": active, "changed_at": datetime.now(timezone.utc).isoformat()}))
    temp.replace(STATE)

def compare():
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = dict(zip(["plain", "secure"], executor.map(lambda server: probe(server=server), ["plain", "secure"])))
    return {"mode": json.loads(STATE.read_text()), "results": results}

def proof():
    records = {server: probe(server=server) for server in ["authority", "tamper"]}
    signatures = {}
    for server, record in records.items():
        if record["error"]: raise AssertionError(record)
        lines = [line for line in record["raw"].splitlines() if " RRSIG A " in line]
        if not lines: raise AssertionError("Missing RRSIG A from " + server)
        signatures[server] = "\n".join(lines)
    if signatures["authority"] != signatures["tamper"]: raise AssertionError("RRSIG changed")
    active = json.loads(STATE.read_text())["attack"]
    assert records["authority"]["answers"] == ["172.30.53.80"]
    assert records["tamper"]["answers"] == (["172.30.53.90"] if active else ["172.30.53.80"])
    return {"records": records, "rrsig_unchanged": True,
            "rrsig_sha256": hashlib.sha256(signatures["authority"].encode()).hexdigest()}

def check(phase):
    active = phase == "attack"
    result = compare()
    assert result["mode"]["attack"] == active, result
    plain, secure = result["results"]["plain"], result["results"]["secure"]
    assert plain["rcode"] == "NOERROR" and not plain["ad"], plain
    assert plain["answers"] == (["172.30.53.90"] if active else ["172.30.53.80"]), plain
    if active:
        assert secure["rcode"] == "SERVFAIL" and not secure["answers"] and not secure["ad"], secure
    else:
        assert secure["rcode"] == "NOERROR" and secure["ad"] and secure["answers"] == ["172.30.53.80"], secure
    control = probe("control.demo.test", server="secure")
    assert control["rcode"] == "NOERROR" and control["ad"] and control["answers"] == ["172.30.53.80"], control
    tcp = probe(server="secure", tcp=True)
    assert tcp["rcode"] == secure["rcode"] and tcp["answers"] == secure["answers"] and tcp["ad"] == secure["ad"], tcp
    negative = probe("not-present.demo.test", server="secure")
    assert negative["rcode"] == "NXDOMAIN" and negative["ad"], negative
    result.update(phase=phase, time_utc=datetime.now(timezone.utc).isoformat(),
                  control=control, tcp=tcp, negative=negative, proof=proof())
    directory = Path("/evidence/runs") / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + phase + "-" + uuid.uuid4().hex[:6])
    directory.mkdir(parents=True)
    (directory / "dns.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS " + phase + " -> " + str(directory))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["on", "off", "compare", "proof", "baseline", "attack", "recovery"])
    args = parser.parse_args()
    if args.action in ["on", "off"]:
        set_mode(args.action == "on"); print("Relay mode: " + args.action)
    elif args.action == "compare": print(json.dumps(compare(), indent=2))
    elif args.action == "proof": print(json.dumps(proof(), indent=2))
    else: check(args.action)
