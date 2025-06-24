from fastapi import APIRouter, UploadFile, File, HTTPException
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel

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

class ProcessBomRequest(BaseModel):
    # ... existing code ...
    pass

@router.post("/upload")
async def upload_bom(files: List[UploadFile] = File(...)):
    """
    Receives a list of BOM files, saves them to a temporary directory with unique IDs,
    and returns a list of job details for the client.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    upload_results = []
    for file in files:
        if not file.filename:
            # Skip this file but log a warning
            logger.warning("Received a file with no name. Skipping.")
            continue

        job_id = str(uuid.uuid4())
        sanitized_filename = "".join(c for c in file.filename if c.isalnum() or c in ('.', '_')).rstrip()
        temp_file_path = UPLOAD_DIR / f"{job_id}_{sanitized_filename}"

        try:
            with open(temp_file_path, "wb") as buffer:
                buffer.write(await file.read())
            logger.info(f"Successfully uploaded {file.filename} and saved to {temp_file_path}")
            upload_results.append({"job_id": job_id, "filename": file.filename, "file_path": str(temp_file_path)})
        except Exception as e:
            logger.error(f"Could not save uploaded file {file.filename}: {e}", exc_info=True)
            # You might want to decide if one failure should fail the whole batch
    
    if not upload_results:
        raise HTTPException(status_code=400, detail="No valid files were uploaded.")

    return upload_results

@router.post("/process/{job_id}")
async def process_bom(job_id: str, request: ProcessBomRequest):
    # ... existing code ...
    pass
