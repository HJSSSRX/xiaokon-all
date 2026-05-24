"""Shared HTTP base handler for collaboration modules.

Extracted from collab_hub and collab_sync to eliminate duplicated
request/response patterns. Both HubHandler and SyncHandler inherit from this.
"""

import http.server
import json
import os
from urllib.parse import parse_qs

# Shared secret set by the server bootstrap. None = auth disabled (dev mode).
_API_KEY: str | None = None
# CORS origin restriction. None = "*" (any origin).
_CORS_ORIGIN: str | None = None


def set_api_key(key: str | None) -> None:
    global _API_KEY
    _API_KEY = key


def set_cors_origin(origin: str | None) -> None:
    global _CORS_ORIGIN
    _CORS_ORIGIN = origin


def _cors_header() -> str:
    if _CORS_ORIGIN:
        return _CORS_ORIGIN
    return os.environ.get("HUB_CORS_ORIGIN", "*")


class BaseHandler(http.server.BaseHTTPRequestHandler):
    """Shared base with _send, _err, _read_json, _split_path, do_OPTIONS."""

    # Override in subclasses to skip auth for public endpoints
    PUBLIC_PATHS = {"/ping"}

    def _check_auth(self) -> bool:
        """Check shared-secret auth. Returns True if request is authorized."""
        if _API_KEY is None:
            return True  # dev mode — no auth required
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == _API_KEY
        api_key_header = self.headers.get("X-API-Key", "")
        if api_key_header:
            return api_key_header == _API_KEY
        return False

    def _send(self, status, body=None, content_type="application/json; charset=utf-8"):
        origin = _cors_header()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
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

    def _check_auth_or_fail(self) -> bool:
        """Check auth; send 401 and return False if unauthorized."""
        if not self._check_auth():
            self._err(401, "Unauthorized — provide Bearer <key> or X-API-Key header")
            return False
        return True

    def do_OPTIONS(self):
        self._send(204)
