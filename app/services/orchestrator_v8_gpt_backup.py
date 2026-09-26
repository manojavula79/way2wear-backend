"""
WAY2WEAR — AI ORCHESTRATION ENGINE

Flow:

User request
    ↓
AI understands natural language
    ↓
User profile
    ↓
Occasion / style / budget
    ↓
outfits.json styling reference
    ↓
Real Supabase product candidates
    ↓
AI selects compatible TOP + BOTTOM pairs
    ↓
Validation
    ↓
Final response

Important:
- outfits.json is reference knowledge only.
- Products always come from the real product catalog.
- AI cannot invent product IDs.
- Only TOP + BOTTOM are product objects.
- Shoes are text-only via shoe_note.
- No random product selection.
"""

from typing import TypedDict, List, Optional, Any
import json
import re
import logging

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings

logger = logging.getLogger("way2wear.orchestrator")


# ============================================================
# OPENAI
# ============================================================

llm = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.7,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=getattr(
        settings,
        "OPENAI_MAX_TOKENS",
        1500,
    ),
)

llm_precise = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.1,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=1000,
)


# ============================================================
# STATE
# ============================================================

class OutfitState(TypedDict):
    user_input: str
    conversation_history: List[dict]
    user_profile: Optional[dict]

    understood_prompt: str
    language: str

    intent: dict
    budget: dict
    style_class: str

    outfit_references: List[Any]

    top_candidates: List[dict]
    bottom_candidates: List[dict]

    matched_outfits: List[dict]

    final_response: dict
    error: Optional[str]


# ============================================================
# HELPERS
# ============================================================

