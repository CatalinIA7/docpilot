from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from routers.auth_routes import router as auth_router
from routers.chat import router as chat_router
from routers.documents import router as documents_router
from routers.evaluation import router as evaluation_router
from routers.conversations import router as conversations_router
from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AI_RATE_LIMIT_PER_MINUTE,
    API_DOCS_ENABLED,
    AUTH_RATE_LIMIT_PER_MINUTE,
    CORS_ORIGINS,
    ENVIRONMENT,
    IS_PRODUCTION,
    JWT_SECRET_KEY,
    MAX_REQUEST_SIZE,
    RATE_LIMIT_ENABLED,
    TRUSTED_HOSTS,
    UPLOAD_RATE_LIMIT_PER_MINUTE,
    validate_runtime_configuration,
)
from observability import configure_logging, log_event, observe_request
from security_middleware import (
    ContentLengthLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)


configure_logging()
logger = logging.getLogger("docpilot.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_configuration(
        environment=ENVIRONMENT,
        jwt_secret=JWT_SECRET_KEY,
        cors_origins=CORS_ORIGINS,
        trusted_hosts=TRUSTED_HOSTS,
    )
    log_event(
        logger,
        logging.INFO,
        "application_startup",
        "DocPilot backend started",
        version="1.0.0",
        environment=ENVIRONMENT,
        api_docs_enabled=API_DOCS_ENABLED,
        rate_limit_enabled=RATE_LIMIT_ENABLED,
        access_token_expire_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    try:
        yield
    finally:
        log_event(
            logger,
            logging.INFO,
            "application_shutdown",
            "DocPilot backend stopped",
            version="1.0.0",
        )


app = FastAPI(
    title="DocPilot API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if API_DOCS_ENABLED else None,
    redoc_url="/redoc" if API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if API_DOCS_ENABLED else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["DELETE", "GET", "OPTIONS", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
app.add_middleware(
    RateLimitMiddleware,
    enabled=RATE_LIMIT_ENABLED,
    auth_limit=AUTH_RATE_LIMIT_PER_MINUTE,
    upload_limit=UPLOAD_RATE_LIMIT_PER_MINUTE,
    ai_limit=AI_RATE_LIMIT_PER_MINUTE,
)
app.add_middleware(ContentLengthLimitMiddleware, max_bytes=MAX_REQUEST_SIZE)
app.add_middleware(SecurityHeadersMiddleware, production=IS_PRODUCTION)
app.middleware("http")(observe_request)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(evaluation_router)
app.include_router(conversations_router)


@app.get("/")
def root():
    response = {"name": "DocPilot API"}
    if API_DOCS_ENABLED:
        response["docs"] = "/docs"
    return response


@app.get("/health")
def health():
    return {"status": "healthy"}
