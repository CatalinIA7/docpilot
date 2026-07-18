import json
import logging
import sys

import pytest
from sqlalchemy import create_engine, text

import database
import observability
from observability import JsonLogFormatter, reset_request_id, set_request_id


def test_json_formatter_emits_structured_event_with_request_id():
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="docpilot.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Operation completed",
            args=(),
            exc_info=None,
        )
        record.event = "test_completed"
        record.duration_ms = 12.5

        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["level"] == "INFO"
    assert payload["event"] == "test_completed"
    assert payload["request_id"] == "request-123"
    assert payload["duration_ms"] == 12.5
    assert payload["message"] == "Operation completed"


def test_json_formatter_omits_exception_messages_that_may_contain_sensitive_data():
    try:
        raise RuntimeError("SELECT secret_value FROM private_table")
    except RuntimeError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="docpilot.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Database operation failed",
        args=(),
        exc_info=exception_info,
    )
    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["exception"]["frames"]
    assert "secret_value" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("candidate", "is_preserved"),
    [
        ("upstream-request_123", True),
        ("bad request id with spaces", False),
    ],
)
def test_resolve_request_id_accepts_only_bounded_safe_values(candidate, is_preserved):
    resolved = observability.resolve_request_id(candidate)

    assert (resolved == candidate) is is_preserved
    assert len(resolved) <= 128


def test_health_response_propagates_request_id_and_logs_timing(client, monkeypatch):
    events = []

    def capture_event(logger, level, event, message, **fields):
        events.append((event, fields))

    monkeypatch.setattr(observability, "log_event", capture_event)

    response = client.get("/health", headers={"X-Request-ID": "health-check-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "health-check-1"
    assert events[-1][0] == "health_check"
    assert events[-1][1]["status_code"] == 200
    assert events[-1][1]["duration_ms"] >= 0


def test_database_observability_records_query_timing(monkeypatch):
    events = []

    def capture_event(logger, level, event, message, **fields):
        events.append((event, fields))

    monkeypatch.setattr(database, "log_event", capture_event)
    test_engine = create_engine("sqlite:///:memory:")
    database.install_database_observability(test_engine)

    with test_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1

    completed = [fields for event, fields in events if event == "database_query_completed"]
    assert completed
    assert completed[-1]["operation"] == "SELECT"
    assert completed[-1]["duration_ms"] >= 0


def test_database_observability_records_failures_without_sql(monkeypatch):
    events = []

    def capture_event(logger, level, event, message, **fields):
        events.append((event, fields))

    monkeypatch.setattr(database, "log_event", capture_event)
    test_engine = create_engine("sqlite:///:memory:")
    database.install_database_observability(test_engine)

    with pytest.raises(Exception):
        with test_engine.connect() as connection:
            connection.execute(text("SELECT * FROM missing_table"))

    failed = [fields for event, fields in events if event == "database_query_failed"]
    assert failed
    assert failed[-1]["operation"] == "SELECT"
    assert "statement" not in failed[-1]
    assert "parameters" not in failed[-1]
