from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile

from document_parser import extract_docx_text


app = FastAPI(
    title="DocPilot API",
    version="2.2.0",
)


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024


@app.get("/")
def root():
    return {
        "message": "DocPilot backend is running",
        "version": "2.2.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file must have a filename.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only DOCX files are supported right now.",
        )

    file_contents = await file.read()

    if not file_contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(file_contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="The uploaded file exceeds the 10 MB limit.",
        )

    document_id = str(uuid4())
    stored_filename = f"{document_id}{extension}"
    stored_path = UPLOAD_FOLDER / stored_filename

    try:
        stored_path.write_bytes(file_contents)

        document_data = extract_docx_text(stored_path)

    except Exception as error:
        if stored_path.exists():
            stored_path.unlink()

        raise HTTPException(
            status_code=500,
            detail="The document could not be processed.",
        ) from error

    return {
        "id": document_id,
        "filename": file.filename,
        "stored_filename": stored_filename,
        "file_type": extension.removeprefix("."),
        "size": len(file_contents),
        "status": "processed",
        "document": document_data,
    }