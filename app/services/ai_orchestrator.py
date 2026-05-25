"""
WAY2WEAR — AI ORCHESTRATION ENGINE
LangGraph 11-Node Fashion Stylist Pipeline
"""
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from app.config import settings
import json
import re

# ── LLM Instance ─────────────────────────────
llm = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.7,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=settings.OPENAI_MAX_TOKENS,
)

llm_precise = ChatOpenAI(
    model=settings.OPENAI_MODEL,
    temperature=0.2,
    api_key=settings.OPENAI_API_KEY,
    max_tokens=800,
)


# ══════════════════════════════════════════════
# STATE DEFINITION
# ══════════════════════════════════════════════

class OutfitState(TypedDict):
    # Input
    user_input: str
    conversation_history: List[dict]
    user_profile: Optional[dict]

    # Node outputs
    understood_prompt: str                  # Node 1
    intent: dict                            # Node 2
    budget: dict                            # Node 3
    style_class: str                        # Node 4
    outfit_plans: List[dict]               # Node 5
    color_analysis: dict                    # Node 6
    matched_products: List[dict]           # Node 7
    affiliate_urls: List[dict]             # Node 8
    validated_outfits: List[dict]          # Node 9
    ranked_outfits: List[dict]             # Node 10
    final_response: dict                   # Node 11

    # Metadata
    error: Optional[str]
    usage: Optional[dict]


# ══════════════════════════════════════════════
# NODE 1 — PROMPT UNDERSTANDING
# ══════════════════════════════════════════════

async def node_understand_prompt(state: OutfitState) -> OutfitState:
    """Deeply understand what the user is asking for"""
    system = """You are a fashion intent analyzer. Given a user message, 
    extract and clarify the fashion request. Return a clean, enriched 
    description of what the user wants. Output plain text only."""

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"User request: {state['user_input']}"),
    ]

    response = await llm_precise.ainvoke(messages)
    state["understood_prompt"] = response.content.strip()
    return state


# ══════════════════════════════════════════════
# NODE 2 — INTENT EXTRACTION
# ══════════════════════════════════════════════

async def node_extract_intent(state: OutfitState) -> OutfitState:
    """Extract structured intent: occasion, gender, formality, season"""
    system = """Extract fashion intent from the prompt. Return JSON only:
    {
        "occasion": "wedding|office|casual|date|party|travel|gym|formal|other",
        "formality": "formal|smart_casual|casual|athletic",
        "gender": "male|female|unisex",
        "season": "summer|winter|spring|fall|any",
        "style_keywords": ["minimalist", "classic", etc],
        "is_gift": true|false,
        "urgency": "now|soon|planning"
    }"""

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=state["understood_prompt"]),
    ]

    response = await llm_precise.ainvoke(messages)
    try:
        state["intent"] = json.loads(_clean_json(response.content))
    except Exception:
        state["intent"] = {
            "occasion": "casual",
            "formality": "casual",
            "gender": "male",
            "season": "any",
            "style_keywords": [],
            "is_gift": False,
            "urgency": "soon",
        }
    return state


# ══════════════════════════════════════════════
# NODE 3 — BUDGET ANALYSIS
# ══════════════════════════════════════════════

async def node_analyze_budget(state: OutfitState) -> OutfitState:
    """Extract budget constraints from the prompt"""
    prompt = state["user_input"]
    profile_budget = (state.get("user_profile") or {}).get("budget_range", "$200 - $500")

    # Parse budget from text (e.g., "under $300", "$200-$400")
    budget_patterns = [
        (r"under\s*\$?(\d+)", lambda m: (0, int(m.group(1)))),
        (r"\$?(\d+)\s*-\s*\$?(\d+)", lambda m: (int(m.group(1)), int(m.group(2)))),
        (r"below\s*\$?(\d+)", lambda m: (0, int(m.group(1)))),
        (r"around\s*\$?(\d+)", lambda m: (int(m.group(1)) * 0.7, int(m.group(1)) * 1.3)),
        (r"budget.*?\$?(\d+)", lambda m: (0, int(m.group(1)))),
    ]

    min_b, max_b = 0, 500  # default
    for pattern, extractor in budget_patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            try:
                min_b, max_b = extractor(match)
                break
            except Exception:
                pass

    state["budget"] = {
        "min": int(min_b),
        "max": int(max_b),
        "currency": "USD",
        "profile_range": profile_budget,
        "top_budget": int(max_b * 0.45),
        "bottom_budget": int(max_b * 0.35),
        "accessory_budget": int(max_b * 0.20),
    }
    return state


