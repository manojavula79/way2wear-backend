"""
WAY2WEAR — PRODUCT CATALOG
Based on user's product list. Replace image URLs with real ones when available.
"""

# ── Unsplash photo pools per category ────────
SHIRT_IMAGES = [
    "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=300&q=80",
    "https://images.unsplash.com/photo-1602810316693-3667c854239a?w=300&q=80",
    "https://images.unsplash.com/photo-1598300042247-d088f8ab3a91?w=300&q=80",
    "https://images.unsplash.com/photo-1563630423918-b58f07336ac9?w=300&q=80",
    "https://images.unsplash.com/photo-1586790170083-2f9ceadc732d?w=300&q=80",
    "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=300&q=80",
    "https://images.unsplash.com/photo-1516826957135-700dedea698c?w=300&q=80",
    "https://images.unsplash.com/photo-1607345366928-199ea26cfe3e?w=300&q=80",
    "https://images.unsplash.com/photo-1620012253295-c15cc3e65df4?w=300&q=80",
    "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?w=300&q=80",
    "https://images.unsplash.com/photo-1602810316693-3667c854239a?w=300&q=80",
    "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=300&q=80",
    "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=300&q=80",
    "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=300&q=80",
    "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=300&q=80",
]

PANTS_IMAGES = [
    "https://images.unsplash.com/photo-1542272604-787c3835535d?w=300&q=80",
    "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=300&q=80",
    "https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=300&q=80",
    "https://images.unsplash.com/photo-1548624313-0396c75e4b1a?w=300&q=80",
    "https://images.unsplash.com/photo-1552902865-b72c031ac5ea?w=300&q=80",
    "https://images.unsplash.com/photo-1517438476312-10d79c077509?w=300&q=80",
    "https://images.unsplash.com/photo-1605518216938-7c31b7b14ad0?w=300&q=80",
    "https://images.unsplash.com/photo-1612902456551-b2a56c053eef?w=300&q=80",
    "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=300&q=80",
    "https://images.unsplash.com/photo-1490551277450-d36cff6d1896?w=300&q=80",
    "https://images.unsplash.com/photo-1582552938357-32b906df40cb?w=300&q=80",
    "https://images.unsplash.com/photo-1559334417-a5b3c5f74f57?w=300&q=80",
    "https://images.unsplash.com/photo-1600700575854-d8d6b3fc5afa?w=300&q=80",
    "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=300&q=80",
    "https://images.unsplash.com/photo-1542272604-787c3835535d?w=300&q=80",
]

LADIES_TOP_IMAGES = [
    "https://images.unsplash.com/photo-1564257631407-4deb1f99d992?w=300&q=80",
    "https://images.unsplash.com/photo-1485462537746-965f33f4f31e?w=300&q=80",
    "https://images.unsplash.com/photo-1551232864-3f0890e580d9?w=300&q=80",
    "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=300&q=80",
    "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=300&q=80",
    "https://images.unsplash.com/photo-1583744946564-b52ac1c389c8?w=300&q=80",
    "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=300&q=80",
    "https://images.unsplash.com/photo-1592301933927-35b597393c0a?w=300&q=80",
    "https://images.unsplash.com/photo-1618932260643-eee4a2f652a6?w=300&q=80",
    "https://images.unsplash.com/photo-1600407010978-dc2c2e1c9f4c?w=300&q=80",
    "https://images.unsplash.com/photo-1550639525-c97d455acf70?w=300&q=80",
    "https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=300&q=80",
    "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=300&q=80",
    "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=300&q=80",
    "https://images.unsplash.com/photo-1564257631407-4deb1f99d992?w=300&q=80",
]

LADIES_BOTTOM_IMAGES = [
    "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=300&q=80",
    "https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=300&q=80",
    "https://images.unsplash.com/photo-1583496661160-fb5218afa9a0?w=300&q=80",
    "https://images.unsplash.com/photo-1509551388413-e18d0ac5d495?w=300&q=80",
    "https://images.unsplash.com/photo-1577900232427-18219b9166a0?w=300&q=80",
    "https://images.unsplash.com/photo-1585914924626-15adac1e6402?w=300&q=80",
    "https://images.unsplash.com/photo-1559334417-a5b3c5f74f57?w=300&q=80",
    "https://images.unsplash.com/photo-1578032292335-df3abbb0d586?w=300&q=80",
    "https://images.unsplash.com/photo-1571945153237-4929e783af4a?w=300&q=80",
    "https://images.unsplash.com/photo-1590735213920-68192a487bc2?w=300&q=80",
    "https://images.unsplash.com/photo-1552902865-b72c031ac5ea?w=300&q=80",
    "https://images.unsplash.com/photo-1542272604-787c3835535d?w=300&q=80",
    "https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=300&q=80",
]

