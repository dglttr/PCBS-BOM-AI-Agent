from openai.types.chat.chat_completion import ChatCompletion
import pandas as pd
import logging
import json
import asyncio
from typing import List, Dict, Any, Union
from pathlib import Path

from ..llm import client
from .schemas import BomColumnMapping, ParsedBomItem
from . import octopart_client
from .router import UPLOAD_DIR


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_parts_list(raw_json):
    """
    Process a list of part data dictionaries into a single DataFrame.
    Args:
        result_json_list (list): List of part data dictionaries
    Returns:
        pd.DataFrame: Complete DataFrame with all parts and their best seller info
    """
    result_json_list = raw_json["octopart_data"]["similarParts"]
    all_parts_data = []
    for part_data in result_json_list:
        # Extract basic part information
        part_info = {
            "name": part_data.get("name", ""),
            "mpn": part_data.get("mpn", ""),
            "manufacturer": part_data.get("manufacturer", {}).get("name", ""),
            "short_description": part_data.get("shortDescription", ""),
            "category": part_data.get("category", {}).get("name", ""),
        }
        # Find best seller (most economic option)
        best_seller_info = {
            "best_seller_company": "No sellers available",
            "best_seller_country": "",
            "best_unit_price": "",
            "best_price_currency": "",
            "best_price_min_qty": "",
        }
        lowest_price = float("inf")
        for seller in part_data.get("sellers", []):
            company_name = seller.get("company", {}).get("name", "Unknown")
            country = seller.get("country", "Unknown")
            for offer in seller.get("offers", []):
                prices = offer.get("prices", [])
                if prices:
                    for price_break in prices:
                        unit_price = price_break.get(
                            "convertedPrice", price_break.get("price", float("inf"))
                        )
                        quantity = price_break.get("quantity", 1)
                        currency = price_break.get(
                            "convertedCurrency", price_break.get("currency", "USD")
                        )
                        if unit_price < lowest_price:
                            lowest_price = unit_price
                            best_seller_info = {
                                "best_seller_company": company_name,
                                "best_seller_country": country,
                                "best_unit_price": f"{unit_price:.4f}",
                                "best_price_currency": currency,
                                "best_price_min_qty": quantity,
                            }
        # Combine part info with best seller info
        combined_info = {**part_info, **best_seller_info}
        # Add specs as columns
        for spec in part_data.get("specs", []):
            column_name = (
                spec["attribute"]["name"]
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .lower()
            )
            value_with_units = f"{spec['value']} {spec['units']}".strip()
            combined_info[column_name] = value_with_units
        all_parts_data.append(combined_info)
    final_df = pd.DataFrame(all_parts_data)
    nan_percentage = final_df.isnull().sum() / len(final_df)
    # Keep columns where NaN percentage < 0.5 (50%)
    df_cleaned = final_df.loc[:, nan_percentage < 0.5]

    return df_cleaned.to_markdown()


def get_bom_head(file_path: str) -> pd.DataFrame:
    """Reads the first 10 rows of a BOM file."""
    logger.info(f"Reading BOM file head from: {file_path}")

    file_ext = Path(file_path).suffix.lower()
    if file_ext not in [".csv", ".xls", ".xlsx"]:
        raise ValueError(
            f"Unsupported file type: '{file_ext}'. Please upload a valid CSV or Excel file."
        )

    try:
        if file_ext == ".csv":
            df = pd.read_csv(file_path, nrows=10)
        else:
            engine = "xlrd" if file_ext == ".xls" else "openpyxl"
            df = pd.read_excel(file_path, nrows=10, engine=engine)
        return df.astype(object).where(pd.notnull(df), None)
    except Exception as e:
        logger.error(f"Error reading BOM head from {file_path}: {e}", exc_info=True)
        raise


def get_full_bom(file_path: str) -> pd.DataFrame:
    """Reads a full BOM file."""
    logger.info(f"Reading full BOM file from: {file_path}")

    file_ext = Path(file_path).suffix.lower()
    if file_ext not in [".csv", ".xls", ".xlsx"]:
        raise ValueError(
            f"Unsupported file type: '{file_ext}'. Please upload a valid CSV or Excel file."
        )

    try:
        if file_ext == ".csv":
            df = pd.read_csv(file_path)
        else:
            engine = "xlrd" if file_ext == ".xls" else "openpyxl"
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
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant that returns JSON data according to a provided schema.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        response_json = json.loads(response.choices[0].message.content or "{}")
        return BomColumnMapping.model_validate(response_json)
    except Exception as e:
        logger.error(f"LLM column mapping failed: {e}", exc_info=True)
        raise


async def _parse_and_enrich_row(
    row_tuple, mapping: BomColumnMapping, sema: asyncio.Semaphore
) -> Union[ParsedBomItem, Dict[str, Any]]:
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
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert AI that parses a single BOM row into a JSON object conforming to the provided schema. If quantity is missing, count the designators.",
                },
                {"role": "user", "content": item_prompt},
            ],
        )
        response_json = json.loads(response.choices[0].message.content or "{}")
        parsed_item = ParsedBomItem.model_validate(response_json)

        if parsed_item.manufacturer_part_number:
            octopart_data = await octopart_client.find_alternative_part_by_mpn(
                parsed_item.manufacturer_part_number, sema
            )
            if octopart_data:
                parsed_item.octopart_data = octopart_data

        return parsed_item

    except Exception as e:
        error_info = {
            "error": f"Failed to process row {row_num}",
            "details": str(e),
            "row_data": row_dict,
        }
        logger.error(f"Row {row_num} processing failed: {e}", exc_info=True)
        return error_info


