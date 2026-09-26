"""
BACKEND TASK B - PART 2: Enhanced Endpoints

Location: app/routes/outfits_v2.py

Endpoints:
- POST /outfits/generate-image (with caching)
- POST /outfits/regenerate-image (with history)
- GET /outfits/history (get user's history)
- GET /outfits/rate-limit (check rate limit)
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.services.image_generation_service_v2 import image_service_v2

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/outfits", tags=["Outfits"])


# REQUEST/RESPONSE MODELS

class GenerateImageRequest(BaseModel):
    outfit_description: str
    style_hint: Optional[str] = "professional fashion photography"
    user_context: Optional[str] = None
    use_cache: Optional[bool] = True


class ImageGenerationResponse(BaseModel):
    success: bool
    image_url: Optional[str] = None
    prompt_used: Optional[str] = None
    cached: Optional[bool] = False
    edited: Optional[bool] = False
    error: Optional[str] = None


class RegenerateImageRequest(BaseModel):
    outfit_description: str
    user_edit: str
    user_context: Optional[str] = None
    style_hint: Optional[str] = "professional fashion photography"


class HistoryItem(BaseModel):
    outfit_description: str
    image_url: str
    prompt_used: str
    user_edit: Optional[str] = None
    created_at: str


class HistoryResponse(BaseModel):
    success: bool
    count: int
    history: List[HistoryItem] = []


class RateLimitResponse(BaseModel):
    allowed: bool
    message: str
    images_generated_this_hour: int
    remaining: int


# ENDPOINTS
@router.post("/generate-image")
async def generate_outfit_image(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Generate outfit image with optional product images
    
    TASK 2: Now accepts base64 product images
    """
    try:
        logger.info(f"Generating image for user {current_user.id}")

        # TASK 2: Extract product images from request
        product_top_image = request.get("product_top_image")
        product_bottom_image = request.get("product_bottom_image")
        product_top_color = request.get("product_top_color")
        product_bottom_color = request.get("product_bottom_color")

        logger.info(
            f"Request has product images: top={bool(product_top_image)}, bottom={bool(product_bottom_image)}"
        )

        # Call service with product images
        result = await image_service_v2.generate_outfit_image(
            user_id=str(current_user.id),
            outfit_description=request.get("outfit_description", ""),
            style_hint=request.get("style_hint", "professional fashion photography"),
            user_context=request.get("user_context", ""),
            use_cache=request.get("use_cache", True),
            # TASK 2: Pass product images
            product_top_image=product_top_image,
            product_bottom_image=product_bottom_image,
            product_top_color=product_top_color,
            product_bottom_color=product_bottom_color,
        )

        return result

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/regenerate-image")
async def regenerate_outfit_image(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate outfit image with edits and product images
    
    TASK 2: Now accepts base64 product images
    """
    try:
        logger.info(f"Regenerating image for user {current_user.id}")

        # TASK 2: Extract product images from request
        product_top_image = request.get("product_top_image")
        product_bottom_image = request.get("product_bottom_image")
        product_top_color = request.get("product_top_color")
        product_bottom_color = request.get("product_bottom_color")

        logger.info(f"User edit: {request.get('user_edit')}")
        logger.info(
            f"Product images: top={bool(product_top_image)}, bottom={bool(product_bottom_image)}"
        )

        # Call service with product images
        result = await image_service_v2.regenerate_with_edit(
            user_id=str(current_user.id),
            outfit_description=request.get("outfit_description", ""),
            user_edit=request.get("user_edit", ""),
            user_context=request.get("user_context", ""),
            style_hint=request.get("style_hint", "professional fashion photography"),
            # TASK 2: Pass product images
            product_top_image=product_top_image,
            product_bottom_image=product_bottom_image,
            product_top_color=product_top_color,
            product_bottom_color=product_bottom_color,
        )

        return result

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", response_model=HistoryResponse)
async def get_generation_history(
    current_user: User = Depends(get_current_user),
):
    """Get user's generation history (last 50 items)"""
    
    try:
        logger.info(f"Fetching history for user {current_user.id}")
        history = await image_service_v2.get_user_history(str(current_user.id))
        history = list(reversed(history))  # Most recent first

        return HistoryResponse(
            success=True,
            count=len(history),
            history=[HistoryItem(**item) for item in history],
        )

    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch history.",
        )


@router.get("/rate-limit", response_model=RateLimitResponse)
async def check_rate_limit(
    current_user: User = Depends(get_current_user),
):
    """Check user's rate limit status"""
    
    try:
        allowed, message = await image_service_v2.check_rate_limit(str(current_user.id))
        
        remaining = 0
        if "Remaining:" in message:
            parts = message.split("Remaining:")[1].strip().split()[0]
            remaining = int(parts)

        return RateLimitResponse(
            allowed=allowed,
            message=message,
            images_generated_this_hour=20 - remaining if allowed else 20,
            remaining=remaining if allowed else 0,
        )

    except Exception as e:
        logger.error(f"Error checking rate limit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check rate limit.",
        )
