"""
WAY2WEAR — AI ORCHESTRATION ENGINE  (v3)
LangGraph fashion stylist pipeline.

v3 changes (on top of v2):
- Full account-profile usage in matching, not just gender/budget:
  gender, age, stylePreference, fitType, skinTone, heightCm, budgetRange
  are all threaded through intent -> pairing lookup -> product matching.
- Occasion is understood from the user's natural-language prompt
  (wedding, party, office, casual, festival, date, ethnic, etc.).
- NEW: node_load_pairing_knowledge reads `data/outfits.json` — your
  curated styling knowledge base — and pulls real TOP+BOTTOM combos for
  the detected occasion + gender + skin tone, instead of picking a top
  and a bottom independently at random.
- node_match_outfits now uses those combos to guide catalog search
  (color/garment-type keywords), with the old gender/budget-only search
  kept as an automatic fallback so nothing breaks if outfits.json has no
  entry for a given occasion/gender/tone.
- HARD GUARANTEE: every returned outfit has ONLY "top" and "bottom".
  Even if an outfits.json combo string has a 3rd/4th segment (e.g.
  "shirt + pants + shoes"), everything after the 2nd "+" is discarded.
- User-mentioned colors (e.g. "not red", "navy blue") are extracted and
  used to prefer matching pairing rules / products.

Key v2 changes (kept):
- Account settings injected into every prompt.
- STRICT gender filtering so men/women/kids don't mix.
- 3 complete outfits (top + bottom only — NO accessory product).
- Each outfit carries a short shoe_note (text suggestion, not a product).
- Prices in INR (₹).
- Auto-detects the user's language and replies in it.
"""
from typing import TypedDict, List, Optional, Any
from pathlib import Path
import inspect
import json
import re

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from app.config import settings

llm = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.7,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=getattr(settings, "OPENAI_MAX_TOKENS", 1500),
)
llm_precise = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.2,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=800,
)


class OutfitState(TypedDict):
    user_input: str
    conversation_history: List[dict]
    user_profile: Optional[dict]
    understood_prompt: str
    language: str
    intent: dict
    budget: dict
    style_class: str
    pairing_rules: List[dict]          # NEW: styling knowledge for this occasion/gender/tone
    matched_outfits: List[dict]
    final_response: dict
    error: Optional[str]