# ── Brand assignment by price ─────────────────
def assign_brand(price: int, gender: str) -> str:
    if gender in ("male", "unisex"):
        if price < 1000:  return "Roadster"
        if price < 1300:  return "Peter England"
        if price < 1600:  return "Allen Solly"
        if price < 1900:  return "Van Heusen"
        return "Louis Philippe"
    else:
        if price < 800:   return "Global Desi"
        if price < 1000:  return "Aurelia"
        if price < 1300:  return "W"
        if price < 1600:  return "Biba"
        return "Fabindia"


# ── Color mapping by title keywords ──────────
def guess_color(title: str) -> tuple[str, str]:
    t = title.lower()
    if "white"   in t: return "white",   "#F5F5F0"
    if "black"   in t: return "black",   "#1A1A1A"
    if "navy"    in t: return "navy",    "#1F2D4E"
    if "blue"    in t: return "blue",    "#2C4A8C"
    if "denim"   in t: return "denim",   "#3D5A80"
    if "grey" in t or "gray" in t: return "grey", "#6B6B6B"
    if "charcoal" in t: return "charcoal","#3D3D3D"
    if "khaki"   in t: return "khaki",   "#C3A882"
    if "beige"   in t: return "beige",   "#D4C5A9"
    if "cream"   in t: return "cream",   "#F5EDD6"
    if "brown"   in t: return "brown",   "#8B5E3C"
    if "maroon"  in t: return "maroon",  "#7B2D2D"
    if "red"     in t: return "red",     "#C0392B"
    if "pink"    in t: return "pink",    "#E8A0A8"
    if "yellow"  in t: return "yellow",  "#F4C430"
    if "green"   in t: return "green",   "#4A7C59"
    if "olive"   in t: return "olive",   "#6B7C45"
    if "purple" in t or "lavender" in t: return "lavender","#9B7FB5"
    if "striped" in t: return "multi",   "#2C3E7A"
    if "floral"  in t: return "floral",  "#E8A87C"
    if "printed" in t or "polka" in t: return "multi","#C5828A"
    return "charcoal", "#3D3D3D"


# ── Occasion mapping ──────────────────────────
def guess_occasions(title: str, category: str) -> list[str]:
    t = title.lower()
    base = ["casual"]
    if "formal" in t or "office" in t: base += ["office", "formal"]
    if "party"  in t or "night"  in t: base += ["party", "date"]
    if "casual" in t or "beach"  in t or "summer" in t: base += ["travel"]
    if "ethnic" in t or "traditional" in t or "anarkali" in t or \
       "sharara" in t or "salwar" in t: base += ["wedding", "festival"]
    if "wedding" in t: base += ["wedding"]
    if "gym" in t or "athletic" in t or "track" in t or "jogger" in t: base += ["gym"]
    if "semi-formal" in t: base += ["office", "date"]
    if not any(x in base for x in ["office","wedding","party","date"]): base += ["date"]
    return list(set(base))


