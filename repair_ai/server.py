"""Web app: `python -m repair_ai.server` then open http://127.0.0.1:8000  (standard library only)."""
import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 
from .circuits import CIRCUITS, apply_fault, build, describe, faults_of
from .diagnose import diagnose, predict
from .netlist import register
 
PAGE = os.path.join(os.path.dirname(__file__), "static", "index.html")
 
 
def circuits_info():
    out = []
    for cid, spec in CIRCUITS.items():
        base = build(cid)
        by_name = {c["name"]: c for c in base}
        out.append({"id": cid, "title": spec["title"], "probes": spec["probes"],
                    "has_led": any(c["kind"] == "led" for c in base),
                    "parts": [{"name": c["name"], "kind": c["kind"], "value": c["value"], "nodes": list(c["n"])} for c in base],
                    "faults": [{"component": n, "mode": m, "title": describe(by_name[n], m)[0]}
                               for n, m in faults_of(base)]})
    return out
 
 
def inject(circuit, component, mode):
    """Readings a multimeter would show for this fault (with ~1 % meter noise)."""
    base = build(circuit)
    comps = base if not component else apply_fault(base, component, mode)
    has_led = any(c["kind"] == "led" for c in base)
    rd = predict(comps, CIRCUITS[circuit]["probes"], has_led)
    return {k: (v if k == "LED" else round(v * (1 + random.uniform(-0.01, 0.01)), 4)) for k, v in rd.items()}
 
 
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
 
    def do_GET(self):
        if self.path == "/api/circuits":
            self._send(200, circuits_info())
        elif self.path in ("/", "/index.html"):
            with open(PAGE, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})
 
    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/diagnose":
                self._send(200, diagnose(req["circuit"], req.get("readings", {}), req.get("checks", {})))
            elif self.path == "/api/netlist":
                self._send(200, {"id": register(req["text"])})
            elif self.path == "/api/inject":
                self._send(200, inject(req["circuit"], req.get("component"), req.get("mode")))
            else:
                self._send(404, {"error": "not found"})
        except (KeyError, ValueError, StopIteration) as e:
            self._send(400, {"error": f"bad request: {e}"})
        except Exception as e:  # never drop the connection silently
            self._send(500, {"error": f"server error: {e}"})
 
    def log_message(self, *args):
        pass
 
 
def main(port=8000):
    print(f"REPAIR-AI running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
 
 
if __name__ == "__main__":
    main()
 