from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any


class OctopartSpec(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    units: Optional[str] = None

class OctopartPriceBreak(BaseModel):
    quantity: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None

class OctopartOffer(BaseModel):
    inventory_level: Optional[int] = Field(alias="inventoryLevel", default=None)
    prices: List[OctopartPriceBreak] = []

class OctopartSeller(BaseModel):
    company_name: Optional[str] = Field(alias="companyName", default=None)
    offers: List[OctopartOffer] = []

    @field_validator('company_name', mode='before')
    @classmethod
    def extract_name_from_company(cls, v):
        if isinstance(v, dict) and 'name' in v:
            return v['name']
        return v

class OctopartPart(BaseModel):
    mpn: Optional[str] = None
    manufacturer_name: Optional[str] = Field(alias="manufacturerName", default=None)
    short_description: Optional[str] = Field(alias="shortDescription", default=None)
    octopart_url: Optional[str] = Field(alias="octopartUrl", default=None)
    specs: List[OctopartSpec] = []
    sellers: List[OctopartSeller] = []
    similar_parts: List['SimilarPart'] = Field(alias="similarParts", default=[])

    @field_validator('manufacturer_name', mode='before')
    @classmethod
    def extract_name_from_manufacturer(cls, v):
        if isinstance(v, dict) and 'name' in v:
            return v['name']
        return v

class SimilarPart(BaseModel):
    mpn: Optional[str] = None
    manufacturer_name: Optional[str] = Field(alias="manufacturerName", default=None)
    octopart_url: Optional[str] = Field(alias="octopartUrl", default=None)
    short_description: Optional[str] = Field(alias="shortDescription", default=None)
    specs: List[OctopartSpec] = []
    sellers: List[OctopartSeller] = []

    @field_validator('manufacturer_name', mode='before')
    @classmethod
    def extract_name_from_manufacturer(cls, v):
        if isinstance(v, dict) and 'name' in v:
            return v['name']
        return v

# This is needed to handle the forward reference of SimilarPart in OctopartPart
OctopartPart.model_rebuild()

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the alternative part is a valid substitute.")
    reasoning: str = Field(description="A brief explanation of why the alternative is or is not valid.")

class CostAnalysis(BaseModel):
    original_part_cost: Optional[float] = None
    alternative_part_cost: Optional[float] = None
    savings_per_board: Optional[float] = None
    total_savings: Optional[float] = None

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
    recommended_alternative: Optional[SimilarPart] = Field(None, description="The best valid alternative found based on the rules engine.")
    cost_analysis: Optional[CostAnalysis] = Field(None, description="An analysis of the cost savings for the recommended alternative.")


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
