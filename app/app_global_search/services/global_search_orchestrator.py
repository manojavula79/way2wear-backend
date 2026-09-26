import json
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from app.config import settings
from app.app_global_search.services.free_web_product_search import FreeWebProductSearch
from app.app_global_search.services.global_search_intent import extract_global_intent


STYLE_SYSTEM_PROMPT = r"""
You are Way2Wear, a premium but practical fashion stylist.

You receive real web-search product records. You must only describe products that are present
in the supplied records. Never invent product details, prices, brands, images, URLs, or stock.
Create outfit names and concise styling notes only. Pair exactly one TOP with one BOTTOM.
Do not add accessories or shoe products. A shoe_note is only a text suggestion.
Respond in the requested language, while leaving product names as supplied.
Return valid JSON only:
{
  "message": "...",
  "tip": "...",
  "outfits": [
    {"id":"1", "name":"...", "note":"...", "shoe_note":"..."}
  ]
}
"""


class GlobalSearchOrchestrator:
    def __init__(self):
        self.searcher = FreeWebProductSearch()

    async def run(self, message: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        intent = await extract_global_intent(message, profile)
        total_budget = intent["max_budget_inr"]
        top_limit = int(total_budget * 0.55)
        bottom_limit = total_budget - top_limit

        top_results, bottom_results = await self._search_products(intent)
        pairs = self._pair_products(top_results, bottom_results, total_budget)
        styled = await self._style_pairs(message, intent, pairs)

        by_id = {str(item.get("id")): item for item in styled.get("outfits", [])}
        final_outfits = []
        for index, pair in enumerate(pairs, start=1):
            outfit_id = str(index)
            meta = by_id.get(outfit_id, {})
            top = pair["top"]
            bottom = pair["bottom"]
            total_price = self._total_price(top, bottom)
            final_outfits.append({
                "id": outfit_id,
                "name": meta.get("name") or f"Global Look {outfit_id}",
                "note": meta.get("note") or "A coordinated top and bottom combination.",
                "shoe_note": meta.get("shoe_note") or "Pair with clean sneakers or loafers.",
                "total_price": total_price,
                "top": self._frontend_product(top),
                "bottom": self._frontend_product(bottom),
            })

        warnings = []
        if not top_results or not bottom_results:
            warnings.append("Some retailer pages were unavailable or blocked. Results may be incomplete.")
        if not final_outfits:
            warnings.append("No compatible public product pages were found within the requested budget.")

        return {
            "message": styled.get(
                "message",
                "Here are some real web-search options."
            ),
            "tip": styled.get(
                "tip",
                "Check size, shipping, return policy, and final price on the retailer page."
            ),
            "outfits": final_outfits,
            "source": "global_web_search",
            "query_params": intent,
            "warnings": warnings,
        }

    async def _search_products(self, intent: Dict[str, Any]):
        top_query = intent["top_query"]
        bottom_query = intent["bottom_query"]
        return await self._search_parallel(top_query, bottom_query)

    async def _search_parallel(self, top_query: str, bottom_query: str):
        import asyncio
        return await asyncio.gather(
            self.searcher.search(top_query, "top", max_results=8),
            self.searcher.search(bottom_query, "bottom", max_results=8),
        )

    @staticmethod
    def _price(product: Dict[str, Any]) -> Optional[float]:
        value = product.get("price")
        return float(value) if isinstance(value, (int, float)) else None

    def _pair_products(self, tops: List[Dict[str, Any]], bottoms: List[Dict[str, Any]], budget: int):
        pairs = []
        used_top = set()
        used_bottom = set()

        for top in tops:
            for bottom in bottoms:
                top_price = self._price(top)
                bottom_price = self._price(bottom)
                if top_price is not None and bottom_price is not None and top_price + bottom_price > budget:
                    continue
                if top["id"] in used_top or bottom["id"] in used_bottom:
                    continue
                pairs.append({"top": top, "bottom": bottom})
                used_top.add(top["id"])
                used_bottom.add(bottom["id"])
                break
            if len(pairs) == 3:
                break
        return pairs

    @staticmethod
    def _total_price(top: Dict[str, Any], bottom: Dict[str, Any]):
        top_price = top.get("price")
        bottom_price = bottom.get("price")
        if isinstance(top_price, (int, float)) and isinstance(bottom_price, (int, float)):
            return round(float(top_price) + float(bottom_price), 2)
        return None

    async def _style_pairs(self, message: str, intent: Dict[str, Any], pairs: List[Dict[str, Any]]):
        if not pairs:
            return {"message": "I couldn't find compatible products right now.", "tip": None, "outfits": []}

        llm = ChatOpenAI(
            model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.5,
            api_key=settings.OPENAI_API_KEY,
            max_tokens=1200,
        )
        context = []
        for index, pair in enumerate(pairs, start=1):
            context.append({
                "id": str(index),
                "top": {"title": pair["top"].get("title"), "color": pair["top"].get("description")},
                "bottom": {"title": pair["bottom"].get("title"), "color": pair["bottom"].get("description")},
            })

        response = await llm.ainvoke([
            SystemMessage(content=STYLE_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps({
                "language": intent.get("language", "English"),
                "user_message": message,
                "pairings": context,
            }, ensure_ascii=False)),
        ])

        try:
            text = response.content.strip()
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception:
            return {
                "message": "Here are some combinations selected from public product pages.",
                "tip": "Check size, shipping, return policy, and final price on the retailer page.",
                "outfits": [],
            }

    @staticmethod
    def _frontend_product(product: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": product.get("title", ""),
            "brand": product.get("brand", "Unknown"),
            "price": product.get("price"),
            "currency": product.get("currency", "INR"),
            "color": product.get("color", "#888888"),
            "image": product.get("image"),
            "url": product.get("url", ""),
        }