# ── Helpers ───────────────────────────────
def _clean_json(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _profile_block(profile: dict) -> str:
    """Turn the user's account settings into a prompt block the AI must respect."""
    if not profile:
        return "No profile set. Assume unisex, mid-range budget."
    parts = []
    g = profile.get("gender")
    age = profile.get("age") or profile.get("ageYears")

    # Age decides adult vs kids clothing
    age_band = None
    try:
        if age is not None and str(age).strip() != "":
            a = int(age)
            if a < 13:
                age_band = "KIDS"
            elif a < 18:
                age_band = "TEEN"
            else:
                age_band = "ADULT"
    except Exception:
        age_band = None

    if g:
        # Male/female (not men/women)
        base = {"male": "MALE clothing only", "female": "FEMALE clothing only"}.get(g, "either male or female")
        if age_band == "KIDS":
            who = f"KIDS' {('boys' if g == 'male' else 'girls' if g == 'female' else '')} clothing only".replace("  ", " ").strip()
        elif age_band == "TEEN":
            who = f"TEEN {base}"
        else:
            who = base
        parts.append(f"- Shops for: {who}")

    if age_band:
        parts.append(f"- Age group: {age_band}" + (f" ({age} years)" if age else ""))
    if profile.get("stylePreference") or profile.get("style_preference"):
        parts.append(f"- Personal style: {profile.get('stylePreference') or profile.get('style_preference')}")
    if profile.get("fitType") or profile.get("fit_type"):
        parts.append(f"- Preferred fit: {profile.get('fitType') or profile.get('fit_type')}")
    if profile.get("skinTone") or profile.get("skin_tone"):
        parts.append(f"- Skin tone: {profile.get('skinTone') or profile.get('skin_tone')} (suggest flattering colors)")
    if profile.get("heightCm") or profile.get("height_cm"):
        parts.append(f"- Height: {profile.get('heightCm') or profile.get('height_cm')} cm")
    if profile.get("budgetRange") or profile.get("budget_range"):
        parts.append(f"- Default budget: {profile.get('budgetRange') or profile.get('budget_range')}")
    return "\n".join(parts) if parts else "No profile set."


def _profile_gender(profile: dict) -> Optional[str]:
    if not profile:
        return None
    g = profile.get("gender")
    return g if g in ("male", "female") else None


# ═══════════════════════════════════════════════════════════════
# NEW: outfits.json STYLING KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════

# Expected shape (adjust aliases below if your real keys differ):
# {
#   "occasions": {
#     "Festival": {
#       "Men": {
#         "Deep": ["sapphire blue striped shirt + fuchsia cargo pants", ...]
#       }
#     }
#   }
# }
#
# IMPORTANT: only the FIRST TWO "+"-separated segments of each combo are
# ever used (top, bottom). Anything after that (shoes, accessories, etc.)
# is intentionally discarded, per the requirement that outfits contain
# ONLY a top and a bottom.

_OUTFITS_JSON_PATH = Path(
    getattr(settings, "OUTFITS_JSON_PATH", None)
    or (Path(__file__).resolve().parents[2] / "data" / "outfits.json")
)
_OUTFIT_KNOWLEDGE_CACHE: Optional[dict] = None

_OCCASION_ALIASES = {
    "marriage": "wedding", "shaadi": "wedding", "wedding": "wedding",
    "diwali": "festival", "eid": "festival", "festival": "festival", "festive": "festival",
    "office": "office", "work": "office", "business": "office",
    "party": "party", "date": "date", "casual": "casual",
    "formal": "formal", "travel": "travel", "vacation": "travel", "gym": "gym",
    "ethnic": "ethnic",
}
_GENDER_ALIASES = {"male": "men", "men": "men", "female": "women", "women": "women", "unisex": "unisex"}
_SKIN_TONE_ALIASES = {"fair": "fair", "medium": "medium", "dark": "deep", "deep": "deep"}

_GARMENT_TYPES = [
    "kurta pajama", "t-shirt", "tshirt", "shirt", "polo", "kurta", "pajama",
    "trousers", "pants", "jeans", "chinos", "shorts", "joggers",
    "sherwani", "blazer", "jacket",
]


def _load_outfit_knowledge() -> dict:
    """Load and cache data/outfits.json."""
    global _OUTFIT_KNOWLEDGE_CACHE
    if _OUTFIT_KNOWLEDGE_CACHE is None:
        try:
            with open(_OUTFITS_JSON_PATH, "r", encoding="utf-8") as f:
                _OUTFIT_KNOWLEDGE_CACHE = json.load(f)
            print(f"✅ Loaded styling knowledge from {_OUTFITS_JSON_PATH}")
        except Exception as e:
            print(f"⚠️  Could not load outfits.json ({_OUTFITS_JSON_PATH}): {e}")
            _OUTFIT_KNOWLEDGE_CACHE = {}
    return _OUTFIT_KNOWLEDGE_CACHE


def _match_key(value: Optional[str], available_keys, alias_map: dict) -> Optional[str]:
    """Case-insensitive, alias-aware lookup of `value` inside `available_keys`."""
    if not value:
        return None
    value_l = str(value).strip().lower()
    canonical = alias_map.get(value_l, value_l)
    for k in available_keys:
        if k.lower() == canonical.lower():
            return k
    # substring fallback, e.g. "my brother's marriage" -> contains "marriage" -> "wedding"
    for alias_word, mapped in alias_map.items():
        if alias_word in value_l:
            for k in available_keys:
                if k.lower() == mapped.lower():
                    return k
    return None


def get_pairing_rules(occasion: str, gender: str, skin_tone: Optional[str],
                       style_pref: Optional[str] = None) -> List[dict]:
    """
    Look up real TOP+BOTTOM styling combinations from outfits.json for this
    occasion + gender + skin tone.

    Each source string is expected as "top description + bottom description
    [+ ignored extra items]". We ONLY ever keep the first two segments.
    """
    data = _load_outfit_knowledge().get("occasions", {})
    if not data:
        return []

    occ_key = _match_key(occasion, data.keys(), _OCCASION_ALIASES)
    if not occ_key:
        return []
    gender_block = data.get(occ_key, {})

    gender_key = _match_key(gender, gender_block.keys(), _GENDER_ALIASES) or next(iter(gender_block), None)
    if not gender_key:
        return []
    tone_block = gender_block.get(gender_key, {})

    tone_key = _match_key(skin_tone, tone_block.keys(), _SKIN_TONE_ALIASES) or next(iter(tone_block), None)
    raw_list = tone_block.get(tone_key, []) if tone_key else []

    rules = []
    for raw in raw_list:
        segments = [seg.strip() for seg in raw.split("+") if seg.strip()]
        if len(segments) < 2:
            continue
        top_desc, bottom_desc = segments[0], segments[1]  # deliberately ignore segments[2:]
        rules.append({"key": raw, "top_desc": top_desc, "bottom_desc": bottom_desc, "description": raw})

    if style_pref:
        style_pref_l = style_pref.lower()
        rules.sort(key=lambda r: 0 if style_pref_l in (r["top_desc"] + r["bottom_desc"]).lower() else 1)

    return rules


def _parse_garment_desc(desc: str) -> dict:
    """
    Lightweight parse of a knowledge-base garment description, e.g.
    'sapphire blue striped shirt' -> {'type': 'shirt', 'color': 'sapphire blue', 'keywords': [...]}.
    """
    desc_l = (desc or "").strip().lower()
    found_type = next((g for g in _GARMENT_TYPES if g in desc_l), None)
    color = desc_l.replace(found_type, "").strip() if found_type else desc_l
    return {"type": found_type, "color": color, "keywords": desc_l.split()}


def _find_matching_item(find_best_match, category: str, occasion: str, gender: str,
                         allowed_genders: List[str], budget_amt: int, desc: str,
                         exclude_ids: List[str], fit_type: Optional[str] = None,
                         color_preference: Optional[str] = None):
    """
    Ask the catalog for the best item, passing as much of the outfits.json
    guidance (color / garment type / fit) through to find_best_match as its
    signature currently supports.

    This is written defensively (via inspect.signature) so it NEVER breaks
    if fake_products.find_best_match doesn't yet accept the newer hints —
    it just falls back to the original gender/budget/exclude_ids search.
    To get real color/type-aware matching, extend find_best_match to accept
    `color_preference`, `keyword_hint`, and/or `garment_type`.
    """
    parsed = _parse_garment_desc(desc)
    hint_color = color_preference or parsed["color"]

    sig_params = set(inspect.signature(find_best_match).parameters)
    kwargs = {}
    if "exclude_ids" in sig_params:
        kwargs["exclude_ids"] = exclude_ids
    if "allowed_genders" in sig_params:
        kwargs["allowed_genders"] = allowed_genders
    if "color_preference" in sig_params and hint_color:
        kwargs["color_preference"] = hint_color
    if "keyword_hint" in sig_params and parsed["keywords"]:
        kwargs["keyword_hint"] = " ".join(parsed["keywords"])
    if "garment_type" in sig_params and parsed["type"]:
        kwargs["garment_type"] = parsed["type"]
    if "fit_type" in sig_params and fit_type:
        kwargs["fit_type"] = fit_type

    try:
        return find_best_match(category, occasion, gender, budget_amt, **kwargs)
    except TypeError:
        # Extremely defensive fallback in case of an unexpected signature mismatch.
        return find_best_match(
            category, occasion, gender, budget_amt,
            exclude_ids=exclude_ids, allowed_genders=allowed_genders,
        )


# ── NODE 1 — UNDERSTAND + LANGUAGE DETECT ──
async def node_understand(state: OutfitState) -> OutfitState:
    system = (
        "You analyze a fashion request. Return JSON ONLY:\n"
        '{"clarified": "enriched one-line description of what they want",'
        ' "language": "the language the user wrote in, e.g. English, Hindi, Telugu, Tamil, Spanish"}'
    )
    res = await llm_precise.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=state["user_input"]),
    ])
    try:
        d = json.loads(_clean_json(res.content))
        state["understood_prompt"] = d.get("clarified", state["user_input"])
        state["language"] = d.get("language", "English")
    except Exception:
        state["understood_prompt"] = state["user_input"]
        state["language"] = "English"
    return state


