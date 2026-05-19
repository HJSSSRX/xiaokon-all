"""Shared HTTP base handler for collaboration modules.

Extracted from collab_hub and collab_sync to eliminate duplicated
request/response patterns. Both HubHandler and SyncHandler inherit from this.
"""

import http.server
import json
from urllib.parse import parse_qs


class BaseHandler(http.server.BaseHTTPRequestHandler):
    """Shared base with _send, _err, _read_json, _split_path, do_OPTIONS."""

    def _send(self, status, body=None, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if body is not None:
            if isinstance(body, (dict, list)):
                payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
            elif isinstance(body, bytes):
                payload = body
            else:
                payload = str(body).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_header("Content-Length", "0")
            self.end_headers()

    def _err(self, status, msg):
        self._send(status, {"error": msg, "code": status})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return None

    def _split_path(self):
        if "?" in self.path:
            path, qs = self.path.split("?", 1)
            query = {k: v[0] for k, v in parse_qs(qs).items()}
        else:
            path, query = self.path, {}
        path = path.rstrip("/") or "/"
        return path, query

    def do_OPTIONS(self):
        self._send(204)
