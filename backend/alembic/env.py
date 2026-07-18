from logging.config import fileConfig
import logging
import time

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import DATABASE_URL
from database import Base
import models  # noqa: F401  Ensures every model is registered in Base.metadata.
from observability import configure_logging, log_event


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

logging.getLogger().handlers.clear()
configure_logging(force=True)
logger = logging.getLogger("docpilot.migrations")

# Runtime configuration is authoritative. Escaping percent signs keeps
# ConfigParser from treating percent-encoded URL characters as interpolation.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    started_at = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "migration_started",
        "Offline database migration started",
        mode="offline",
    )
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    try:
        with context.begin_transaction():
            context.run_migrations()
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "migration_failed",
            "Offline database migration failed",
            exc_info=True,
            mode="offline",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            error_type=type(exc).__name__,
        )
        raise
    log_event(
        logger,
        logging.INFO,
        "migration_completed",
        "Offline database migration completed",
        mode="offline",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
    )


def run_migrations_online() -> None:
    """Run migrations using the configured application database."""
    started_at = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "migration_started",
        "Database migration started",
        mode="online",
    )
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "migration_failed",
            "Database migration failed",
            exc_info=True,
            mode="online",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            error_type=type(exc).__name__,
        )
        raise
    log_event(
        logger,
        logging.INFO,
        "migration_completed",
        "Database migration completed",
        mode="online",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
