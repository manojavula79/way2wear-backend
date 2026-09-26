import json
import re
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from app.config import settings


GLOBAL_SEARCH_SYSTEM_PROMPT = r"""
You are Way2Wear Global Search Intent Engine, an expert fashion-shopping query planner.

Your job is to convert a user's natural-language fashion request into a precise JSON
search plan for finding publicly available real product pages on the web.

STRICT RULES:
1. Return valid JSON only. Never use Markdown fences.
2. Never invent product names, prices, URLs, images, brands, or availability.
3. Keep the output practical for Indian shopping and INR budgets.
4. The system searches only for two product categories: TOP and BOTTOM.
5. Do not add shoes, watches, bags, accessories, cosmetics, or complete outfits as products.
6. Preserve explicit gender from the user message. If gender is not stated, return null.
7. If a profile gender is supplied, it may be used as a default, but do not override explicit
   gender stated in the message.
8. If the request is for another person, the caller will separately handle the profile form.
9. Translate vague requests into useful search terms without adding unsupported assumptions.
10. Use concise search queries suitable for a normal web search engine.
11. Budget means the total budget for one top plus one bottom unless the user clearly says otherwise.
12. If no budget is supplied, use 5000 INR as the total budget.
13. Detect the user's response language, but keep product names and search queries in English.

Allowed values:
- gender: male, female, unisex, or null
- occasion: casual, office, party, wedding, beach, date, gym, formal, festive, ethnic, travel, other
- formality: casual, smart_casual, formal, athletic, ethnic
- category: top, bottom

Return exactly this structure:
{
  "language": "English",
  "gender": "male|female|unisex|null",
  "occasion": "...",
  "formality": "...",
  "style_keywords": ["..."],
  "color_preferences": ["..."],
  "size_or_fit": "...",
  "max_budget_inr": 5000,
  "top_query": "...",
  "bottom_query": "...",
  "search_query": "..."
}
"""


def _clean_json(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^```json\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^```\s*", "", value)
    value = re.sub(r"```$", "", value)
    return value.strip()


def _safe_int(value: Any, fallback: int = 5000) -> int:
    try:
        number = int(float(value))
        return max(500, min(number, 100000))
    except (TypeError, ValueError):
        return fallback


async def extract_global_intent(
    message: str,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    llm = ChatOpenAI(
        model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
        max_tokens=900,
    )

    profile_text = json.dumps(profile or {}, ensure_ascii=False)
    response = await llm.ainvoke([
        SystemMessage(content=GLOBAL_SEARCH_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"USER MESSAGE:\n{message}\n\n"
                f"PROFILE JSON:\n{profile_text}\n\n"
                "Create the search plan now."
            )
        ),
    ])

    try:
        parsed = json.loads(_clean_json(response.content))
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    profile_gender = (profile or {}).get("gender")
    explicit_gender = parsed.get("gender")
    if explicit_gender not in {"male", "female", "unisex"}:
        explicit_gender = profile_gender if profile_gender in {"male", "female", "unisex"} else "unisex"

    max_budget = _safe_int(parsed.get("max_budget_inr"), 5000)

    return {
        "language": parsed.get("language") or "English",
        "gender": explicit_gender,
        "occasion": parsed.get("occasion") or "casual",
        "formality": parsed.get("formality") or "casual",
        "style_keywords": parsed.get("style_keywords") or [],
        "color_preferences": parsed.get("color_preferences") or [],
        "size_or_fit": parsed.get("size_or_fit"),
        "max_budget_inr": max_budget,
        "top_query": parsed.get("top_query") or f"{explicit_gender} casual clothing top",
        "bottom_query": parsed.get("bottom_query") or f"{explicit_gender} casual clothing bottom",
        "search_query": parsed.get("search_query") or message,
    }
