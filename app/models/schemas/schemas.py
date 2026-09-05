from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# ══════════════════════════════════════════════
# AUTH SCHEMAS
# ══════════════════════════════════════════════

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ══════════════════════════════════════════════
# USER SCHEMAS
# ══════════════════════════════════════════════

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    style_preference: Optional[str] = None
    budget_range: Optional[str] = None
    gender: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: UUID
    phone: str
    full_name: Optional[str]
    style_preference: str
    budget_range: str
    plan: str
    total_likes: int
    total_orders: int
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════
# CHAT SCHEMAS
# ══════════════════════════════════════════════

class ProductItem(BaseModel):
    title: str
    brand: str
    price: float
    color: str
    url: str


class OutfitItem(BaseModel):
    id: str
    name: str
    top: ProductItem
    bottom: ProductItem
    accessory: Optional[ProductItem] = None
    note: str


class OutfitResponse(BaseModel):
    message: str
    tip: Optional[str] = None
    outfits: List[OutfitItem] = []


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: Optional[str] = None
    history: Optional[List[dict]] = []
    profile: Optional[dict] = None


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    response: str          # JSON string of OutfitResponse
    outfit_data: Optional[dict] = None
    usage: Optional[dict] = None


class MessageSchema(BaseModel):
    id: UUID
    role: str
    content: str
    outfit_data: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionSchema(BaseModel):
    id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionDetailSchema(SessionSchema):
    messages: List[MessageSchema] = []


# ══════════════════════════════════════════════
# LIKED PRODUCTS
# ══════════════════════════════════════════════

class LikeProductRequest(BaseModel):
    product_title: str
    brand: Optional[str] = None
    price: Optional[float] = None
    product_type: Optional[str] = None
    color: Optional[str] = None
    affiliate_url: Optional[str] = None
    session_id: Optional[str] = None
    outfit_name: Optional[str] = None


class LikedProductResponse(BaseModel):
    id: UUID
    product_title: str
    brand: Optional[str]
    price: Optional[float]
    product_type: Optional[str]
    color: Optional[str]
    affiliate_url: Optional[str]
    outfit_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════

class CreateOrderRequest(BaseModel):
    items: List[dict]
    total_price: Optional[float] = None
    outfit_name: Optional[str] = None
    session_id: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    items: List[dict]
    total_price: Optional[float]
    status: str
    outfit_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════
# FEEDBACK
# ══════════════════════════════════════════════

class FeedbackRequest(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_type: Optional[str] = "outfit"
    comment: Optional[str] = None
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    outfit_data: Optional[dict] = None

class QueryOutfitsRequest(BaseModel):
    """Request to query curated outfits database (steps 1-3)."""
    message: str
    profile: Optional[Dict[str, Any]] = None  # Optional gender, skin_tone override
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "I need a nice outfit for an office party. I'm a woman with fair skin. Budget is 2000.",
                "profile": {
                    "gender": "female",
                    "skin_tone": "fair"
                }
            }
        }


class CuratedOutfitData(BaseModel):
    """Single curated outfit from database."""
    id: int
    outfit_text: str
    occasion: str
    gender: str
    skin_tone: str
    budget_min: int
    budget_max: int
    style_tags: Optional[List[str]] = []
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 42,
                "outfit_text": "white kurti + light blue palazzo pants + dupatta",
                "occasion": "office",
                "gender": "female",
                "skin_tone": "fair",
                "budget_min": 800,
                "budget_max": 2000,
                "style_tags": ["curated", "ethnic"]
            }
        }


class QueryOutfitsResponse(BaseModel):
    """Response from curated outfits query (steps 1-3)."""
    success: bool
    intent: Dict[str, Any]  # Raw AI parsing: occasion, gender, skin_tone, budget, mood, description
    query_params: Dict[str, Any]  # Normalized: occasion, gender, skin_tone, budget
    curated_outfits: List[Dict[str, Any]]  # Full outfit records from DB
    count: int  # Number of matching outfits
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "intent": {
                    "occasion": "office party",
                    "gender": "female",
                    "skin_tone": "fair",
                    "budget": 2000,
                    "mood": "professional",
                    "description": "nice outfit, professional"
                },
                "query_params": {
                    "occasion": "office",
                    "gender": "female",
                    "skin_tone": "fair",
                    "budget": 2000
                },
                "curated_outfits": [
                    {
                        "id": 42,
                        "outfit_text": "white kurti + light blue palazzo pants + dupatta",
                        "occasion": "office",
                        "gender": "female",
                        "skin_tone": "fair",
                        "budget_min": 800,
                        "budget_max": 2000,
                        "style_tags": ["curated"]
                    }
                ],
                "count": 1
            }
        }


class ProfileFormResponse(BaseModel):
    """Response indicating user needs to fill profile form."""
    needs_form: bool
    message: str
    form_fields: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "needs_form": True,
                "message": "To give you the best recommendations, what's your brother's gender and skin tone preference?",
                "form_fields": {
                    "gender": {
                        "type": "buttons",
                        "options": ["Male", "Female", "Unisex"],
                        "required": True
                    },
                    "skin_tone": {
                        "type": "buttons",
                        "options": ["Fair", "Medium", "Dark"],
                        "required": False
                    },
                    "size": {
                        "type": "dropdown",
                        "options": ["XS", "S", "M", "L", "XL", "XXL"],
                        "required": False
                    }
                }
            }
        }

