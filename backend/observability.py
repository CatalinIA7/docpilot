"""Lightweight structured logging and request correlation for DocPilot."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any
from uuid import uuid4

from fastapi import Request, Response


_request_id: ContextVar[str | None] = ContextVar("docpilot_request_id", default=None)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_STANDARD_LOG_FIELDS = frozenset(
    logging.makeLogRecord({}).__dict__
) | {"message", "asctime"}


def get_request_id() -> str | None:
    """Return the request ID associated with the current execution context."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token:
    """Associate a request ID with the current execution context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token) -> None:
    """Restore the previous request context."""
    _request_id.reset(token)


def resolve_request_id(candidate: str | None) -> str:
    """Accept a bounded correlation ID or generate a new opaque identifier."""
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid4())


def _json_value(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class JsonLogFormatter(logging.Formatter):
    """Render a log record as one JSON object suitable for platform logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": os.getenv("DOCPILOT_SERVICE_NAME", "docpilot-backend"),
            "logger": record.name,
            "event": getattr(record, "event", "application_log"),
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_FIELDS and key not in payload:
                payload[key] = _json_value(value)

        if record.exc_info:
            exception_type, _, exception_traceback = record.exc_info
            payload["exception"] = {
                "type": exception_type.__name__,
                "frames": [
                    {
                        "file": Path(frame.filename).name,
                        "function": frame.name,
                        "line": frame.lineno,
                    }
                    for frame in traceback.extract_tb(exception_traceback)
                ],
            }

        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class TextLogFormatter(logging.Formatter):
    """Readable local formatter that still includes event and request context."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "event"):
            record.event = "application_log"
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or "-"
        return super().format(record)


def _log_level() -> int:
    configured = os.getenv("DOCPILOT_LOG_LEVEL", "INFO").upper()
    return getattr(logging, configured, logging.INFO)


def configure_logging(*, force: bool = False) -> None:
    """Install one application log handler without disturbing test/tool handlers."""
    root = logging.getLogger()
    existing = [
        handler
        for handler in root.handlers
        if getattr(handler, "_docpilot_handler", False)
    ]
    if existing and not force:
        return

    for handler in existing:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler._docpilot_handler = True  # type: ignore[attr-defined]
    if os.getenv("DOCPILOT_LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(
            TextLogFormatter(
                "%(asctime)s %(levelname)s %(name)s "
                "event=%(event)s request_id=%(request_id)s %(message)s"
            )
        )
    else:
        handler.setFormatter(JsonLogFormatter())

    root.addHandler(handler)
    root.setLevel(_log_level())
    logging.captureWarnings(True)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Emit a named event without logging request bodies, prompts, or secrets."""
    logger.log(
        level,
        message,
        extra={"event": event, **fields},
        exc_info=exc_info,
    )


async def observe_request(request: Request, call_next) -> Response:
    """Correlate and time one HTTP request."""
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    token = set_request_id(request_id)
    started_at = time.perf_counter()
    logger = logging.getLogger("docpilot.http")

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000
        log_event(
            logger,
            logging.ERROR,
            "http_request_failed",
            "Unhandled request failure",
            exc_info=True,
            method=request.method,
            path=request.url.path,
            duration_ms=round(duration_ms, 3),
            error_type=type(exc).__name__,
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        duration_ms = (time.perf_counter() - started_at) * 1000
        event = "health_check" if request.url.path == "/health" else "http_request_completed"
        level = logging.ERROR if response.status_code >= 500 else logging.INFO
        log_event(
            logger,
            level,
            event,
            "HTTP request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 3),
        )
        return response
    finally:
        reset_request_id(token)
