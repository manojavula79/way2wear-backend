from pathlib import Path
import json
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================
# outfits.json location
# ============================================================

OUTFITS_JSON_PATH = (
    Path(__file__).resolve().parents[2] / "outfits.json"
)


# ============================================================
# LOAD outfits.json
# ============================================================

def load_outfits_reference() -> list:
    """
    Load outfits.json as styling knowledge.

    IMPORTANT:
    This file is NOT treated as the product database.

    It is only reference knowledge for the AI.
    """

    if not OUTFITS_JSON_PATH.exists():
        logger.warning(
            "outfits.json not found at: %s",
            OUTFITS_JSON_PATH
        )
        return []

    try:
        with open(
            OUTFITS_JSON_PATH,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

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
            "Unsupported outfits.json structure"
        )

        return []

    except Exception as exc:

        logger.exception(
            "Failed to load outfits.json: %s",
            exc
        )

        return []


# ============================================================
# SEARCH RELEVANT REFERENCES
# ============================================================

def get_relevant_outfit_references(
    *,
    occasion: str,
    gender: str,
    style: str | None = None,
    style_keywords: list | None = None,
    limit: int = 15,
) -> list:

    outfits = load_outfits_reference()

    if not outfits:
        return []

    occasion = str(occasion or "").lower()
    gender = str(gender or "").lower()
    style = str(style or "").lower()

    style_keywords = [
        str(x).lower()
        for x in (style_keywords or [])
    ]

    scored = []

    for outfit in outfits:

        try:
            text = json.dumps(
                outfit,
                ensure_ascii=False
            ).lower()
        except Exception:
            continue

        score = 0

        # Occasion is most important.
        if occasion and occasion in text:
            score += 10

        # Gender.
        if gender and gender in text:
            score += 5

        # Style preference.
        if style and style in text:
            score += 5

        # Style keywords.
        for keyword in style_keywords:
            if keyword in text:
                score += 2

        if score > 0:
            scored.append(
                {
                    "score": score,
                    "reference": outfit,
                }
            )

    scored.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return [
        item["reference"]
        for item in scored[:limit]
    ]


# ============================================================
# CLEAN REFERENCE FOR AI
# ============================================================

def build_reference_context(
    references: list,
    max_chars: int = 12000,
) -> str:

    if not references:
        return (
            "No matching outfit reference examples were found. "
            "Use general fashion coordination knowledge."
        )

    cleaned = []

    for index, item in enumerate(references, 1):

        try:

            text = json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":")
            )

            cleaned.append(
                f"REFERENCE {index}:\n{text}"
            )

        except Exception:
            continue

    result = "\n\n".join(cleaned)

    if len(result) > max_chars:
        result = result[:max_chars]

    return result