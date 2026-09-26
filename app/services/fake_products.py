"""
WAY2WEAR — PRODUCT CATALOG

Loads real products from the Supabase `products` table into memory
and exposes deterministic product matching helpers.

This module is responsible ONLY for product retrieval/filtering.

It does NOT decide the final outfit styling.
OpenAI + orchestrator_v8.py handle the actual TOP + BOTTOM pairing.

Important:
- No random product selection.
- No shoe/accessory product generation for the AI outfit pipeline.
- Strict gender filtering.
- Real products come from Supabase.
"""

import json
import ssl
import logging
from typing import Optional

import asyncpg

from app.config import settings

logger = logging.getLogger("way2wear")


# ============================================================
# PRODUCT CACHE
# ============================================================

FAKE_PRODUCTS: list[dict] = []
_loaded = False


# ============================================================
# FALLBACK PRODUCTS
# ============================================================

_SEED = [
    {
        "id": "S1",
        "title": "Classic White Shirt",
        "brand": "Roadster",
        "type": "top",
        "gender": "male",
        "color": "white",
        "color_hex": "#F5F5F0",
        "price": 999,
        "occasions": ["office", "casual", "formal"],
        "style": ["classic"],
        "image": None,
        "url": "#product-S1",
    },
    {
        "id": "S2",
        "title": "Slim Fit Blue Jeans",
        "brand": "Levi's",
        "type": "bottom",
        "gender": "male",
        "color": "blue",
        "color_hex": "#2C4A8C",
        "price": 1799,
        "occasions": ["casual", "date"],
        "style": ["casual"],
        "image": None,
        "url": "#product-S2",
    },
    {
        "id": "S3",
        "title": "Floral Summer Top",
        "brand": "W",
        "type": "top",
        "gender": "female",
        "color": "pink",
        "color_hex": "#E8A0A8",
        "price": 899,
        "occasions": ["casual", "party"],
        "style": ["feminine"],
        "image": None,
        "url": "#product-S3",
    },
    {
        "id": "S4",
        "title": "High Waist Trousers",
        "brand": "Aurelia",
        "type": "bottom",
        "gender": "female",
        "color": "black",
        "color_hex": "#1A1A1A",
        "price": 1299,
        "occasions": ["office", "formal"],
        "style": ["classic"],
        "image": None,
        "url": "#product-S4",
    },
]


# ============================================================
# DATABASE
# ============================================================

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def load_products_from_db() -> None:
    """
    Load all products from Supabase into the in-memory catalog.

    This should be called once during application startup.
    """

    global FAKE_PRODUCTS, _loaded

    db_url = (
        settings.DATABASE_URL
        .replace("postgresql+asyncpg://", "postgresql://")
        .split("?")[0]
    )

    try:
        conn = await asyncpg.connect(
            db_url,
            ssl=_ssl_ctx(),
            statement_cache_size=0,
        )

        rows = await conn.fetch("SELECT * FROM products")
        await conn.close()

        items = []

        for r in rows:
            items.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "brand": r["brand"],
                    "type": r["type"],
                    "gender": r["gender"],
                    "color": r["color"],
                    "color_hex": r["color_hex"],
                    "price": r["price"],
                    "occasions": (
                        json.loads(r["occasions"])
                        if isinstance(r["occasions"], str)
                        else (r["occasions"] or [])
                    ),
                    "style": (
                        json.loads(r["style"])
                        if isinstance(r["style"], str)
                        else (r["style"] or [])
                    ),
                    "image": r["image"],
                    "url": r["url"],
                }
            )

        if items:
            FAKE_PRODUCTS = items
            _loaded = True

            logger.info(
                "Loaded %s products from database",
                len(items),
            )
        else:
            FAKE_PRODUCTS = list(_SEED)

            logger.warning(
                "products table is empty — using seed products"
            )

    except Exception as e:
        FAKE_PRODUCTS = list(_SEED)

        logger.warning(
            "Could not load products from DB (%s) — using seed products",
            e,
        )


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def _normalize(value) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def _contains(value, target) -> bool:
    value = _normalize(value)
    target = _normalize(target)

    if not value or not target:
        return False

    return target in value


def _gender_allowed(
    product_gender: str,
    requested_gender: str,
    allowed_genders: Optional[list[str]],
) -> bool:

    pg = _normalize(product_gender)
    rg = _normalize(requested_gender)

    if allowed_genders is not None:
        return pg in {
            _normalize(g)
            for g in allowed_genders
        }

    return pg in {rg, "unisex"}


# ============================================================
# DETERMINISTIC PRODUCT MATCH
# ============================================================

