"""
Features:
- Redis caching (24 hour TTL)
- Rate limiting (20 images/hour/user)
- Generation history (7 days)
- Prompt refinement
"""

import logging
import json
import hashlib
from typing import Optional, List, Dict
from datetime import datetime
from openai import AsyncOpenAI, api_key
from dotenv import load_dotenv
import os

load_dotenv()
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DALLE_MODEL = "gpt-image-2"
IMAGE_SIZE = "1024x1024"
IMAGE_QUALITY = "standard"

CACHE_TTL = 24 * 3600
RATE_LIMIT_IMAGES_PER_HOUR = 20


class ImageGenerationServiceV2:
    """Enhanced service with caching, rate limiting, history"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = DALLE_MODEL

    def _get_cache_key(self, outfit: str, context: str = "") -> str:
        """Generate cache key"""
        key_str = f"{outfit}:{context}"
        key_hash = hashlib.md5(key_str.encode()).hexdigest()
        return f"outfit:image:{key_hash}"

    def _get_history_key(self, user_id: str) -> str:
        """Get history key"""
        return f"outfit:history:{user_id}"

    def _get_rate_limit_key(self, user_id: str) -> str:
        """Get rate limit key"""
        return f"outfit:rate_limit:{user_id}"

    async def check_rate_limit(self, user_id: str) -> tuple[bool, str]:
        """Check rate limit"""
        from app.redis_client import RedisCache
        
        rate_limit_key = self._get_rate_limit_key(user_id)
        
        try:
            count = await RedisCache.get(rate_limit_key)
            current_count = int(count) if count else 0
        except:
            current_count = 0

        if current_count >= RATE_LIMIT_IMAGES_PER_HOUR:
            return False, f"Rate limit exceeded. Max {RATE_LIMIT_IMAGES_PER_HOUR} images per hour."

        await RedisCache.increment(rate_limit_key, ttl=3600)
        remaining = RATE_LIMIT_IMAGES_PER_HOUR - current_count - 1
        return True, f"OK. Remaining: {remaining} images this hour."

    async def get_cached_image(self, outfit: str, context: str = "") -> Optional[str]:
        """Get cached image URL"""
        from app.redis_client import RedisCache
        
        cache_key = self._get_cache_key(outfit, context)
        
        try:
            cached = await RedisCache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for outfit: {outfit}")
                return cached
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        return None

    async def cache_image(self, outfit: str, context: str, image_url: str, prompt: str) -> bool:
        """Cache image in Redis"""
        from app.redis_client import RedisCache
        
        cache_key = self._get_cache_key(outfit, context)
        cache_data = {
            "image_url": image_url,
            "prompt_used": prompt,
            "created_at": datetime.now().isoformat(),
        }

        try:
            await RedisCache.set(cache_key, json.dumps(cache_data), ttl=CACHE_TTL)
            logger.info(f"Cached image for outfit: {outfit}")
            return True
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
            return False

    async def save_to_history(
        self,
        user_id: str,
        outfit: str,
        image_url: str,
        prompt: str,
        user_edit: Optional[str] = None,
    ) -> bool:
        """Save to user's history"""
        from app.redis_client import RedisCache
        
        history_key = self._get_history_key(user_id)
        history_entry = {
            "outfit_description": outfit,
            "image_url": image_url,
            "prompt_used": prompt,
            "user_edit": user_edit,
            "created_at": datetime.now().isoformat(),
        }

        try:
            existing = await RedisCache.get(history_key)
            history_list = json.loads(existing) if existing else []
            history_list.append(history_entry)
            
            if len(history_list) > 50:
                history_list = history_list[-50:]

            await RedisCache.set(history_key, json.dumps(history_list), ttl=7 * 24 * 3600)
            logger.info(f"Saved to history for user {user_id}")
            return True
        except Exception as e:
            logger.warning(f"History save error: {e}")
            return False

    async def get_user_history(self, user_id: str) -> List[Dict]:
        """Get user's history"""
        from app.redis_client import RedisCache
        
        history_key = self._get_history_key(user_id)
        try:
            history = await RedisCache.get(history_key)
            return json.loads(history) if history else []
        except Exception as e:
            logger.warning(f"History read error: {e}")
            return []

    def _build_enhanced_prompt(
        self,
        outfit: str,
        style_hint: str,
        context: str,
        user_edit: Optional[str] = None,
    ) -> str:
        """Build enhanced prompt"""
        base = f"An outfit consisting of: {outfit}"
        context_part = f". Person wearing: {context}" if context else ""
        edit_part = f". Style adjustment: {user_edit}" if user_edit else ""
        style_part = f". {style_hint}. High quality, professional styling, good lighting, studio background. Realistic, natural colors."
        
        full_prompt = base + context_part + edit_part + style_part
        if len(full_prompt) > 1000:
            full_prompt = full_prompt[:1000]
        return full_prompt

    async def generate_outfit_image(
        self,
        user_id: str,
        outfit_description: str,
        style_hint: str = "professional fashion photography",
        user_context: str = "",
        use_cache: bool = True,
    ) -> dict:
        """Generate image with caching"""
        
        allowed, limit_msg = await self.check_rate_limit(user_id)
        if not allowed:
            logger.warning(f"Rate limit for user {user_id}: {limit_msg}")
            return {"success": False, "error": limit_msg}

        if use_cache:
            cached_url = await self.get_cached_image(outfit_description, user_context)
            if cached_url:
                return {
                    "success": True,
                    "image_url": cached_url,
                    "cached": True,
                    "prompt_used": None,
                }

        try:
            outfit_desc = outfit_description[:400] if outfit_description else ""
            
            prompt = self._build_enhanced_prompt(
                outfit_desc,
                style_hint,
                user_context,
            )
            logger.info(f"Generating image for user {user_id}")
            logger.info(f"Prompt: {prompt[:100]}...")

            # ✅ Remove response_format - gpt-image-2 doesn't support it
            response = await self.client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                size="1024x1024",
                n=1,
            )

            logger.info(f"Response received")
            
            # Extract base64 and convert to data URL
            if response.data and len(response.data) > 0:
                b64_data = response.data[0].b64_json
                if not b64_data:
                    logger.error(f"No b64_json in response")
                    return {"success": False, "error": "Image generation returned no data"}
                
                # Convert base64 to data URL
                image_url = f"data:image/png;base64,{b64_data}"
                logger.info(f"✅ Image generated (data URL created)")
            else:
                logger.error(f"No data in response")
                return {"success": False, "error": "No image data in response"}

            await self.cache_image(outfit_desc, user_context, image_url, prompt)
            await self.save_to_history(user_id, outfit_desc, image_url, prompt)

            return {
                "success": True,
                "image_url": image_url,
                "prompt_used": prompt,
                "cached": False,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error generating image: {error_msg}")
            return {"success": False, "error": error_msg}

    async def regenerate_with_edit(
        self,
        user_id: str,
        outfit_description: str,
        user_edit: str,
        user_context: str = "",
        style_hint: str = "professional fashion photography",
    ) -> dict:
        """Regenerate with user edit"""
        
        allowed, limit_msg = await self.check_rate_limit(user_id)
        if not allowed:
            return {"success": False, "error": limit_msg}

        try:
            prompt = self._build_enhanced_prompt(
                outfit_description,
                style_hint,
                user_context,
                user_edit=user_edit,
            )
            logger.info(f"Regenerating image for user {user_id}")

            # ✅ Remove response_format - gpt-image-2 doesn't support it
            response = await self.client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                size="1024x1024",
                n=1,
            )

            logger.info(f"Response received")
            
            # Extract base64 and convert to data URL
            if response.data and len(response.data) > 0:
                b64_data = response.data[0].b64_json
                if not b64_data:
                    logger.error(f"No b64_json in response")
                    return {"success": False, "error": "Image generation returned no data"}
                
                # Convert base64 to data URL
                image_url = f"data:image/png;base64,{b64_data}"
                logger.info(f"✅ Image regenerated (data URL created)")
            else:
                logger.error(f"No data in response")
                return {"success": False, "error": "No image data in response"}

            await self.save_to_history(
                user_id,
                outfit_description,
                image_url,
                prompt,
                user_edit=user_edit,
            )

            return {
                "success": True,
                "image_url": image_url,
                "prompt_used": prompt,
                "cached": False,
                "edited": True,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error regenerating image: {error_msg}")
            return {"success": False, "error": error_msg}

image_service_v2 = ImageGenerationServiceV2()
