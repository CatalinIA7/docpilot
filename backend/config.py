from pathlib import Path
import os
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "null",
)
DEFAULT_TRUSTED_HOSTS = ("localhost", "127.0.0.1", "testserver")
DEVELOPMENT_JWT_SECRET = "docpilot-development-only-secret-change-me"


def _normalize_database_url(database_url: str) -> str:
    """Use the installed psycopg v3 driver for provider-style PostgreSQL URLs."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _parse_cors_origins(raw_origins: str | None) -> list[str]:
    """Parse comma-separated browser origins while preserving local defaults."""
    if raw_origins is None:
        return list(DEFAULT_CORS_ORIGINS)

    origins = []
    for raw_origin in raw_origins.split(","):
        origin = raw_origin.strip()
        if not origin:
            continue
        origins.append(origin if origin == "null" else origin.rstrip("/"))
    return origins


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_trusted_hosts(
    raw_hosts: str | None,
    *,
    render_hostname: str | None = None,
) -> list[str]:
    """Build an exact Host allowlist, including Render's assigned hostname."""
    hosts = [] if raw_hosts is not None else list(DEFAULT_TRUSTED_HOSTS)
    if raw_hosts:
        hosts.extend(host.strip().lower() for host in raw_hosts.split(",") if host.strip())
    if render_hostname:
        hosts.append(render_hostname.strip().lower())
    return list(dict.fromkeys(hosts))


def _is_exact_https_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def validate_runtime_configuration(
    *,
    environment: str,
    jwt_secret: str,
    cors_origins: list[str],
    trusted_hosts: list[str],
) -> None:
    """Fail closed when production would start with unsafe public settings."""
    if environment != "production":
        return

    errors = []
    if jwt_secret == DEVELOPMENT_JWT_SECRET or len(jwt_secret) < 32:
        errors.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
    if not cors_origins or any(
        origin in {"*", "null"} or not _is_exact_https_origin(origin)
        for origin in cors_origins
    ):
        errors.append("DOCPILOT_CORS_ORIGINS must contain exact HTTPS origins")
    if not trusted_hosts or "*" in trusted_hosts:
        errors.append("DOCPILOT_TRUSTED_HOSTS must contain exact hostnames")

    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'docpilot.db'}")
)
ENVIRONMENT = os.getenv("DOCPILOT_ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"
UPLOAD_DIR = Path(os.getenv("DOCPILOT_UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CORS_ORIGINS = _parse_cors_origins(os.getenv("DOCPILOT_CORS_ORIGINS"))
_raw_trusted_hosts = os.getenv("DOCPILOT_TRUSTED_HOSTS")
TRUSTED_HOSTS = _parse_trusted_hosts(
    "" if IS_PRODUCTION and _raw_trusted_hosts is None else _raw_trusted_hosts,
    render_hostname=os.getenv("RENDER_EXTERNAL_HOSTNAME"),
)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEVELOPMENT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("DOCPILOT_ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24))
)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_REQUEST_SIZE = int(os.getenv("DOCPILOT_MAX_REQUEST_SIZE", str(11 * 1024 * 1024)))
MAX_DOCX_UNCOMPRESSED_SIZE = int(
    os.getenv("DOCPILOT_MAX_DOCX_UNCOMPRESSED_SIZE", str(50 * 1024 * 1024))
)
MAX_DOCX_ENTRIES = int(os.getenv("DOCPILOT_MAX_DOCX_ENTRIES", "2000"))
ALLOWED_EXTENSIONS = {".docx", ".pdf"}
API_DOCS_ENABLED = not IS_PRODUCTION

# Lightweight per-process controls. Render currently runs one backend process.
RATE_LIMIT_ENABLED = _parse_bool(
    os.getenv("DOCPILOT_RATE_LIMIT_ENABLED"),
    default=False,
)
AUTH_RATE_LIMIT_PER_MINUTE = int(
    os.getenv("DOCPILOT_AUTH_RATE_LIMIT_PER_MINUTE", "20")
)
UPLOAD_RATE_LIMIT_PER_MINUTE = int(
    os.getenv("DOCPILOT_UPLOAD_RATE_LIMIT_PER_MINUTE", "10")
)
AI_RATE_LIMIT_PER_MINUTE = int(
    os.getenv("DOCPILOT_AI_RATE_LIMIT_PER_MINUTE", "30")
)

# Embedding configuration
EMBEDDING_MODEL = os.getenv("DOCPILOT_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BATCH_SIZE = int(os.getenv("DOCPILOT_EMBEDDING_BATCH_SIZE", "100"))

# Retrieval configuration
RETRIEVAL_TOP_K = int(os.getenv("DOCPILOT_RETRIEVAL_TOP_K", "5"))
RETRIEVAL_MIN_SCORE = float(os.getenv("DOCPILOT_RETRIEVAL_MIN_SCORE", "0.0"))

# Evaluation comparison configuration
EVAL_MAX_LATENCY_MS = float(os.getenv("DOCPILOT_EVAL_MAX_LATENCY_MS", "5000.0"))
EVAL_MIN_CONTEXT_REDUCTION = float(os.getenv("DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION", "50.0"))
EVAL_MIN_CITATION_PRESERVATION = float(os.getenv("DOCPILOT_EVAL_MIN_CITATION_PRESERVATION", "0.8"))
EVAL_PERSIST_RESULTS = os.getenv("DOCPILOT_EVAL_PERSIST_RESULTS", "true").lower() in ("true", "1", "yes")

# Conversation history configuration
CONVERSATION_MAX_MESSAGES = int(os.getenv("DOCPILOT_CONVERSATION_MAX_MESSAGES", "10"))

# Operational logging configuration
LOG_LEVEL = os.getenv("DOCPILOT_LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("DOCPILOT_LOG_FORMAT", "json")
SLOW_QUERY_MS = float(os.getenv("DOCPILOT_SLOW_QUERY_MS", "250.0"))
