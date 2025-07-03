from fastapi import APIRouter, UploadFile, File, HTTPException
import logging
import uuid
import csv
from .logic import production_plans_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/production",
    tags=["production"],
)

# Use the shared cache from logic.py
production_plans = production_plans_cache


@router.post("/upload")
async def upload_production_plan(
    file: UploadFile = File(...)
):
    """
    Upload a production plan CSV file and get a job ID for processing.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided or filename is missing")
        
    if not file.filename.endswith(('.csv')):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    job_id = str(uuid.uuid4())
    
    try:
        # Read the CSV file content
        content = await file.read()
        
        # Decode the content and parse as CSV
        decoded_content = content.decode('utf-8')
        reader = csv.DictReader(decoded_content.splitlines())
        data = list(reader)
        
        # Store the parsed data in the shared cache
        production_plans[job_id] = data
        
        logger.info(f"Production plan uploaded successfully with job_id: {job_id}")
        return {"job_id": job_id, "message": "Production plan uploaded successfully"}
    except Exception as e:
        logger.error(f"Error processing production plan: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.get("/status/{job_id}")
async def get_production_plan_status(job_id: str):
    """
    Check if a production plan has been uploaded and is ready for processing.
    """
    if job_id not in production_plans:
        raise HTTPException(status_code=404, detail="Production plan not found")
    
    return {"status": "ready", "job_id": job_id}