def _clean_json(text: str) -> str:

    text = (text or "").strip()

    text = re.sub(
        r"```json\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"```\s*",
        "",
        text,
    )

    return text.strip()


def _safe_json_loads(text: str, default: dict) -> dict:

    try:
        return json.loads(
            _clean_json(text)
        )
    except Exception:
        return default


def _normalize_profile(profile: Optional[dict]) -> dict:

    p = profile or {}

    return {
        "gender": (
            p.get("gender")
            or p.get("sex")
            or ""
        ),

        "age": (
            p.get("age")
            or p.get("ageYears")
            or ""
        ),

        "stylePreference": (
            p.get("stylePreference")
            or p.get("style_preference")
            or ""
        ),

        "fitType": (
            p.get("fitType")
            or p.get("fit_type")
            or ""
        ),

        "skinTone": (
            p.get("skinTone")
            or p.get("skin_tone")
            or ""
        ),

        "heightCm": (
            p.get("heightCm")
            or p.get("height_cm")
            or ""
        ),

        "budgetRange": (
            p.get("budgetRange")
            or p.get("budget_range")
            or ""
        ),
    }


def _profile_gender(
    profile: Optional[dict],
) -> Optional[str]:

    p = _normalize_profile(profile)

    gender = str(
        p.get("gender") or ""
    ).lower()

    if gender in ("male", "female"):
        return gender

    if gender == "unisex":
        return "unisex"

    return None


def _profile_block(
    profile: Optional[dict],
) -> str:

    p = _normalize_profile(profile)

    if not any(p.values()):
        return (
            "No profile is available. "
            "Use neutral fashion assumptions."
        )

    lines = []

    gender = str(
        p.get("gender") or ""
    ).lower()

    age = p.get("age")

    age_band = None

    try:

        if age not in ("", None):

            age_number = int(age)

            if age_number < 13:
                age_band = "KIDS"

            elif age_number < 18:
                age_band = "TEEN"

            else:
                age_band = "ADULT"

    except Exception:
        age_band = None

    if gender:

        if gender == "male":
            clothing = "MALE clothing"

        elif gender == "female":
            clothing = "FEMALE clothing"

        else:
            clothing = "UNISEX clothing"

        lines.append(
            f"- Gender: {gender}"
        )

        lines.append(
            f"- Clothing category: {clothing}"
        )

    if age_band:

        lines.append(
            f"- Age group: {age_band}"
            + (
                f" ({age} years)"
                if age
                else ""
            )
        )

    if p.get("stylePreference"):
        lines.append(
            f"- Preferred style: {p['stylePreference']}"
        )

    if p.get("fitType"):
        lines.append(
            f"- Preferred fit: {p['fitType']}"
        )

    if p.get("skinTone"):
        lines.append(
            f"- Skin tone: {p['skinTone']}"
        )

    if p.get("heightCm"):
        lines.append(
            f"- Height: {p['heightCm']} cm"
        )

    if p.get("budgetRange"):
        lines.append(
            f"- Budget: {p['budgetRange']}"
        )

    return "\n".join(lines)


def _extract_budget_from_profile(
    profile: Optional[dict],
) -> tuple[int, int]:

    p = _normalize_profile(profile)

    value = str(
        p.get("budgetRange") or ""
    )

    numbers = [
        int(x)
        for x in re.findall(
            r"\d+",
            value.replace(",", ""),
        )
    ]

    if len(numbers) >= 2:
        return numbers[0], numbers[1]

    if len(numbers) == 1:
        return 0, numbers[0]

    return 0, 5000


# ============================================================
# NODE 1
# UNDERSTAND REQUEST
# ============================================================

async def node_understand(
    state: OutfitState,
) -> OutfitState:

    system = """
You are the natural-language understanding layer of Way2Wear.

Understand the user's fashion request.

Return JSON ONLY:

{
  "clarified": "one concise enriched description",
  "language": "English"
}

The clarified description should identify:
- what the user wants
- who it is for
- occasion
- clothing preference
- important constraints
"""

    response = await llm_precise.ainvoke(
        [
            SystemMessage(
                content=system
            ),
            HumanMessage(
                content=state["user_input"]
            ),
        ]
    )

    data = _safe_json_loads(
        response.content,
        {
            "clarified": state["user_input"],
            "language": "English",
        },
    )

    state["understood_prompt"] = (
        data.get("clarified")
        or state["user_input"]
    )

    state["language"] = (
        data.get("language")
        or "English"
    )

    return state


# ============================================================
# NODE 2
# INTENT
# ============================================================

async def node_extract_intent(
    state: OutfitState,
) -> OutfitState:

    system = """
Extract fashion intent.

Return JSON ONLY:

{
  "occasion":
    "wedding|office|casual|date|party|travel|gym|festival|formal|vacation|other",

  "formality":
    "formal|smart_casual|casual|athletic|ethnic",

  "gender":
    "male|female|unisex",

  "season":
    "summer|winter|spring|fall|any",

  "style_keywords":
    []
}

Rules:
- Understand natural language.
- "marriage" means wedding.
- "wedding function" means wedding.
- "office meeting" means office.
- "party" means party.
- "date night" means date.
- Traditional/ethnic wedding requests should use ethnic/formal reasoning.
"""

    response = await llm_precise.ainvoke(
        [
            SystemMessage(
                content=system
            ),
            HumanMessage(
                content=state["understood_prompt"]
            ),
        ]
    )

    intent = _safe_json_loads(
        response.content,
        {
            "occasion": "casual",
            "formality": "casual",
            "gender": "unisex",
            "season": "any",
            "style_keywords": [],
        },
    )

    profile_gender = _profile_gender(
        state.get("user_profile")
    )

    if profile_gender:
        intent["gender"] = profile_gender

    state["intent"] = intent

    return state


# ============================================================
# COMPATIBILITY ALIAS
# Existing chat.py / old code can use this name.
# ============================================================

async def node_understand_intent(
    state: dict,
) -> dict:

    temporary: OutfitState = {
        "user_input": state.get(
            "user_message",
            "",
        ),
        "conversation_history": [],
        "user_profile": state.get(
            "user_profile"
        ),

        "understood_prompt": "",
        "language": "English",

        "intent": state.get(
            "intent",
            {},
        ),

        "budget": {},
        "style_class": "",

        "outfit_references": [],
        "top_candidates": [],
        "bottom_candidates": [],

        "matched_outfits": [],

        "final_response": {},
        "error": None,
    }

    temporary = await node_understand(
        temporary
    )

    temporary = await node_extract_intent(
        temporary
    )

    state["intent"] = temporary["intent"]

    return state


# ============================================================
# NODE 3
# BUDGET
# ============================================================

async def node_analyze_budget(
    state: OutfitState,
) -> OutfitState:

    prompt = state["user_input"]

    patterns = [
        (
            r"under\s*(?:rs\.?|₹)?\s*(\d+)",
            lambda m: (
                0,
                int(m.group(1)),
            ),
        ),

        (
            r"below\s*(?:rs\.?|₹)?\s*(\d+)",
            lambda m: (
                0,
                int(m.group(1)),
            ),
        ),

        (
            r"(?:rs\.?|₹)?\s*(\d+)\s*-\s*(?:rs\.?|₹)?\s*(\d+)",
            lambda m: (
                int(m.group(1)),
                int(m.group(2)),
            ),
        ),

        (
            r"around\s*(?:rs\.?|₹)?\s*(\d+)",
            lambda m: (
                int(
                    int(m.group(1)) * 0.7
                ),
                int(
                    int(m.group(1)) * 1.3
                ),
            ),
        ),

        (
            r"budget.*?(?:rs\.?|₹)?\s*(\d+)",
            lambda m: (
                0,
                int(m.group(1)),
            ),
        ),
    ]

    min_budget = 0
    max_budget = None

    for pattern, converter in patterns:

        match = re.search(
            pattern,
            prompt,
            re.IGNORECASE,
        )

        if match:

            try:
                min_budget, max_budget = (
                    converter(match)
                )
                break

            except Exception:
                pass

    if max_budget is None:

        min_budget, max_budget = (
            _extract_budget_from_profile(
                state.get("user_profile")
            )
        )

    if max_budget <= 0:
        max_budget = 5000

    state["budget"] = {
        "min": int(min_budget),
        "max": int(max_budget),
        "currency": "INR",

        # IMPORTANT:
        # These are maximum catalog budgets.
        # AI still decides the final combination.
        "top_budget": int(
            max_budget * 0.55
        ),

        "bottom_budget": int(
            max_budget * 0.45
        ),
    }

    return state


# ============================================================
# NODE 4
# STYLE
# ============================================================

async def node_classify_style(
    state: OutfitState,
) -> OutfitState:

    intent = state["intent"]

    occasion = intent.get(
        "occasion",
        "casual",
    )

    formality = intent.get(
        "formality",
        "casual",
    )

    profile = _normalize_profile(
        state.get("user_profile")
    )

    preferred_style = (
        profile.get(
            "stylePreference"
        )
        or ""
    )

    style_map = {
        ("formal", "wedding"):
            "Wedding Formal",

        ("ethnic", "wedding"):
            "Ethnic Wedding",

        ("formal", "office"):
            "Business Formal",

        ("smart_casual", "office"):
            "Smart Business Casual",

        ("casual", "date"):
            "Elevated Casual",

        ("casual", "vacation"):
            "Vacation Casual",

        ("casual", "casual"):
            "Modern Casual",

        ("athletic", "gym"):
            "Athleisure",

        ("ethnic", "festival"):
            "Festive Ethnic",
    }

    state["style_class"] = (
        preferred_style
        if preferred_style
        else style_map.get(
            (
                formality,
                occasion,
            ),
            "Contemporary Casual",
        )
    )

    return state


# ============================================================
# NODE 5
# LOAD outfits.json REFERENCE
# ============================================================

async def node_load_reference(
    state: OutfitState,
) -> OutfitState:

    from app.services.outfit_reference import (
        get_relevant_outfit_references,
    )

    intent = state["intent"]

    references = (
        get_relevant_outfit_references(
            occasion=intent.get(
                "occasion",
                "casual",
            ),

            gender=intent.get(
                "gender",
                "unisex",
            ),

            style=state.get(
                "style_class",
                "",
            ),

            style_keywords=intent.get(
                "style_keywords",
                [],
            ),

            limit=15,
        )
    )

    state["outfit_references"] = (
        references
    )

    return state


# ============================================================
# NODE 6
# LOAD REAL PRODUCT CANDIDATES
# ============================================================

async def node_load_product_candidates(
    state: OutfitState,
) -> OutfitState:

    from app.services.fake_products import (
        find_candidate_products,
    )

    intent = state["intent"]

    occasion = intent.get(
        "occasion",
        "casual",
    )

    gender = intent.get(
        "gender",
        "unisex",
    )

    budget = state["budget"]

    profile = _normalize_profile(
        state.get("user_profile")
    )

    style_preference = (
        profile.get(
            "stylePreference"
        )
        or state.get(
            "style_class"
        )
    )

    top_candidates = (
        find_candidate_products(
            item_type="top",
            occasion=occasion,
            gender=gender,
            max_price=budget.get(
                "top_budget",
                3000,
            ),
            count=12,
            style_preference=style_preference,
        )
    )

    bottom_candidates = (
        find_candidate_products(
            item_type="bottom",
            occasion=occasion,
            gender=gender,
            max_price=budget.get(
                "bottom_budget",
                2500,
            ),
            count=12,
            style_preference=style_preference,
        )
    )

    state["top_candidates"] = (
        top_candidates
    )

    state["bottom_candidates"] = (
        bottom_candidates
    )

    return state


# ============================================================
# NODE 7
# AI SELECTS ACTUAL PRODUCT PAIRS
# ============================================================

async def node_ai_match_products(
    state: OutfitState,
) -> OutfitState:

    from app.services.outfit_reference_gpt import (
        build_reference_context,
    )

    profile_block = _profile_block(
        state.get("user_profile")
    )

    reference_context = (
        build_reference_context(
            state.get(
                "outfit_references",
                [],
            )
        )
    )

    top_candidates = state.get(
        "top_candidates",
        [],
    )

    bottom_candidates = state.get(
        "bottom_candidates",
        [],
    )

    # Keep the AI prompt reasonably sized.
    top_for_ai = top_candidates[:12]
    bottom_for_ai = bottom_candidates[:12]

    candidate_context = {
        "tops": [
            _catalog_item_for_ai(x)
            for x in top_for_ai
        ],

        "bottoms": [
            _catalog_item_for_ai(x)
            for x in bottom_for_ai
        ],
    }

    system = f"""
You are the core styling intelligence for Way2Wear.

Your job is to select EXACTLY 3 outfit combinations
from the REAL products supplied below.

==================================================
USER PROFILE
==================================================

{profile_block}

==================================================
REQUEST
==================================================

{state["user_input"]}

==================================================
UNDERSTOOD REQUEST
==================================================

{state["understood_prompt"]}

==================================================
INTENT
==================================================

{json.dumps(
    state["intent"],
    ensure_ascii=False,
    indent=2,
)}

==================================================
STYLE
==================================================

{state["style_class"]}

==================================================
BUDGET
==================================================

{json.dumps(
    state["budget"],
    ensure_ascii=False,
    indent=2,
)}

==================================================
OUTFITS.JSON REFERENCE KNOWLEDGE
==================================================

The following examples are styling references.

They are NOT products.

Do NOT copy product IDs from them.

Do NOT invent products.

Use them only to understand styling relationships.

{reference_context}

==================================================
REAL PRODUCT CATALOG
==================================================

{json.dumps(
    candidate_context,
    ensure_ascii=False,
    indent=2,
)}

==================================================
IMPORTANT RULES
==================================================

1. Select products ONLY from the supplied catalog.

2. NEVER invent a product.

3. Every outfit must contain exactly:
   - one TOP
   - one BOTTOM

4. Do NOT select:
   - shoes
   - sneakers
   - sandals
   - footwear
   - watches
   - belts
   - bags
   - accessories
   - third clothing products

5. The outfits.json file is reference knowledge only.

6. Use the user's:
   - gender
   - age
   - style preference
   - fit type
   - skin tone
   - height
   - budget

   when deciding which combinations make sense.

7. Consider actual color harmony.

8. Consider occasion appropriateness.

9. Consider traditional/modern/formal/casual requirements.

10. Do not simply pair products because their colors are identical.

11. Prefer visually compatible combinations.

12. Do not repeat the same TOP.

13. Do not repeat the same BOTTOM.

14. Keep total outfit price within the user's budget whenever possible.

15. If exact budget matching is impossible, select the closest valid combination.

16. shoe_note must be TEXT ONLY.
   Example:
   "Complete the look with traditional brown mojari."

17. Do NOT return shoe product IDs.

18. Do NOT return shoe images.
19. Do NOT return shoe prices.
SHOE DISPLAY RULE:
- Shoes must NEVER be returned as a product.
- Do NOT create a shoe product card.
- Do NOT return shoe image.
- Do NOT return shoe price.
- Do NOT return shoe URL.
- Do NOT return shoe ID.
- You may include ONE short shoe_note as plain text.
- shoe_note should be optional and concise.
- Example:
  "White sneakers would pair well."
  "Brown loafers would complement this outfit."
  "White sneakers work well for this casual look."

==================================================
RETURN JSON ONLY
==================================================

{{
  "outfits": [
    {{
      "top_id": "REAL_TOP_ID",
      "bottom_id": "REAL_BOTTOM_ID",
      "shoe_note": "text only"
    }},
    {{
      "top_id": "REAL_TOP_ID",
      "bottom_id": "REAL_BOTTOM_ID",
      "shoe_note": "text only"
    }},
    {{
      "top_id": "REAL_TOP_ID",
      "bottom_id": "REAL_BOTTOM_ID",
      "shoe_note": "text only"
    }}
  ]
}}

Return exactly 3 outfits if enough valid products exist.
"""

    response = await llm_precise.ainvoke(
        [
            SystemMessage(
                content=system
            ),
            HumanMessage(
                content=(
                    "Select the best real TOP + BOTTOM combinations "
                    "based primarily on the user's intent and occasion. "
                    "Do not select shoe products. "
                    "A shoe_note may be included only as short text."
                )
            ),
        ]
    )

    data = _safe_json_loads(
        response.content,
        {
            "outfits": []
        },
    )

    # --------------------------------------------------------
    # Create product lookup
    # --------------------------------------------------------

    all_products = (
        top_candidates
        + bottom_candidates
    )

    product_by_id = {
        str(p.get("id")): p
        for p in all_products
    }

    matched = []

    used_top = set()
    used_bottom = set()

    for item in data.get(
        "outfits",
        [],
    ):

        top_id = str(
            item.get("top_id", "")
        )

        bottom_id = str(
            item.get("bottom_id", "")
        )

        top = product_by_id.get(
            top_id
        )

        bottom = product_by_id.get(
            bottom_id
        )

        if not top or not bottom:
            continue

        if (
            top_id in used_top
            or bottom_id in used_bottom
        ):
            continue

        # ----------------------------------------------------
        # HARD VALIDATION
        # ----------------------------------------------------

        if top.get("type") != "top":
            continue

        if bottom.get("type") != "bottom":
            continue

        gender = state["intent"].get(
            "gender",
            "unisex",
        )

        if gender in (
            "male",
            "female",
        ):

            top_gender = top.get(
                "gender"
            )

            bottom_gender = bottom.get(
                "gender"
            )

            if top_gender not in (
                gender,
                "unisex",
            ):
                continue

            if bottom_gender not in (
                gender,
                "unisex",
            ):
                continue

        matched.append(
            {
                "top": top,
                "bottom": bottom,
                "shoe_note": (
                    item.get(
                        "shoe_note",
                        "",
                    )
                    or ""
                ),
            }
        )

        used_top.add(top_id)
        used_bottom.add(bottom_id)

        if len(matched) >= 3:
            break

    state["matched_outfits"] = matched

    return state

# ============================================================
# AI PRODUCT VIEW
# ============================================================

def _catalog_item_for_ai(
    product: dict,
) -> dict:

    return {
        "id": str(
            product.get("id")
        ),

        "title": product.get(
            "title"
        ),

        "brand": product.get(
            "brand"
        ),

        "type": product.get(
            "type"
        ),

        "gender": product.get(
            "gender"
        ),

        "color": product.get(
            "color"
        ),

        "style": product.get(
            "style",
            [],
        ),

        "occasions": product.get(
            "occasions",
            [],
        ),

        "price": product.get(
            "price"
        ),
    }


# ============================================================
# NODE 8
# FORMAT RESPONSE
# ============================================================

async def node_format_response(
    state: OutfitState,
) -> OutfitState:

    language = state.get(
        "language",
        "English",
    )

    profile_block = _profile_block(
        state.get("user_profile")
    )

    outfits = state.get(
        "matched_outfits",
        [],
    )

    if not outfits:

        state["final_response"] = {
            "message": (
                "I couldn't find enough matching "
                "products for this request."
            ),

            "tip": (
                "Try increasing the budget or "
                "changing the occasion."
            ),

            "outfits": [],
        }

        return state

    catalog = []

    for index, outfit in enumerate(
        outfits,
        start=1,
    ):

        catalog.append(
            {
                "id": str(index),

                "top": _catalog_item_for_ai(
                    outfit["top"]
                ),

                "bottom": _catalog_item_for_ai(
                    outfit["bottom"]
                ),

                "shoe_note": outfit.get(
                    "shoe_note",
                    "",
                ),
            }
        )

    system = f"""
You are Way2Wear AI, a premium fashion stylist.

Reply entirely in:
{language}

Keep product names and brand names exactly as provided.

USER PROFILE:
{profile_block}

REQUEST:
{state["user_input"]}

OCCASION:
{state["intent"].get("occasion")}

STYLE:
{state["style_class"]}

You are given real product combinations already selected.

Do NOT change the products.

Do NOT invent products.

For each outfit:
- create a useful outfit name
- explain briefly why the TOP + BOTTOM combination works
- keep shoe_note as a short text-only suggestion

Never add:
- shoe products
- accessory products
- third clothing products

Return JSON ONLY:

{{
  "message": "...",
  "tip": "...",
  "outfits": [
    {{
      "id": "1",
      "name": "...",
      "note": "...",
      "shoe_note": "..."
    }}
  ]
}}
"""

    response = await llm.ainvoke(
        [
            SystemMessage(
                content=system
            ),
            HumanMessage(
                content=json.dumps(
                    catalog,
                    ensure_ascii=False,
                    indent=2,
                )
            ),
        ]
    )

    ai = _safe_json_loads(
        response.content,
        {
            "message": (
                "Here are some outfit "
                "ideas for you."
            ),

            "tip": None,

            "outfits": [],
        },
    )

    ai_by_id = {
        str(x.get("id")): x
        for x in ai.get(
            "outfits",
            [],
        )
    }

    final_outfits = []

    for index, outfit in enumerate(
        outfits,
        start=1,
    ):

        oid = str(index)

        metadata = ai_by_id.get(
            oid,
            {},
        )

        final_outfits.append(
            {
                "id": oid,

                "name": metadata.get(
                    "name",
                    f"Look {oid}",
                ),

                "note": metadata.get(
                    "note",
                    "",
                ),

                "shoe_note": metadata.get(
                    "shoe_note",
                    outfit.get(
                        "shoe_note",
                        "",
                    ),
                ),

                # ONLY PRODUCTS
                "top": _fmt_item(
                    outfit["top"]
                ),

                "bottom": _fmt_item(
                    outfit["bottom"]
                ),
            }
        )

    state["final_response"] = {
        "message": ai.get(
            "message",
            "",
        ),

        "tip": ai.get(
            "tip"
        ),

        "outfits": final_outfits,
    }

    return state


# ============================================================
# PRODUCT RESPONSE FORMAT
# ============================================================

def _fmt_item(
    product: dict,
) -> dict:

    return {
        "title": product.get(
            "title"
        ),

        "brand": product.get(
            "brand"
        ),

        "price": product.get(
            "price"
        ),

        "currency": "INR",

        "color": (
            product.get(
                "color_hex"
            )
            or product.get(
                "color"
            )
        ),

        "image": product.get(
            "image"
        ),

        "url": product.get(
            "url"
        ),
    }


# ============================================================
# BUILD WORKFLOW
# ============================================================

def build_workflow() -> Any:

    graph = StateGraph(
        OutfitState
    )

    graph.add_node(
        "understand",
        node_understand,
    )

    graph.add_node(
        "extract_intent",
        node_extract_intent,
    )

    graph.add_node(
        "analyze_budget",
        node_analyze_budget,
    )

    graph.add_node(
        "classify_style",
        node_classify_style,
    )

    graph.add_node(
        "load_reference",
        node_load_reference,
    )

    graph.add_node(
        "load_products",
        node_load_product_candidates,
    )

    graph.add_node(
        "ai_match",
        node_ai_match_products,
    )

    graph.add_node(
        "format_response",
        node_format_response,
    )

    graph.set_entry_point(
        "understand"
    )

    graph.add_edge(
        "understand",
        "extract_intent",
    )

    graph.add_edge(
        "extract_intent",
        "analyze_budget",
    )

    graph.add_edge(
        "analyze_budget",
        "classify_style",
    )

    graph.add_edge(
        "classify_style",
        "load_reference",
    )

    graph.add_edge(
        "load_reference",
        "load_products",
    )

    graph.add_edge(
        "load_products",
        "ai_match",
    )

    graph.add_edge(
        "ai_match",
        "format_response",
    )

    graph.add_edge(
        "format_response",
        END,
    )

    return graph.compile()


outfit_workflow = build_workflow()


# ============================================================
# PUBLIC API
# ============================================================

async def run_outfit_pipeline(
    user_input: str,
    conversation_history: List[dict] = None,
    user_profile: dict = None,
) -> dict:

    initial: OutfitState = {

        "user_input": user_input,

        "conversation_history":
            conversation_history or [],

        "user_profile":
            user_profile or {},

        "understood_prompt": "",

        "language": "English",

        "intent": {},

        "budget": {},

        "style_class": "",

        "outfit_references": [],

        "top_candidates": [],

        "bottom_candidates": [],

        "matched_outfits": [],

        "final_response": {},

        "error": None,
    }

    try:

        result = await outfit_workflow.ainvoke(
            initial
        )

        return result[
            "final_response"
        ]

    except Exception as e:

        logger.exception(
            "Outfit pipeline failed"
        )

        return {
            "message": (
                "I couldn't generate "
                "the outfit right now."
            ),

            "tip": (
                "Please try again with "
                "the occasion and budget."
            ),

            "outfits": [],

            "error": str(e),
        }


# ============================================================
# LEGACY COMPATIBILITY
# ============================================================

async def run_steps_1_to_3(
    user_message: str,
    user_profile: dict = None,
) -> dict:
    """
    Compatibility wrapper for the old /query-curated endpoint.

    New /chat does NOT use this as the primary outfit generator.
    """

    state: OutfitState = {

        "user_input": user_message,

        "conversation_history": [],

        "user_profile":
            user_profile or {},

        "understood_prompt": "",

        "language": "English",

        "intent": {},

        "budget": {},

        "style_class": "",

        "outfit_references": [],

        "top_candidates": [],

        "bottom_candidates": [],

        "matched_outfits": [],

        "final_response": {},

        "error": None,
    }

    state = await node_understand(
        state
    )

    state = await node_extract_intent(
        state
    )

    state = await node_analyze_budget(
        state
    )

    state = await node_classify_style(
        state
    )

    state = await node_load_reference(
        state
    )

    state = await node_load_product_candidates(
        state
    )

    state = await node_ai_match_products(
        state
    )

    return {
        "intent": state["intent"],

        "query_params": {
            "occasion":
                state["intent"].get(
                    "occasion"
                ),

            "gender":
                state["intent"].get(
                    "gender"
                ),

            "style":
                state["style_class"],

            "budget":
                state["budget"],
        },

        "curated_outfits": [
            {
                "id": index + 1,

                "outfit_text": (
                    f"{o['top'].get('title')} "
                    f"+ "
                    f"{o['bottom'].get('title')}"
                ),

                "budget_min": (
                    (o["top"].get("price") or 0)
                    +
                    (o["bottom"].get("price") or 0)
                ),

                "budget_max": (
                    (o["top"].get("price") or 0)
                    +
                    (o["bottom"].get("price") or 0)
                ),

                "style_tags": (
                    state["intent"].get(
                        "style_keywords",
                        [],
                    )
                ),
            }

            for index, o in enumerate(
                state[
                    "matched_outfits"
                ]
            )
        ],
    }


# ============================================================
# PERSON CONTEXT HELPERS
# ============================================================

def detect_person_context(
    message: str,
) -> dict:

    text = (
        message or ""
    ).lower()

    relationships = {
        "brother": "brother",
        "sister": "sister",
        "son": "son",
        "daughter": "daughter",
        "wife": "wife",
        "husband": "husband",
        "mother": "mother",
        "mom": "mother",
        "father": "father",
        "dad": "father",
        "friend": "friend",
        "cousin": "cousin",
    }

    for word, person_type in (
        relationships.items()
    ):

        if re.search(
            rf"\b{re.escape(word)}\b",
            text,
        ):

            return {
                "is_for_someone_else": True,
                "person_type": person_type,
            }

    return {
        "is_for_someone_else": False,
        "person_type": None,
    }


def check_profile_form_needed(
    intent: dict,
    is_for_someone_else: bool,
) -> bool:

    if not is_for_someone_else:
        return False

    gender = (
        intent or {}
    ).get("gender")

    return gender not in (
        "male",
        "female",
    )