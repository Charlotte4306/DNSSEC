"""Query the lab authority directly; no system DNS fallback."""
import argparse
import json
import time
import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdatatype

AUTHORITY = "172.30.53.10"
NAMES = ["www.demo.test", "control.demo.test", "not-present.demo.test"]


def probe(name="www.demo.test", rdtype="A", tcp=False):
    if name not in NAMES or rdtype not in ["A", "AAAA"]:
        raise ValueError("Only the documented lab names and A/AAAA queries are allowed")
    result = {"server": AUTHORITY, "name": name, "type": rdtype,
              "transport": "TCP" if tcp else "UDP", "rcode": None,
              "ad": None, "aa": None, "answers": [], "raw": None, "error": None}
    start = time.monotonic()
    try:
        question = dns.message.make_query(name + ".", rdtype, want_dnssec=True)
        if tcp:
            response = dns.query.tcp(question, AUTHORITY, timeout=3)
        else:
            response, used_tcp = dns.query.udp_with_fallback(question, AUTHORITY, timeout=3)
            if used_tcp: result["transport"] = "TCP (UDP fallback)"
        result.update(rcode=dns.rcode.to_text(response.rcode()),
                      ad=bool(response.flags & dns.flags.AD),
                      aa=bool(response.flags & dns.flags.AA), raw=response.to_text())
        # Accept only the requested owner's A RRset, not unrelated additional data.
        owner = dns.name.from_text(name + ".")
        if rdtype == "A":
            result["answers"] = [item.address for rrset in response.answer
                if rrset.name == owner and rrset.rdtype == dns.rdatatype.A for item in rrset]
    except (dns.exception.DNSException, OSError, EOFError) as error:
        result["error"] = str(error)
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=NAMES, default=NAMES[0])
    parser.add_argument("--type", choices=["A", "AAAA"], default="A")
    parser.add_argument("--tcp", action="store_true")
    args = parser.parse_args()
    result = probe(args.name, args.type, args.tcp)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["error"] else 0)
