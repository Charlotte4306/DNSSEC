"""Store raw measurements separately from sanitized, offline-only previews."""
from html import escape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import bleach
from dashboard.services.docker_runner import APIError

RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts, self.hidden = [], []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style", "template"}:
            self.hidden.append(tag)
        elif not self.hidden:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        else:
            self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if not self.hidden:
            self.parts.append(f"<{tag}>")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(escape(data))

    def handle_entityref(self, name):
        if not self.hidden:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.hidden:
            self.parts.append(f"&#{name};")


def sanitize_preview(body, site_id):
    parser = VisibleHTML()
    parser.feed(body)
    fragment = bleach.clean("".join(parser.parts), tags={
        "main", "section", "article", "div", "span", "h1", "h2", "h3", "p",
        "strong", "em", "b", "i", "br", "hr", "ul", "ol", "li", "code", "pre",
        "table", "thead", "tbody", "tr", "td", "th"}, attributes={}, protocols=[], strip=True)
    color = "#8c2630" if site_id == "training-fake" else "#20533b"
    return ('<!doctype html><html lang="vi"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<style>body{{font:16px "Segoe UI",sans-serif;padding:18px;color:{color};background:#f8fafc}}'
            'h1{font-size:24px}p{line-height:1.5}</style><body>' + fragment + '</body></html>')


class EvidenceStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, run_id):
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise APIError("INVALID_RUN_ID", "run_id không hợp lệ.", 400)
        return self.directory / run_id

    def save(self, run_id, result, worker, logs, context):
        folder = self.path(run_id)
        folder.mkdir(parents=True, exist_ok=False)
        for name, value in [("worker.json", worker), ("http-access.json", logs)]:
            (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "dns-context.log").write_text(context, encoding="utf-8")
        for branch, measured in worker["results"].items():
            data = measured["http"]
            if data["status"] == 200 and data["body"] is not None:
                preview = sanitize_preview(data["body"], data["site_id"])
                (folder / f"preview-{branch}.html").write_text(preview, encoding="utf-8")
        # Publish result last: incomplete directories never look like completed runs.
        temp = folder / "result.tmp"
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(folder / "result.json")

    def get(self, run_id):
        try:
            return json.loads((self.path(run_id) / "result.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise APIError("RUN_NOT_FOUND", "Không tìm thấy lần chạy đã hoàn thành.", 404) from exc

    def preview(self, run_id, branch):
        if branch not in {"plain", "secure"}:
            raise APIError("INVALID_BRANCH", "Chỉ nhận plain hoặc secure.", 400)
        result = self.get(run_id)
        http = result["results"][branch]["http"]
        if not result["consistent"] or http["status"] != 200 or http["error"] or not http.get("preview_url"):
            raise APIError("NO_PREVIEW", "Nhánh này không có nội dung HTTP hợp lệ.", 404)
        try:
            return (self.path(run_id) / f"preview-{branch}.html").read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise APIError("NO_PREVIEW", "Chưa lưu được preview của lần chạy.", 404) from exc


def match_logs(worker, rows):
    matching = [row for row in rows if row.get("run_id") == worker["run_id"]]
    evidence = {}
    for branch, result in worker["results"].items():
        http = result["http"]
        records = [row for row in matching if row.get("branch_id") == branch]
        expected = [row for row in records if row.get("method") == "GET" and row.get("path") == "/"
                    and row.get("host") == worker["target"] and row.get("status") == http["status"]
                    and row.get("site_id") == http["site_id"]]
        evidence[branch] = {
            "matched_log_ids": [hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() for row in expected],
            "observed_request_count": len(records),
            "http_corroborated": bool(expected) if http["status"] == 200 else False,
            "no_http_observed": not http["attempted"] and not records,
        }
    return matching, evidence