# ══════════════════════════════════════════════
# NODE 4 — STYLE CLASSIFICATION
# ══════════════════════════════════════════════

async def node_classify_style(state: OutfitState) -> OutfitState:
    """Classify the primary style direction"""
    intent = state["intent"]
    formality = intent.get("formality", "casual")
    occasion = intent.get("occasion", "casual")
    keywords = intent.get("style_keywords", [])

    # Rule-based + AI classification
    style_map = {
        ("formal", "wedding"): "Black Tie / Formal",
        ("smart_casual", "office"): "Smart Business Casual",
        ("casual", "date"): "Elevated Casual",
        ("formal", "office"): "Business Formal",
        ("casual", "casual"): "Modern Minimalist Casual",
        ("athletic", "gym"): "Performance Athleisure",
    }

    style = style_map.get((formality, occasion), "Contemporary Casual")

    if "minimalist" in keywords:
        style = f"Minimalist {style}"
    elif "classic" in keywords:
        style = f"Classic {style}"

    state["style_class"] = style
    return state


# ══════════════════════════════════════════════
# NODE 5 — OUTFIT PLANNING
# ══════════════════════════════════════════════

async def node_plan_outfits(state: OutfitState) -> OutfitState:
    """Plan 2-3 outfit combinations"""
    system = f"""You are an elite fashion stylist. Plan 2 distinct outfit combinations.
    
    Context:
    - Style: {state['style_class']}
    - Occasion: {state['intent'].get('occasion')}
    - Formality: {state['intent'].get('formality')}
    - Gender: {state['intent'].get('gender', 'male')}
    - Budget: ${state['budget']['min']} - ${state['budget']['max']}
    - Top budget: ~${state['budget']['top_budget']}
    - Bottom budget: ~${state['budget']['bottom_budget']}

    Return JSON array only:
    [
        {{
            "outfit_number": 1,
            "outfit_name": "Classic Navy Ensemble",
            "top": {{"item": "Navy Wool Blazer", "color": "navy", "hex": "#1a3a5c", "price_range": [180, 260]}},
            "bottom": {{"item": "Slim Fit Charcoal Trousers", "color": "charcoal", "hex": "#3d3d3d", "price_range": [80, 140]}},
            "accessory": {{"item": "Brown Oxford Shoes", "color": "cognac brown", "hex": "#8B4513", "price_range": [60, 120]}},
            "color_story": "navy and charcoal with warm cognac accent"
        }}
    ]"""

    history_context = "\n".join([
        f"{m['role']}: {m['content'][:100]}"
        for m in (state.get("conversation_history") or [])[-4:]
    ])

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"Request: {state['understood_prompt']}\n\nHistory:\n{history_context}"),
    ]

    response = await llm.ainvoke(messages)
    try:
        state["outfit_plans"] = json.loads(_clean_json(response.content))
    except Exception:
        state["outfit_plans"] = []
    return state


# ══════════════════════════════════════════════
# NODE 6 — COLOR COMPATIBILITY ANALYSIS
# ══════════════════════════════════════════════

async def node_color_compatibility(state: OutfitState) -> OutfitState:
    """Validate and optimize color combinations"""
    outfits = state["outfit_plans"]

    # Color harmony rules
    harmonious_combos = {
        "navy": ["white", "grey", "beige", "khaki", "cognac", "charcoal", "light blue"],
        "black": ["white", "grey", "red", "beige", "gold", "silver", "navy"],
        "white": ["navy", "black", "beige", "grey", "pastels", "olive"],
        "beige": ["navy", "white", "brown", "olive", "burgundy", "black"],
        "grey": ["navy", "white", "black", "blue", "burgundy", "pink"],
        "olive": ["beige", "white", "brown", "navy", "rust"],
        "brown": ["beige", "navy", "olive", "white", "cream"],
        "burgundy": ["grey", "navy", "beige", "cream", "black"],
    }

    analysis = {}
    for i, outfit in enumerate(outfits):
        top_color = (outfit.get("top") or {}).get("color", "").lower()
        bottom_color = (outfit.get("bottom") or {}).get("color", "").lower()
        acc_color = (outfit.get("accessory") or {}).get("color", "").lower()

        compatible = harmonious_combos.get(top_color, [])
        score = 100
        notes = []

        if any(c in bottom_color for c in compatible):
            notes.append("Top and bottom colors harmonize well")
        else:
            score -= 15
            notes.append("Color contrast creates visual interest")

        analysis[f"outfit_{i+1}"] = {
            "harmony_score": score,
            "notes": notes,
            "valid": score >= 70,
        }

    state["color_analysis"] = analysis
    return state


