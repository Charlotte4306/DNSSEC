"""Only fixed, argument-list Docker commands. No shell or caller-provided command."""
import json
import subprocess
from dashboard.config import REPO_ROOT, SERVICES


class APIError(Exception):
    def __init__(self, code, message, status=503, details=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or {}


class DockerRunner:
    def command(self, args, timeout=25, allowed=(0,)):
        try:
            result = subprocess.run(
                ["docker", "compose", "--project-directory", str(REPO_ROOT), *args],
                cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise APIError("DOCKER_TIMEOUT", "Docker không trả kết quả trong thời hạn.", 504) from exc
        except OSError as exc:
            raise APIError("DOCKER_UNAVAILABLE", "Không chạy được Docker CLI.") from exc
        if result.returncode not in allowed:
            raise APIError("DOCKER_COMMAND_FAILED", "Thao tác Docker thất bại.", details={
                "exit_code": result.returncode, "stderr": result.stderr[-4000:]})
        return result.stdout

    @staticmethod
    def decode(raw):
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise APIError("INVALID_WORKER_OUTPUT", "Worker không trả JSON hợp lệ.", 502) from exc

    def health(self):
        raw = self.command(["ps", "--all", "--format", "json"], timeout=10)
        try:
            rows = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(line) for line in raw.splitlines() if line.strip()]
            rows = rows if isinstance(rows, list) else [rows]
            found = {row["Service"]: row for row in rows}
            services = {name: {"state": found.get(name, {}).get("State", "missing"),
                               "health": found.get(name, {}).get("Health", "")} for name in sorted(SERVICES)}
        except (ValueError, KeyError, TypeError) as exc:
            raise APIError("INVALID_DOCKER_OUTPUT", "Không đọc được trạng thái dịch vụ.", 502) from exc
        ready = all(s["state"] == "running" and s["health"] not in {"unhealthy", "starting"} for s in services.values())
        return {"source": "live", "ready": ready, "services": services}

    def snapshot(self):
        raw = self.command(["exec", "-T", "client", "python", "-c",
                            "from pathlib import Path; print(Path('/state/mode.json').read_text())"])
        data = self.decode(raw)
        if not isinstance(data, dict) or type(data.get("attack")) is not bool or not isinstance(data.get("changed_at"), str):
            raise APIError("INVALID_MODE", "Trạng thái relay không hợp lệ.", 502)
        return data

    def set_mode(self, active):
        return self.command(["exec", "-T", "client", "python", "/app/lab/dns_scenario.py", "on" if active else "off"])

    def flush(self, resolver):
        if resolver not in {"plain", "secure"}:
            raise ValueError("Unknown resolver")
        return self.command(["exec", "-T", resolver, "unbound-control", "-c",
                             f"/app/conf/{resolver}.conf", "flush_zone", "demo.test"])

    def compare(self, run_id):
        # Exit 1 can carry measured DNS/HTTP errors; preserve them as measurements.
        return self.decode(self.command(["exec", "-T", "client", "python", "/app/lab/api_worker.py",
                                         "compare", "--name", "www.demo.test", "--run-id", run_id], allowed=(0, 1)))

    def proof(self):
        return self.decode(self.command(["exec", "-T", "client", "python", "/app/lab/dns_scenario.py", "proof"]))

    def web_logs(self, since):
        raw = self.command(["logs", "--no-color", "--since", since, "--tail", "500", "web-good", "web-fake"], timeout=10)
        rows = []
        for line in raw.splitlines():
            start = line.find("{")
            if start < 0:
                continue
            # Concurrent http.server threads can write adjacent JSON objects on one
            # Docker log line. Decode objects individually, preserving both branches.
            fragment = line[start:]
            decoder = json.JSONDecoder()
            while fragment:
                try:
                    value, end = decoder.raw_decode(fragment)
                except ValueError:
                    break
                if isinstance(value, dict):
                    rows.append(value)
                fragment = fragment[end:].lstrip()
        return rows

    def dns_logs(self, since):
        return self.command(["logs", "--no-color", "--timestamps", "--since", since,
                             "--tail", "200", "secure", "tamper"], timeout=10)
