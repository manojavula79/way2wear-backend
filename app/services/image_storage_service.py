"""
BACKEND TASK B - PART 3: Image Storage & Database Persistence

Location: app/services/image_storage_service.py

Features:
- Download images from DALL-E temporary URLs
- Upload to AWS S3 or cloud storage
- Store metadata in database
- Create permanent image URLs
"""

import logging
import httpx
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

logger = logging.getLogger(__name__)


class ImageStorageService:
    """Service to download, upload, and persist images"""

    def __init__(self, cloud_provider: str = "s3"):
        self.cloud_provider = cloud_provider
        self.logger = logging.getLogger(__name__)

    async def download_image_from_url(
        self,
        image_url: str,
        timeout: int = 30,
    ) -> Optional[bytes]:
        """Download image from DALL-E temporary URL"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=timeout)
                response.raise_for_status()
                self.logger.info(f"Downloaded image: {len(response.content)} bytes")
                return response.content
        except Exception as e:
            self.logger.error(f"Failed to download image: {str(e)}")
            return None

    async def upload_to_s3(
        self,
        image_bytes: bytes,
        bucket: str,
        key: str,
        content_type: str = "image/png",
    ) -> Optional[str]:
        """Upload image to AWS S3"""
        try:
            import boto3
            
            s3_client = boto3.client('s3')
            
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=image_bytes,
                ContentType=content_type,
                # ACL='public-read',
            )
            
            url = f"https://{bucket}.s3.amazonaws.com/{key}"
            self.logger.info(f"Uploaded to S3: {url}")
            return url
            
        except Exception as e:
            self.logger.error(f"S3 upload failed: {str(e)}")
            return None

    async def save_to_local_storage(
        self,
        image_bytes: bytes,
        file_path: str,
    ) -> Optional[str]:
        """Save image to local filesystem (for development)"""
        try:
            import os
            
            directory = os.path.dirname(file_path)
            os.makedirs(directory, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(image_bytes)
            
            self.logger.info(f"Saved to local storage: {file_path}")
            return f"/images/{os.path.basename(file_path)}"
            
        except Exception as e:
            self.logger.error(f"Local storage save failed: {str(e)}")
            return None

    async def save_image_metadata(
        self,
        db: AsyncSession,
        user_id: str,
        outfit_description: str,
        temporary_url: str,
        permanent_url: str,
        storage_path: str,
        prompt_used: str,
        user_edit: Optional[str] = None,
        style_hint: Optional[str] = None,
        user_context: Optional[str] = None,
    ) -> Optional[str]:
        """Save image metadata to database"""
        try:
            from app.models.db.generated_image import GeneratedImage
            
            image_id = str(uuid.uuid4())
            
            image = GeneratedImage(
                id=image_id,
                user_id=user_id,
                outfit_description=outfit_description,
                temporary_url=temporary_url,
                permanent_url=permanent_url,
                storage_path=storage_path,
                prompt_used=prompt_used,
                user_edit=user_edit,
                style_hint=style_hint,
                user_context=user_context,
                status="stored",
            )
            
            db.add(image)
            await db.commit()
            
            self.logger.info(f"Saved metadata: {image_id}")
            return image_id
            
        except Exception as e:
            self.logger.error(f"Failed to save metadata: {str(e)}")
            await db.rollback()
            return None

    async def process_and_store_image(
        self,
        db: AsyncSession,
        user_id: str,
        temporary_url: str,
        outfit_description: str,
        prompt_used: str,
        bucket: str = "way2wear-images",
        user_edit: Optional[str] = None,
        style_hint: Optional[str] = None,
        user_context: Optional[str] = None,
    ) -> dict:
        """Complete workflow: Download → Upload → Store metadata"""
        try:
            # Step 1: Download
            self.logger.info(f"Downloading image from: {temporary_url}")
            image_bytes = await self.download_image_from_url(temporary_url)
            
            if not image_bytes:
                return {"success": False, "error": "Failed to download image"}
            
            # Step 2: Upload to S3
            storage_key = f"outfits/{user_id}/{uuid.uuid4()}.png"
            permanent_url = await self.upload_to_s3(
                image_bytes,
                bucket=bucket,
                key=storage_key,
            )
            
            if not permanent_url:
                return {"success": False, "error": "Failed to upload to storage"}
            
            # Step 3: Save to database
            image_id = await self.save_image_metadata(
                db=db,
                user_id=user_id,
                outfit_description=outfit_description,
                temporary_url=temporary_url,
                permanent_url=permanent_url,
                storage_path=storage_key,
                prompt_used=prompt_used,
                user_edit=user_edit,
                style_hint=style_hint,
                user_context=user_context,
            )
            
            if not image_id:
                return {"success": False, "error": "Failed to save metadata"}
            
            return {
                "success": True,
                "image_id": image_id,
                "permanent_url": permanent_url,
            }
            
        except Exception as e:
            self.logger.error(f"Error processing image: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_user_generated_images(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 20,
    ) -> list:
        """Get all images generated by user"""
        try:
            from app.models.db.generated_image import GeneratedImage
            
            query = (
                select(GeneratedImage)
                .where(GeneratedImage.user_id == user_id)
                .order_by(GeneratedImage.created_at.desc())
                .limit(limit)
            )
            
            result = await db.execute(query)
            images = result.scalars().all()
            
            return [
                {
                    "id": str(img.id),
                    "outfit_description": img.outfit_description,
                    "permanent_url": img.permanent_url,
                    "user_edit": img.user_edit,
                    "created_at": img.created_at.isoformat(),
                }
                for img in images
            ]
            
        except Exception as e:
            self.logger.error(f"Error fetching images: {str(e)}")
            return []


image_storage = ImageStorageService()