# ══════════════════════════════════════════════
# NODE 7 — PRODUCT MATCHING (Fake Catalog)
# ══════════════════════════════════════════════

async def node_match_products(state: OutfitState) -> OutfitState:
    """
    Match outfit plans to real products from the fake catalog.
    No AI call needed — pure catalog lookup.
    Replace fake_products.py with real DB/API when ready.
    """
    from app.services.fake_products import find_best_match

    occasion = state["intent"].get("occasion", "casual")
    gender   = state["intent"].get("gender", "male")
    budget   = state["budget"]

    matched = []

    for i, plan in enumerate(state["outfit_plans"]):
        # Find real products from catalog
        top = find_best_match(
            product_type="top",
            occasion=occasion,
            gender=gender,
            max_price=budget.get("top_budget", 150),
            color_preference=plan.get("top", {}).get("color", ""),
            exclude_ids=[m.get("top", {}).get("id") for m in matched],
        )
        bottom = find_best_match(
            product_type="bottom",
            occasion=occasion,
            gender=gender,
            max_price=budget.get("bottom_budget", 100),
            color_preference=plan.get("bottom", {}).get("color", ""),
            exclude_ids=[m.get("bottom", {}).get("id") for m in matched],
        )
        accessory = find_best_match(
            product_type="accessory",
            occasion=occasion,
            gender=gender,
            max_price=budget.get("accessory_budget", 80),
            exclude_ids=[],
        )

        if not top or not bottom:
            # Fallback: keep original AI plan with placeholder
            matched.append(plan)
            continue

        matched.append({
            **plan,
            "top":       top,
            "bottom":    bottom,
            "accessory": accessory,
        })

    state["matched_products"] = matched if matched else state["outfit_plans"]
    return state


# ══════════════════════════════════════════════
# NODE 8 — URL MAPPING (Fake → real later)
# ══════════════════════════════════════════════

async def node_map_affiliate_urls(state: OutfitState) -> OutfitState:
    """
    Products from fake catalog already have URLs set.
    This node normalises the structure and adds price_range
    so downstream nodes work without changes.
    When you get your Amazon affiliate tag, update
    fake_products.py URLs to real Amazon links.
    """
    normalised = []

    for outfit in state["matched_products"]:
        outfit_copy = outfit.copy()

        for key in ["top", "bottom", "accessory"]:
            item = outfit_copy.get(key)
            if not item:
                continue

            # Ensure all fields the formatter expects exist
            item.setdefault("affiliate_url", item.get("url", "#"))
            item.setdefault("price_range",   [item.get("price", 0)] * 2)
            item.setdefault("brand",         item.get("brand", ""))
            item.setdefault("color_hex",     item.get("color_hex", "#888888"))
            outfit_copy[key] = item

        normalised.append(outfit_copy)

    state["affiliate_urls"] = normalised
    return state


# ══════════════════════════════════════════════
# NODE 9 — OUTFIT VALIDATION
# ══════════════════════════════════════════════

async def node_validate_outfit(state: OutfitState) -> OutfitState:
    """Quality gate: ensure outfits meet standards"""
    validated = []

    for i, outfit in enumerate(state["affiliate_urls"]):
        color_key = f"outfit_{i+1}"
        color_valid = state["color_analysis"].get(color_key, {}).get("valid", True)

        # Validate price within budget
        # Use `or {}` so a None value (key exists but is None) doesn't crash .get()
        top_item = outfit.get("top") or {}
        bot_item = outfit.get("bottom") or {}
        acc_item = outfit.get("accessory") or {}

        top_price = _safe_price(top_item.get("price_range", [top_item.get("price", 0)] * 2))
        bot_price = _safe_price(bot_item.get("price_range", [bot_item.get("price", 0)] * 2))
        acc_price = _safe_price(acc_item.get("price_range", [acc_item.get("price", 0)] * 2))
        total = top_price + bot_price + acc_price

        # Validate required fields — catalog uses "title", AI plans use "item"
        has_top = bool(top_item.get("item") or top_item.get("title"))
        has_bottom = bool(bot_item.get("item") or bot_item.get("title"))

        if has_top and has_bottom and color_valid:
            outfit["total_price"] = total
            outfit["validation_score"] = 100 if total <= state["budget"]["max"] else 80
            validated.append(outfit)

    state["validated_outfits"] = validated or state["affiliate_urls"]
    return state


