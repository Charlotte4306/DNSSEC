"""Accidental-change detection for a bounded set of run artifacts; not a signature."""
import hashlib
import json
from pathlib import Path
import re

CORE = {"worker.json", "http-access.json", "dns-context.log", "result.json"}
ALLOWED = CORE | {"proof.json", "preview-plain.html", "preview-secure.html"}
LIMIT = 8 * 1024 * 1024


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(folder, run_id):
    files = {name: digest(folder / name) for name in sorted(ALLOWED - {"result.json"}) if (folder/name).is_file()}
    files["result.json"] = digest(folder / "result.tmp")
    value = {"schema_version": 1, "algorithm": "sha256", "run_id": run_id, "files": files,
             "scope": "file_integrity_not_authenticity_or_dnssec_validation"}
    (folder/"checksums.json").write_text(json.dumps(value, indent=2), encoding="utf-8")


def verify_manifest(folder, run_id):
    folder = Path(folder)
    report = {"run_id": run_id, "verified": False, "status": "unavailable", "files": [],
              "scope": "SHA-256 detects changed bytes; anyone who can rewrite files and this manifest can forge it."}
    manifest = folder / "checksums.json"
    try:
        if folder.is_symlink() or manifest.is_symlink():
            raise ValueError("Symlink artifact directory or manifest is not allowed")
        if not manifest.exists():
            return report
        if manifest.stat().st_size > 65536:
            raise ValueError("Manifest too large")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        files = value["files"]
        if (value.get("schema_version") != 1 or value.get("algorithm") != "sha256"
            or value.get("run_id") != run_id or not isinstance(files, dict)
            or not CORE <= set(files) or not set(files) <= ALLOWED):
            raise ValueError("Invalid manifest identity or file list")
        for name, expected in sorted(files.items()):
            if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected):
                raise ValueError("Invalid SHA-256")
            artifact = folder / name
            usable = artifact.is_file() and not artifact.is_symlink() and artifact.stat().st_size <= LIMIT
            actual = digest(artifact) if usable else None
            report["files"].append({"file": name, "expected_sha256": expected,
                                    "actual_sha256": actual, "match": usable and expected == actual})
        report["verified"] = all(row["match"] for row in report["files"])
        report["status"] = "verified" if report["verified"] else "mismatch"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.update(status="invalid_manifest", error=str(exc))
    return report
