from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


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