# ══════════════════════════════════════════════
# NODE 10 — RECOMMENDATION RANKING
# ══════════════════════════════════════════════

async def node_rank_recommendations(state: OutfitState) -> OutfitState:
    """Sort outfits by relevance score"""
    outfits = state["validated_outfits"]

    def score(outfit: dict) -> float:
        s = float(outfit.get("validation_score", 80))
        # Prefer outfits within budget
        total = outfit.get("total_price", 0)
        max_b = state["budget"]["max"]
        if max_b > 0 and total <= max_b:
            s += 10
        elif max_b > 0 and total <= max_b * 1.1:
            s += 5
        return s

    state["ranked_outfits"] = sorted(outfits, key=score, reverse=True)
    return state


# ══════════════════════════════════════════════
# NODE 11 — FINAL RESPONSE FORMATTING
# ══════════════════════════════════════════════

async def node_format_response(state: OutfitState) -> OutfitState:
    """
    Node 11: Generate conversational text via AI, then attach
    real catalog products. Falls back to AI-generated products
    if catalog matching returned empty results.
    """
    from app.services.fake_products import build_outfit_from_catalog

    occasion = state["intent"].get("occasion", "casual")
    gender   = state["intent"].get("gender", "male")
    budget   = state["budget"]

    # ── Step A: ALWAYS build from catalog (guaranteed real data) ──
    # ranked_outfits may contain AI-plan items (no brand/image/color).
    # We use the catalog directly so every response has real products.
    catalog_outfits = build_outfit_from_catalog(occasion, gender, budget)

    # Fallback: if catalog returns nothing, try ranked_outfits
    if not catalog_outfits:
        catalog_outfits = state["ranked_outfits"][:2]

    # ── Step B: AI writes conversational text only ──
    system = f"""You are Way2Wear AI, a warm expert fashion stylist.
Style: {state["style_class"]}  Occasion: {occasion}
Return JSON ONLY (no markdown, no backticks):
{{"message":"2-3 warm expert sentences about the outfits","tip":"one punchy styling tip",
"outfit_names":["Creative outfit name 1","Creative outfit name 2"],
"outfit_notes":["Why outfit 1 works for this occasion","Why outfit 2 works"]}}"""

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=f"User asked: {state['user_input']}"),
        ])
        td = json.loads(_clean_json(resp.content))
    except Exception:
        td = {
            "message": f"I've put together some great outfit options for your {occasion}! These combinations are carefully selected for style and occasion.",
            "tip": "A well-fitted outfit always outperforms an expensive ill-fitting one.",
            "outfit_names": ["Outfit Option 1", "Outfit Option 2"],
            "outfit_notes": ["A classic combination that works perfectly.", "A versatile look for the occasion."],
        }

    # ── Step C: Map catalog items to API response format ──
    def fmt_item(item: dict) -> dict:
        """Safely extract fields from catalog product dict."""
        if not item:
            return {"title": "Style Item", "brand": "Brand", "price": 0, "color": "#888888", "url": "#", "image": None}
        return {
            "title": item.get("title") or item.get("item") or "Style Item",
            "brand": item.get("brand") or "Brand",
            "price": float(item.get("price") or item.get("price_range", [0, 0])[0] or 0),
            "color": item.get("color_hex") or item.get("hex") or item.get("color") or "#888888",
            "url":   item.get("url") or item.get("affiliate_url") or "#",
            "image": item.get("image") or None,
        }

    names = td.get("outfit_names") or []
    notes = td.get("outfit_notes") or []
    outfits = []

    for i, ranked in enumerate(catalog_outfits[:2]):
        entry: dict = {
            "id":     str(i + 1),
            "name":   names[i] if i < len(names) else f"Outfit {i + 1}",
            "top":    fmt_item(ranked.get("top")),
            "bottom": fmt_item(ranked.get("bottom")),
            "note":   notes[i] if i < len(notes) else "A great combination for this occasion.",
        }
        accessory = ranked.get("accessory")
        if accessory:
            entry["accessory"] = fmt_item(accessory)
        outfits.append(entry)

    # Final safety: ensure at least 1 outfit always returned
    if not outfits:
        from app.services.fake_products import FAKE_PRODUCTS
        tops  = [p for p in FAKE_PRODUCTS if p["type"] == "top"][:1]
        bots  = [p for p in FAKE_PRODUCTS if p["type"] == "bottom"][:1]
        accs  = [p for p in FAKE_PRODUCTS if p["type"] == "accessory"][:1]
        if tops and bots:
            outfits = [{
                "id": "1", "name": "Curated Look",
                "top":       fmt_item(tops[0]),
                "bottom":    fmt_item(bots[0]),
                "accessory": fmt_item(accs[0]) if accs else None,
                "note":      "A timeless combination that works for any occasion.",
            }]

    state["final_response"] = {
        "message": td.get("message", "Here are your outfit recommendations!"),
        "tip":     td.get("tip") or None,
        "outfits": outfits,
    }
    return state


