import pandas as pd
import logging
import json
import asyncio
from openai import AsyncOpenAI
from openai.types.chat import ParsedChatCompletion
from typing import List, Dict, Any, Union
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

from .schemas import BomColumnMapping, ParsedBomItem, OctopartPart, OctopartSpec, OctopartSeller, OctopartOffer, OctopartPriceBreak, GeneratedQuestions
from . import octopart_client

client = AsyncOpenAI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_bom_head(file_path: str) -> pd.DataFrame:
    """Reads the first 10 rows of a BOM file."""
    logger.info(f"Reading BOM file head from: {file_path}")
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, nrows=10)
        else:
            engine = 'xlrd' if file_path.endswith('.xls') else 'openpyxl'
            df = pd.read_excel(file_path, nrows=10, engine=engine)
        return df.astype(object).where(pd.notnull(df), None)
    except Exception as e:
        logger.error(f"Error reading BOM head from {file_path}: {e}", exc_info=True)
        raise


def get_full_bom(file_path: str) -> pd.DataFrame:
    """Reads a full BOM file."""
    logger.info(f"Reading full BOM file from: {file_path}")
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            engine = 'xlrd' if file_path.endswith('.xls') else 'openpyxl'
            df = pd.read_excel(file_path, engine=engine)
        return df.astype(object).where(pd.notnull(df), None)
    except Exception as e:
        logger.error(f"Error reading full BOM from {file_path}: {e}", exc_info=True)
        raise


async def get_column_mapping(df: pd.DataFrame) -> BomColumnMapping:
    """Sends BOM head to LLM to get column mapping using the beta client."""
    logger.info("Requesting column mapping from LLM.")
    bom_head_markdown = df.to_markdown(index=False)
    
    prompt = f"""
    Identify the columns in the following BOM snippet for 'manufacturer_part_number', 'designators', 'quantity', and 'description'.
    If a field cannot be confidently identified, its value should be null.
    BOM Data:
    ```markdown
    {bom_head_markdown}
    ```
    """
    
    try:
        completion: ParsedChatCompletion[BomColumnMapping] = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert AI assistant for electronics manufacturing. You identify key columns in a BOM and return a validated Pydantic object."},
                {"role": "user", "content": prompt}
            ],
            response_format=BomColumnMapping,
        )
        
        if not (result := completion.choices[0].message.parsed):
            raise ValueError(f"LLM failed to map columns. Refusal: {completion.choices[0].message.refusal}")

        logger.info(f"LLM successfully mapped columns: {result.model_dump_json(indent=2)}")
        return result
    except Exception as e:
        logger.error(f"LLM column mapping failed: {e}", exc_info=True)
        raise


async def generate_setup_questions(df: pd.DataFrame) -> GeneratedQuestions:
    """Sends BOM head to LLM to generate clarifying questions for the user."""
    logger.info("Requesting setup questions from LLM.")
    bom_head_markdown = df.to_markdown(index=False)
    
    prompt = f"""
    You are an expert manufacturing analyst. I have just received this Bill of Materials (BOM).
    Based on the components you see here, what are the three most important questions I should ask the user to ensure I can find the best and most cost-effective alternative parts?
    Frame these as direct questions to the user. Also ask for the total order quantity.
    
    BOM Data:
    ```markdown
    {bom_head_markdown}
    ```
    """
    
    try:
        completion: ParsedChatCompletion[GeneratedQuestions] = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert AI assistant that generates clarifying questions about a BOM. Return them in a `GeneratedQuestions` Pydantic object."},
                {"role": "user", "content": prompt}
            ],
            response_format=GeneratedQuestions,
        )
        
        if not (result := completion.choices[0].message.parsed):
            raise ValueError(f"LLM failed to generate questions. Refusal: {completion.choices[0].message.refusal}")

        logger.info(f"LLM successfully generated questions: {result.model_dump_json(indent=2)}")
        return result
    except Exception as e:
        logger.error(f"LLM question generation failed: {e}", exc_info=True)
        raise


