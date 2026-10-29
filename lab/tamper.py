"""Controlled response mutation; no Kaminsky exploit or key access."""
import json
from pathlib import Path
import socketserver
import struct
import threading
import dns.flags
import dns.message
import dns.query
import dns.rdatatype
import dns.rrset

def mutate(response, active):
    changed = False
    if active:
        for i, rrset in enumerate(response.answer):
            if rrset.name.to_text().lower() == "www.demo.test." and rrset.rdtype == dns.rdatatype.A:
                response.answer[i] = dns.rrset.from_text(rrset.name, rrset.ttl, "IN", "A", "172.30.53.90")
                changed = True
    return response, changed

def relay(wire):
    query = dns.message.from_wire(wire)
    query.use_edns(edns=0, ednsflags=dns.flags.DO, payload=1232)
    response, _ = dns.query.udp_with_fallback(query, "172.30.53.10", timeout=3)
    active = json.loads(Path("/state/mode.json").read_text())["attack"]
    response, changed = mutate(response, active)
    q = query.question[0]
    print(json.dumps({"event": "TAMPER" if changed else "PASS", "name": q.name.to_text(),
                      "type": dns.rdatatype.to_text(q.rdtype), "signature_retained": changed}), flush=True)
    return response.to_wire(max_size=65535)

def exact(sock, size):
    data = b""
    while len(data) < size:
        piece = sock.recv(size - len(data))
        if not piece: raise EOFError("Incomplete TCP DNS message")
        data += piece
    return data

class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        wire, sock = self.request
        try: sock.sendto(relay(wire), self.client_address)
        except Exception as exc: print("UDP relay error:", repr(exc), flush=True)

class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            size = struct.unpack("!H", exact(self.request, 2))[0]
            response = relay(exact(self.request, size))
            self.request.sendall(struct.pack("!H", len(response)) + response)
        except Exception as exc: print("TCP relay error:", repr(exc), flush=True)

class UDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True

class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    udp = UDPServer(("0.0.0.0", 53), UDP)
    tcp = TCPServer(("0.0.0.0", 53), TCP)
    threading.Thread(target=udp.serve_forever, daemon=True).start()
    print("Tamper relay ready on UDP/TCP 53", flush=True)
    tcp.serve_forever()