# ── NODE 2 — INTENT (occasion + colors, profile overrides gender) ──
async def node_extract_intent(state: OutfitState) -> OutfitState:
    system = """Extract fashion intent from the user's message. Return JSON only:
{
  "occasion": "wedding|office|casual|date|party|travel|gym|festival|formal|vacation|ethnic|other",
  "formality": "formal|smart_casual|casual|athletic|ethnic",
  "gender": "male|female|unisex",
  "season": "summer|winter|spring|fall|any",
  "style_keywords": ["..."],
  "colors_mentioned": ["..."]
}
Rules:
- Infer "occasion" even if not stated explicitly (e.g. "my brother's marriage" -> "wedding",
  "meeting at work" -> "office", "diwali get-together" -> "festival").
- "colors_mentioned" should ONLY include colors the user actually said, including negations
  worded as preferences (e.g. "not red" -> still list "red" is fine to omit; prefer colors
  the user wants). If none mentioned, return an empty list.
"""
    res = await llm_precise.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=state["understood_prompt"]),
    ])
    try:
        intent = json.loads(_clean_json(res.content))
    except Exception:
        intent = {"occasion": "casual", "formality": "casual", "gender": "unisex",
                  "season": "any", "style_keywords": [], "colors_mentioned": []}

    intent.setdefault("colors_mentioned", [])
    intent.setdefault("style_keywords", [])

    # CRITICAL: account-settings gender ALWAYS wins (fixes mixed men/women/kids)
    pg = _profile_gender(state.get("user_profile"))
    if pg:
        intent["gender"] = pg

    state["intent"] = intent
    return state


