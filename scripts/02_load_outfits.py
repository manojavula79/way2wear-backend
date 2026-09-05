#!/usr/bin/env python3
"""
Load 10k curated outfit pairs into Supabase from JSON.

Usage:
    python3 load_outfits.py path/to/outfits.json

Expected JSON format:
{
  "occasions": {
    "Beach Trip": {
      "Women": {
        "Fair/Cool": [
          "white kurti + light blue palazzo pants + dupatta",
          "cream saree + sandals + sunglasses"
        ],
        "Medium/Warm": [...],
        "Dark/Warm": [...]
      },
      "Men": {...}
    },
    "Office Party": {...}
  }
}
"""

import json
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set in .env")
    sys.exit(1)

# Map human-readable skin tones to normalized values
SKIN_TONE_MAP = {
    "fair/cool": "fair",
    "fair": "fair",
    "medium/warm": "medium",
    "medium": "medium",
    "dark/warm": "dark",
    "dark": "dark",
    "light": "fair",
    "olive": "medium",
    "deep": "dark",
}

# Normalize occasion names
OCCASION_MAP = {
    "beach trip": "beach",
    "beach": "beach",
    "office party": "office",
    "office": "office",
    "casual": "casual",
    "casual outing": "casual",
    "party": "party",
    "wedding": "wedding",
    "date night": "date",
    "gym": "gym",
    "formal": "formal",
    "festive": "festive",
    "ethnic": "ethnic",
}


def normalize_occasion(occ):
    """Normalize occasion name."""
    return OCCASION_MAP.get(occ.lower(), occ.lower())


def normalize_skin_tone(tone):
    """Normalize skin tone name."""
    return SKIN_TONE_MAP.get(tone.lower(), "fair")


def parse_json_structure(data: dict) -> list:
    """
    Parse the JSON structure and flatten to outfit records.
    
    Input: {"occasions": {"Beach Trip": {"Women": {"Fair/Cool": ["outfit1", "outfit2"]}}}}
    Output: [
        {"outfit_text": "outfit1", "occasion": "beach", "gender": "women", "skin_tone": "fair", ...},
        {"outfit_text": "outfit2", "occasion": "beach", "gender": "women", "skin_tone": "fair", ...},
    ]
    """
    outfits = []
    
    if "occasions" not in data:
        print("❌ JSON must have 'occasions' key at root level")
        return []
    
    occasions = data["occasions"]
    
    for occasion_name, gender_dict in occasions.items():
        normalized_occasion = normalize_occasion(occasion_name)
        
        if not isinstance(gender_dict, dict):
            print(f"⚠️  Skipping {occasion_name}: not a dict")
            continue
        
        for gender, tone_dict in gender_dict.items():
            normalized_gender = gender.lower()
            
            if not isinstance(tone_dict, dict):
                print(f"⚠️  Skipping {occasion_name}/{gender}: not a dict")
                continue
            
            for tone, outfit_list in tone_dict.items():
                normalized_tone = normalize_skin_tone(tone)
                
                if not isinstance(outfit_list, list):
                    print(f"⚠️  Skipping {occasion_name}/{gender}/{tone}: not a list")
                    continue
                
                for outfit_text in outfit_list:
                    if not outfit_text or not isinstance(outfit_text, str):
                        continue
                    
                    outfit = {
                        "outfit_text": outfit_text.strip(),
                        "occasion": normalized_occasion,
                        "gender": normalized_gender,
                        "skin_tone": normalized_tone,
                        "budget_min": 500,
                        "budget_max": 5000,
                        "color_palette": [],
                        "style_tags": ["curated"],
                    }
                    outfits.append(outfit)
    
    return outfits


async def load_outfits_to_db(outfits: list):
    """Batch insert outfits into Supabase."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        return 0
    
    try:
        query = """
        INSERT INTO curated_outfits 
        (outfit_text, occasion, gender, skin_tone, budget_min, budget_max, color_palette, style_tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT DO NOTHING;
        """
        
        count = 0
        for outfit in outfits:
            try:
                await conn.execute(
                    query,
                    outfit["outfit_text"],
                    outfit["occasion"],
                    outfit["gender"],
                    outfit["skin_tone"],
                    outfit["budget_min"],
                    outfit["budget_max"],
                    outfit.get("color_palette", []),
                    outfit.get("style_tags", []),
                )
                count += 1
            except Exception as e:
                print(f"⚠️  Row insert failed: {e}")
        
        await conn.close()
        return count
    except Exception as e:
        print(f"❌ DB error: {e}")
        return 0


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 load_outfits.py path/to/outfits.json")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        sys.exit(1)
    
    print(f"📖 Reading JSON from {json_path}...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Read failed: {e}")
        sys.exit(1)
    
    print("🔄 Parsing JSON structure...")
    outfits = parse_json_structure(data)
    print(f"   Found {len(outfits)} outfits")
    
    if not outfits:
        print("❌ No outfits parsed from JSON")
        sys.exit(1)
    
    # Group by occasion/gender/tone for stats
    stats = {}
    for outfit in outfits:
        key = f"{outfit['occasion']}_{outfit['gender']}_{outfit['skin_tone']}"
        stats[key] = stats.get(key, 0) + 1
    
    print("\n📊 Breakdown:")
    for key, count in sorted(stats.items()):
        occasion, gender, tone = key.split("_")
        print(f"   {occasion:15} | {gender:8} | {tone:8} → {count:3} outfits")
    
    print(f"\n💾 Loading {len(outfits)} outfits to Supabase...")
    loaded = await load_outfits_to_db(outfits)
    print(f"✅ Loaded {loaded} outfits")
    
    # Verify
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        total = await conn.fetchval("SELECT COUNT(*) FROM curated_outfits")
        await conn.close()
        print(f"\n📈 Total outfits in database: {total}")
    except Exception as e:
        print(f"⚠️  Verify failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
