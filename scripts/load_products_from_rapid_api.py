#!/usr/bin/env python3
"""
Load real fashion products from Rapid API (Real-Time Amazon Data) into Supabase.

Setup:
1. Sign up on RapidAPI.com and subscribe to "Real-Time Amazon Data"
2. Get your API key from the Rapid API dashboard
3. Add to .env: RAPID_API_KEY=your_key_here
4. Run: python3 load_products_from_rapid_api.py
"""
import os
import asyncio
import httpx
import asyncpg
from dotenv import load_dotenv
import json
import time
from typing import Optional

load_dotenv()

RAPID_API_KEY = os.getenv("RAPID_API_KEY")
RAPID_API_HOST = "real-time-amazon-data.p.rapidapi.com"
DATABASE_URL = os.getenv("DATABASE_URL")

if not RAPID_API_KEY:
    print("❌ RAPID_API_KEY not found in .env")
    exit(1)
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    exit(1)

# Fashion search queries — mix of Indian and global fashion terms
SEARCH_QUERIES = {
    # Men's tops
    "men_tops": [
        "black oversized hoodie men",
        "white t-shirt men cotton",
        "formal shirt men",
        "casual shirt men",
        "polo t-shirt men",
    ],
    # Men's bottoms
    "men_bottoms": [
        "blue jeans men",
        "black trousers men",
        "cargo pants men",
        "casual pants men",
        "track pants men",
    ],
    # Women's Indian wear
    "women_indian": [
        "saree cotton",
        "kurti women",
        "lehenga",
        "salwar kameez",
        "dupatta",
    ],
    # Women's Western
    "women_western": [
        "jeans women",
        "top women casual",
        "dress women",
        "blouse women",
        "skirt women",
    ],
    # Footwear (unisex)
    "footwear": [
        "casual shoes",
        "sneakers",
        "formal shoes",
        "sandals",
        "boots",
    ],
    # Accessories
    "accessories": [
        "scarf",
        "belt",
        "handbag women",
        "backpack",
    ],
}

# Map gender/category
CATEGORY_GENDER = {
    "men_tops": ("male", "top"),
    "men_bottoms": ("male", "bottom"),
    "women_indian": ("female", "top"),
    "women_western": ("female", "top"),
    "footwear": ("unisex", "bottom"),
    "accessories": ("unisex", "accessory"),
}

async def fetch_products(query: str, page: int = 1, country: str = "IN") -> Optional[dict]:
    """Fetch products from Rapid API."""
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": RAPID_API_HOST,
        "Content-Type": "application/json",
    }
    params = {
        "query": query,
        "page": page,
        "country": country,
        "sort_by": "RELEVANCE",
        "product_condition": "ALL",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(url, headers=headers, params=params)
            if res.status_code == 200:
                return res.json()
            else:
                print(f"❌ API error {res.status_code}: {res.text[:200]}")
                return None
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        return None

async def load_into_db(products_list: list):
    """Batch insert products into Supabase."""
    if not products_list:
        return 0

    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        return 0

    try:
        # Upsert: on conflict, do nothing (keep existing if duplicate)
        query = """
        INSERT INTO products (id, title, brand, type, gender, color, color_hex, price, image, url, occasions, style)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (id) DO NOTHING;
        """

        count = 0
        for p in products_list:
            try:
                await conn.execute(
                    query,
                    p["id"],
                    p["title"],
                    p.get("brand", ""),
                    p["type"],
                    p["gender"],
                    p.get("color", ""),
                    p.get("color_hex", "#888888"),
                    int(p.get("price", 0)),
                    p.get("image", ""),
                    p.get("url", ""),
                    json.dumps(p.get("occasions", [])),
                    json.dumps(p.get("style", [])),
                )
                count += 1
            except Exception as e:
                print(f"  ⚠️  Row insert failed: {e}")

        await conn.close()
        return count
    except Exception as e:
        print(f"❌ DB error: {e}")
        return 0

def parse_product(item: dict, gender: str, product_type: str) -> Optional[dict]:
    """Parse a Rapid API product item."""
    try:
        # Amazon affiliate link structure
        asin = item.get("asin", "")
        if not asin:
            return None

        title = item.get("product_title", "")
        if not title or len(title) < 5:
            return None

        # Price: extract from string if needed
        price_str = item.get("product_price", "0")
        price = 0
        try:
            # Remove currency symbols and convert
            price = int(float(price_str.replace("₹", "").replace("$", "").replace(",", "").strip()))
            if price < 100 or price > 50000:  # sanity check
                price = 0
        except:
            pass

        image_url = item.get("product_photo", "")
        affiliate_url = f"https://www.amazon.in/s?k={asin}" if asin else ""

        # Infer occasion/style from title
        title_lower = title.lower()
        occasions = []
        style = []

        if any(w in title_lower for w in ["casual", "everyday", "daily"]):
            occasions.append("casual")
            style.append("casual")
        if any(w in title_lower for w in ["formal", "office", "business"]):
            occasions.append("office")
            style.append("formal")
        if any(w in title_lower for w in ["party", "wedding", "festive", "ethnic"]):
            occasions.append("party")
            style.append("ethnic")
        if any(w in title_lower for w in ["sports", "gym", "athletic"]):
            occasions.append("gym")
            style.append("athletic")

        if not occasions:
            occasions = ["casual"]
        if not style:
            style = ["modern"]

        return {
            "id": f"RAPIDK{asin}",
            "title": title[:200],
            "brand": item.get("product_brand", "Amazon")[:50],
            "type": product_type,
            "gender": gender,
            "color": item.get("product_color", "")[:30],
            "color_hex": "#888888",  # Rapid API doesn't provide hex; use neutral
            "price": price,
            "image": image_url,
            "url": affiliate_url,
            "occasions": occasions,
            "style": style,
        }
    except Exception as e:
        print(f"  Parse error: {e}")
        return None

async def main():
    print("🚀 Loading products from Rapid API into Supabase...\n")

    total_loaded = 0

    for category, queries in SEARCH_QUERIES.items():
        gender, product_type = CATEGORY_GENDER[category]
        print(f"\n📂 Category: {category} ({gender} / {product_type})")

        for query in queries:
            print(f"  🔍 Searching: '{query}'")

            # Fetch pages 1-3 for variety
            batch = []
            for page in range(1, 4):
                print(f"    Page {page}...", end=" ", flush=True)
                data = await fetch_products(query, page=page)

                if not data or "data" not in data:
                    print("(no data)")
                    break

                items = data.get("data", {}).get("products", [])
                if not items:
                    print("(empty)")
                    break

                for item in items:
                    parsed = parse_product(item, gender, product_type)
                    if parsed:
                        batch.append(parsed)

                print(f"({len(items)} products)")
                time.sleep(0.5)  # Polite rate limit

            # Load this batch
            if batch:
                loaded = await load_into_db(batch)
                print(f"    ✅ Loaded {loaded} / {len(batch)}")
                total_loaded += loaded

    print(f"\n✨ Done! Loaded {total_loaded} products total.")

if __name__ == "__main__":
    asyncio.run(main())