async def get_bom_data_with_alternatives(
    job_id: str, cache: Dict[str, Any]
) -> List[Dict[str, Any]]:
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

    bom_rows = full_bom_df.to_dict(orient="records")
    sema = asyncio.Semaphore(10)

    tasks = [
        _parse_and_enrich_row(row_tuple, column_mapping, sema)
        for row_tuple in enumerate(bom_rows)
    ]

    results = await asyncio.gather(*tasks)

    processed_data = [
        item.model_dump(exclude_none=True) if isinstance(item, ParsedBomItem) else item
        for item in results
    ]

    # Store the full data in the cache
    cache[job_id] = processed_data
    logger.info(f"Full BOM data for job_id '{job_id}' stored in cache.")

    return processed_data


async def evaluate_alternative(
    part: Dict[str, Any],
    assumptions: Dict[str, Any],
) -> str:
    """
    TOOL: Compares an original part to a potential alternative using an LLM, based on user-provided assumptions.
    It fetches part data from a server-side cache and returns the validation result along with the simplified data used.
    """
    # Simplify the part data for a much smaller and more focused prompt
    simple_part = process_parts_list(part)

    prompt = f"""
# Background information
You are an electronics expert tasked with analyzing a table containing information about electronic components.
The table contains a list of components, each with attributes such as type, specifications, and availability.
You also get a list of cheapest offers for each component (including unit price, minimum order quantity and total cost for the target quantity), as well as the number of sellers retailing the component.
All components are similar to each other, with only minor differences in specifications, price and several other attributes.
This is the table:
<Table>
{simple_part}
</Table>

**Project Assumptions**: {json.dumps(assumptions, indent=2)}

# Knowledge base

## Background knowledge on suppliers and countries:
The following suppliers are preferred: 
- Element14

Known information about supplier reliability: 
- Element14: very highly reliable
- Bettlink: Highly reliable
- Future Electronics: low reliability
- Farnell: medium reliability
- Chip One Stop: high reliability
- Core Staff: medium reliability
- Rutronik: high reliability

The following countries should be avoided: 
- Russia
- Ukraine
- Yemen
- Israel
- Iran
- Syria
- Democratic Republic of the Congo
- Sudan
- Somalia
- South Sudan
- Ethiopia
- Myanmar
- Mexico
- Columbia
- Haiti

The following countries/ economic regions should be preferred 
- European Union

# Your task
Your job is to choose the component to be used for a specific project.
In general, you should optimize for minimum price for the target quantity of the component.

Next to the price, you should consider the following attributes:
- All electronic characteristics should match the project requirements.
- The characteristics should match the project requirements, especially the requirements from the mentioned industry.
- Leverage the information about the industry standards, suppliers and countries in the knowledge base to select a component meeting industry standards if possible, and that has a reliable supplier.

Note that if a certification is not mentioned in the description, it does not mean that the component does not have it. Do not assume that a component does not have a certification if it is not mentioned in the description.

# Personality
Clearly explain your reasoning for the choice you make.
Next to your selection, return all other suitable alternatives and rank them from best to worst.
If you cannot find a suitable component, please explain why and what data you are missing.

# Output format
Start by stating the number of potential alternative components you found. Internal note: this is the number of components (similarParts) in the JSON file.

Then, state the name of the component you selected, along with the manufacturer and price.
Next, provide a very brief explanation of why you chose this component, including any relevant specifications or certifications. Max. 3 sentences.

Then, please output a table with chosen components as well as the other suitable alternatives. Make sure it is a valid Markdown table.
Add an empty row between the chosen component and the alternatives.
It should have the following columns:
- Rank: Checkmark (✅) for the chosen component, numbering for the alternatives (1 for the best alternative, 2 for the second best, etc.)
- Component Name
- Manufacturer
- Best price (both unit price and total price for the target quantity) - behind the price, there should be a traffic light emoji (green 🟢, yellow 🟡, red 🔴) indicating how good the price is relative to the other alternatives
- Name of seller and country
- Expected supplier reliability (based on the information in the knowledge base, the seller country and the number of sellers) - this should be a traffic light emoji (green 🟢, yellow 🟡, red 🔴)
- One column for each of the relevant attributes, such as capacitance, voltage rating, etc. (you can choose which attributes to include based on the JSON file).

Below the table, provide a brief explanation of why you ranked the alternatives as you did, focusing on the most important attributes and their relevance to the project requirements.

Then, list the not suitable alternatives, if any, and explain briefly why they were not selected.

At the bottom in a new section, list the project requirements you identified in a bulleted list."""

    completion: ChatCompletion = await client.chat.completions.create(
        model="gemini-2.5-flash-preview-05-20",
        reasoning_effort="low",
        messages=[
            {
                "role": "system",
                "content": "You are an expert AI assistant that validates electronic components.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    logger.info(f"Evaluation result: {completion.choices[0].message.content}")

    return completion.choices[0].message.content or ""