# ══════════════════════════════════════════════
# BUILD THE LANGGRAPH WORKFLOW
# ══════════════════════════════════════════════

def build_workflow() -> Any:
    workflow = StateGraph(OutfitState)

    # Add all 11 nodes
    workflow.add_node("understand",          node_understand_prompt)
    workflow.add_node("extract_intent",      node_extract_intent)
    workflow.add_node("analyze_budget",      node_analyze_budget)
    workflow.add_node("classify_style",      node_classify_style)
    workflow.add_node("plan_outfits",        node_plan_outfits)
    workflow.add_node("check_colors",         node_color_compatibility)
    workflow.add_node("match_products",      node_match_products)
    workflow.add_node("map_affiliate_urls",  node_map_affiliate_urls)
    workflow.add_node("validate_outfit",     node_validate_outfit)
    workflow.add_node("rank_recommendations",node_rank_recommendations)
    workflow.add_node("format_response",     node_format_response)

    # Chain all nodes
    workflow.set_entry_point("understand")
    workflow.add_edge("understand",           "extract_intent")
    workflow.add_edge("extract_intent",       "analyze_budget")
    workflow.add_edge("analyze_budget",       "classify_style")
    workflow.add_edge("classify_style",       "plan_outfits")
    workflow.add_edge("plan_outfits",         "check_colors")
    workflow.add_edge("check_colors",         "match_products")
    workflow.add_edge("match_products",       "map_affiliate_urls")
    workflow.add_edge("map_affiliate_urls",   "validate_outfit")
    workflow.add_edge("validate_outfit",      "rank_recommendations")
    workflow.add_edge("rank_recommendations", "format_response")
    workflow.add_edge("format_response",      END)

    return workflow.compile()


# Global compiled workflow
outfit_workflow = build_workflow()


# ── Helpers ───────────────────────────────────
def _clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _safe_price(price_range) -> float:
    try:
        if isinstance(price_range, list) and len(price_range) >= 2:
            return (price_range[0] + price_range[1]) / 2
        if isinstance(price_range, (int, float)):
            return float(price_range)
        return 0.0
    except Exception:
        return 0.0


# ── Main entry point ──────────────────────────
async def run_outfit_pipeline(
    user_input: str,
    conversation_history: List[dict] = None,
    user_profile: dict = None,
) -> dict:
    """Run the complete 11-node pipeline and return the final response"""
    initial_state: OutfitState = {
        "user_input": user_input,
        "conversation_history": conversation_history or [],
        "user_profile": user_profile,
        "understood_prompt": "",
        "intent": {},
        "budget": {},
        "style_class": "",
        "outfit_plans": [],
        "color_analysis": {},
        "matched_products": [],
        "affiliate_urls": [],
        "validated_outfits": [],
        "ranked_outfits": [],
        "final_response": {},
        "error": None,
        "usage": None,
    }

    try:
        result = await outfit_workflow.ainvoke(initial_state)
        return result["final_response"]
    except Exception as e:
        return {
            "message": "I'm having a moment — please try again! I'm ready to style you.",
            "tip": None,
            "outfits": [],
            "error": str(e),
        }
