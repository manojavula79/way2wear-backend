"""
Changes:
- Support multi-image input (person, top, bottom)
- Pass actual images to generation service
- Enable clothing-preserving generation
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, List
import logging

from app.services.image_generation_service_v3_q import ImageGenerationServiceV3
from app.services.refinement_parser_service import RefinementParserService
from app.models.db.user import User
from app.api.v1.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/outfits", tags=["outfits-v4"])

# Global service instances (initialized in main.py)
image_service: Optional[ImageGenerationServiceV3] = None
refinement_parser: Optional[RefinementParserService] = None


def set_services(
    image_gen_service: ImageGenerationServiceV3,
    refinement_service: RefinementParserService,
):
    """Initialize services from main.py"""
    global image_service, refinement_parser
    image_service = image_gen_service
    refinement_parser = refinement_service
    logger.info("✅ Services initialized in outfits_v4")


# ===== TASK 5 & 6: Generate with Multi-Image + Refinement =====

@router.post("/v4/generate")
async def generate_outfit_v4(
    request: dict,
    current_user = Depends(get_current_user),
):
    """
    
    Request:
    {
        "outfit_description": "Blue shirt and black pants",
        "person_image": "base64...",
        "product_top_image": "base64...",
        "product_bottom_image": "base64...",
        "refinement_instructions": "5.8 height, beach with sunset",
        "user_skin_tone": "medium",
        "user_height": "175cm"
    }
    """
    try:
        if not image_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image generation service not initialized"
            )

        # Extract parameters
        outfit_description = request.get("outfit_description", "")
        person_image = request.get("person_image")
        product_top_image = request.get("product_top_image")
        product_bottom_image = request.get("product_bottom_image")
        refinement_instructions = request.get("refinement_instructions", "")

        user_skin_tone = request.get("user_skin_tone")
        user_height = request.get("user_height")
        user_occasion = request.get("user_occasion")

        logger.info(f"📸 Generating outfit V4 for user {current_user.id}")

        # TASK 6: Parse refinement if provided
        parsed_refinements = None
        if refinement_instructions and refinement_parser:
            logger.info(f"📝 Parsing refinement: {refinement_instructions}")
            parsed_refinements = refinement_parser.parse_refinement(refinement_instructions)
            
            if parsed_refinements.combined_prompt:
                refinement_instructions = parsed_refinements.combined_prompt
            
            logger.info(
                f"✅ Parsed: {refinement_parser.get_refinement_summary(parsed_refinements)}"
            )

        # TASK 5: Generate with multi-image references
        result = await image_service.generate_outfit_with_images(
            user_id=str(current_user.id),
            outfit_description=outfit_description,
            person_image=person_image,
            product_top_image=product_top_image,
            product_bottom_image=product_bottom_image,
            user_skin_tone=user_skin_tone,
            user_height=user_height,
            user_occasion=user_occasion,
            refinement_instructions=refinement_instructions,
            use_cache=request.get("use_cache", True),
        )

        # Add refinement info to response
        if parsed_refinements:
            result["refinements_parsed"] = {
                "count": len(parsed_refinements.refinements),
                "types": [r.refinement_type.value for r in parsed_refinements.refinements],
                "preserves_clothing": parsed_refinements.preserves_clothing,
            }

        return result

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v4/regenerate")
async def regenerate_outfit_v4(
    request: dict,
    current_user = Depends(get_current_user),
):
    """
    TASK 5 + 6: Regenerate with refinement
    
    Request:
    {
        "outfit_description": "Blue shirt and black pants",
        "refinement_instructions": "Make it casual at beach",
        "person_image": "base64...",
        "product_top_image": "base64...",
        "product_bottom_image": "base64..."
    }
    """
    try:
        if not image_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image generation service not initialized"
            )

        refinement_instructions = request.get("refinement_instructions", "")
        logger.info(f"🔄 Regenerating with refinement: {refinement_instructions}")

        # TASK 6: Parse refinement
        if refinement_instructions and refinement_parser:
            parsed_refinements = refinement_parser.parse_refinement(refinement_instructions)
            if parsed_refinements.combined_prompt:
                refinement_instructions = parsed_refinements.combined_prompt

        # TASK 5: Regenerate with multi-image
        result = await image_service.regenerate_with_refinement(
            user_id=str(current_user.id),
            outfit_description=request.get("outfit_description", ""),
            refinement_instructions=refinement_instructions,
            person_image=request.get("person_image"),
            product_top_image=request.get("product_top_image"),
            product_bottom_image=request.get("product_bottom_image"),
            user_skin_tone=request.get("user_skin_tone"),
            user_height=request.get("user_height"),
            user_occasion=request.get("user_occasion"),
        )

        return result

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== TASK 6: Parse Refinement (for frontend preview) =====

@router.post("/v4/parse-refinement")
async def parse_refinement(
    request: dict,
    current_user = Depends(get_current_user),
):
    """
    TASK 6: Parse refinement without generating image
    
    Useful for frontend to show preview of what will change
    """
    try:
        if not refinement_parser:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refinement parser not initialized"
            )

        instruction = request.get("refinement_instructions", "")

        if not instruction:
            return {
                "success": True,
                "instruction": instruction,
                "refinements": [],
                "message": "No refinement provided"
            }

        parsed = refinement_parser.parse_refinement(instruction)

        return {
            "success": True,
            "instruction": instruction,
            "refinements": [
                {
                    "type": r.refinement_type.value,
                    "value": r.value,
                    "confidence": r.confidence,
                    "preserves_clothing": r.preserves_clothing,
                }
                for r in parsed.refinements
            ],
            "preserves_clothing": parsed.preserves_clothing,
            "warnings": parsed.warnings,
            "summary": refinement_parser.get_refinement_summary(parsed),
        }

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v4/refinement-examples")
async def get_refinement_examples(
    current_user = Depends(get_current_user)
):
    """TASK 6: Get example refinement instructions"""
    return {
        "examples": [
            {
                "instruction": "My height is 5.8",
                "description": "Adjust body proportions",
                "preserves_clothing": True,
            },
            {
                "instruction": "Show me at a beach",
                "description": "Change environment to beach",
                "preserves_clothing": True,
            },
            {
                "instruction": "Casual pose with sunset lighting",
                "description": "Adjust pose and lighting",
                "preserves_clothing": True,
            },
            {
                "instruction": "5.8 height, beach with sunset, confident pose",
                "description": "Combined refinements",
                "preserves_clothing": True,
            },
            {
                "instruction": "Professional office setting, warm lighting",
                "description": "Environment and lighting",
                "preserves_clothing": True,
            },
        ],
        "supported_types": [
            "height",
            "environment",
            "pose",
            "lighting",
            "mood",
        ],
    }