async def _parse_and_enrich_row(row_tuple, mapping: BomColumnMapping, sema: asyncio.Semaphore) -> Union[ParsedBomItem, Dict[str, Any]]:
    index, row_dict = row_tuple
    row_num = index + 1
    row_json_str = json.dumps(row_dict)

    item_prompt = f"""
    Parse the following single BOM row into the ParsedBomItem JSON format.
    The column mapping is: MPN='{mapping.manufacturer_part_number}', Designators='{mapping.designators}', Qty='{mapping.quantity}', Desc='{mapping.description}'.
    Full row data (JSON):
    {row_json_str}
    """
    
    try:
        logger.info(f"Sending row {row_num} to LLM for parsing.")
        completion: ParsedChatCompletion[ParsedBomItem] = await client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert AI that parses a single BOM row into a ParsedBomItem JSON object. If quantity is missing, count the designators."},
                {"role": "user", "content": item_prompt},
            ],
            response_format=ParsedBomItem
        )
        
        if not (parsed_item := completion.choices[0].message.parsed):
            raise ValueError(f"LLM failed to parse row. Refusal: {completion.choices[0].message.refusal}")

        if parsed_item.manufacturer_part_number:
            logger.info(f"Row {row_num}: Found MPN '{parsed_item.manufacturer_part_number}', querying Octopart.")
            octopart_data = await octopart_client.find_part_by_mpn(parsed_item.manufacturer_part_number, sema)
            
            if octopart_data:
                logger.info(f"Row {row_num}: Received data from Octopart, parsing into model.")
                try:
                    # Manually and safely build the OctopartPart object from the raw dictionary
                    specs = [
                        OctopartSpec(
                            name=spec.get('attribute', {}).get('name'),
                            value=spec.get('value'),
                            units=spec.get('units')
                        ) for spec in octopart_data.get('specs', [])
                    ]
                    
                    sellers = []
                    for seller_data in octopart_data.get('sellers', []):
                        offers = []
                        for offer_data in seller_data.get('offers', []):
                            prices = [OctopartPriceBreak(**p) for p in offer_data.get('prices', [])]
                            offers.append(OctopartOffer(inventory_level=offer_data.get('inventoryLevel'), prices=prices))
                        sellers.append(OctopartSeller(company_name=seller_data.get('company', {}).get('name'), offers=offers))

                    parsed_item.octopart_data = OctopartPart(
                        mpn=octopart_data.get('mpn'),
                        manufacturer_name=octopart_data.get('manufacturer', {}).get('name'),
                        short_description=octopart_data.get('shortDescription'),
                        octopart_url=octopart_data.get('octopartUrl'),
                        specs=specs,
                        sellers=sellers
                    )
                    logger.info(f"Successfully enriched row {row_num} with Octopart data.")
                except Exception as e:
                    logger.error(f"Failed to parse Octopart data for row {row_num}: {e}", exc_info=True)
            else:
                logger.warning(f"Row {row_num}: No data received from Octopart for MPN '{parsed_item.manufacturer_part_number}'.")

        logger.info(f"Successfully processed row {row_num}")
        return parsed_item

    except Exception as e:
        error_info = {"error": f"Failed to process row {row_num}", "details": str(e), "row_data": row_dict}
        logger.error(f"Row {row_num} processing failed: {e}", exc_info=True)
        return error_info


async def parse_bom_items(df: pd.DataFrame, mapping: BomColumnMapping) -> List[Union[ParsedBomItem, Dict[str, Any]]]:
    """Concurrently parses and enriches all BOM rows."""
    bom_rows = df.to_dict(orient='records')
    sema = asyncio.Semaphore(10)  # Limit concurrent requests to Octopart
    
    tasks = [_parse_and_enrich_row(row_tuple, mapping, sema) for row_tuple in enumerate(bom_rows)]
    
    results = await asyncio.gather(*tasks)
    return results


async def start_bom_processing(file_path: str, assumptions: Dict[str, Any]) -> Dict[str, Any]:
    """Orchestrates the two-stage BOM processing, now including user assumptions."""
    logger.info(f"Starting BOM processing with assumptions: {assumptions}")
    # Stage 1: Analyze structure
    bom_head_df = get_bom_head(file_path)
    column_mapping = await get_column_mapping(bom_head_df)

    full_bom_df = get_full_bom(file_path)
    parsed_items_result = await parse_bom_items(full_bom_df, column_mapping)

    # Check if there were any processing errors to report to the frontend
    has_enrichment_error = any(
        isinstance(item, dict) and 'error' in item for item in parsed_items_result
    )
    
    # Check if at least one item was successfully enriched
    was_any_item_enriched = any(
        isinstance(item, ParsedBomItem) and item.octopart_data is not None for item in parsed_items_result
    )

    return {
        "column_mapping": column_mapping.model_dump(),
        "parsed_items": [item.model_dump() if isinstance(item, ParsedBomItem) else item for item in parsed_items_result],
        "processing_error": "Failed to enrich some parts. API limits may have been reached." if has_enrichment_error and not was_any_item_enriched else None
    }
