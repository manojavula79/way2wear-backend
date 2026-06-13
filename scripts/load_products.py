"""
WAY2WEAR — PRODUCT LOADER
Reads the Kaggle "Fashion Product Images (Small)" styles.csv,
selects ~2000 clothing items, maps them to Way2Wear's product
shape, and inserts them into a Supabase `products` table.

HOW TO RUN (from way2wear-backend folder, venv active):
    pip install pandas asyncpg
    # put styles.csv next to this script (scripts/styles.csv)
    python scripts/load_products.py

It reads DATABASE_URL from your .env automatically.
"""

import os
import csv
import re
import ssl
import asyncio
import random

import asyncpg
from dotenv import load_dotenv

# ── Load DATABASE_URL from backend .env ───────────────
load_dotenv()
RAW_DB_URL = os.getenv("DATABASE_URL", "")

# Convert SQLAlchemy URL → plain asyncpg URL
#   postgresql+asyncpg://...  →  postgresql://...
DB_URL = RAW_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
# strip any ?ssl=... query the driver added
DB_URL = DB_URL.split("?")[0]

CSV_PATH = os.path.join(os.path.dirname(__file__), "styles.csv")

TARGET_COUNT = 4000   # total products to load

# Per-type quotas — outfit pairing needs MANY tops & bottoms,
# accessories are optional extras so we cap them low.
QUOTA = {
    "top":       2000,
    "bottom":    1500,
    "accessory":  500,
}

# Myntra hosted image URL pattern (the dataset's own CDN)
IMG_URL = "http://assets.myntassets.com/v1/images/style/properties/{}_images.jpg"


# ── Map dataset categories → Way2Wear "type" ──────────
# articleType values in the dataset → top / bottom / accessory
TOP_TYPES = {
    "Shirts", "Tshirts", "Tops", "Kurtas", "Kurtis", "Sweaters",
    "Sweatshirts", "Jackets", "Blazers", "Tunics", "Waistcoat",
    "Suits", "Nehru Jackets", "Rain Jacket", "Shrug", "Blouse",
}
BOTTOM_TYPES = {
    "Jeans", "Trousers", "Track Pants", "Shorts", "Skirts",
    "Leggings", "Capris", "Churidar", "Salwar", "Patiala",
    "Tights", "Jeggings", "Rain Trousers", "Lounge Pants",
    "Trousers ", "Formal Trousers", "Casual Trousers",
    "Cargos", "Chinos", "Dhotis", "Palazzos", "Culottes",
    "Lounge Shorts", "Swim Bottoms",
}
ACCESSORY_TYPES = {
    "Casual Shoes", "Formal Shoes", "Sports Shoes", "Heels",
    "Flats", "Sandals", "Flip Flops", "Sneakers", "Belts",
    "Watches", "Sunglasses", "Handbags", "Wallets", "Caps",
    "Ties", "Backpacks", "Clutches", "Scarves", "Bracelet",
    "Earrings", "Necklace and Chains",
}

# Color name → hex
COLOR_HEX = {
    "white": "#F5F5F0", "black": "#1A1A1A", "navy blue": "#1F2D4E",
    "blue": "#2C4A8C", "grey": "#6B6B6B", "gray": "#6B6B6B",
    "charcoal": "#3D3D3D", "khaki": "#C3A882", "beige": "#D4C5A9",
    "cream": "#F5EDD6", "brown": "#8B5E3C", "maroon": "#7B2D2D",
    "red": "#C0392B", "pink": "#E8A0A8", "yellow": "#F4C430",
    "green": "#4A7C59", "olive": "#6B7C45", "purple": "#9B7FB5",
    "lavender": "#9B7FB5", "orange": "#E08A4B", "teal": "#2A7F7F",
    "gold": "#C9A85C", "silver": "#C0C0C0", "tan": "#C19A6B",
    "peach": "#F1C9A5", "magenta": "#C5288A", "burgundy": "#7B2D2D",
    "rust": "#A8501F", "mustard": "#D4A017", "coffee brown": "#6F4E37",
}

# Indian brand pools by gender for realistic naming
MALE_BRANDS   = ["Roadster", "Peter England", "Allen Solly", "Van Heusen", "Louis Philippe", "HRX", "Highlander"]
FEMALE_BRANDS = ["Global Desi", "Aurelia", "W", "Biba", "Fabindia", "Sangria", "Libas"]
UNISEX_BRANDS = ["H&M", "Levi's", "Puma", "Adidas", "Nike", "Mango"]


def hex_for_color(color: str) -> str:
    c = (color or "").strip().lower()
    return COLOR_HEX.get(c, "#888888")


def occasions_for(usage: str, season: str, article: str) -> list[str]:
    """Derive Way2Wear occasion tags from dataset 'usage' + article type."""
    u = (usage or "").lower()
    occ = set()
    if "formal" in u:              occ.update(["office", "formal"])
    if "casual" in u:              occ.update(["casual", "travel"])
    if "party" in u:               occ.update(["party", "date"])
    if "ethnic" in u:              occ.update(["wedding", "festival"])
    if "sports" in u:              occ.update(["gym", "casual"])
    if "smart casual" in u:        occ.update(["office", "date", "casual"])
    # Kurtas / ethnic wear → weddings
    if article in {"Kurtas", "Kurtis", "Sarees", "Salwar"}:
        occ.update(["wedding", "festival"])
    if not occ:
        occ.add("casual")
    return sorted(occ)