def find_best_match(
    item_type: str,
    occasion: str,
    gender: str,
    max_price: int,
    color_preference: str = None,
    exclude_ids: list = None,
    allowed_genders: list = None,
    style_preference: str = None,
) -> dict:
    """
    Return the highest-scoring REAL product.

    IMPORTANT:
    There is intentionally NO random score.

    Repeated calls with the same inputs produce deterministic results.
    """

    exclude_ids = exclude_ids or []

    candidates = []

    requested_type = _normalize(item_type)
    requested_occasion = _normalize(occasion)
    requested_gender = _normalize(gender)
    requested_style = _normalize(style_preference)

    try:
        max_price = int(max_price)
    except Exception:
        max_price = 5000

    for product in FAKE_PRODUCTS:

        product_id = str(product.get("id", ""))

        # Already used
        if product_id in {str(x) for x in exclude_ids}:
            continue

        # TOP / BOTTOM
        if _normalize(product.get("type")) != requested_type:
            continue

        # Gender
        if not _gender_allowed(
            product.get("gender"),
            requested_gender,
            allowed_genders,
        ):
            continue

        # Price
        try:
            price = float(product.get("price") or 0)
        except Exception:
            price = 0

        if price > max_price:
            continue

        score = 0.0

        # ----------------------------------------------------
        # Occasion
        # ----------------------------------------------------

        occasions = [
            _normalize(x)
            for x in (product.get("occasions") or [])
        ]

        if requested_occasion in occasions:
            score += 40

        # Related occasion aliases
        if requested_occasion == "wedding":
            if "formal" in occasions or "festival" in occasions:
                score += 15

        elif requested_occasion == "party":
            if "date" in occasions or "casual" in occasions:
                score += 8

        elif requested_occasion == "office":
            if "formal" in occasions:
                score += 12

        elif requested_occasion == "festival":
            if "wedding" in occasions or "traditional" in occasions:
                score += 12

        # ----------------------------------------------------
        # Style
        # ----------------------------------------------------

        styles = [
            _normalize(x)
            for x in (product.get("style") or [])
        ]

        if requested_style:
            if requested_style in styles:
                score += 25

            if any(
                requested_style in s or s in requested_style
                for s in styles
            ):
                score += 10

        # ----------------------------------------------------
        # Color
        # ----------------------------------------------------

        product_color = _normalize(product.get("color"))

        if color_preference:
            preferred = _normalize(color_preference)

            if product_color == preferred:
                score += 20
            elif preferred in product_color:
                score += 10

        # ----------------------------------------------------
        # Price positioning
        # ----------------------------------------------------

        # Prefer products that use a reasonable portion of the budget
        target_price = max_price * 0.65

        if target_price > 0:
            price_distance = abs(price - target_price)

            price_score = max(
                0,
                15 - (price_distance / max(target_price, 1)) * 15,
            )

            score += price_score

        # ----------------------------------------------------
        # Stable tie breaker
        # ----------------------------------------------------

        # Do NOT use random.
        # Product ID creates deterministic ordering.
        stable_key = product_id

        candidates.append(
            (
                score,
                stable_key,
                product,
            )
        )

    # --------------------------------------------------------
    # No candidate
    # --------------------------------------------------------

    if not candidates:

        # If strict gender was used, allow unisex as last resort
        if (
            allowed_genders
            and "unisex" not in [
                _normalize(g)
                for g in allowed_genders
            ]
        ):
            return find_best_match(
                item_type=item_type,
                occasion=occasion,
                gender=gender,
                max_price=max_price,
                color_preference=color_preference,
                exclude_ids=exclude_ids,
                allowed_genders=["unisex"],
                style_preference=style_preference,
            )

        return {
            "id": "FALLBACK",
            "title": f"No {item_type} found",
            "brand": None,
            "type": item_type,
            "gender": gender,
            "color": None,
            "color_hex": None,
            "price": 0,
            "occasions": [],
            "style": [],
            "image": None,
            "url": None,
        }

    # Highest score first.
    # Product ID provides deterministic tie-breaking.
    candidates.sort(
        key=lambda x: (-x[0], x[1])
    )

    return candidates[0][2]


# ============================================================
# MULTIPLE CANDIDATES
# ============================================================

def find_candidate_products(
    item_type: str,
    occasion: str,
    gender: str,
    max_price: int,
    count: int = 10,
    color_preference: str = None,
    style_preference: str = None,
) -> list[dict]:
    """
    Return multiple deterministic real products.

    The AI uses these candidates to make the final styling decision.
    """

    candidates = []

    used_ids = []

    allowed_genders = [gender]

    if gender != "unisex":
        allowed_genders.append("unisex")

    for _ in range(count):

        product = find_best_match(
            item_type=item_type,
            occasion=occasion,
            gender=gender,
            max_price=max_price,
            color_preference=color_preference,
            exclude_ids=used_ids,
            allowed_genders=allowed_genders,
            style_preference=style_preference,
        )

        if not product:
            break

        product_id = str(product.get("id"))

        if product_id == "FALLBACK":
            break

        if product_id in used_ids:
            break

        used_ids.append(product_id)
        candidates.append(product)

    return candidates


# ============================================================
# LEGACY FUNCTION
# ============================================================

def build_outfit_from_catalog(
    occasion: str,
    gender: str,
    budget: dict,
) -> list[dict]:
    """
    Backward-compatible helper.

    NOTE:
    The new AI pipeline does NOT use this function.

    It is kept so existing code does not crash.
    """

    outfits = []

    used_top = []
    used_bottom = []

    for _ in range(2):

        top = find_best_match(
            item_type="top",
            occasion=occasion,
            gender=gender,
            max_price=budget.get("top_budget", 2000),
            exclude_ids=used_top,
        )

        bottom = find_best_match(
            item_type="bottom",
            occasion=occasion,
            gender=gender,
            max_price=budget.get("bottom_budget", 2000),
            color_preference=None,
            exclude_ids=used_bottom,
        )

        if not top or not bottom:
            continue

        if top.get("id") == "FALLBACK":
            continue

        if bottom.get("id") == "FALLBACK":
            continue

        used_top.append(top["id"])
        used_bottom.append(bottom["id"])

        outfits.append(
            {
                "top": top,
                "bottom": bottom,
            }
        )

    return outfits