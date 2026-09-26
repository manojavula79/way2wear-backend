
"""
Way2Wear - Image Generation Service V3

Purpose:
- Generate outfit images from real clothing references
- Support optional person reference
- Support top + bottom clothing references
- Use OpenAI image editing/generation workflow
- Preserve existing Redis caching/history/rate limiting
- Return useful errors for moderation/API failures

IMPORTANT:
- Clothing images are sent to the OpenAI image API.
- The previous implementation prepared image_references but never
  actually included them in the API request.
"""

import os
import base64
import hashlib
import logging
import asyncio
import io
from datetime import datetime
from typing import Optional, Dict, Any, List

from openai import AsyncOpenAI
from redis import asyncio as aioredis

from app.services.image_fetch_service import resolve_image_to_base64


logger = logging.getLogger(__name__)


class ImageGenerationServiceV3:
    """
    Generate Way2Wear outfit images using clothing reference images.

    The important difference from the previous implementation is that
    the actual reference images are now supplied to the image API.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        # Use the documented image-generation model available to your API project.
        #
        # If your project specifically provides another image model,
        # change this through the OPENAI_IMAGE_MODEL environment variable.
        self.IMAGE_MODEL = os.getenv(
            "OPENAI_IMAGE_MODEL",
            "gpt-image-2"
        )

        self.IMAGE_SIZE = os.getenv(
            "OPENAI_IMAGE_SIZE",
            "1024x1024"
        )

        self.IMAGE_QUALITY = os.getenv(
            "OPENAI_IMAGE_QUALITY",
            "medium"
        )

        logger.info(
            "✅ Initialized ImageGenerationServiceV3 "
            f"with model: {self.IMAGE_MODEL}"
        )

    # ============================================================
    # PUBLIC API
    # ============================================================

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
        Generate a complete outfit image.

        Inputs:
        - person_image:
            Optional user/person reference image in base64 or resolvable URL.

        - product_top_image:
            Top/shirt/hoodie product image.

        - product_bottom_image:
            Pants/jeans/joggers/etc. product image.

        Returns:
            {
                "success": True,
                "image_url": "...",
                ...
            }

        or

            {
                "success": False,
                "error": "...",
                "error_code": "..."
            }
        """

        logger.info(
            f"📸 Generating outfit V4 for user {user_id}"
        )

        # --------------------------------------------------------
        # Resolve input images
        # --------------------------------------------------------

        try:
            (
                person_image,
                product_top_image,
                product_bottom_image,
            ) = await asyncio.gather(
                resolve_image_to_base64(
                    person_image,
                    self.redis
                ),
                resolve_image_to_base64(
                    product_top_image,
                    self.redis
                ),
                resolve_image_to_base64(
                    product_bottom_image,
                    self.redis
                ),
            )

        except Exception as e:
            logger.exception(
                "❌ Failed to resolve input images"
            )

            return {
                "success": False,
                "error": f"Failed to resolve reference images: {str(e)}",
                "error_code": "REFERENCE_IMAGE_ERROR",
            }

        # --------------------------------------------------------
        # Rate limit
        # --------------------------------------------------------

        allowed, limit_msg = await self.check_rate_limit(user_id)

        if not allowed:
            logger.warning(
                f"Rate limit for user {user_id}: {limit_msg}"
            )

            return {
                "success": False,
                "error": limit_msg,
                "error_code": "RATE_LIMITED",
            }

        # --------------------------------------------------------
        # Cache
        # --------------------------------------------------------

        cache_key_base = self._build_cache_key(
            outfit_desc=outfit_description,
            user_context=user_context,
            skin_tone=user_skin_tone,
            occasion=user_occasion,
            has_person=bool(person_image),
            has_top=bool(product_top_image),
            has_bottom=bool(product_bottom_image),
            top_image=product_top_image,
            bottom_image=product_bottom_image,
            person_image=person_image,
            refinement_instructions=refinement_instructions,
        )

        cache_hash = hashlib.md5(
            cache_key_base.encode("utf-8")
        ).hexdigest()

        if use_cache:
            cached_url = await self.get_cached_image(cache_hash)

            if cached_url:
                logger.info(
                    f"✅ Using cached image for user {user_id}"
                )

                return {
                    "success": True,
                    "image_url": cached_url,
                    "cached": True,
                    "prompt_used": None,
                }

        # --------------------------------------------------------
        # Build prompt
        # --------------------------------------------------------

        try:
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

            logger.info(
                f"🎨 Master prompt built, length: {len(prompt)}"
            )

            logger.info(
                f"📝 Prompt preview: {prompt[:500]}..."
            )

        except Exception as e:
            logger.exception(
                "❌ Failed to build image prompt"
            )

            return {
                "success": False,
                "error": f"Failed to build prompt: {str(e)}",
                "error_code": "PROMPT_BUILD_ERROR",
            }

        # --------------------------------------------------------
        # Log references
        # --------------------------------------------------------

        logger.info(
            "📸 Image references prepared: "
            f"person={bool(person_image)}, "
            f"top={bool(product_top_image)}, "
            f"bottom={bool(product_bottom_image)}"
        )

        # --------------------------------------------------------
        # Generate image
        # --------------------------------------------------------

        try:
            response = await self._generate_with_images(
                prompt=prompt,
                person_image=person_image,
                product_top_image=product_top_image,
                product_bottom_image=product_bottom_image,
            )

            if response and response.get("success"):
                image_url = response.get("image_url")

                # ------------------------------------------------
                # Cache
                # ------------------------------------------------

                await self.cache_image(
                    cache_hash,
                    image_url,
                    prompt
                )

                # ------------------------------------------------
                # History
                # ------------------------------------------------

                await self.save_to_history(
                    user_id=user_id,
                    outfit_description=outfit_description,
                    image_url=image_url,
                    prompt=prompt,
                    has_images=bool(
                        person_image
                        or product_top_image
                        or product_bottom_image
                    ),
                    user_skin_tone=user_skin_tone,
                    user_occasion=user_occasion,
                    refinement_instructions=refinement_instructions,
                )

                return {
                    "success": True,
                    "image_url": image_url,
                    "prompt_used": prompt,
                    "cached": False,
                    "image_references_used": sum(
                        bool(x)
                        for x in [
                            person_image,
                            product_top_image,
                            product_bottom_image,
                        ]
                    ),
                }

            error_msg = (
                response.get("error", "Unknown error")
                if response
                else "No response"
            )

            error_code = (
                response.get("error_code")
                if response
                else "IMAGE_GENERATION_ERROR"
            )

            logger.error(
                f"❌ Generation failed: {error_msg}"
            )

            return {
                "success": False,
                "error": error_msg,
                "error_code": error_code,
            }

        except Exception as e:
            logger.exception(
                "❌ Exception during image generation"
            )

            return {
                "success": False,
                "error": str(e),
                "error_code": "IMAGE_GENERATION_EXCEPTION",
            }

    # ============================================================
    # REFINEMENT
    # ============================================================

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

        allowed, limit_msg = await self.check_rate_limit(user_id)

        if not allowed:
            return {
                "success": False,
                "error": limit_msg,
                "error_code": "RATE_LIMITED",
            }

        logger.info(
            f"🔄 Regenerating with refinement: "
            f"{refinement_instructions}"
        )

        try:
            (
                person_image,
                product_top_image,
                product_bottom_image,
            ) = await asyncio.gather(
                resolve_image_to_base64(
                    person_image,
                    self.redis
                ),
                resolve_image_to_base64(
                    product_top_image,
                    self.redis
                ),
                resolve_image_to_base64(
                    product_bottom_image,
                    self.redis
                ),
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

            logger.info(
                f"📝 Refinement prompt: "
                f"{refinement_instructions}"
            )

            response = await self._generate_with_images(
                prompt=prompt,
                person_image=person_image,
                product_top_image=product_top_image,
                product_bottom_image=product_bottom_image,
            )

            if response and response.get("success"):

                image_url = response.get("image_url")

                await self.save_to_history(
                    user_id=user_id,
                    outfit_description=outfit_description,
                    image_url=image_url,
                    prompt=prompt,
                    has_images=bool(
                        person_image
                        or product_top_image
                        or product_bottom_image
                    ),
                    user_skin_tone=user_skin_tone,
                    user_occasion=user_occasion,
                    refinement_instructions=refinement_instructions,
                )

                return {
                    "success": True,
                    "image_url": image_url,
                    "prompt_used": prompt,
                    "refined": True,
                    "image_references_used": sum(
                        bool(x)
                        for x in [
                            person_image,
                            product_top_image,
                            product_bottom_image,
                        ]
                    ),
                }

            return {
                "success": False,
                "error": (
                    response.get("error")
                    if response
                    else "Failed"
                ),
                "error_code": (
                    response.get("error_code")
                    if response
                    else "IMAGE_GENERATION_ERROR"
                ),
            }

        except Exception as e:
            logger.exception(
                "❌ Error during refinement"
            )

            return {
                "success": False,
                "error": str(e),
                "error_code": "REFINEMENT_ERROR",
            }

    # ============================================================
    # PROMPT
    # ============================================================

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

        prompt_parts: List[str] = []

        # --------------------------------------------------------
        # Base objective
        # --------------------------------------------------------

        prompt_parts.append(
            "Create a photorealistic full-body fashion catalog image "
            "of an adult model wearing the requested outfit."
        )

        # --------------------------------------------------------
        # Person reference
        # --------------------------------------------------------

        if has_person_image:
            prompt_parts.append(
                "Use the supplied person image as the person reference. "
                "Preserve the person's recognizable appearance, hairstyle, "
                "skin tone and general body proportions."
            )
        else:
            prompt_parts.append(
                "Use an adult fashion model."
            )

        # --------------------------------------------------------
        # Clothing references
        # --------------------------------------------------------

        if has_top_image:
            prompt_parts.append(
                "Use the supplied TOP clothing image as the visual "
                "reference for the top garment. Preserve its visible "
                "color, print, graphic, pattern, silhouette, sleeves, "
                "collar, fabric appearance, fit and overall design."
            )

        if has_bottom_image:
            prompt_parts.append(
                "Use the supplied BOTTOM clothing image as the visual "
                "reference for the bottom garment. Preserve its visible "
                "color, wash, pattern, cut, silhouette, pockets, fabric "
                "appearance, fit and overall design."
            )

        # --------------------------------------------------------
        # Outfit description
        # --------------------------------------------------------

        if outfit_description:
            prompt_parts.append(
                f"Requested outfit: {outfit_description}."
            )

        # --------------------------------------------------------
        # User context
        # --------------------------------------------------------

        if user_context:
            prompt_parts.append(
                f"User context: {user_context}."
            )

        # --------------------------------------------------------
        # Skin tone
        # --------------------------------------------------------

        if user_skin_tone:
            prompt_parts.append(
                f"Skin tone preference: {user_skin_tone}."
            )

        # --------------------------------------------------------
        # Preferred colors
        # --------------------------------------------------------

        if user_color_preference:
            colors = ", ".join(
                user_color_preference[:5]
            )

            prompt_parts.append(
                f"Preferred colors: {colors}."
            )

        # --------------------------------------------------------
        # Height
        # --------------------------------------------------------

        if user_height:
            prompt_parts.append(
                f"Approximate height: {user_height}. "
                "Use natural realistic body proportions."
            )

        # --------------------------------------------------------
        # Occasion
        # --------------------------------------------------------

        if user_occasion:
            prompt_parts.append(
                f"Occasion: {user_occasion}."
            )

        # --------------------------------------------------------
        # Refinement
        # --------------------------------------------------------

        if refinement_instructions:
            prompt_parts.append(
                "Apply the following user-requested refinement while "
                "keeping the selected clothing consistent: "
                f"{refinement_instructions}"
            )

        # --------------------------------------------------------
        # Style
        # --------------------------------------------------------

        prompt_parts.append(
            f"Style: {style_hint}."
        )

        prompt_parts.append(
            "Use realistic lighting, natural fabric folds, "
            "realistic shadows and accurate garment proportions."
        )

        prompt_parts.append(
            "Show the complete outfit clearly from head to toe "
            "in a neutral natural standing pose."
        )

        prompt_parts.append(
            "Use a clean professional fashion-catalog composition."
        )

        final_prompt = " ".join(prompt_parts)

        # Keep prompt reasonably sized.
        if len(final_prompt) > 3000:
            final_prompt = final_prompt[:3000]

        return final_prompt

    # ============================================================
    # IMAGE GENERATION
    # ============================================================

    async def _generate_with_images(
        self,
        prompt: str,
        person_image: Optional[str],
        product_top_image: Optional[str],
        product_bottom_image: Optional[str],
    ) -> Dict[str, Any]:

        logger.info(
            f"🚀 Calling {self.IMAGE_MODEL} "
            "with clothing/person references"
        )

        try:
            # ----------------------------------------------------
            # Build actual image inputs
            # ----------------------------------------------------

            image_files = []

            if person_image:
                image_files.append(
                    (
                        "person.png",
                        self._base64_to_bytes(person_image),
                        "image/png",
                    )
                )

                logger.info(
                    "✅ Person reference attached to API request"
                )

            if product_top_image:
                image_files.append(
                    (
                        "top.png",
                        self._base64_to_bytes(product_top_image),
                        "image/png",
                    )
                )

                logger.info(
                    "✅ Top reference attached to API request"
                )

            if product_bottom_image:
                image_files.append(
                    (
                        "bottom.png",
                        self._base64_to_bytes(product_bottom_image),
                        "image/png",
                    )
                )

                logger.info(
                    "✅ Bottom reference attached to API request"
                )

            # ----------------------------------------------------
            # IMPORTANT
            #
            # The previous implementation created:
            #
            #     message_content
            #
            # but never sent it.
            #
            # Here the actual reference files are supplied to the
            # image edit API.
            # ----------------------------------------------------

            if not image_files:
                logger.info(
                    "ℹ️ No reference images supplied; "
                    "using text-only image generation"
                )

                response = await self.client.images.generate(
                    model=self.IMAGE_MODEL,
                    prompt=prompt,
                    size=self.IMAGE_SIZE,
                    quality=self.IMAGE_QUALITY,
                    n=1,
                )

            else:
                logger.info(
                    f"📎 Sending {len(image_files)} reference "
                    "image(s) to image edit API"
                )

                # OpenAI image edit endpoint accepts image files
                # together with the generation prompt.
                #
                # Use a single file for the common case and a list
                # when the SDK supports multiple image inputs.

                if len(image_files) == 1:
                    response = await self.client.images.edit(
                        model=self.IMAGE_MODEL,
                        image=image_files[0],
                        prompt=prompt,
                        size=self.IMAGE_SIZE,
                        quality=self.IMAGE_QUALITY,
                )
                else:
                    response = await self.client.images.edit(
                        model=self.IMAGE_MODEL,
                        image=image_files,
                        prompt=prompt,
                        size=self.IMAGE_SIZE,
                        quality=self.IMAGE_QUALITY,
                    )

            # ----------------------------------------------------
            # Response handling
            # ----------------------------------------------------

            logger.info(
                f"✅ Response received from {self.IMAGE_MODEL}"
            )

            if not response:
                return {
                    "success": False,
                    "error": "OpenAI returned an empty response.",
                    "error_code": "EMPTY_RESPONSE",
                }

            if not response.data:
                return {
                    "success": False,
                    "error": "OpenAI returned no image data.",
                    "error_code": "NO_IMAGE_DATA",
                }

            image_data = response.data[0]

            b64_data = getattr(
                image_data,
                "b64_json",
                None
            )

            if not b64_data:
                return {
                    "success": False,
                    "error": "OpenAI returned no b64_json image data.",
                    "error_code": "EMPTY_IMAGE_DATA",
                }

            image_url = (
                f"data:image/png;base64,{b64_data}"
            )

            logger.info(
                "✅ Image generated successfully"
            )

            return {
                "success": True,
                "image_url": image_url,
            }

        except Exception as e:

            error_msg = str(e)

            logger.error(
                f"❌ OpenAI image API failed: {error_msg}"
            )

            # ----------------------------------------------------
            # Moderation
            # ----------------------------------------------------

            if (
                "moderation_blocked" in error_msg
                or "safety system" in error_msg
            ):
                logger.warning(
                    "⚠️ OpenAI image output was blocked "
                    "by the safety system."
                )

                return {
                    "success": False,
                    "error": (
                        "The generated image was blocked by "
                        "the image safety system."
                    ),
                    "error_code": "IMAGE_MODERATION_BLOCKED",
                }

            # ----------------------------------------------------
            # Bad request
            # ----------------------------------------------------

            if (
                "400 Bad Request" in error_msg
                or "Error code: 400" in error_msg
            ):
                return {
                    "success": False,
                    "error": (
                        "OpenAI rejected the image generation request. "
                        f"{error_msg}"
                    ),
                    "error_code": "OPENAI_BAD_REQUEST",
                }

            # ----------------------------------------------------
            # Generic API failure
            # ----------------------------------------------------

            return {
                "success": False,
                "error": error_msg,
                "error_code": "OPENAI_IMAGE_API_ERROR",
            }

    # ============================================================
    # IMAGE HELPERS
    # ============================================================

    @staticmethod
    def _base64_to_bytes(value: str) -> bytes:
        """
        Convert base64 image data into bytes.

        Handles:
        - raw base64
        - data:image/png;base64,...
        - data:image/jpeg;base64,...
        """

        if not value:
            raise ValueError(
                "Empty image data"
            )

        if value.startswith("data:"):
            try:
                value = value.split(
                    ",",
                    1
                )[1]
            except IndexError:
                raise ValueError(
                    "Invalid data URL"
                )

        # Remove whitespace/newlines that sometimes appear
        # in base64 strings.
        value = "".join(
            value.split()
        )

        try:
            return base64.b64decode(
                value,
                validate=True
            )
        except Exception as e:
            raise ValueError(
                f"Invalid base64 image data: {e}"
            )

    # ============================================================
    # CACHE KEY
    # ============================================================

    def _build_cache_key(
        self,
        outfit_desc: str,
        user_context: str,
        skin_tone: Optional[str],
        occasion: Optional[str],
        has_person: bool,
        has_top: bool,
        has_bottom: bool,
        person_image: Optional[str] = None,
        top_image: Optional[str] = None,
        bottom_image: Optional[str] = None,
        refinement_instructions: Optional[str] = None,
    ) -> str:
        """
        Build a cache key that includes image fingerprints.

        This is important because two different Amazon products
        can otherwise produce the same cache key if only the
        boolean `has_top=True` / `has_bottom=True` is used.
        """

        def image_fingerprint(
            image: Optional[str]
        ) -> str:

            if not image:
                return "none"

            try:
                return hashlib.sha256(
                    image.encode("utf-8")
                ).hexdigest()[:24]

            except Exception:
                return "present"

        key_parts = [
            outfit_desc or "",
            user_context or "",
            skin_tone or "none",
            occasion or "none",
            refinement_instructions or "none",
            f"person={has_person}",
            f"top={has_top}",
            f"bottom={has_bottom}",
            f"person_img={image_fingerprint(person_image)}",
            f"top_img={image_fingerprint(top_image)}",
            f"bottom_img={image_fingerprint(bottom_image)}",
        ]

        return "|".join(key_parts)

    # ============================================================
    # RATE LIMIT
    # ============================================================

    async def check_rate_limit(
        self,
        user_id: str
    ) -> tuple[bool, str]:

        key = (
            f"outfit:rate_limit:{user_id}"
        )

        count = await self.redis.get(key)

        if count and int(count) >= 20:
            return (
                False,
                "Limit reached (20/hour). Try again later."
            )

        return True, "OK"

    # ============================================================
    # CACHE
    # ============================================================

    async def get_cached_image(
        self,
        cache_hash: str
    ) -> Optional[str]:

        key = (
            f"outfit:image:{cache_hash}"
        )

        return await self.redis.get(key)

    async def cache_image(
        self,
        cache_hash: str,
        image_url: str,
        prompt: str,
    ) -> None:

        key = (
            f"outfit:image:{cache_hash}"
        )

        await self.redis.setex(
            key,
            86400,
            image_url
        )

        logger.info(
            "✅ Image cached for 24h"
        )

    # ============================================================
    # HISTORY
    # ============================================================

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

        key = (
            f"outfit:history:{user_id}"
        )

        history_item = {
            "outfit_description": outfit_description,
            "image_url": image_url[:100],
            "prompt": prompt[:500],
            "has_images": has_images,
            "user_skin_tone": (
                user_skin_tone or ""
            ),
            "user_occasion": (
                user_occasion or ""
            ),
            "refinement_instructions": (
                refinement_instructions or ""
            ),
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.redis.lpush(
            key,
            str(history_item)
        )

        await self.redis.ltrim(
            key,
            0,
            49
        )

        await self.redis.expire(
            key,
            604800
        )
