"""Small, dependency-free HTTP hardening controls for DocPilot."""

from __future__ import annotations

from collections import defaultdict, deque
from math import ceil
from threading import Lock
import time
from typing import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Attach browser hardening and no-store headers to API responses."""

    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Cache-Control", "no-store")
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), geolocation=(), microphone=()",
                )
                if self.production:
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'none'; frame-ancestors 'none'",
                    )
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class ContentLengthLimitMiddleware:
    """Reject declared request bodies above the configured application limit."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_length = Headers(scope=scope).get("content-length")
        if raw_length:
            try:
                content_length = int(raw_length)
            except ValueError:
                response = JSONResponse(
                    {"detail": "Invalid Content-Length header"},
                    status_code=400,
                )
                await response(scope, receive, send)
                return
            if content_length < 0:
                response = JSONResponse(
                    {"detail": "Invalid Content-Length header"},
                    status_code=400,
                )
                await response(scope, receive, send)
                return
            if content_length > self.max_bytes:
                response = JSONResponse(
                    {"detail": "Request body exceeds the configured limit"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Bound abuse of authentication, upload, and provider-backed endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        auth_limit: int,
        upload_limit: int,
        ai_limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.limits = {
            "authentication": max(1, auth_limit),
            "upload": max(1, upload_limit),
            "ai": max(1, ai_limit),
        }
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    @staticmethod
    def _bucket(scope: Scope) -> str | None:
        if scope.get("method") != "POST":
            return None
        path = scope.get("path", "")
        if path in {"/auth/login", "/auth/register"}:
            return "authentication"
        if path == "/documents":
            return "upload"
        if (
            path.endswith("/chat")
            or path == "/evaluation/runs"
            or path.startswith("/evaluation/compare/baseline-vs-rag/")
        ):
            return "ai"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        bucket = self._bucket(scope) if self.enabled and scope["type"] == "http" else None
        if bucket is None:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        key = (bucket, client_host)
        now = self.clock()
        limit = self.limits[bucket]

        with self._lock:
            timestamps = self._requests[key]
            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, ceil(self.window_seconds - (now - timestamps[0])))
            else:
                timestamps.append(now)
                retry_after = 0

        if retry_after:
            response = JSONResponse(
                {"detail": "Too many requests. Please retry later."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
