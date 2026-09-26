"""
BACKEND TASK B - PART 1: DALL-E Image Generation Service

What it does:
1. Set up DALL-E client
2. Create image generation service
3. Create FastAPI endpoint to generate outfit images

Location: app/services/image_generation_service.py
"""

import asyncio
import logging
from typing import Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DALLE_MODEL = "gpt-image-2"
IMAGE_SIZE = "1024x1024"  # DALL-E 3 supports: 1024x1024, 1024x1792, 1792x1024
IMAGE_QUALITY = "standard"  # or "hd" for higher quality (costs more)


class ImageGenerationService:
    """
    Service to generate outfit images using DALL-E 3
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = DALLE_MODEL

    async def generate_outfit_image(
        self,
        outfit_description: str,
        style_hint: str = "professional fashion photography",
        user_context: str = "",
    ) -> dict:
        """
        Generate an outfit image using DALL-E.

        Args:
            outfit_description: Description of the outfit (e.g., "white kurti + blue palazzo")
            style_hint: Photography style hint (e.g., "professional fashion photography")
            user_context: User preferences (e.g., "fair skin tone, woman")

        Returns:
            {
                "success": bool,
                "image_url": str,
                "prompt_used": str,
                "error": str (if failed)
            }

        Example:
            >>> outfit = "white kurti + blue palazzo pants + gold sandals"
            >>> result = await service.generate_outfit_image(outfit, user_context="woman, fair skin")
            >>> print(result["image_url"])
        """

        try:
            # Build the prompt
            prompt = self._build_prompt(outfit_description, style_hint, user_context)
            logger.info(f"Generating image with prompt: {prompt[:100]}...")

            # Call DALL-E API
            response = await self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=IMAGE_SIZE,
                # quality=IMAGE_QUALITY,
                n=1,  # Generate 1 image
            )

            # Extract image URL
            image_url = response.data[0].url
            logger.info(f"Image generated successfully: {image_url}")

            return {
                "success": True,
                "image_url": image_url,
                "prompt_used": prompt,
            }

        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return {
                "success": False,
                "image_url": None,
                "prompt_used": None,
                "error": str(e),
            }

    def _build_prompt(
        self,
        outfit_description: str,
        style_hint: str,
        user_context: str,
    ) -> str:
        """
        Build a detailed prompt for DALL-E.

        Takes outfit description and enhances it with context.
        """

        # Core outfit description
        base_prompt = f"An outfit consisting of: {outfit_description}"

        # Add user context
        if user_context:
            context_part = f". Person wearing: {user_context}"
        else:
            context_part = ""

        # Add style and quality hints
        style_part = f". {style_hint}. High quality, professional styling, good lighting, studio background. Realistic, natural colors."

        # Combine all parts
        full_prompt = base_prompt + context_part + style_part

        # Limit to ~300 chars for DALL-E
        if len(full_prompt) > 1000:
            full_prompt = full_prompt[:1000]

        return full_prompt

    async def generate_outfit_image(
        self,
        outfit_description: str,
        style_hint: str = "professional fashion photography",
        user_context: str = "",
    ) -> dict:
        """Generate outfit image"""
        try:
            outfit_desc = outfit_description[:400] if outfit_description else ""
            
            prompt = self._build_prompt(outfit_desc, style_hint, user_context)
            logger.info(f"Generating image, prompt: {prompt[:100]}...")

            response = await self.client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                size="1024x1024",
                n=1,
            )

            logger.info(f"Response received: {response}")
            
            # Extract base64
            if response.data and len(response.data) > 0:
                b64_data = response.data[0].b64_json
                logger.info(f"b64_json length: {len(b64_data) if b64_data else 0}")
                
                if b64_data:
                    # Convert to data URL
                    image_url = f"data:image/png;base64,{b64_data}"
                    logger.info(f"✅ Created data URL, length: {len(image_url)}")
                    return {
                        "success": True,
                        "image_url": image_url,
                        "prompt_used": prompt,
                    }
            
            logger.error(f"❌ No image data in response")
            return {"success": False, "error": "No image data"}

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return {"success": False, "error": str(e)}

# Global instance
image_service = ImageGenerationService()


async def generate_image_async(
    outfit_description: str,
    user_context: str = "",
) -> dict:
    """
    Convenience function to generate image (can be called from anywhere)
    """
    return await image_service.generate_outfit_image(
        outfit_description=outfit_description,
        user_context=user_context,
    )