from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from routers.auth_routes import router as auth_router
from routers.chat import router as chat_router
from routers.documents import router as documents_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="DocPilot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/")
def root():
    return {"name": "DocPilot API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