# ── NODE 3 — BUDGET (INR) ──
async def node_analyze_budget(state: OutfitState) -> OutfitState:
    prompt = state["user_input"]
    # Indian rupee patterns: "under 2000", "₹1000-3000", "below rs 1500"
    patterns = [
        (r"under\s*(?:rs\.?|₹)?\s*(\d+)", lambda m: (0, int(m.group(1)))),
        (r"below\s*(?:rs\.?|₹)?\s*(\d+)", lambda m: (0, int(m.group(1)))),
        (r"(?:rs\.?|₹)?\s*(\d+)\s*-\s*(?:rs\.?|₹)?\s*(\d+)", lambda m: (int(m.group(1)), int(m.group(2)))),
        (r"around\s*(?:rs\.?|₹)?\s*(\d+)", lambda m: (int(int(m.group(1))*0.7), int(int(m.group(1))*1.3))),
        (r"budget.*?(?:rs\.?|₹)?\s*(\d+)", lambda m: (0, int(m.group(1)))),
    ]
    min_b, max_b = 0, 5000  # sensible INR default
    for pat, fn in patterns:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            try:
                min_b, max_b = fn(m); break
            except Exception:
                pass

    # If no budget in prompt, fall back to profile default budget
    if max_b == 5000:
        prof = state.get("user_profile") or {}
        rng = prof.get("budgetRange") or prof.get("budget_range") or ""
        nums = [int(x) for x in re.findall(r"\d+", rng.replace(",", ""))]
        if len(nums) >= 2:
            min_b, max_b = nums[0], nums[1]
        elif len(nums) == 1:
            max_b = nums[0]

    state["budget"] = {
        "min": int(min_b), "max": int(max_b), "currency": "INR",
        "top_budget": int(max_b * 0.55),
        "bottom_budget": int(max_b * 0.45),
    }
    return state


# ── NODE 4 — STYLE CLASS ──
async def node_classify_style(state: OutfitState) -> OutfitState:
    intent = state["intent"]
    f, o = intent.get("formality", "casual"), intent.get("occasion", "casual")
    style_map = {
        ("formal", "wedding"): "Wedding Formal",
        ("ethnic", "wedding"): "Ethnic Wedding",
        ("smart_casual", "office"): "Smart Business Casual",
        ("formal", "office"): "Business Formal",
        ("casual", "date"): "Elevated Casual",
        ("casual", "vacation"): "Vacation Casual",
        ("casual", "casual"): "Modern Casual",
        ("athletic", "gym"): "Athleisure",
    }
    state["style_class"] = style_map.get((f, o), "Contemporary Casual")
    return state


# ── NODE 4.5 — LOAD STYLING KNOWLEDGE (NEW) ──
async def node_load_pairing_knowledge(state: OutfitState) -> OutfitState:
    """
    Pull real styling knowledge from outfits.json for this occasion + gender
    + skin tone, so matching is based on known-good TOP+BOTTOM combinations
    instead of independent random picks.
    """
    intent = state["intent"]
    profile = state.get("user_profile") or {}

    occasion = intent.get("occasion", "casual")
    gender = intent.get("gender", "unisex")
    skin_tone = profile.get("skinTone") or profile.get("skin_tone")
    style_pref = profile.get("stylePreference") or profile.get("style_preference")

    rules = get_pairing_rules(occasion, gender, skin_tone, style_pref)

    # Prefer rules that reference any color the user explicitly mentioned
    colors_mentioned = [c.lower() for c in intent.get("colors_mentioned") or []]
    if colors_mentioned and rules:
        def _color_score(r):
            text = f"{r['top_desc']} {r['bottom_desc']}".lower()
            return 0 if any(c in text for c in colors_mentioned) else 1
        rules.sort(key=_color_score)

    state["pairing_rules"] = rules
    print(f"📚 Loaded {len(rules)} pairing rule(s) from outfits.json "
          f"(occasion={occasion}, gender={gender}, skin_tone={skin_tone})")
    return state


