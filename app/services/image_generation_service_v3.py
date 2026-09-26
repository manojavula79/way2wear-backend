"""
Purpose:
- Migrate from gpt-image-2 to gpt-image-2.5-sunburst
- Implement multi-image input support
- Pass actual clothing images as references
- Enable accurate outfit reproduction

FIXES APPLIED IN THIS VERSION (vs. what you pasted):
1. _prepare_image_references() no longer double-wraps the data URL —
   resolve_image_to_base64() already returns a full "data:...;base64,..."
   string, so re-prepending "data:image/png;base64," produced a malformed
   nested URL. Fixed to use the resolved value directly.
2. regenerate_with_refinement() was missing the resolve_image_to_base64()
   call entirely — added it, matching generate_outfit_with_images().
3. Debug logging added throughout so you can see in your console exactly
   what's resolving, what's being built, and (STILL UNRESOLVED, see the
   loud warning in _generate_with_images) that the images aren't actually
   being sent to the OpenAI call yet — that needs your provider's actual
   multi-image API shape before it can be wired correctly.
"""

import os
import base64
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx
from openai import AsyncOpenAI
from redis import asyncio as aioredis
import asyncio
from app.services.image_fetch_service import resolve_image_to_base64

logger = logging.getLogger(__name__)


class ImageGenerationServiceV3:
    """Image generation with multi-image references and gpt-image-2.5-sunburst"""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.IMAGE_MODEL = "gpt-image-2.5-sunburst"
        self.IMAGE_SIZE = "1024x1024"
        logger.info(f"✅ Initialized ImageGenerationServiceV3 with model: {self.IMAGE_MODEL}")

    async def generate_outfit_with_images(
        self,
        user_id: str,
        outfit_description: str,
        person_image: Optional[str] = None,
        product_top_image: Optional[str] = None,
        product_bottom_image: Optional[str] = None,
        style_hint: str = "professional fashion photography",
        user_context: str = "",
        use_cache: bool = True,
        user_skin_tone: Optional[str] = None,
        user_color_preference: Optional[List[str]] = None,
        user_height: Optional[str] = None,
        user_occasion: Optional[str] = None,
        refinement_instructions: Optional[str] = None,
    ) -> dict:
        """
        Generate outfit image with multi-image references

        TASK 5: Use actual clothing images as visual references
        instead of just color hex codes
        """
        # ── Resolve every image reference to a real base64 data URL ──
        # (data: URL passthrough for the avatar, server-side fetch for
        # remote product photos — see image_fetch_service.py)
        logger.info("🔍 Resolving image references (generate)...")
        person_image, product_top_image, product_bottom_image = await asyncio.gather(
            resolve_image_to_base64(person_image, self.redis),
            resolve_image_to_base64(product_top_image, self.redis),
            resolve_image_to_base64(product_bottom_image, self.redis),
        )
        logger.info(
            f"🔍 Resolved — person={self._describe(person_image)}, "
            f"top={self._describe(product_top_image)}, "
            f"bottom={self._describe(product_bottom_image)}"
        )

        allowed, limit_msg = await self.check_rate_limit(user_id)
        if not allowed:
            logger.warning(f"Rate limit for user {user_id}: {limit_msg}")
            return {"success": False, "error": limit_msg}

        cache_key_base = self._build_cache_key(
            outfit_description,
            user_context,
            user_skin_tone,
            user_occasion,
            bool(person_image),
            bool(product_top_image),
            bool(product_bottom_image),
        )
        cache_hash = hashlib.md5(cache_key_base.encode()).hexdigest()

        if use_cache:
            cached_url = await self.get_cached_image(cache_hash)
            if cached_url:
                logger.info(f"✅ Using cached image for user {user_id}")
                return {
                    "success": True,
                    "image_url": cached_url,
                    "cached": True,
                    "prompt_used": None,
                }

        try:
            image_references = await self._prepare_image_references(
                person_image=person_image,
                product_top_image=product_top_image,
                product_bottom_image=product_bottom_image,
            )

            logger.info(
                f"📸 Image references prepared: "
                f"person={bool(person_image)}, "
                f"top={bool(product_top_image)}, "
                f"bottom={bool(product_bottom_image)}"
            )

            prompt = await self._build_master_prompt(
                outfit_description=outfit_description,
                style_hint=style_hint,
                user_context=user_context,
                user_skin_tone=user_skin_tone,
                user_color_preference=user_color_preference,
                user_height=user_height,
                user_occasion=user_occasion,
                refinement_instructions=refinement_instructions,
                has_person_image=bool(person_image),
                has_top_image=bool(product_top_image),
                has_bottom_image=bool(product_bottom_image),
            )

            logger.info(f"🎨 Master prompt built, length: {len(prompt)}")
            logger.info(f"📝 Prompt preview: {prompt[:300]}...")

            response = await self._generate_with_images(
                prompt=prompt,
                image_references=image_references,
            )

            if response and response.get("success"):
                image_url = response.get("image_url")

                await self.cache_image(cache_hash, image_url, prompt)

                await self.save_to_history(
                    user_id=user_id,
                    outfit_description=outfit_description,
                    image_url=image_url,
                    prompt=prompt,
                    has_images=bool(image_references),
                    user_skin_tone=user_skin_tone,
                    user_occasion=user_occasion,
                    refinement_instructions=refinement_instructions,
                )

                return {
                    "success": True,
                    "image_url": image_url,
                    "prompt_used": prompt,
                    "cached": False,
                    "image_references_used": len(image_references),
                }
            else:
                error_msg = response.get("error", "Unknown error") if response else "No response"
                logger.error(f"❌ Generation failed: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Exception during generation: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": error_msg}

    async def regenerate_with_refinement(
        self,
        user_id: str,
        outfit_description: str,
        refinement_instructions: str,
        person_image: Optional[str] = None,
        product_top_image: Optional[str] = None,
        product_bottom_image: Optional[str] = None,
        user_context: str = "",
        style_hint: str = "professional fashion photography",
        user_skin_tone: Optional[str] = None,
        user_color_preference: Optional[List[str]] = None,
        user_height: Optional[str] = None,
        user_occasion: Optional[str] = None,
    ) -> dict:
        """
        Regenerate with user refinement while preserving clothing

        TASK 5: Multi-image approach ensures clothing is preserved
        """
        # ── FIX: this resolve step was missing entirely before ──
        # Without it, edits/refinements were sending raw Amazon URLs (or
        # a raw data: URL for the avatar) straight into
        # _prepare_image_references(), which is why refinement requests
        # were even more broken than the initial generate.
        logger.info("🔍 Resolving image references (regenerate)...")
        person_image, product_top_image, product_bottom_image = await asyncio.gather(
            resolve_image_to_base64(person_image, self.redis),
            resolve_image_to_base64(product_top_image, self.redis),
            resolve_image_to_base64(product_bottom_image, self.redis),
        )
        logger.info(
            f"🔍 Resolved — person={self._describe(person_image)}, "
            f"top={self._describe(product_top_image)}, "
            f"bottom={self._describe(product_bottom_image)}"
        )

        allowed, limit_msg = await self.check_rate_limit(user_id)
        if not allowed:
            return {"success": False, "error": limit_msg}

        try:
            logger.info(f"🔄 Regenerating with refinement: {refinement_instructions}")

            image_references = await self._prepare_image_references(
                person_image=person_image,
                product_top_image=product_top_image,
                product_bottom_image=product_bottom_image,
            )

            prompt = await self._build_master_prompt(
                outfit_description=outfit_description,
                style_hint=style_hint,
                user_context=user_context,
                user_skin_tone=user_skin_tone,
                user_color_preference=user_color_preference,
                user_height=user_height,
                user_occasion=user_occasion,
                refinement_instructions=refinement_instructions,
                has_person_image=bool(person_image),
                has_top_image=bool(product_top_image),
                has_bottom_image=bool(product_bottom_image),
            )

            logger.info(f"📝 Refinement prompt: {refinement_instructions}")

            response = await self._generate_with_images(
                prompt=prompt,
                image_references=image_references,
            )

            if response and response.get("success"):
                image_url = response.get("image_url")

                await self.save_to_history(
                    user_id=user_id,
                    outfit_description=outfit_description,
                    image_url=image_url,
                    prompt=prompt,
                    has_images=bool(image_references),
                    refinement_instructions=refinement_instructions,
                )

                return {
                    "success": True,
                    "image_url": image_url,
                    "prompt_used": prompt,
                    "refined": True,
                    "image_references_used": len(image_references),
                }
            else:
                return {"success": False, "error": response.get("error") if response else "Failed"}

        except Exception as e:
            logger.error(f"Error during refinement: {str(e)}")
            return {"success": False, "error": str(e)}

    # ===== TASK 5: Multi-image support =====

    async def _prepare_image_references(
        self,
        person_image: Optional[str] = None,
        product_top_image: Optional[str] = None,
        product_bottom_image: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Prepare image references for gpt-image-2.5-sunburst

        FIX: person_image / product_top_image / product_bottom_image are
        already FULL data URLs by the time they get here (resolved by
        resolve_image_to_base64() upstream) — so we use them as-is
        instead of re-wrapping with another "data:image/png;base64,"
        prefix, which was producing malformed double-prefixed URLs.
        """
        image_references = []

        if person_image:
            logger.info(f"🖼️  person_image ready: {person_image[:60]}...")
            image_references.append({
                "type": "image_url",
                "image_url": {
                    "url": person_image,  # already a full data: URL
                    "detail": "high"
                },
                "role": "person_reference"
            })
            logger.info("✅ Person image reference added")

        if product_top_image:
            logger.info(f"🖼️  product_top_image ready: {product_top_image[:60]}...")
            image_references.append({
                "type": "image_url",
                "image_url": {
                    "url": product_top_image,  # already a full data: URL
                    "detail": "high"
                },
                "role": "top_reference"
            })
            logger.info("✅ Top clothing reference added")

        if product_bottom_image:
            logger.info(f"🖼️  product_bottom_image ready: {product_bottom_image[:60]}...")
            image_references.append({
                "type": "image_url",
                "image_url": {
                    "url": product_bottom_image,  # already a full data: URL
                    "detail": "high"
                },
                "role": "bottom_reference"
            })
            logger.info("✅ Bottom clothing reference added")

        logger.info(f"📦 Total image references prepared: {len(image_references)}")
        return image_references

    async def _build_master_prompt(
        self,
        outfit_description: str,
        style_hint: str,
        user_context: str,
        user_skin_tone: Optional[str],
        user_color_preference: Optional[List[str]],
        user_height: Optional[str],
        user_occasion: Optional[str],
        refinement_instructions: Optional[str],
        has_person_image: bool,
        has_top_image: bool,
        has_bottom_image: bool,
    ) -> str:
        """Build comprehensive master prompt for clothing preservation"""
        prompt_parts = []

        prompt_parts.append(
            "Create a photorealistic full-body fashion photograph. "
            "The provided clothing images are the exact visual references "
            "and SOURCE OF TRUTH."
        )

        if has_person_image:
            prompt_parts.append(
                "Use the provided person image as the person reference. "
                "Preserve their recognizable appearance (face, hairstyle, skin tone, body proportions)."
            )

        if has_top_image:
            prompt_parts.append(
                "Use the provided TOP image as the exact visual reference for the top/shirt. "
                "Reproduce the selected top's color, pattern, print, collar, neckline, sleeves, "
                "buttons, pockets, fabric, texture, fit, proportions, and overall design. "
                "Do not substitute with generic or similar clothing."
            )

        if has_bottom_image:
            prompt_parts.append(
                "Use the provided BOTTOM image as the exact visual reference for the bottom/pants. "
                "Reproduce the selected bottom's color, wash, pattern, cut, fit, pockets, "
                "fabric, texture, proportions, and overall design. "
                "Do not substitute with generic or similar clothing."
            )

        if outfit_description:
            prompt_parts.append(f"Outfit: {outfit_description}")

        if user_skin_tone:
            prompt_parts.append(f"Skin tone: {user_skin_tone}. Color harmonization for this tone.")

        if user_color_preference:
            colors = ", ".join(user_color_preference[:5])
            prompt_parts.append(f"User's preferred colors: {colors}")

        if user_height:
            prompt_parts.append(f"Height: {user_height}. Appropriate body proportions.")

        if user_occasion:
            prompt_parts.append(f"Occasion: {user_occasion}. Context-appropriate styling.")

        if refinement_instructions:
            prompt_parts.append(
                f"User refinement instructions: {refinement_instructions} "
                f"Apply these refinements while PRESERVING the selected clothing."
            )

        prompt_parts.append(
            f"Style: {style_hint}. "
            f"High-quality photorealistic lighting, natural fabric interaction, "
            f"realistic shadows and folds, professional fashion photography."
        )

        prompt_parts.append(
            "Only change the attributes explicitly requested by the user. "
            "Do not unnecessarily change the selected clothing, person appearance, or other attributes. "
            "Generate a high-quality, photorealistic full-body fashion image."
        )

        final_prompt = " ".join(prompt_parts)

        if len(final_prompt) > 2000:
            final_prompt = final_prompt[:2000]

        return final_prompt

    async def _generate_with_images(
        self,
        prompt: str,
        image_references: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Call gpt-image-2.5-sunburst with multi-image references

        ⚠️ STILL UNRESOLVED (Bug 3 — see chat): `message_content` below
        includes the image references, but `self.client.images.generate()`
        only accepts `prompt` / `size` / `n` / `quality` — it has no
        parameter for input images. So right now `image_references` is
        built and then silently dropped; the model only ever sees the
        text prompt. The loud warning log below will fire on every call
        until this is wired to whatever multi-image API shape your
        provider actually exposes for this model.
        """
        try:
            logger.info(f"🚀 Calling {self.IMAGE_MODEL} with {len(image_references)} image references")

            message_content = [
                {
                    "type": "text",
                    "text": prompt
                }
            ]
            for img_ref in image_references:
                message_content.append(img_ref)

            if image_references:
                logger.warning(
                    f"⚠️  {len(image_references)} image reference(s) were built but "
                    f"images.generate() does not accept them — this call is text-only "
                    f"right now. See Bug 3 in image_generation_service_v3.py."
                )

            response = await self.client.images.generate(
                model=self.IMAGE_MODEL,
                prompt=prompt,  # Text prompt only — see warning above
                size=self.IMAGE_SIZE,
                n=1,
                quality="medium",
            )

            logger.info(f"✅ Response received from {self.IMAGE_MODEL}")

            if response.data and len(response.data) > 0:
                b64_data = response.data[0].b64_json

                if b64_data:
                    image_url = f"data:image/png;base64,{b64_data}"
                    logger.info(f"✅ Image generated with clothing preservation")
                    return {
                        "success": True,
                        "image_url": image_url,
                    }
                else:
                    logger.error("b64_json is empty")
                    return {"success": False, "error": "No image data"}
            else:
                logger.error("No response data")
                return {"success": False, "error": "No response data"}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ API call failed: {error_msg}")
            return {"success": False, "error": error_msg}

    def _build_cache_key(
        self,
        outfit_desc: str,
        user_context: str,
        skin_tone: Optional[str],
        occasion: Optional[str],
        has_person: bool,
        has_top: bool,
        has_bottom: bool,
    ) -> str:
        """Build cache key including image presence"""
        key_parts = [
            outfit_desc,
            user_context,
            skin_tone or "none",
            occasion or "none",
            f"person={has_person}",
            f"top={has_top}",
            f"bottom={has_bottom}",
        ]
        return "|".join(key_parts)

    @staticmethod
    def _describe(image_value: Optional[str]) -> str:
        """Small helper for readable debug logs — avoids dumping raw base64."""
        if not image_value:
            return "None"
        return f"present ({len(image_value)} chars, {image_value[:25]}...)"

    # ===== Existing helper methods =====

    async def check_rate_limit(self, user_id: str) -> tuple[bool, str]:
        key = f"outfit:rate_limit:{user_id}"
        count = await self.redis.get(key)

        if count and int(count) >= 20:
            return False, "Limit reached (20/hour). Try again later."

        return True, "OK"

    async def get_cached_image(self, cache_hash: str) -> Optional[str]:
        key = f"outfit:image:{cache_hash}"
        return await self.redis.get(key)

    async def cache_image(
        self, cache_hash: str, image_url: str, prompt: str
    ) -> None:
        key = f"outfit:image:{cache_hash}"
        await self.redis.setex(key, 86400, image_url)
        logger.info(f"✅ Image cached for 24h")

    async def save_to_history(
        self,
        user_id: str,
        outfit_description: str,
        image_url: str,
        prompt: str,
        has_images: bool = False,
        user_skin_tone: Optional[str] = None,
        user_occasion: Optional[str] = None,
        refinement_instructions: Optional[str] = None,
    ) -> None:
        key = f"outfit:history:{user_id}"

        history_item = {
            "outfit_description": outfit_description,
            "image_url": image_url[:100],
            "prompt": prompt[:200],
            "has_images": has_images,
            "user_skin_tone": user_skin_tone or "",
            "user_occasion": user_occasion or "",
            "refinement_instructions": refinement_instructions or "",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.redis.lpush(key, str(history_item))
        await self.redis.ltrim(key, 0, 49)
        await self.redis.expire(key, 604800)  # 7 days