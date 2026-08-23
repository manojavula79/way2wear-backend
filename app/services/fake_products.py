"""
WAY2WEAR — PRODUCT CATALOG (database-backed)

Loads products from the Supabase `products` table (populated by
scripts/load_products.py) into memory once at startup, then serves
them through the same functions the AI orchestrator already calls:
    find_best_match(...)
    build_outfit_from_catalog(...)
    FAKE_PRODUCTS  (list, kept for backward compatibility)

If the DB table is empty or unreachable, it falls back to a tiny
built-in seed list so the app never crashes.
"""

import json
import ssl
import logging
import random
from typing import Optional

import asyncpg
from app.config import settings

logger = logging.getLogger("way2wear")

# In-memory product cache (loaded once)
FAKE_PRODUCTS: list[dict] = []
_loaded = False


# ── Minimal seed fallback (only if DB empty) ──────────
_SEED = [
    {"id": "S1", "title": "Classic White Shirt", "brand": "Roadster", "type": "top",
     "gender": "male", "color": "white", "color_hex": "#F5F5F0", "price": 999,
     "occasions": ["office", "casual", "formal"], "style": ["classic"],
     "image": None, "url": "#product-S1"},
    {"id": "S2", "title": "Slim Fit Blue Jeans", "brand": "Levi's", "type": "bottom",
     "gender": "male", "color": "blue", "color_hex": "#2C4A8C", "price": 1799,
     "occasions": ["casual", "date"], "style": ["casual"],
     "image": None, "url": "#product-S2"},
    {"id": "S3", "title": "Floral Summer Top", "brand": "W", "type": "top",
     "gender": "female", "color": "pink", "color_hex": "#E8A0A8", "price": 899,
     "occasions": ["casual", "party"], "style": ["feminine"],
     "image": None, "url": "#product-S3"},
    {"id": "S4", "title": "High Waist Trousers", "brand": "Aurelia", "type": "bottom",
     "gender": "female", "color": "black", "color_hex": "#1A1A1A", "price": 1299,
     "occasions": ["office", "formal"], "style": ["classic"],
     "image": None, "url": "#product-S4"},
]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def load_products_from_db() -> None:
    """Load all products from Supabase into FAKE_PRODUCTS. Call once on startup."""
    global FAKE_PRODUCTS, _loaded

    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]
    try:
        conn = await asyncpg.connect(db_url, ssl=_ssl_ctx(), statement_cache_size=0)
        rows = await conn.fetch("SELECT * FROM products")
        await conn.close()

        items = []
        for r in rows:
            items.append({
                "id":        r["id"],
                "title":     r["title"],
                "brand":     r["brand"],
                "type":      r["type"],
                "gender":    r["gender"],
                "color":     r["color"],
                "color_hex": r["color_hex"],
                "price":     r["price"],
                "occasions": json.loads(r["occasions"]) if isinstance(r["occasions"], str) else (r["occasions"] or []),
                "style":     json.loads(r["style"]) if isinstance(r["style"], str) else (r["style"] or []),
                "image":     r["image"],
                "url":       r["url"],
            })

        if items:
            FAKE_PRODUCTS = items
            _loaded = True
            logger.info(f"✅ Loaded {len(items)} products from database")
        else:
            FAKE_PRODUCTS = _SEED
            logger.warning("⚠️  products table empty — using seed fallback")
    except Exception as e:
        FAKE_PRODUCTS = _SEED
        logger.warning(f"⚠️  Could not load products from DB ({e}) — using seed fallback")


# ── Lookup helpers (same signatures as before) ────────

def find_best_match(
    item_type: str,
    occasion: str,
    gender: str,
    max_price: int,
    color_preference: str = None,
    exclude_ids: list = None,
    allowed_genders: list = None,  # NEW: strict gender list
) -> dict:
    """
    Find the best product match from the catalogue.
    
    Args:
        item_type: 'top' / 'bottom' / 'accessory'
        occasion: 'casual' / 'office' / 'party' / etc.
        gender: 'male' / 'female' / 'unisex'
        max_price: budget in rupees
        color_preference: optional hex or name to match
        exclude_ids: list of IDs to skip (already used)
        allowed_genders: NEW - strict list like ['female', 'unisex']. 
                         If provided, ONLY these genders are acceptable.
    """
    if exclude_ids is None:
        exclude_ids = []

    candidates = []
    for p in FAKE_PRODUCTS:
        # Skip if already used
        if p["id"] in exclude_ids:
            continue

        # Type match
        if p.get("type") != item_type:
            continue

        # STRICT GENDER: if allowed_genders is specified, ONLY match those
        if allowed_genders is not None:
            if p.get("gender") not in allowed_genders:
                continue
        else:
            # Old logic: gender + unisex
            if p.get("gender") not in (gender, "unisex"):
                continue

        # Price filter
        if p.get("price", 0) > max_price:
            continue

        # Scoring
        occasions = p.get("occasions", [])
        occasion_score = 30 if occasion in occasions else 0

        price = p.get("price", 1)
        price_score = max(0, 20 - abs(price - (max_price * 0.6)) / 100)

        color_score = 0
        if color_preference:
            prod_color = p.get("color", "").lower()
            pref_color = color_preference.lower()
            if prod_color == pref_color or pref_color in prod_color:
                color_score = 15

        random_score = __import__("random").randint(0, 10)
        total_score = occasion_score + price_score + color_score + random_score
        candidates.append((total_score, p))

    if not candidates:
        # Fallback: if no matches with strict gender, try unisex only
        if allowed_genders and "unisex" not in allowed_genders:
            return find_best_match(
                item_type, occasion, gender, max_price,
                color_preference, exclude_ids,
                allowed_genders=["unisex"],  # last resort
            )
        return {"id": "FALLBACK", "title": f"No {item_type} found", "price": 0}

    # Sort by score and return top match
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def build_outfit_from_catalog(occasion: str, gender: str, budget: dict) -> list[dict]:
    outfits = []
    used_top, used_bottom = [], []

    for _ in range(2):
        top = find_best_match("top", occasion, gender,
                              budget.get("top_budget", 2000), exclude_ids=used_top)
        bottom = find_best_match("bottom", occasion, gender,
                                 budget.get("bottom_budget", 2000), exclude_ids=used_bottom,
                                 color_preference=top["color"] if top else None)
        accessory = find_best_match("accessory", occasion, gender,
                                    budget.get("accessory_budget", 2000))
        if top:    used_top.append(top["id"])
        if bottom: used_bottom.append(bottom["id"])
        if top and bottom:
            outfits.append({"top": top, "bottom": bottom, "accessory": accessory})

    return outfits
