from fastapi import FastAPI

app = FastAPI(
    title="DocPilot API",
    version="2.0.0",
)


@app.get("/")
def root():
    return {
        "message": "DocPilot backend is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }