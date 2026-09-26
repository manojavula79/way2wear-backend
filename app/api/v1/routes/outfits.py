"""
BACKEND TASK B - PART 1: FastAPI Endpoint

Create new file: app/routes/outfits.py

This endpoint:
- Receives outfit description
- Calls DALL-E to generate image
- Returns image URL
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional
import logging
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.services.image_generation_service import image_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outfits", tags=["Outfits"])


# ═══════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class GenerateImageRequest(BaseModel):
    """Request to generate outfit image"""
    outfit_description: str  # "white kurti + blue palazzo + gold sandals"
    style_hint: Optional[str] = "professional fashion photography"
    user_context: Optional[str] = None  # "woman, fair skin, 28 years old"


class ImageGenerationResponse(BaseModel):
    """Response with generated image"""
    success: bool
    image_url: Optional[str] = None
    prompt_used: Optional[str] = None
    error: Optional[str] = None


class RegenerateImageRequest(BaseModel):
    """Request to regenerate with user edits"""
    outfit_description: str
    user_edit: str  # "make it more casual" or "lighter colors"
    user_context: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/generate-image", response_model=ImageGenerationResponse)
async def generate_outfit_image(
    request: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate an AI image of an outfit using DALL-E.
    
    This endpoint:
    1. Takes outfit description (e.g., "white kurti + blue palazzo")
    2. Calls DALL-E to generate image
    3. Returns image URL
    
    Steps 1-4 of image preview feature:
    - Step 1: User taps View Details ✓ (done in frontend)
    - Step 2: Modal shows outfit breakdown ✓ (done in frontend)
    - Step 3: User clicks Preview ✓ (done in frontend)
    - Step 4: Generates AI image ← YOU ARE HERE
    
    Example request:
    {
        "outfit_description": "white kurti + light blue palazzo pants + gold sandals",
        "style_hint": "professional fashion photography",
        "user_context": "woman, fair skin, Indian style"
    }
    
    Example response:
    {
        "success": true,
        "image_url": "https://oaidalleapiprodpcs.blob.core.windows.net/...",
        "prompt_used": "An outfit consisting of: white kurti + light blue palazzo pants..."
    }
    """
    
    try:
        logger.info(
            f"Generating image for user {current_user.id}: {request.outfit_description}"
        )

        # Call image generation service
        result = await image_service.generate_outfit_image(
            outfit_description=request.outfit_description,
            style_hint=request.style_hint or "professional fashion photography",
            user_context=request.user_context or "",
        )

        if not result["success"]:
            logger.error(f"Image generation failed: {result.get('error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate image: {result.get('error')}",
            )

        logger.info(f"Image generated successfully for user {current_user.id}")

        return ImageGenerationResponse(
            success=True,
            image_url=result["image_url"],
            prompt_used=result["prompt_used"],
        )

    except Exception as e:
        logger.error(f"Error in generate_outfit_image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate image. Please try again.",
        )


@router.post("/regenerate-image", response_model=ImageGenerationResponse)
async def regenerate_outfit_image(
    request: RegenerateImageRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate outfit image with user's refinements.
    
    User says: "make it more casual" or "lighter colors"
    We regenerate the image with their feedback.
    
    Example request:
    {
        "outfit_description": "white kurti + blue palazzo",
        "user_edit": "make it more casual, lighter colors",
        "user_context": "woman, fair skin"
    }
    """
    
    try:
        logger.info(
            f"Regenerating image for user {current_user.id}: {request.user_edit}"
        )

        # Call regenerate service
        result = await image_service.regenerate_outfit_image(
            outfit_description=request.outfit_description,
            user_edit=request.user_edit,
            user_context=request.user_context or "",
        )

        if not result["success"]:
            logger.error(f"Image regeneration failed: {result.get('error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to regenerate image. Please try again.",
            )

        logger.info(f"Image regenerated successfully for user {current_user.id}")

        return ImageGenerationResponse(
            success=True,
            image_url=result["image_url"],
            prompt_used=result["prompt_used"],
        )

    except Exception as e:
        logger.error(f"Error in regenerate_outfit_image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate image. Please try again.",
        )