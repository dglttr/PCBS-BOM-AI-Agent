from pydantic import BaseModel, Field
from typing import List, Optional


class OctopartSpec(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    units: Optional[str] = None

class OctopartPriceBreak(BaseModel):
    quantity: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None

class OctopartOffer(BaseModel):
    inventory_level: Optional[int] = None
    prices: List[OctopartPriceBreak] = []

class OctopartSeller(BaseModel):
    company_name: Optional[str] = None
    offers: List[OctopartOffer] = []

class OctopartPart(BaseModel):
    mpn: Optional[str] = None
    manufacturer_name: Optional[str] = None
    short_description: Optional[str] = None
    octopart_url: Optional[str] = None
    specs: List[OctopartSpec] = []
    sellers: List[OctopartSeller] = []


class ExtractedParameters(BaseModel):
    electrical_value: Optional[str] = Field(
        None, description="The primary electrical value, e.g., '100nF' or '10kΩ'."
    )
    tolerance: Optional[str] = Field(None, description="The tolerance, e.g., '1%' or '±5%'.")
    voltage: Optional[str] = Field(None, description="The voltage rating, e.g., '25V'.")
    package_footprint: Optional[str] = Field(
        None, description="The component package or footprint, e.g., '0603' or 'SOT-23-3'."
    )


class ParsedBomItem(BaseModel):
    original_row_text: str = Field(..., description="The original, unmodified text from the BOM row.")
    manufacturer_part_number: Optional[str] = Field(
        None, description="The primary manufacturer part number (MPN)."
    )
    designators: List[str] = Field(description="A list of all reference designators, e.g., ['R1', 'R2'].")
    quantity: int = Field(description="The total quantity for this line item.")
    parameters: ExtractedParameters = Field(
        description="Key technical parameters extracted from the description or other columns."
    )
    parsing_notes: Optional[str] = Field(
        None, description="Any issues or ambiguities the AI found, e.g., 'Could not determine quantity, defaulted to number of designators.'"
    )
    octopart_data: Optional[OctopartPart] = Field(None, description="Structured data retrieved from the Octopart API.")


class BomColumnMapping(BaseModel):
    manufacturer_part_number: Optional[str] = Field(
        None, description="The column header that corresponds to the Manufacturer Part Number (MPN)."
    )
    designators: Optional[str] = Field(
        None, description="The column header that corresponds to the component reference designators."
    )
    quantity: Optional[str] = Field(
        None, description="The column header that corresponds to the component quantity."
    )
    description: Optional[str] = Field(
        None, description="The column header that corresponds to the component description."
    )


class GeneratedQuestions(BaseModel):
    questions: List[str] = Field(
        description="A list of clarifying questions for the user based on the BOM content."
    )