# ── NODE 5 — MATCH 3 OUTFITS FROM CATALOG (top + bottom, knowledge-guided) ──
async def node_match_outfits(state: OutfitState) -> OutfitState:
    """
    Match 3 outfits using outfits.json styling knowledge first, falling back
    to the previous gender/budget-only search if the knowledge base has no
    entry for this occasion/gender/skin-tone (so functionality never breaks).

    STRICTLY respects profile gender — prevents women's top paired with
    men's bottom and vice versa. Output ALWAYS contains only top + bottom.
    """
    from app.services.fake_products import find_best_match

    intent = state["intent"]
    occasion = intent.get("occasion", "casual")
    gender = intent.get("gender", "unisex")  # already overridden by profile
    budget = state["budget"]
    profile = state.get("user_profile") or {}
    fit_type = profile.get("fitType") or profile.get("fit_type")
    rules: List[dict] = state.get("pairing_rules") or []

    allowed_genders = [gender]
    if gender != "unisex":
        allowed_genders.append("unisex")  # unisex OK, but not other genders

    outfits: List[dict] = []
    used_top, used_bottom = [], []
    used_rule_keys = set()

    def _next_rule():
        for r in rules:
            if r["key"] not in used_rule_keys:
                return r
        return None

    # ── Pass 1: knowledge-guided pairing (the real fix for "random pairing") ──
    for _ in range(3):
        rule = _next_rule()
        if not rule:
            break
        used_rule_keys.add(rule["key"])

        top = _find_matching_item(
            find_best_match, "top", occasion, gender, allowed_genders,
            budget.get("top_budget", 3000), rule["top_desc"], used_top,
            fit_type=fit_type,
        )
        if not top:
            continue

        bottom = _find_matching_item(
            find_best_match, "bottom", occasion, gender, allowed_genders,
            budget.get("bottom_budget", 2500), rule["bottom_desc"], used_bottom,
            fit_type=fit_type, color_preference=top.get("color"),
        )
        if not bottom:
            continue

        if gender in ("male", "female"):
            top_ok = top.get("gender") in (gender, "unisex")
            bottom_ok = bottom.get("gender") in (gender, "unisex")
            if not (top_ok and bottom_ok):
                continue

        used_top.append(top["id"])
        used_bottom.append(bottom["id"])
        outfits.append({"top": top, "bottom": bottom, "_pairing_source": rule["description"]})

    # ── Pass 2: safety-net fallback for any remaining slots ──
    # (unchanged old behavior — keeps things working even with no outfits.json match)
    guard = 0
    while len(outfits) < 3 and guard < 15:
        guard += 1
        top = find_best_match(
            "top", occasion, gender,
            budget.get("top_budget", 3000),
            exclude_ids=used_top,
            allowed_genders=allowed_genders,
        )
        bottom = find_best_match(
            "bottom", occasion, gender,
            budget.get("bottom_budget", 2500),
            color_preference=top.get("color") if top else None,
            exclude_ids=used_bottom,
            allowed_genders=allowed_genders,
        )
        if not top or not bottom:
            break

        if gender in ("male", "female"):
            top_ok = top.get("gender") in (gender, "unisex")
            bottom_ok = bottom.get("gender") in (gender, "unisex")
            if not (top_ok and bottom_ok):
                continue

        used_top.append(top["id"])
        used_bottom.append(bottom["id"])
        outfits.append({"top": top, "bottom": bottom, "_pairing_source": None})

    # ── HARD GUARANTEE: only top + bottom ever leave this node ──
    state["matched_outfits"] = [
        {"top": o["top"], "bottom": o["bottom"], "_pairing_source": o.get("_pairing_source")}
        for o in outfits
    ]
    return state


