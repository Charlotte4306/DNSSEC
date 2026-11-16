"""Fixed lab diagnostics, separate from the evidence of an earlier measurement."""
from datetime import datetime, timezone
import subprocess
import re
import shlex
import threading
import time

from dashboard.config import REPO_ROOT
from dashboard.services.docker_runner import APIError

OUTPUT_LIMIT = 32 * 1024
COMMANDS = {
    "plain-a": ("Hỏi IP qua plain", "Plain trả lời gì khi không xác thực DNSSEC?", "172.30.53.40", "www.demo.test", "A", False),
    "secure-a": ("Hỏi IP qua secure", "Đọc RCODE và AD; SERVFAIL cần đối chiếu thêm log.", "172.30.53.30", "www.demo.test", "A", False),
    "dnskey": ("Xem khóa và chữ ký", "DNSKEY là khóa công khai; có RRSIG chưa có nghĩa đã xác thực.", "172.30.53.10", "demo.test", "DNSKEY", False),
    "nxdomain": ("Hỏi tên không tồn tại", "NXDOMAIN có AD là kết quả phủ định được xác thực trong lab hợp lệ.", "172.30.53.30", "not-present.demo.test", "A", False),
    "control": ("Đối chứng tên không bị sửa", "control.demo.test không bị relay sửa, kể cả khi đang bật can thiệp.", "172.30.53.30", "control.demo.test", "A", False),
    "secure-tcp": ("Kiểm tra DNS qua TCP", "Đối chiếu với UDP; DNSSEC bảo vệ dữ liệu, không chỉ một transport.", "172.30.53.30", "www.demo.test", "A", True),
    "dns-logs": ("Xem log xác thực", "40 dòng gần nhất mỗi dịch vụ; log là ngữ cảnh, không gắn chính xác với run_id.", None, None, None, False),
}


def command_spec(command_id):
    if isinstance(command_id,str) and command_id not in COMMANDS:
        return typed_spec(command_id)
    if not isinstance(command_id, str) or command_id not in COMMANDS:
        raise APIError("INVALID_TERMINAL_COMMAND", "Chọn một lệnh kiểm tra có trong danh mục.", 400)
    label, explanation, server, name, kind, tcp = COMMANDS[command_id]
    if command_id == "dns-logs":
        args = ["logs", "--no-color", "--timestamps", "--tail", "40", "secure", "tamper"]
        command = "docker compose " + " ".join(args)
        location = "host lab"
    else:
        query = ["dig", "@" + server, name, kind, "+dnssec", "+time=2", "+tries=1"]
        if tcp:
            query.append("+tcp")
        args = ["exec", "-T", "authority", "timeout", "8", *query]
        command = " ".join(query)
        location = "authority"
    return {"command_id": command_id, "label": label, "explanation": explanation,
            "command": command, "executed_in": location, "args": args}


