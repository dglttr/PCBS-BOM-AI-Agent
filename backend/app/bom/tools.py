import logging
from .service import start_bom_processing
from .router import UPLOAD_DIR
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_and_enrich_bom(job_id: str, assumptions: dict):
    """
    Processes a BOM file to parse its structure and enrich it with supplier data.
    
    Args:
        job_id (str): The unique ID of the BOM file processing job.
        assumptions (dict): A dictionary of user-provided assumptions, like industry and quantity.
    """
    logger.info(f"Tool 'process_and_enrich_bom' called for job_id: {job_id}")
    
    # Find the file in the upload directory using the job_id
    files = list(UPLOAD_DIR.glob(f"{job_id}_*"))
    if not files:
        error_msg = f"No file found for job_id: {job_id}"
        logger.error(error_msg)
        return {"error": error_msg}
    
    file_path = str(files[0])
    
    try:
        result = await start_bom_processing(file_path, assumptions)
        return result
    except Exception as e:
        logger.error(f"Error in 'process_and_enrich_bom' tool: {e}", exc_info=True)
        # Return a dictionary with the error to be handled by the agent
        return {"error": str(e)} 