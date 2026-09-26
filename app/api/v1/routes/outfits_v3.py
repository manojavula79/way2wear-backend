"""
BACKEND TASK B - PART 3: Image Storage Endpoints

Location: app/routes/outfits_v3.py

Endpoints:
- POST /outfits/store-image (convert temp URL to permanent)
- GET /outfits/gallery (get user's generated images)
- DELETE /outfits/image/{image_id} (delete stored image)
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging
from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.image_storage_service import image_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/outfits", tags=["Outfits"])


# REQUEST/RESPONSE MODELS

class StoreImageRequest(BaseModel):
    temporary_url: str
    outfit_description: str
    prompt_used: str
    user_edit: Optional[str] = None
    style_hint: Optional[str] = None
    user_context: Optional[str] = None


class StoredImageResponse(BaseModel):
    success: bool
    image_id: Optional[str] = None
    permanent_url: Optional[str] = None
    error: Optional[str] = None


class ImageGalleryItem(BaseModel):
    id: str
    outfit_description: str
    permanent_url: str
    user_edit: Optional[str] = None
    created_at: str


class ImageGalleryResponse(BaseModel):
    success: bool
    count: int
    images: List[ImageGalleryItem] = []


class DeleteImageResponse(BaseModel):
    success: bool
    message: str
    error: Optional[str] = None


# ENDPOINTS

@router.post("/store-image", response_model=StoredImageResponse)
async def store_image_permanently(
    request: StoreImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Convert temporary DALL-E image to permanent storage.
    
    Process:
    1. Downloads image from temporary DALL-E URL
    2. Uploads to S3 or cloud storage
    3. Saves metadata to database
    4. Returns permanent URL
    """
    
    try:
        logger.info(f"Storing image for user {current_user.id}")
        
        result = await image_storage.process_and_store_image(
            db=db,
            user_id=str(current_user.id),
            temporary_url=request.temporary_url,
            outfit_description=request.outfit_description,
            prompt_used=request.prompt_used,
            user_edit=request.user_edit,
            style_hint=request.style_hint,
            user_context=request.user_context,
        )
        
        if not result["success"]:
            logger.error(f"Failed to store image: {result.get('error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get('error', 'Failed to store image'),
            )
        
        logger.info(f"Image stored successfully: {result['image_id']}")
        
        return StoredImageResponse(
            success=True,
            image_id=result["image_id"],
            permanent_url=result["permanent_url"],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in store_image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store image. Please try again.",
        )


@router.get("/gallery", response_model=ImageGalleryResponse)
async def get_image_gallery(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user's gallery of generated and stored images.
    
    Returns:
    - Permanently stored images only
    - Sorted by creation date (newest first)
    - Max 20 images per request
    """
    
    try:
        logger.info(f"Fetching gallery for user {current_user.id}")
        
        images = await image_storage.get_user_generated_images(
            db=db,
            user_id=str(current_user.id),
            limit=limit,
        )
        
        return ImageGalleryResponse(
            success=True,
            count=len(images),
            images=[ImageGalleryItem(**img) for img in images],
        )
        
    except Exception as e:
        logger.error(f"Error fetching gallery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch gallery.",
        )


@router.delete("/image/{image_id}", response_model=DeleteImageResponse)
async def delete_generated_image(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a stored image from gallery.
    
    Process:
    1. Verifies user owns the image
    2. Removes from database
    3. Returns success status
    """
    
    try:
        from app.models.db.generated_image import GeneratedImage
        from sqlalchemy import select
        
        logger.info(f"Deleting image {image_id} for user {current_user.id}")
        
        query = select(GeneratedImage).where(
            GeneratedImage.id == image_id,
            GeneratedImage.user_id == str(current_user.id)
        )
        result = await db.execute(query)
        image = result.scalar()
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found",
            )
        
        await db.delete(image)
        await db.commit()
        
        logger.info(f"Image deleted: {image_id}")
        
        return DeleteImageResponse(
            success=True,
            message=f"Image {image_id} deleted successfully",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete image.",
        )