def price_for(article: str, gender: str) -> int:
    """Realistic INR price by category."""
    base = {
        "Shirts": (799, 1899), "Tshirts": (399, 999), "Jeans": (999, 2499),
        "Trousers": (899, 2199), "Kurtas": (699, 1999), "Dresses": (999, 2999),
        "Jackets": (1499, 3999), "Blazers": (1999, 4999), "Sweaters": (899, 2499),
        "Casual Shoes": (999, 2999), "Formal Shoes": (1499, 3499),
        "Heels": (799, 2199), "Watches": (999, 4999), "Belts": (399, 999),
        "Handbags": (699, 2499), "Sunglasses": (599, 1999),
    }
    lo, hi = base.get(article, (499, 1999))
    return int(round(random.randint(lo, hi) / 10) * 10)


def brand_for(gender: str) -> str:
    if gender == "male":   return random.choice(MALE_BRANDS)
    if gender == "female": return random.choice(FEMALE_BRANDS)
    return random.choice(UNISEX_BRANDS)


def style_tags(usage: str) -> list[str]:
    u = (usage or "").lower()
    if "formal" in u:   return ["formal", "classic"]
    if "ethnic" in u:   return ["ethnic", "classic"]
    if "sports" in u:   return ["athleisure", "casual"]
    if "party" in u:    return ["party", "trendy"]
    return ["casual", "classic"]


def classify_type(article: str) -> str | None:
    if article in TOP_TYPES:       return "top"
    if article in BOTTOM_TYPES:    return "bottom"
    if article in ACCESSORY_TYPES: return "accessory"
    return None


def map_gender(g: str) -> str:
    g = (g or "").strip().lower()
    if g == "men":   return "male"
    if g == "women": return "female"
    return "unisex"   # Boys/Girls/Unisex → unisex


def build_products(limit: int) -> list[dict]:
    products = []
    counts = {"top": 0, "bottom": 0, "accessory": 0}

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    random.shuffle(rows)   # variety across genders/colors

    for row in rows:
        # Stop once every quota is filled
        if all(counts[t] >= QUOTA[t] for t in QUOTA):
            break

        article = (row.get("articleType") or "").strip()
        ptype = classify_type(article)
        if not ptype:
            continue

        # Skip if this type's quota is already full
        if counts[ptype] >= QUOTA[ptype]:
            continue

        gender = map_gender(row.get("gender"))
        pid    = (row.get("id") or "").strip()
        if not pid:
            continue

        name = (row.get("productDisplayName") or "").strip()
        if not name:
            continue

        color  = (row.get("baseColour") or "").strip()
        usage  = (row.get("usage") or "").strip()
        season = (row.get("season") or "").strip()

        products.append({
            "id":         f"K{pid}",
            "title":      name,
            "brand":      brand_for(gender),
            "type":       ptype,
            "gender":     gender,
            "color":      color.lower() or "multi",
            "color_hex":  hex_for_color(color),
            "price":      price_for(article, gender),
            "occasions":  occasions_for(usage, season, article),
            "style":      style_tags(usage),
            "image":      IMG_URL.format(pid),
            "url":        f"#product-K{pid}",
        })
        counts[ptype] += 1

    print(f"Selected — tops: {counts['top']}, bottoms: {counts['bottom']}, accessories: {counts['accessory']}")
    return products


async def main():
    if not DB_URL:
        print("ERROR: DATABASE_URL not found in .env")
        return
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: styles.csv not found at {CSV_PATH}")
        print("Download it from Kaggle and place it in the scripts/ folder.")
        return

    print("Reading styles.csv and building products...")
    products = build_products(TARGET_COUNT)
    print(f"Built {len(products)} products. Connecting to Supabase...")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    conn = await asyncpg.connect(DB_URL, ssl=ctx, statement_cache_size=0)

    # Create products table if it doesn't exist
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            brand       TEXT,
            type        TEXT NOT NULL,
            gender      TEXT NOT NULL,
            color       TEXT,
            color_hex   TEXT,
            price       INTEGER,
            occasions   JSONB,
            style       JSONB,
            image       TEXT,
            url         TEXT
        );
    """)

    print("Clearing old products and inserting fresh set...")
    await conn.execute("DELETE FROM products;")
    inserted = 0
    for p in products:
        await conn.execute("""
            INSERT INTO products
                (id, title, brand, type, gender, color, color_hex,
                 price, occasions, style, image, url)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12)
            ON CONFLICT (id) DO UPDATE SET
                title=$2, brand=$3, type=$4, gender=$5, color=$6,
                color_hex=$7, price=$8, occasions=$9::jsonb,
                style=$10::jsonb, image=$11, url=$12;
        """,
            p["id"], p["title"], p["brand"], p["type"], p["gender"],
            p["color"], p["color_hex"], p["price"],
            __import__("json").dumps(p["occasions"]),
            __import__("json").dumps(p["style"]),
            p["image"], p["url"],
        )
        inserted += 1
        if inserted % 200 == 0:
            print(f"  ... {inserted} inserted")

    # Quick summary
    rows = await conn.fetch("SELECT type, count(*) FROM products GROUP BY type")
    print("\nDONE. Products in database by type:")
    for r in rows:
        print(f"  {r['type']:10s} : {r['count']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
