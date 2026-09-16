"""Minimal HTTP layer: routing, JSON plumbing, static files, security headers.

Standard library only.  The server binds to loopback by default -- this holds
PHI and must not be exposed on a network interface without a TLS terminator
and a real risk assessment.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from . import config

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

SECURITY_HEADERS = {
    # No third-party origins at all: everything is served from this process.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # PHI must not be cached by the browser.
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
}


class HttpError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


class Request:
    def __init__(self, method: str, path: str, query: dict, headers, body: bytes, params: dict):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body
        self.params = params
        self.client = ""
        self._json = None

    @property
    def json(self) -> dict:
        if self._json is None:
            if not self.body:
                self._json = {}
            else:
                try:
                    self._json = json.loads(self.body.decode("utf-8"))
                except ValueError:
                    raise HttpError(400, "Request body was not valid JSON.")
            if not isinstance(self._json, dict):
                raise HttpError(400, "Request body must be a JSON object.")
        return self._json

    def cookie(self, name: str):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            return None
        morsel = jar.get(name)
        return morsel.value if morsel else None

    def q(self, name: str, default=None):
        values = self.query.get(name)
        return values[0] if values else default


class Response:
    def __init__(self, body=None, status: int = 200, headers: dict | None = None,
                 content_type: str = "application/json", raw: bytes | None = None):
        self.status = status
        self.headers = dict(headers or {})
        self.content_type = content_type
        if raw is not None:
            self.raw = raw
        else:
            self.raw = json.dumps(body if body is not None else {}, ensure_ascii=False).encode("utf-8")

    def set_cookie(self, name: str, value: str, max_age: int = 43200, http_only: bool = True):
        parts = [f"{name}={value}", "Path=/", "SameSite=Strict", f"Max-Age={max_age}"]
        if http_only:
            parts.append("HttpOnly")
        if config.HOSTED:
            # Behind a TLS terminator the browser only ever sees HTTPS, so the
            # session cookie must never be sent over a plain connection.
            parts.append("Secure")
        self.headers["Set-Cookie"] = "; ".join(parts)


Route = Tuple[str, re.Pattern, Callable]


class Router:
    def __init__(self):
        self.routes: List[Route] = []

    def add(self, method: str, pattern: str, handler: Callable):
        regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")
        self.routes.append((method, regex, handler))

    def get(self, pattern):
        return lambda fn: (self.add("GET", pattern, fn), fn)[1]

    def post(self, pattern):
        return lambda fn: (self.add("POST", pattern, fn), fn)[1]

    def put(self, pattern):
        return lambda fn: (self.add("PUT", pattern, fn), fn)[1]

    def match(self, method: str, path: str):
        allowed = False
        for route_method, regex, handler in self.routes:
            match = regex.match(path)
            if match:
                if route_method == method:
                    return handler, {k: v for k, v in match.groupdict().items()}
                allowed = True
        if allowed:
            raise HttpError(405, "Method not allowed for this endpoint.")
        return None, {}


def make_handler(router: Router, context_factory: Callable):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PsychReport"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quieter, and never logs PHI-bearing bodies
            if os.environ.get("PSYCHREPORT_VERBOSE"):
                super().log_message(fmt, *args)

        # -- helpers ----------------------------------------------------
        def _send(self, response: Response):
            body = response.raw
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            if config.HOSTED:
                self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _client_key(self) -> str:
            """Identifies a connection for sign-in throttling. Behind a proxy the
            socket peer is the proxy itself, so the forwarded header is used. That
            header can be forged, which lets a client evade its own throttle but
            never lets it throttle someone else -- the property that matters on a
            shared demo whose passwords are printed on the sign-in page."""
            peer = self.client_address[0] if self.client_address else ""
            if config.HOSTED:
                return (self.headers.get("X-Forwarded-For") or "").strip() or peer
            return peer

        def _error(self, status: int, message: str, **extra):
            payload = {"error": message}
            payload.update(extra)
            self._send(Response(payload, status=status))

        def _static(self, path: str):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            full = os.path.normpath(os.path.join(WEB_ROOT, rel))
            if not full.startswith(WEB_ROOT) or not os.path.isfile(full):
                return self._error(404, "Not found.")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as handle:
                data = handle.read()
            self._send(Response(raw=data, content_type=ctype))

        def _dispatch(self, method: str):
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/healthz" and method in ("GET", "HEAD"):
                    # Liveness probe for the hosting platform. Touches no data
                    # and is not audited, so health checks don't flood the log.
                    return self._send(Response(raw=b"ok", content_type="text/plain; charset=utf-8"))
                if not path.startswith("/api/"):
                    if method in ("GET", "HEAD"):
                        return self._static(path)
                    raise HttpError(404, "Not found.")

                length = int(self.headers.get("Content-Length") or 0)
                if length > 8 * 1024 * 1024:
                    raise HttpError(413, "Request body too large.")
                body = self.rfile.read(length) if length else b""

                handler, params = router.match(method, path)
                if handler is None:
                    raise HttpError(404, "No such endpoint.")

                request = Request(method, path, parse_qs(parsed.query), self.headers, body, params)
                request.client = self._client_key()
                # CSRF: state-changing calls must carry the custom header a
                # cross-site form cannot set, in addition to SameSite=Strict.
                if method in ("POST", "PUT", "DELETE") and request.headers.get("X-PsychReport") != "1":
                    raise HttpError(403, "Missing X-PsychReport header (CSRF protection).")

                ctx = context_factory()
                response = handler(ctx, request)
                if isinstance(response, Response):
                    return self._send(response)
                return self._send(Response(response))
            except HttpError as exc:
                return self._error(exc.status, exc.message, **exc.extra)
            except BrokenPipeError:
                return
            except Exception:
                traceback.print_exc()
                return self._error(500, "Internal error. The action was not completed.")

        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):
            self._dispatch("HEAD")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


def serve(router: Router, context_factory: Callable, host: str = "127.0.0.1", port: int = 8765):
    httpd = ThreadingHTTPServer((host, port), make_handler(router, context_factory))
    httpd.daemon_threads = True
    return httpd