# ── Build product list from user data ────────
_RAW = [
    # SHIRTS (men's tops)
    {"id":1,"title":"Slim Fit Men's Denim Shirt","category":"shirts","price":1299},
    {"id":2,"title":"Classic White Casual Shirt","category":"shirts","price":999},
    {"id":3,"title":"Formal Blue Striped Shirt","category":"shirts","price":1499},
    {"id":4,"title":"Black Regular Fit Shirt","category":"shirts","price":1199},
    {"id":5,"title":"Men's Olive Green Cargo Shirt","category":"shirts","price":1399},
    {"id":6,"title":"Maroon Premium Cotton Shirt","category":"shirts","price":1599},
    {"id":7,"title":"Grey Linen Summer Shirt","category":"shirts","price":1799},
    {"id":8,"title":"Yellow Casual Beach Shirt","category":"shirts","price":899},
    {"id":9,"title":"Dark Grey Oxford Shirt","category":"shirts","price":1349},
    {"id":10,"title":"Navy Blue Printed Shirt","category":"shirts","price":1099},
    {"id":11,"title":"Red Checked Flannel Shirt","category":"shirts","price":1249},
    {"id":12,"title":"Khaki Casual Corduroy Shirt","category":"shirts","price":1699},
    {"id":13,"title":"Pink Semi-Formal Shirt","category":"shirts","price":1150},
    {"id":14,"title":"Brown Vintage Party Shirt","category":"shirts","price":1450},
    {"id":15,"title":"Light Green Slim Shirt","category":"shirts","price":950},
    # PANTS (men's bottoms)
    {"id":16,"title":"Men's Dark Blue Jeans","category":"pants","price":1999},
    {"id":17,"title":"Slim Fit Black Chinos","category":"pants","price":1499},
    {"id":18,"title":"Khaki Regular Cargo Pants","category":"pants","price":1799},
    {"id":19,"title":"Light Grey Formal Trousers","category":"pants","price":1699},
    {"id":20,"title":"Olive Green Track Pants","category":"pants","price":999},
    {"id":21,"title":"Beige Cotton Chino Pants","category":"pants","price":1549},
    {"id":22,"title":"Charcoal Grey Slim Trousers","category":"pants","price":1899},
    {"id":23,"title":"Off-White Summer Linen Pants","category":"pants","price":1650},
    {"id":24,"title":"Ripped Blue Denim Jeans","category":"pants","price":2199},
    {"id":25,"title":"Men's Jogger Pants Black","category":"pants","price":1199},
    {"id":26,"title":"Navy Blue Stretchable Chinos","category":"pants","price":1499},
    {"id":27,"title":"Brown Corduroy Pants","category":"pants","price":1750},
    {"id":28,"title":"Classic Cream Dress Pants","category":"pants","price":1950},
    {"id":29,"title":"Dark Grey Sweatpants","category":"pants","price":899},
    {"id":30,"title":"Regular Fit Stonewash Jeans","category":"pants","price":1849},
    # LADIES TOPS
    {"id":31,"title":"Women's Floral Summer Top","category":"ladies_tops","price":799},
    {"id":32,"title":"Elegant Black Lace Top","category":"ladies_tops","price":1199},
    {"id":33,"title":"Casual White Cotton Tunic","category":"ladies_tops","price":899},
    {"id":34,"title":"Yellow Crop Top Casual","category":"ladies_tops","price":599},
    {"id":35,"title":"Pink Designer Kurti Top","category":"ladies_tops","price":1399},
    {"id":36,"title":"Blue Denim Sleeveless Top","category":"ladies_tops","price":999},
    {"id":37,"title":"Red Off-Shoulder Party Top","category":"ladies_tops","price":1249},
    {"id":38,"title":"Striped Casual V-Neck Top","category":"ladies_tops","price":699},
    {"id":39,"title":"Olive Green Satin Top","category":"ladies_tops","price":1499},
    {"id":40,"title":"Lavender Ruffled Top","category":"ladies_tops","price":1099},
    {"id":41,"title":"Polka Dot Retro Top","category":"ladies_tops","price":749},
    {"id":42,"title":"Printed Traditional Anarkali Top","category":"ladies_tops","price":1799},
    {"id":43,"title":"Maroon Velvet Winter Top","category":"ladies_tops","price":1599},
    {"id":44,"title":"White Boho Fringe Top","category":"ladies_tops","price":949},
    {"id":45,"title":"Peplum Style Yellow Top","category":"ladies_tops","price":849},
    # LADIES BOTTOMS
    {"id":46,"title":"Women's High Waist Blue Jeans","category":"ladies_bottoms","price":1899},
    {"id":47,"title":"Black Cotton Leggings Regular","category":"ladies_bottoms","price":499},
    {"id":48,"title":"Beige Palazzo Pants Wide Leg","category":"ladies_bottoms","price":1199},
    {"id":49,"title":"White Ethnic Sharara Bottom","category":"ladies_bottoms","price":1499},
    {"id":50,"title":"Olive Green Ankle Length Trousers","category":"ladies_bottoms","price":1299},
    {"id":51,"title":"Grey Casual Joggers Women","category":"ladies_bottoms","price":949},
    {"id":52,"title":"Light Pink Pleated Skirt","category":"ladies_bottoms","price":1399},
    {"id":53,"title":"Dark Denim Ripped Shorts","category":"ladies_bottoms","price":899},
    {"id":54,"title":"Maroon Cotton Salwar Bottom","category":"ladies_bottoms","price":699},
    {"id":55,"title":"Navy Blue Formal Trousers","category":"ladies_bottoms","price":1549},
    {"id":56,"title":"Cream Silk Cigarette Pants","category":"ladies_bottoms","price":1150},
    {"id":57,"title":"Classic Bootcut Blue Jeans","category":"ladies_bottoms","price":1999},
    {"id":58,"title":"Active Athletic Gym Tights","category":"ladies_bottoms","price":1099},
]

