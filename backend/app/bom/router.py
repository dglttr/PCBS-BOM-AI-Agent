from fastapi import APIRouter, UploadFile, File, HTTPException
import logging
import os
import uuid
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/bom",
    tags=["bom"],
)

# Create a temporary directory for uploads if it doesn't exist
UPLOAD_DIR = Path("/tmp/bom_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload")
async def upload_bom(file: UploadFile = File(...)):
    """
    Receives a BOM file, saves it to a temporary directory with a unique ID,
    and returns a job ID for the client to use.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided.")

    job_id = str(uuid.uuid4())
    # Sanitize filename and create a unique path
    sanitized_filename = "".join(c for c in file.filename if c.isalnum() or c in ('.', '_')).rstrip()
    temp_file_path = UPLOAD_DIR / f"{job_id}_{sanitized_filename}"

    try:
        with open(temp_file_path, "wb") as buffer:
            buffer.write(await file.read())
        logger.info(f"Successfully uploaded {file.filename} and saved to {temp_file_path}")
        return {"job_id": job_id, "filename": file.filename, "file_path": str(temp_file_path)}
    except Exception as e:
        logger.error(f"Could not save uploaded file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not save file.")
