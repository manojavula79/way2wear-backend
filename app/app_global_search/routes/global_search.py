import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from app.app_global_search.services.global_search_models import (
    FormField,
    FormFieldOption,
    GlobalSearchRequest,
    GlobalSearchResponse,
)
from app.app_global_search.services.global_search_orchestrator import GlobalSearchOrchestrator
from uuid import uuid4

def detect_person_context(message: str) -> dict:
    text = (message or "").lower()
    patterns = {
        "brother": ["my brother", "brother's", "bro"],
        "sister": ["my sister", "sister's"],
        "son": ["my son", "son he"],
        "daughter": ["my daughter", "daughter she"],
        "friend": ["my friend", "friend's", "my bff"],
        "wife": ["my wife", "wife's"],
        "husband": ["my husband", "husband's"],
        "mom": ["my mom", "my mother", "mom's"],
        "dad": ["my dad", "my father", "dad's"],
        "cousin": ["my cousin", "cousin's"],
    }
    for person_type, keywords in patterns.items():
        if any(keyword in text for keyword in keywords):
            return {"is_for_someone_else": True, "person_type": person_type}
    return {"is_for_someone_else": False, "person_type": "self"}


def message_gender(message: str) -> Optional[str]:
    text = (message or "").lower()
    if any(x in text for x in ["female", "woman", "women", "girl", "she", "her"]):
        return "female"
    if any(x in text for x in ["male", "man", "men", "boy", "he", "his"]):
        return "male"
    if "unisex" in text or "gender neutral" in text:
        return "unisex"
    return None


def check_profile_form_needed(intent: dict, is_for_someone_else: bool) -> bool:
    if not is_for_someone_else:
        return False
    return not bool(intent.get("gender"))


router = APIRouter(prefix="/chat", tags=["Chat"])
search_orchestrator = GlobalSearchOrchestrator()


def _form_fields() -> List[FormField]:
    return [
        FormField(
            name="gender",
            label="Who are you shopping for? Gender",
            type="buttons",
            options=[
                FormFieldOption(label="Male", value="male"),
                FormFieldOption(label="Female", value="female"),
                FormFieldOption(label="Unisex", value="unisex"),
            ],
        ),
        FormField(
            name="skin_tone",
            label="Skin tone",
            type="buttons",
            options=[
                FormFieldOption(label="Fair", value="fair"),
                FormFieldOption(label="Medium", value="medium"),
                FormFieldOption(label="Dark", value="dark"),
            ],
        ),
        FormField(
            name="size",
            label="Size",
            type="dropdown",
            options=[FormFieldOption(label=x, value=x) for x in ["XS", "S", "M", "L", "XL", "XXL"]],
        ),
    ]


@router.post("", response_model=GlobalSearchResponse)
async def global_search(payload: GlobalSearchRequest):
    """
    Global web product search.

    Returns the same response structure expected by the
    existing Way2Wear frontend.
    """

    person = detect_person_context(payload.message)
    profile = dict(payload.profile or {})
    session_id=payload.session_id or str(uuid4())

    intent = {
        "gender": message_gender(payload.message)
    }

    submitted_gender = profile.get("gender")

    if submitted_gender in {"male", "female", "unisex"}:
        intent["gender"] = submitted_gender

    # Preserve existing someone-else form behavior
    if check_profile_form_needed(
        intent,
        person["is_for_someone_else"],
    ):
        form_data = {
            "message": (
                f"Please provide the profile details for your "
                f"{person['person_type']} before I search for products."
            ),
            "tip": None,
            "outfits": [],
            "source": "global_web_search",
            "needs_form": True,
            "person_type": person["person_type"],
            "form_fields": [
                field.model_dump()
                for field in _form_fields()
            ],
        }

        return GlobalSearchResponse(
            success=True,
            session_id=session_id,
            message_id=str(uuid4()),
            response=json.dumps(
                form_data,
                ensure_ascii=False,
            ),
            outfit_data=form_data,
            usage=None,
        )

    # Execute global web search
    result = await search_orchestrator.run(
        payload.message,
        profile,
    )

    # Keep only frontend-compatible outfit fields
    outfit_data = {
        "message": result.get(
            "message",
            "Here are some real web-search options.",
        ),
        "tip": result.get("tip"),
        "outfits": result.get("outfits", []),
        "source": result.get(
            "source",
            "global_web_search",
        ),
    }

    return GlobalSearchResponse(
        success=True,
        session_id=session_id,
        message_id=str(uuid4()),
        response=json.dumps(
            outfit_data,
            ensure_ascii=False,
        ),
        outfit_data=outfit_data,
        usage=None,
    )