# ── Map category → type + gender ─────────────
_CAT_MAP = {
    "shirts":         ("top",    "male"),
    "pants":          ("bottom", "male"),
    "ladies_tops":    ("top",    "female"),
    "ladies_bottoms": ("bottom", "female"),
}

# ── Image pools per category ──────────────────
_IMG_POOLS = {
    "shirts":         SHIRT_IMAGES,
    "pants":          PANTS_IMAGES,
    "ladies_tops":    LADIES_TOP_IMAGES,
    "ladies_bottoms": LADIES_BOTTOM_IMAGES,
}

# ── Build FAKE_PRODUCTS ───────────────────────
FAKE_PRODUCTS = []
_cat_counters: dict = {}

for raw in _RAW:
    cat      = raw["category"]
    p_type, gender = _CAT_MAP[cat]
    color, color_hex = guess_color(raw["title"])
    brand    = assign_brand(raw["price"], gender)
    imgs     = _IMG_POOLS[cat]
    idx      = _cat_counters.get(cat, 0)
    image    = imgs[idx % len(imgs)]
    _cat_counters[cat] = idx + 1

    FAKE_PRODUCTS.append({
        "id":         f"P{raw['id']:03d}",
        "title":      raw["title"],
        "brand":      brand,
        "type":       p_type,
        "gender":     gender,
        "color":      color,
        "color_hex":  color_hex,
        "price":      raw["price"],
        "occasions":  guess_occasions(raw["title"], cat),
        "style":      ["casual", "classic"],
        "image":      image,
        "url":        f"#product-P{raw['id']:03d}",
    })


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def find_best_match(
    product_type: str,
    occasion: str,
    gender: str,
    max_price: float,
    color_preference: str = None,
    exclude_ids: list = None,
) -> dict | None:
    exclude_ids = exclude_ids or []

    candidates = [
        p for p in FAKE_PRODUCTS
        if p["type"] == product_type
        and (p["gender"] == gender or p["gender"] == "unisex")
        and p["id"] not in exclude_ids
    ]

    if not candidates:
        # Relax gender constraint
        candidates = [
            p for p in FAKE_PRODUCTS
            if p["type"] == product_type and p["id"] not in exclude_ids
        ]

    if not candidates:
        return None

    def score(p):
        s = 0
        if occasion in p.get("occasions", []):              s += 30
        if p["price"] <= max_price:                          s += 20
        if color_preference and color_preference in p["color"]: s += 15
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def build_outfit_from_catalog(
    occasion: str,
    gender: str,
    budget: dict,
) -> list[dict]:
    outfits = []
    used_top_ids:    list = []
    used_bottom_ids: list = []

    for _ in range(2):
        top = find_best_match(
            "top", occasion, gender,
            budget.get("top_budget", 1500),
            exclude_ids=used_top_ids,
        )
        bottom = find_best_match(
            "bottom", occasion, gender,
            budget.get("bottom_budget", 1200),
            exclude_ids=used_bottom_ids,
            color_preference=top["color"] if top else None,
        )

        if top:    used_top_ids.append(top["id"])
        if bottom: used_bottom_ids.append(bottom["id"])

        if top and bottom:
            outfits.append({"top": top, "bottom": bottom, "accessory": None})

    return outfits
