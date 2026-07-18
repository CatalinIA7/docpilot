import logging
import time

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from config import DATABASE_URL, SLOW_QUERY_MS
from observability import log_event


logger = logging.getLogger("docpilot.database")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _query_operation(statement: str) -> str:
    stripped = statement.lstrip()
    return stripped.split(None, 1)[0].upper() if stripped else "UNKNOWN"


def install_database_observability(target_engine: Engine) -> None:
    """Attach safe timing and failure events without logging SQL or parameters."""
    if getattr(target_engine, "_docpilot_observability_installed", False):
        return
    target_engine._docpilot_observability_installed = True  # type: ignore[attr-defined]

    @event.listens_for(target_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._docpilot_started_at = time.perf_counter()

    @event.listens_for(target_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started_at = getattr(context, "_docpilot_started_at", time.perf_counter())
        duration_ms = (time.perf_counter() - started_at) * 1000
        fields = {
            "operation": _query_operation(statement),
            "duration_ms": round(duration_ms, 3),
            "executemany": bool(executemany),
        }
        log_event(
            logger,
            logging.DEBUG,
            "database_query_completed",
            "Database query completed",
            **fields,
        )
        if duration_ms >= SLOW_QUERY_MS:
            log_event(
                logger,
                logging.WARNING,
                "database_slow_query",
                "Database query exceeded the slow-query threshold",
                threshold_ms=SLOW_QUERY_MS,
                **fields,
            )

    @event.listens_for(target_engine, "handle_error")
    def handle_error(exception_context):
        context = exception_context.execution_context
        started_at = getattr(context, "_docpilot_started_at", time.perf_counter())
        duration_ms = (time.perf_counter() - started_at) * 1000
        statement = exception_context.statement or ""
        log_event(
            logger,
            logging.ERROR,
            "database_query_failed",
            "Database query failed",
            operation=_query_operation(statement),
            duration_ms=round(duration_ms, 3),
            error_type=type(exception_context.original_exception).__name__,
        )


install_database_observability(engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as exc:
        db.rollback()
        log_event(
            logger,
            logging.ERROR,
            "database_session_failed",
            "Database session failed",
            error_type=type(exc).__name__,
        )
        raise
    finally:
        db.close()
