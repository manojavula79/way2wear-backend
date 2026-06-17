"""
WAY2WEAR — AI ORCHESTRATION ENGINE  (v2)
LangGraph fashion stylist pipeline.

Key v2 changes:
- Account settings (gender, style, fit, skin tone, height, budget) injected into EVERY prompt.
- STRICT gender filtering so men/women/kids don't mix.
- 3 complete outfits (top + bottom only — NO accessory product).
- Each outfit carries a short shoe_note (text suggestion, not a product).
- Prices in INR (₹).
- Auto-detects the user's language and replies in it (product names stay original).
"""
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from app.config import settings
import json
import re

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


# ── NODE 2 — INTENT (profile overrides gender) ──
async def node_extract_intent(state: OutfitState) -> OutfitState:
    system = """Extract fashion intent. Return JSON only:
{
  "occasion": "wedding|office|casual|date|party|travel|gym|festival|formal|vacation|other",
  "formality": "formal|smart_casual|casual|athletic|ethnic",
  "gender": "male|female|unisex",
  "season": "summer|winter|spring|fall|any",
  "style_keywords": ["..."]
}"""
    res = await llm_precise.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=state["understood_prompt"]),
    ])
    try:
        intent = json.loads(_clean_json(res.content))
    except Exception:
        intent = {"occasion": "casual", "formality": "casual",
                  "gender": "unisex", "season": "any", "style_keywords": []}

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


# ── NODE 5 — MATCH 3 OUTFITS FROM CATALOG (top + bottom) ──
async def node_match_outfits(state: OutfitState) -> OutfitState:
    from app.services.fake_products import find_best_match

    occasion = state["intent"].get("occasion", "casual")
    gender   = state["intent"].get("gender", "unisex")
    budget   = state["budget"]

    outfits = []
    used_top, used_bottom = [], []

    for _ in range(3):  # THREE outfits
        top = find_best_match(
            "top", occasion, gender,
            budget.get("top_budget", 3000),
            exclude_ids=used_top,
        )
        bottom = find_best_match(
            "bottom", occasion, gender,
            budget.get("bottom_budget", 2500),
            color_preference=top.get("color") if top else None,
            exclude_ids=used_bottom,
        )
        if not top or not bottom:
            continue
        used_top.append(top["id"])
        used_bottom.append(bottom["id"])
        outfits.append({"top": top, "bottom": bottom})

    state["matched_outfits"] = outfits
    return state


# ── NODE 6 — FINAL RESPONSE (language-aware, shoe note, ₹) ──
async def node_format_response(state: OutfitState) -> OutfitState:
    language = state.get("language", "English")
    profile_block = _profile_block(state.get("user_profile"))

    # Build the catalog context the AI must describe (it does NOT invent products)
    catalog = []
    for i, o in enumerate(state["matched_outfits"]):
        catalog.append({
            "id": str(i + 1),
            "top_title": o["top"].get("title"),
            "top_color": o["top"].get("color"),
            "bottom_title": o["bottom"].get("title"),
            "bottom_color": o["bottom"].get("color"),
        })

    system = f"""You are Way2Wear AI, a premium Indian fashion stylist.
Reply ENTIRELY in this language: {language}. (Keep product/brand names in their original form.)

The user's profile (RESPECT IT):
{profile_block}

Occasion: {state['intent'].get('occasion')} | Style: {state['style_class']}

You are given {len(catalog)} outfit pairings (top + bottom) already chosen from the catalog.
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
    """Format a catalog product for the API. Price in ₹."""
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
    g.add_node("match_outfits", node_match_outfits)
    g.add_node("format_response", node_format_response)
    g.set_entry_point("understand")
    g.add_edge("understand", "extract_intent")
    g.add_edge("extract_intent", "analyze_budget")
    g.add_edge("analyze_budget", "classify_style")
    g.add_edge("classify_style", "match_outfits")
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
        "matched_outfits": [],
        "final_response": {},
        "error": None,
    }
    try:
        result = await outfit_workflow.ainvoke(initial)
        return result["final_response"]
    except Exception as e:
        return {"message": "I'm having a moment — please try again!", "tip": None, "outfits": [], "error": str(e)}
