import pandas as pd
import logging
import json
import asyncio
from typing import List, Dict, Any, Union, Optional
from pathlib import Path
from openai.types.chat import ParsedChatCompletion

from ..llm import client # Import client from the new central location
from .schemas import BomColumnMapping, ParsedBomItem, OctopartPart, ValidationResult
from . import octopart_client
from .router import UPLOAD_DIR


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _simplify_part_for_prompt(part: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts only the most essential details for an LLM prompt."""
    if not part:
        return {}
        
    octopart_data = part.get("octopart_data", {})
    if not octopart_data:
         # Fallback for parts without full octopart data
        return {
            "manufacturer_part_number": part.get("manufacturer_part_number"),
            "description": part.get("description", "N/A"),
            "specs": part.get("parameters", {}),
            "sellers": []
        }

    simple_part = {
        "manufacturer_part_number": octopart_data.get("mpn"),
        "description": octopart_data.get("short_description"),
        "specs": {},
        "sellers": [seller.get("company_name") for seller in octopart_data.get("sellers", []) if seller.get("company_name")]
    }
    
    # Extract ALL specifications, not just a predefined list
    for spec in octopart_data.get("specs", []):
        attr_name = spec.get("name")
        if attr_name:
            simple_part["specs"][attr_name] = f"{spec.get('value')} {spec.get('units', '')}".strip()

    return simple_part

def get_bom_head(file_path: str) -> pd.DataFrame:
    """Reads the first 10 rows of a BOM file."""
    logger.info(f"Reading BOM file head from: {file_path}")
    
    file_ext = Path(file_path).suffix.lower()
    if file_ext not in ['.csv', '.xls', '.xlsx']:
        raise ValueError(f"Unsupported file type: '{file_ext}'. Please upload a valid CSV or Excel file.")

    try:
        if file_ext == '.csv':
            df = pd.read_csv(file_path, nrows=10)
        else:
            engine = 'xlrd' if file_ext == '.xls' else 'openpyxl'
            df = pd.read_excel(file_path, nrows=10, engine=engine)
        return df.astype(object).where(pd.notnull(df), None)
    except Exception as e:
        logger.error(f"Error reading BOM head from {file_path}: {e}", exc_info=True)
        raise

def get_full_bom(file_path: str) -> pd.DataFrame:
    """Reads a full BOM file."""
    logger.info(f"Reading full BOM file from: {file_path}")

    file_ext = Path(file_path).suffix.lower()
    if file_ext not in ['.csv', '.xls', '.xlsx']:
        raise ValueError(f"Unsupported file type: '{file_ext}'. Please upload a valid CSV or Excel file.")
        
    try:
        if file_ext == '.csv':
            df = pd.read_csv(file_path)
        else:
            engine = 'xlrd' if file_ext == '.xls' else 'openpyxl'
            df = pd.read_excel(file_path, engine=engine)
        return df.astype(object).where(pd.notnull(df), None)
    except Exception as e:
        logger.error(f"Error reading full BOM from {file_path}: {e}", exc_info=True)
        raise

async def get_column_mapping(df: pd.DataFrame) -> BomColumnMapping:
    """Sends BOM head to LLM to get column mapping."""
    logger.info("Requesting column mapping from LLM.")
    bom_head_markdown = df.to_markdown(index=False)
    
    prompt = f"""
    You are an expert manufacturing analyst. Your task is to identify the columns in a Bill of Materials (BOM) snippet.
    Return a JSON object that maps to the `BomColumnMapping` schema. The `description` field is the most important one to map.
    
    Schema: {json.dumps(BomColumnMapping.model_json_schema(), indent=2)}
    
    BOM Data:
    ```markdown
    {bom_head_markdown}
    ```
    """
    
    try:
        response = await client.chat.completions.create(
            model="gemini-2.5-flash-preview-05-20",
            # model="o4-mini-2025-04-16",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant that returns JSON data according to a provided schema."},
                {"role": "user", "content": prompt}
            ]
        )
        response_json = json.loads(response.choices[0].message.content or "{}")
        return BomColumnMapping.model_validate(response_json)
    except Exception as e:
        logger.error(f"LLM column mapping failed: {e}", exc_info=True)
        raise

async def _parse_and_enrich_row(row_tuple, mapping: BomColumnMapping, sema: asyncio.Semaphore) -> Union[ParsedBomItem, Dict[str, Any]]:
    index, row_dict = row_tuple
    row_num = index + 1
    row_json_str = json.dumps(row_dict)

    item_prompt = f"""
    Parse the following single BOM row into the ParsedBomItem JSON format.
    The column mapping is: MPN='{mapping.manufacturer_part_number}', Designators='{mapping.designators}', Qty='{mapping.quantity}', Desc='{mapping.description}'.
    Your output MUST conform to this JSON schema: {json.dumps(ParsedBomItem.model_json_schema(), indent=2)}
    
    Full row data (JSON):
    {row_json_str}
    """
    
    try:
        logger.info(f"Sending row {row_num} to LLM for parsing.")
        response = await client.chat.completions.create(
            model="gemini-2.5-flash-preview-05-20",
            # model="o4-mini-2025-04-16",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert AI that parses a single BOM row into a JSON object conforming to the provided schema. If quantity is missing, count the designators."},
                {"role": "user", "content": item_prompt},
            ],
        )
        response_json = json.loads(response.choices[0].message.content or "{}")
        parsed_item = ParsedBomItem.model_validate(response_json)

        if parsed_item.manufacturer_part_number:
            octopart_data = await octopart_client.find_part_by_mpn(parsed_item.manufacturer_part_number, sema)
            if octopart_data:
                parsed_item.octopart_data = OctopartPart(**octopart_data)
        
        return parsed_item

    except Exception as e:
        error_info = {"error": f"Failed to process row {row_num}", "details": str(e), "row_data": row_dict}
        logger.error(f"Row {row_num} processing failed: {e}", exc_info=True)
        return error_info

async def get_bom_data_with_alternatives(job_id: str, cache: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    This is the main data processing function called by the agent's tool.
    It now saves the full data to a cache and returns a summary.
    """
    files = list(UPLOAD_DIR.glob(f"{job_id}_*"))
    if not files:
        raise FileNotFoundError(f"No file found for job_id: {job_id}")
    file_path = str(files[0])

    bom_head_df = get_bom_head(file_path)
    column_mapping = await get_column_mapping(bom_head_df)
    
    full_bom_df = get_full_bom(file_path)
    
    bom_rows = full_bom_df.to_dict(orient='records')
    sema = asyncio.Semaphore(10)
    
    tasks = [_parse_and_enrich_row(row_tuple, column_mapping, sema) for row_tuple in enumerate(bom_rows)]
    
    results = await asyncio.gather(*tasks)
    
    processed_data = [item.model_dump(exclude_none=True) if isinstance(item, ParsedBomItem) else item for item in results]
    
    # Store the full data in the cache
    cache[job_id] = processed_data
    logger.info(f"Full BOM data for job_id '{job_id}' stored in cache.")

    # Return a lightweight summary to the LLM
    summary = []
    for item in processed_data:
        # Basic data validation: Ensure there is an MPN and it's not just a manufacturer name
        mpn = item.get("manufacturer_part_number")
        if not mpn or mpn.lower() in ["texas instruments", "panasonic", "vishay", "bourns", "cliff", "rubycon"]:
             continue
        if "error" in item:
            summary.append({"error": item["error"], "row_data": item.get("row_data")})
        else:
            summary.append({
                "manufacturer_part_number": item.get("manufacturer_part_number"),
                "description": item.get("octopart_data", {}).get("short_description"),
                "has_alternatives": "Yes" if item.get("octopart_data", {}).get("similar_parts") else "No",
                "alternatives": [alt["mpn"] for alt in item.get("octopart_data", {}).get("similar_parts", [])]
            })
    return summary

async def evaluate_alternative(
    job_id: str,
    original_mpn: str,
    alternative_mpn: str,
    assumptions: Dict[str, Any],
    cache: Dict[str, Any]
) -> Dict[str, Any]:
    """
    TOOL: Compares an original part to a potential alternative using an LLM, based on user-provided assumptions.
    It fetches part data from a server-side cache and returns the validation result along with the simplified data used.
    """
    # Log the start of the evaluation in a structured, single-line format
    # to prevent interleaving from concurrent calls.
    logger.info(json.dumps({
        "event": "evaluating_alternative",
        "job_id": job_id,
        "original_mpn": original_mpn,
        "alternative_mpn": alternative_mpn,
    }))

    # 1. Retrieve the full data from the cache
    full_bom_data = cache.get(job_id)
    if not full_bom_data:
        return {
            "validation_result": ValidationResult(is_valid=False, reasoning=f"Error: No data found in cache for job_id '{job_id}'. Cannot perform evaluation.").model_dump(),
            "original_part": {},
            "alternative_part": {}
        }

    # 2. Find the original and alternative parts in the cached data
    original_part = next((p for p in full_bom_data if p.get("manufacturer_part_number") == original_mpn), None)
    
    if not original_part:
        return {
            "validation_result": ValidationResult(is_valid=False, reasoning=f"Error: Original part with MPN '{original_mpn}' not found in cached data.").model_dump(),
            "original_part": {},
            "alternative_part": {}
        }
        
    alternatives = original_part.get("octopart_data", {}).get("similar_parts", [])
    alternative_part_data = next((p for p in alternatives if p.get("mpn") == alternative_mpn), None)

    if not alternative_part_data:
        return {
            "validation_result": ValidationResult(is_valid=False, reasoning=f"Error: Alternative part with MPN '{alternative_mpn}' not found for original part '{original_mpn}'.").model_dump(),
            "original_part": _simplify_part_for_prompt(original_part),
            "alternative_part": {}
        }

    # Simplify the part data for a much smaller and more focused prompt
    simple_original = _simplify_part_for_prompt(original_part)
    # The alternative part data is just a dict, so we wrap it to match the structure of the original part
    simple_alternative = _simplify_part_for_prompt({"octopart_data": alternative_part_data})

    # Log the data being sent to the LLM for evaluation
    logger.info(json.dumps({
        "event": "evaluate_alternative_prompt_data",
        "job_id": job_id,
        "original_mpn": original_mpn,
        "alternative_mpn": alternative_mpn,
        "assumptions": assumptions,
        "simple_original": simple_original,
        "simple_alternative": simple_alternative
    }, indent=2))

    prompt = f"""
# SYSTEM INSTRUCTION
You are an expert electronics engineer. Your task is to determine if an alternative component is a valid substitute for an original component based on a set of project assumptions and a detailed knowledge base.

# Knowledge Base

## 1. Industry Requirements
- **Automotive**: Must be RoHS compliant, lead-free, and operate from -55°C to +85°C.

## 2. Sourcing & Supplier Rules
- **Preferred Suppliers**: Element14
- **Supplier Reliability**:
  - Very High: Element14
  - High: Bettlink, Chip One Stop, Rutronik
  - Medium: Farnell, Core Staff
  - Low: Future Electronics
- **Country Sourcing**:
  - **Avoid**: Russia, Ukraine, Yemen, Israel, Iran, Syria, Democratic Republic of the Congo, Sudan, Somalia, South Sudan, Ethiopia, Myanmar, Mexico, Columbia, Haiti
  - **Prefer**: European Union

# Your Task
Based on all the information below, determine if the alternative part is a valid substitute for the original. A part is considered a valid substitute **only if it meets all critical technical requirements.**

Your evaluation must be strict. If any critical data is missing from the alternative part's specifications, you must declare it invalid.

## Evaluation Criteria:
1.  **Technical Equivalence (Strict)**:
    - The physical package/footprint MUST be compatible.
    - For the '{assumptions.get('industry', 'default')}' industry, the alternative MUST meet all specified requirements (e.g., temperature range, RoHS). If compliance is not explicitly stated, it is not met.
    - All primary electrical values (Resistance, Capacitance, Voltage, etc.) must be equivalent or within an acceptable tolerance.
    - **Voltage Rating**: The alternative's voltage rating must be **equal to or greater than** the original. A lower voltage rating is an immediate invalidation.

2.  **Sourcing Information (For context in reasoning)**:
    - Note the reliability of the suppliers for the alternative part.
    - Note if the suppliers are in preferred or avoided countries.

## Reasoning Format:
- If the part is valid, the reasoning should be a brief, factual statement of compatibility (e.g., "Valid substitute, key parameters match.").
- If the part is invalid, the reasoning **must** state the single most critical reason for failure (e.g., "Invalid: Lower voltage rating (16V vs 25V).", "Invalid: Incompatible package.", "Invalid: Operating temperature does not meet Automotive standard.", "Invalid: RoHS compliance not specified.").

**Note**: This validation step does **not** consider price. It is purely for technical and compliance verification.

---
# Data

**Project Assumptions**: {json.dumps(assumptions, indent=2)}

**Original Part**: {json.dumps(simple_original, indent=2)}

**Alternative Part**: {json.dumps(simple_alternative, indent=2)}

---
# Output Format
Provide your answer as a structured JSON object. Your response MUST conform to the `ValidationResult` schema.
"""
    
    try:
        completion: ParsedChatCompletion[ValidationResult] = await client.beta.chat.completions.parse(
            model="gemini-2.5-flash-preview-05-20",
            messages=[
                {"role": "system", "content": "You are an expert AI assistant that validates electronic components and returns a `ValidationResult` Pydantic object."},
                {"role": "user", "content": prompt}
            ],
            response_format=ValidationResult,
        )
        
        if not (result := completion.choices[0].message.parsed):
            raise ValueError(f"LLM failed to validate alternative. Refusal: {completion.choices[0].message.refusal}")
        
        return {
            "validation_result": result.model_dump(),
            "original_part": simple_original,
            "alternative_part": simple_alternative
        }
        
    except Exception as e:
        logger.error(f"Error in 'evaluate_alternative' tool for {original_mpn} vs {alternative_mpn}: {e}", exc_info=True)
        return {
            "validation_result": ValidationResult(is_valid=False, reasoning=f"An internal error occurred during validation: {e}").model_dump(),
            "original_part": simple_original,
            "alternative_part": simple_alternative
        } 