import os
import sys
import json
from http.server import BaseHTTPRequestHandler

# Ensure the FastAPI backend package is importable in Vercel
CLIENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if CLIENT_ROOT not in sys.path:
    sys.path.insert(0, CLIENT_ROOT)

from server.main import app as fastapi_app
from fastapi.testclient import TestClient

test_client = TestClient(fastapi_app)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                payload = {}
            resp = test_client.post("/api/tts", json=payload)

            self.send_response(resp.status_code)
            # Forward response headers except hop-by-hop ones
            skip = {"transfer-encoding", "content-encoding", "content-length", "connection"}
            sent = set()
            for k, v in resp.headers.items():
                lk = k.lower()
                if lk in skip:
                    continue
                self.send_header(k, v)
                sent.add(lk)
            if "content-type" not in sent:
                self.send_header("Content-Type", "application/octet-stream" if resp.status_code == 200 else "application/json")
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Internal Server Error", "detail": str(e)}).encode("utf-8"))