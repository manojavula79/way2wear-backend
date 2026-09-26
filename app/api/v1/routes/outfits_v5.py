"""Changes:
- Support multi-image input (person, top, bottom)
- Pass actual images to generation service
- Enable clothing-preserving generation
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from app.database import get_db
from app.models.db.user import User
from app.api.v1.middleware.auth import get_current_user
from app.services.image_generation_service_v3_q import ImageGenerationServiceV3

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/outfits", tags=["outfits"])

# Initialize service (in your main.py: image_service_v3 = ImageGenerationServiceV3(redis_client))
image_service_v3: ImageGenerationServiceV3 = None


def set_image_service(service: ImageGenerationServiceV3):
    """Dependency injection for service"""
    global image_service_v3
    image_service_v3 = service


@router.post("/generate-image-v3")
async def generate_outfit_image_v3(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Generate outfit image with multi-image references
    
    TASK 5: New endpoint using gpt-image-2.5-sunburst
    
    Request payload:
    {
        "outfit_description": "Blue shirt and black pants",
        "person_image": "base64...",  # Optional
        "product_top_image": "base64...",  # Actual clothing image
        "product_bottom_image": "base64...",  # Actual clothing image
        "user_skin_tone": "medium",
        "user_height": "175cm",
        "user_occasion": "office",
        "style_hint": "professional fashion photography"
    }
    """
    try:
        logger.info(f"🎨 Generating outfit with multi-image references for user {current_user.id}")

        # Extract request parameters
        outfit_description = request.get("outfit_description", "")
        person_image = request.get("person_image")
        product_top_image = request.get("product_top_image")
        product_bottom_image = request.get("product_bottom_image")
        
        # User context (Task 3)
        user_skin_tone = request.get("user_skin_tone")
        user_color_preference = request.get("user_color_preference", [])
        user_height = request.get("user_height")
        user_occasion = request.get("user_occasion")

        # Log what we received
        logger.info(
            f"📸 Images received: "
            f"person={bool(person_image)}, "
            f"top={bool(product_top_image)}, "
            f"bottom={bool(product_bottom_image)}"
        )

        # Call service with all images
        result = await image_service_v3.generate_outfit_with_images(
            user_id=str(current_user.id),
            outfit_description=outfit_description,
            # TASK 5: Multi-image support
            person_image=person_image,
            product_top_image=product_top_image,
            product_bottom_image=product_bottom_image,
            # Context
            style_hint=request.get("style_hint", "professional fashion photography"),
            user_context=request.get("user_context", ""),
            use_cache=request.get("use_cache", True),
            # TASK 3: User context
            user_skin_tone=user_skin_tone,
            user_color_preference=user_color_preference,
            user_height=user_height,
            user_occasion=user_occasion,
        )

        return result

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate-image-v3")
async def regenerate_outfit_image_v3(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate outfit image with refinement
    
    TASK 5: Multi-image approach preserves clothing
    
    Request payload:
    {
        "outfit_description": "Blue shirt and black pants",
        "refinement_instructions": "Make it more casual at a beach",
        "person_image": "base64...",
        "product_top_image": "base64...",
        "product_bottom_image": "base64...",
        "user_skin_tone": "medium"
    }
    """
    try:
        logger.info(f"🔄 Regenerating outfit with refinement for user {current_user.id}")

        refinement = request.get("refinement_instructions", "")
        logger.info(f"📝 Refinement: {refinement}")

        result = await image_service_v3.regenerate_with_refinement(
            user_id=str(current_user.id),
            outfit_description=request.get("outfit_description", ""),
            refinement_instructions=refinement,
            # TASK 5: Multi-image support
            person_image=request.get("person_image"),
            product_top_image=request.get("product_top_image"),
            product_bottom_image=request.get("product_bottom_image"),
            # Context
            user_context=request.get("user_context", ""),
            style_hint=request.get("style_hint", "professional fashion photography"),
            # TASK 3: User context
            user_skin_tone=request.get("user_skin_tone"),
            user_color_preference=request.get("user_color_preference", []),
            user_height=request.get("user_height"),
            user_occasion=request.get("user_occasion"),
        )

        return result

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-info")
async def get_model_info(current_user: User = Depends(get_current_user)):
    """Get current model information"""
    return {
        "current_model": "gpt-image-2.5-sunburst",
        "previous_model": "gpt-image-2",
        "features": [
            "Multi-image input support",
            "Clothing preservation",
            "Person reference support",
            "User refinements",
            "High-quality generation"
        ],
        "image_size": "1024x1024",
        "quality": "hd"
    }