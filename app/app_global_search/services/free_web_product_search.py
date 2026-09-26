import asyncio
import hashlib
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS


RETAILER_DOMAINS = {
    "myntra.com",
    "ajio.com",
    "flipkart.com",
    "amazon.in",
    "tatacliq.com",
    "meesho.com",
    "snitch.co.in",
    "bewakoof.com",
    "westside.com",
    "h-and-m.com",
    "zara.com",
}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host


def _is_relevant_url(url: str) -> bool:
    domain = _domain(url)
    return any(domain == item or domain.endswith("." + item) for item in RETAILER_DOMAINS)


def _clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()[:1000]


def _price_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*)", text, flags=re.IGNORECASE)
    if not matches:
        return None
    try:
        return float(matches[0].replace(",", ""))
    except ValueError:
        return None


def _meta(soup: BeautifulSoup, *names: str) -> Optional[str]:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            return _clean(node.get("content"))
    return None


class FreeWebProductSearch:
    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, category: str, max_results: int = 8) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._search_sync, query, category, max_results)

    def _search_sync(self, query: str, category: str, max_results: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_urls = set()

        search_query = f"{query} buy online India {category}"
        try:
            with DDGS() as ddgs:
                raw_results = ddgs.text(
                    search_query,
                    region="in-en",
                    safesearch="moderate",
                    max_results=max_results * 3,
                )
        except Exception:
            return []

        for raw in raw_results or []:
            url = raw.get("href") or raw.get("url")
            if not url or url in seen_urls or not _is_relevant_url(url):
                continue
            seen_urls.add(url)

            product = self._extract_product(url, raw, category)
            if product:
                results.append(product)
            if len(results) >= max_results:
                break

        return results

    def _extract_product(self, url: str, raw: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
        title = _clean(raw.get("title")) or "Product"
        description = _clean(raw.get("body"))
        image = None
        price = _price_from_text(f"{title} {description or ''}")
        brand = _domain(url).split(".")[0].title()

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                )
            }
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
                if response.status_code < 400 and "text/html" in response.headers.get("content-type", ""):
                    soup = BeautifulSoup(response.text, "lxml")
                    title = _meta(soup, "og:title", "twitter:title") or title
                    description = _meta(soup, "og:description", "description") or description
                    image = _meta(soup, "og:image", "twitter:image")
                    price = price or _price_from_text(description or "")
        except Exception:
            # Search results are still useful even if a retailer blocks metadata extraction.
            pass

        if not title or not url:
            return None

        product_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return {
            "id": product_id,
            "title": title,
            "brand": brand,
            "price": price,
            "currency": "INR",
            "image": image,
            "url": url,
            "category": category,
            "gender": "unisex",
            "source": "free_web_search",
            "description": description,
        }
