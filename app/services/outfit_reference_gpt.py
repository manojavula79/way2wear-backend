"""
WAY2WEAR — Outfit Reference Knowledge

outfits.json is styling knowledge/reference only.

It is NOT the product catalog.
It is NOT the final source of product IDs.
It is NOT used to directly return products.

OpenAI uses relevant examples from this file to understand
how different occasions/styles are normally combined.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("way2wear.reference")


# ============================================================
# LOCATE outfits.json
# ============================================================

def _find_outfits_file() -> Path | None:

    current = Path(__file__).resolve()

    candidates = [
        current.parents[2] / "outfits.json",
        current.parents[3] / "outfits.json",
        Path.cwd() / "outfits.json",
    ]

    for path in candidates:
        if path.exists():
            return path

    logger.warning("outfits.json not found")

    return None


# ============================================================
# LOAD
# ============================================================

def load_outfit_reference() -> list[Any]:

    path = _find_outfits_file()

    if not path:
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):

            for key in [
                "outfits",
                "combinations",
                "styles",
                "data",
                "items",
            ]:
                value = data.get(key)

                if isinstance(value, list):
                    return value

        logger.warning(
            "Unsupported outfits.json root structure"
        )

        return []

    except Exception as e:

        logger.warning(
            "Could not load outfits.json: %s",
            e,
        )

        return []


# ============================================================
# TEXT REPRESENTATION
# ============================================================

def _stringify(value: Any) -> str:

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
        )
    except Exception:
        return str(value)


# ============================================================
# RELEVANCE
# ============================================================

def get_relevant_outfit_references(
    occasion: str,
    gender: str,
    style: str,
    style_keywords: list[str] | None = None,
    limit: int = 15,
) -> list[Any]:

    records = load_outfit_reference()

    if not records:
        return []

    occasion = str(occasion or "").lower()
    gender = str(gender or "").lower()
    style = str(style or "").lower()

    keywords = [
        str(x).lower()
        for x in (style_keywords or [])
    ]

    scored = []

    for record in records:

        text = _stringify(record).lower()

        score = 0

        if occasion and occasion in text:
            score += 10

        if gender and gender in text:
            score += 5

        if style and style in text:
            score += 5

        for keyword in keywords:

            if keyword and keyword in text:
                score += 2

        # Keep record even when exact keyword isn't present.
        scored.append(
            (
                score,
                text,
                record,
            )
        )

    scored.sort(
        key=lambda x: (
            -x[0],
            x[1],
        )
    )

    return [
        item[2]
        for item in scored[:limit]
    ]


# ============================================================
# AI CONTEXT
# ============================================================

def build_reference_context(
    references: list[Any],
    max_chars: int = 12000,
) -> str:

    if not references:
        return (
            "No matching outfit reference examples were found. "
            "Use general fashion knowledge together with the "
            "real product catalog."
        )

    parts = []

    for index, reference in enumerate(
        references,
        start=1,
    ):

        try:
            text = json.dumps(
                reference,
                ensure_ascii=False,
            )
        except Exception:
            text = str(reference)

        parts.append(
            f"REFERENCE {index}:\n{text}"
        )

    context = "\n\n".join(parts)

    if len(context) > max_chars:
        context = context[:max_chars]

    return context