"""
Image resolution utility — converts an image reference (either an
already-base64 data URL, or a remote http(s) URL) into a base64 data URL
suitable for sending to OpenAI's image API.

WHY THIS EXISTS
---------------
Browsers cannot read the raw bytes of a cross-origin image (e.g. Amazon's
CDN) via fetch()/XHR — the CORS preflight fails because Amazon doesn't
send back an Access-Control-Allow-Origin header for arbitrary origins.
This is true even though <img src="..."> renders the same image fine —
*displaying* an image and *reading its bytes* are subject to different
rules in the browser.

A server making the same request has no such restriction — it's a plain
server-to-server HTTP call. So this conversion has to happen here, not
in Angular.

File: app/services/image_fetch_service.py
"""

import base64
import hashlib
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10.0
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days — product photos rarely change
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB safety cap

# Some CDNs (Amazon included) reject requests that don't look like a
# real browser — a bare httpx default User-Agent can get refused.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/*",
}


async def resolve_image_to_base64(
    image_ref: Optional[str],
    redis_client=None,
) -> Optional[str]:
    """
    Accepts either:
      - an already-base64 data URL (e.g. a locally-uploaded profile photo)
        → returned as-is, no network call
      - a plain http(s) URL (e.g. an Amazon product photo)
        → fetched and base64-encoded server-side

    Returns None if the input is empty, or if fetching/encoding fails —
    callers should treat that as "skip this image" rather than fail the
    whole generation.
    """
    if not image_ref:
        return None

    if image_ref.startswith("data:"):
        return image_ref  # already base64 — nothing to do

    if not image_ref.startswith("http://") and not image_ref.startswith("https://"):
        logger.warning(f"Unrecognized image reference format, skipping: {image_ref[:80]}")
        return None

    return await _fetch_url_as_base64(image_ref, redis_client)


async def _fetch_url_as_base64(url: str, redis_client=None) -> Optional[str]:
    cache_key = None

    if redis_client is not None:
        cache_key = f"img_b64:{hashlib.sha256(url.encode()).hexdigest()}"
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"✅ Image cache hit: {url[:60]}...")
                return cached if isinstance(cached, str) else cached.decode()
        except Exception as e:
            logger.warning(f"Redis lookup failed for image cache (continuing without cache): {e}")

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers=REQUEST_HEADERS)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            logger.warning(f"URL did not return an image ({content_type}): {url}")
            return None

        if len(response.content) > MAX_IMAGE_BYTES:
            logger.warning(f"Image too large ({len(response.content)} bytes), skipping: {url}")
            return None

        encoded = base64.b64encode(response.content).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded}"

        if redis_client is not None and cache_key:
            try:
                await redis_client.set(cache_key, data_url, ex=CACHE_TTL_SECONDS)
            except Exception as e:
                logger.warning(f"Failed to cache fetched image: {e}")

        logger.info(f"✅ Fetched & encoded image ({len(response.content)} bytes): {url[:60]}...")
        return data_url

    except httpx.HTTPStatusError as e:
        logger.warning(f"Image fetch failed ({e.response.status_code}): {url}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"Image fetch timed out after {FETCH_TIMEOUT_SECONDS}s: {url}")
        return None
    except Exception as e:
        logger.warning(f"Image fetch failed: {url} — {e}")
        return None