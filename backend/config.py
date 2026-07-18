from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "null",
)


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


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'docpilot.db'}")
)
UPLOAD_DIR = Path(os.getenv("DOCPILOT_UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CORS_ORIGINS = _parse_cors_origins(os.getenv("DOCPILOT_CORS_ORIGINS"))
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".docx", ".pdf"}

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
