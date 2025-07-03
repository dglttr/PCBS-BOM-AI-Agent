from pydantic import BaseModel
from typing import Dict, Any, Optional


class ProductionPlanItem(BaseModel):
    date: str
    transaction_type: str
    product: str
    quantity: str


class ProductionPlanResponse(BaseModel):
    result: str


class ProductionPlanChunk(BaseModel):
    text: str


class ProductionPlanRequest(BaseModel):
    job_id: str
    current_stock: int = 0
    scrap_rate: float = 0.05
    cache: Optional[Dict[str, Any]]