from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'docpilot.db'}")
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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

# Observability configuration
OBSERVABILITY_ENABLED = os.getenv("DOCPILOT_OBSERVABILITY_ENABLED", "true").lower() in ("true", "1", "yes")
OBSERVABILITY_PERSIST = os.getenv("DOCPILOT_OBSERVABILITY_PERSIST", "true").lower() in ("true", "1", "yes")
OBSERVABILITY_LOG_LEVEL = os.getenv("DOCPILOT_OBSERVABILITY_LOG_LEVEL", "INFO")
