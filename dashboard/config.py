from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = REPO_ROOT / "evidence" / "runs"
TARGET = "www.demo.test"
SERVICES = {"authority", "tamper", "plain", "secure", "client", "web-good", "web-fake"}
