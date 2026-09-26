from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GlobalSearchRequest(BaseModel):
    message: str = Field(..., min_length=2)
    profile: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class ProductResult(BaseModel):
    id: str
    title: str
    brand: Optional[str] = None
    price: Optional[float] = None
    currency: str = "INR"
    image: Optional[str] = None
    url: str
    category: str
    gender: str = "unisex"
    source: str = "web"
    description: Optional[str] = None


class GlobalOutfit(BaseModel):
    id: str
    name: str
    note: str
    shoe_note: str
    total_price: Optional[float] = None
    top: ProductResult
    bottom: ProductResult


class FormFieldOption(BaseModel):
    label: str
    value: str


class FormField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = True
    options: List[FormFieldOption] = []

class GlobalSearchResponse(BaseModel):
    success: bool = True
    source: str = "global_web_search"
    needs_form: bool = False
    person_type: Optional[str] = None
    form_fields: Optional[List[FormField]] = None
    query_params: Dict[str, Any] = {}
    outfits: List[GlobalOutfit] = []
    count: int = 0
    warnings: List[str] = []

    session_id: str
    message_id: str
    response: str
    outfit_data: Dict[str, Any]
    usage: Optional[Dict[str, Any]] = None
    success: bool=True
    source: str = "global_web_search"
    needs_form: bool = False
    person_type: Optional[str] = None
    form_fields: Optional[List[FormField]] = None
    query_params: Dict[str, Any] = {}
    outfits: List[GlobalOutfit] = []
    count: int = 0
    warnings: List[str] = []
    session_id: str
    message_id: str
    response: str
    outfit_data: Dict[str, Any]
    usage: Optional[Dict[str, Any]] = None