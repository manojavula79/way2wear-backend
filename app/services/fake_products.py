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
    product_type: str,
    occasion: str,
    gender: str,
    max_price: float,
    color_preference: Optional[str] = None,
    exclude_ids: Optional[list] = None,
) -> Optional[dict]:
    exclude_ids = exclude_ids or []
    pool = FAKE_PRODUCTS or _SEED

    candidates = [
        p for p in pool
        if p["type"] == product_type
        and (p["gender"] == gender or p["gender"] == "unisex")
        and p["id"] not in exclude_ids
    ]
    if not candidates:
        candidates = [
            p for p in pool
            if p["type"] == product_type and p["id"] not in exclude_ids
        ]
    if not candidates:
        return None

    def score(p):
        s = 0
        if occasion in (p.get("occasions") or []):              s += 30
        if max_price and p.get("price", 0) <= max_price:        s += 20
        if color_preference and color_preference.lower() in (p.get("color", "").lower()): s += 15
        s += random.randint(0, 8)   # variety so it's not always identical
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]


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
