from pydantic import BaseModel
from typing import List, Dict


class AnalysisRequest(BaseModel):
    contract_text: str


class AnalysisResponse(BaseModel):
    contract_text: str
    relevant_regulations: List[str]
    analysis: Dict
