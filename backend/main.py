from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.auth_routes import router as auth_router
from routers.chat import router as chat_router
from routers.documents import router as documents_router
from routers.evaluation import router as evaluation_router
from routers.conversations import router as conversations_router
from config import CORS_ORIGINS
from observability import configure_logging, log_event, observe_request


configure_logging()
logger = logging.getLogger("docpilot.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(
        logger,
        logging.INFO,
        "application_startup",
        "DocPilot backend started",
        version="1.0.0",
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


app = FastAPI(title="DocPilot API", version="1.0.0", lifespan=lifespan)
app.middleware("http")(observe_request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(evaluation_router)
app.include_router(conversations_router)


@app.get("/")
def root():
    return {"name": "DocPilot API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