def typed_spec(command):
    """Parse a diagnostic command into argv, never a host/container shell."""
    def invalid(message):
        raise APIError('INVALID_TERMINAL_COMMAND', message, 400)
    if len(command)>512 or any(c in command for c in '\n\r\x00;&|`$<>\\'):
        invalid('Nhập một lệnh dig hoặc logs trên một dòng; không ghép lệnh shell.')
    try:
        words=shlex.split(command)
    except ValueError:
        invalid('Dấu nháy trong lệnh chưa khép.')
    if not words:invalid('Nhập lệnh trước khi chạy.')
    if words[0]=='logs':
        services=[];tail='40';i=1
        while i<len(words):
            word=words[i]
            if word=='--tail' and i+1<len(words):
                i+=1;tail=words[i]
                if not tail.isdigit() or not 1<=int(tail)<=200:invalid('--tail từ 1 đến 200.')
            elif word in {'secure','plain','tamper','authority','web-good','web-fake'} and word not in services:services.append(word)
            else:invalid('Cú pháp: logs secure tamper --tail 40')
            i+=1
        services=services or ['secure','tamper']
        return {'command_id':command,'command':command,'label':'Log lab','explanation':'Log theo thời gian, không gắn chính xác với run trước.','executed_in':'host lab','args':['logs','--no-color','--timestamps','--tail',tail,*services]}
    if words[0]!='dig':invalid('Console hỗ trợ dig và logs. Nhập help để xem cú pháp; shell đầy đủ dùng SSH.')
    servers={'plain':'172.30.53.40','secure':'172.30.53.30','relay':'172.30.53.20','authority':'172.30.53.10'}
    types={'A','AAAA','DNSKEY','RRSIG','DS','NSEC','NSEC3','SOA','NS','TXT','CNAME','MX','ANY','CAA','SRV','PTR','HTTPS'}
    options={'+dnssec','+nodnssec','+tcp','+notcp','+cdflag','+nocdflag','+short','+noshort','+multi','+nomulti','+norecurse','+recurse','+noall','+all','+answer','+noanswer','+comments','+nocomments','+stats','+nostats','+authority','+noauthority','+additional','+noadditional','+question','+noquestion','+rrcomments','+ttlunits'}
    server=None;name=None;kind=None;flags=[]
    for word in words[1:]:
        if word.startswith('@'):
            candidate=servers.get(word[1:],word[1:])
            if server is not None or candidate not in servers.values():invalid('Resolver phải là @plain, @secure, @relay, @authority hoặc IP tương ứng trong lab.')
            server=candidate
        elif word.upper() in types:
            if kind is not None:invalid('Mỗi lệnh chỉ hỏi một loại bản ghi.')
            kind=word.upper()
        elif word.upper()=='IN':continue
        elif word.lower() in options:flags.append(word.lower())
        elif word.startswith('+'):invalid('Tùy chọn chưa hỗ trợ. Dùng help để xem tùy chọn kiểm tra DNS.')
        else:
            candidate=word.rstrip('.').lower()
            if name is not None or len(candidate)>253 or not re.fullmatch(r'(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)*demo\.test',candidate):
                invalid('Tên truy vấn phải thuộc demo.test; mỗi lệnh hỏi một tên.')
            name=word
    query=['dig','@'+(server or servers['secure']),name or 'www.demo.test',kind or 'A',*flags,'+time=2','+tries=1']
    return {'command_id':command,'command':command,'label':'Truy vấn tự nhập','explanation':'Đầu ra mới từ dig trong lab.','executed_in':'authority','args':['exec','-T','authority','timeout','8',*query]}


def catalog():
    return [{k: v for k, v in command_spec(key).items() if k != "args"} for key in COMMANDS]


def execute_terminal(command_id):
    spec = command_spec(command_id)
    command = ["docker", "compose", "--project-directory", str(REPO_ROOT), *spec["args"]]
    started = time.monotonic()
    try:
        process = subprocess.Popen(command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise APIError("DOCKER_UNAVAILABLE", "Không chạy được Docker CLI.", 503) from exc
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    lock = threading.Lock()
    count = 0
    truncated = False

    def drain(stream, channel):
        nonlocal count, truncated
        try:
            while True:
                piece = stream.read(4096)
                if not piece:
                    break
                with lock:
                    kept = piece[:max(0, OUTPUT_LIMIT - count)]
                    chunks[channel].extend(kept)
                    count += len(kept)
                    truncated = truncated or len(kept) != len(piece)
        finally:
            stream.close()

    readers = [threading.Thread(target=drain, args=(getattr(process, channel), channel), daemon=True)
               for channel in chunks]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=2)
    for reader in readers:
        reader.join(timeout=1)
    with lock:
        output = {channel: bytes(data).decode("utf-8", errors="replace") for channel, data in chunks.items()}
    return {**output, "exit_code": process.returncode, "timed_out": timed_out,
            "truncated": truncated, "output_complete": not any(t.is_alive() for t in readers),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}


class TerminalService:
    def __init__(self, lab):
        self.lab = lab

    def run(self, command_id):
        spec = command_spec(command_id)  # Validate before reserving or invoking Docker.

        def operation():
            requested_at = datetime.now(timezone.utc).isoformat()
            before = self.lab.runner.snapshot()
            value = self.lab.runner.terminal_command(command_id)
            after = self.lab.runner.snapshot()
            consistent = before == after
            if not consistent:
                with self.lab.meta_lock:
                    self.lab.prepared = None
            return {"source": "live", "kind": "supplementary_command", "requested_at": requested_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "revision": before["changed_at"], "revision_after": after["changed_at"],
                    "consistent": consistent, **{k: v for k, v in spec.items() if k != "args"}, **value}

        return self.lab.exclusive("terminal:" + command_id, operation)
