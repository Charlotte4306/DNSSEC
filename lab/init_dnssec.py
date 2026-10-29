"""Create lab-only keys and refresh signatures before BIND starts."""
import json
from pathlib import Path
import subprocess
import time

KEYS = Path("/keys")
SIGNED = Path("/signed")
TRUST = Path("/trust")
STATE = Path("/state")

def run(*args):
    return subprocess.check_output(args, cwd=KEYS, text=True).strip()

def main():
    for directory in [KEYS, SIGNED, TRUST, STATE]:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)
    if not list(KEYS.glob("Kdemo.test.*.key")):
        run("dnssec-keygen", "-q", "-a", "ECDSAP256SHA256", "-f", "KSK", "demo.test")
        run("dnssec-keygen", "-q", "-a", "ECDSAP256SHA256", "demo.test")
    zone = Path("/app/zones/demo.test").read_text()
    zone = zone.replace("2026102901", str(int(time.time())))
    (SIGNED / "demo.test").write_text(zone)
    run("dnssec-signzone", "-S", "-K", str(KEYS), "-n", "1", "-o", "demo.test",
        "-s", "now-3600", "-e", "now+2592000", "-f", "/signed/demo.test.signed", "/signed/demo.test")
    ksk = next(key for key in KEYS.glob("*.key") if "DNSKEY 257 " in key.read_text())
    (TRUST / "anchor.key").write_text(ksk.read_text())
    (TRUST / "anchor.ds").write_text(run("dnssec-dsfromkey", "-2", str(ksk)) + "\n")
    (STATE / "mode.json").write_text(json.dumps({"attack": False}))
    for p in list(SIGNED.iterdir()) + list(TRUST.iterdir()) + list(STATE.iterdir()):
        if p.is_file(): p.chmod(0o644)
    print("Signed demo.test; local DNSKEY trust anchor ready; attack OFF.")

if __name__ == "__main__": main()