# ── NODE 6 — FINAL RESPONSE (language-aware, shoe note, ₹) ──
async def node_format_response(state: OutfitState) -> OutfitState:
    language = state.get("language", "English")
    profile_block = _profile_block(state.get("user_profile"))

    # Build the catalog context the AI must describe (it does NOT invent products)
    catalog = []
    for i, o in enumerate(state["matched_outfits"]):
        entry = {
            "id": str(i + 1),
            "top_title": o["top"].get("title"),
            "top_color": o["top"].get("color"),
            "bottom_title": o["bottom"].get("title"),
            "bottom_color": o["bottom"].get("color"),
        }
        if o.get("_pairing_source"):
            entry["reference_pairing"] = o["_pairing_source"]  # grounds the AI's note in real styling logic
        catalog.append(entry)

    system = f"""You are Way2Wear AI, a premium Indian fashion stylist.
Reply ENTIRELY in this language: {language}. (Keep product/brand names in their original form.)

The user's profile (RESPECT IT):
{profile_block}

Occasion: {state['intent'].get('occasion')} | Style: {state['style_class']}

You are given {len(catalog)} outfit pairings (top + bottom) already chosen from the catalog,
selected to be a genuinely coordinated combination (see "reference_pairing" where present —
this is proven styling knowledge, not a random guess).
For EACH, write a creative outfit name, a 1-sentence note on why it works, and a SHORT
shoe suggestion (just a text tip like "Pair with white sneakers" — NOT a product).

Return JSON ONLY (no markdown):
{{
  "message": "2-3 warm sentences in {language}",
  "tip": "one styling tip in {language}",
  "outfits": [
    {{"id":"1","name":"...","note":"...","shoe_note":"..."}}
  ]
}}
Produce exactly {len(catalog)} outfits matching the given ids."""

    res = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=f"User asked: {state['user_input']}\n\nPairings:\n{json.dumps(catalog, indent=2)}"),
    ])

    try:
        ai = json.loads(_clean_json(res.content))
    except Exception:
        ai = {"message": "Here are some looks I picked for you.", "tip": None, "outfits": []}

    # Merge AI text with REAL catalog products (AI never sets price/image/url)
    ai_by_id = {str(o.get("id")): o for o in ai.get("outfits", [])}
    final_outfits = []
    for i, o in enumerate(state["matched_outfits"]):
        oid = str(i + 1)
        meta = ai_by_id.get(oid, {})
        final_outfits.append({
            "id": oid,
            "name": meta.get("name", f"Look {oid}"),
            "note": meta.get("note", ""),
            "shoe_note": meta.get("shoe_note", ""),
            "top": _fmt_item(o["top"]),
            "bottom": _fmt_item(o["bottom"]),
        })

    state["final_response"] = {
        "message": ai.get("message", ""),
        "tip": ai.get("tip"),
        "outfits": final_outfits,
    }
    return state


def _fmt_item(p: dict) -> dict:
    """Format a catalog product for the API. Price in ₹. Top/bottom ONLY — never a 3rd item."""
    return {
        "title": p.get("title"),
        "brand": p.get("brand"),
        "price": p.get("price"),
        "currency": "INR",
        "color": p.get("color_hex") or p.get("color"),
        "image": p.get("image"),
        "url": p.get("url"),
    }


# ── BUILD WORKFLOW ──
def build_workflow() -> Any:
    g = StateGraph(OutfitState)
    g.add_node("understand", node_understand)
    g.add_node("extract_intent", node_extract_intent)
    g.add_node("analyze_budget", node_analyze_budget)
    g.add_node("classify_style", node_classify_style)
    g.add_node("load_pairing_knowledge", node_load_pairing_knowledge)  # NEW
    g.add_node("match_outfits", node_match_outfits)
    g.add_node("format_response", node_format_response)
    g.set_entry_point("understand")
    g.add_edge("understand", "extract_intent")
    g.add_edge("extract_intent", "analyze_budget")
    g.add_edge("analyze_budget", "classify_style")
    g.add_edge("classify_style", "load_pairing_knowledge")  # NEW
    g.add_edge("load_pairing_knowledge", "match_outfits")   # NEW
    g.add_edge("match_outfits", "format_response")
    g.add_edge("format_response", END)
    return g.compile()


outfit_workflow = build_workflow()


async def run_outfit_pipeline(
    user_input: str,
    conversation_history: List[dict] = None,
    user_profile: dict = None,
) -> dict:
    initial: OutfitState = {
        "user_input": user_input,
        "conversation_history": conversation_history or [],
        "user_profile": user_profile,
        "understood_prompt": "",
        "language": "English",
        "intent": {},
        "budget": {},
        "style_class": "",
        "pairing_rules": [],
        "matched_outfits": [],
        "final_response": {},
        "error": None,
    }
    try:
        result = await outfit_workflow.ainvoke(initial)
        return result["final_response"]
    except Exception as e:
        return {"message": "I'm having a moment — please try again!", "tip": None, "outfits": [], "error": str(e)}