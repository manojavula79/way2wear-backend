from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.models.schemas.schemas import (
    ChatRequest, 
    ChatResponse,
    QueryOutfitsRequest,  # NEW
    QueryOutfitsResponse,  # NEW
)
from app.repositories.session_repo import SessionRepository
from app.services.ai_orchestrator_claude import run_outfit_pipeline
from app.services.orchestrator_v8 import run_steps_1_to_3  # EXISTING IMPORT
from app.redis_client import RedisCache
from pydantic import BaseModel
from app.config import settings
import json
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ═══════════════════════════════════════════════════════════════
# EXISTING ENDPOINT: Chat with AI (unchanged, but enhanced)
# ═══════════════════════════════════════════════════════════════


@router.post("", response_model=ChatResponse)
async def send_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get AI outfit recommendations."""
    
    repo = SessionRepository(db)

    # Get or create session
    session = None
    if payload.session_id:
        try:
            sid = uuid.UUID(payload.session_id)
            session = await repo.get_session_with_messages(sid, current_user.id)
        except ValueError:
            pass
    if not session:
        session = await repo.create_session(user_id=current_user.id, title=payload.message[:50])

    # Rate limit
    rate_key = RedisCache.rate_limit_key(str(current_user.id))
    count = await RedisCache.increment(rate_key, ttl=settings.RATE_LIMIT_WINDOW)
    if count > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded.",
        )

    # ═══ NEW: Check if asking about someone else ═══
    from app.services.orchestrator_v8 import (
        detect_person_context,
        check_profile_form_needed,
        node_understand_intent,
        node_build_query,
    )
    
    person_context = detect_person_context(payload.message)
    
    # If asking about someone else, check intent first
    if person_context["is_for_someone_else"]:
        # Need to parse intent to see if gender was mentioned
        intent_state = {
            "user_message": payload.message,
            "intent": {},
            "is_for_someone_else": True,
            "needs_profile_form": False,
            "query_params": {},
            "curated_outfits": [],
        }
        intent_state = node_understand_intent(intent_state)
        intent = intent_state.get("intent", {})
        
        # Check if form is needed
        needs_form = check_profile_form_needed(intent, True)
        
        if needs_form:
            # Save user message first
            await repo.add_message(session_id=session.id, role="user", content=payload.message)
            
            # Return form response (don't process outfit yet)
            form_response = {
                "needs_form": True,
                "message": f"To give you the best recommendations for your {person_context['person_type']}, what's their gender and skin tone preference?",
                "form_fields": {
                    "gender": {
                        "type": "buttons",
                        "options": ["Male", "Female", "Unisex"],
                        "required": True
                    },
                    "skin_tone": {
                        "type": "buttons",
                        "options": ["Fair", "Medium", "Dark"],
                        "required": False
                    },
                    "size": {
                        "type": "dropdown",
                        "options": ["XS", "S", "M", "L", "XL", "XXL"],
                        "required": False
                    }
                }
            }
            
            # Save form request as assistant message
            await repo.add_message(
                session_id=session.id,
                role="assistant",
                content=json.dumps(form_response),
            )
            
            return ChatResponse(
                session_id=str(session.id),
                message_id=str(uuid.uuid4()),
                response=json.dumps(form_response),
                outfit_data=form_response,
            )
    
    # ═══ END OF NEW CODE ═══
    
    # Save user message
    await repo.add_message(session_id=session.id, role="user", content=payload.message)

    # History
    recent = await repo.get_recent_messages(session.id, limit=8)
    history = [{"role": m.role, "content": m.content[:500]} for m in recent[:-1]]

    # Build profile
    user_profile = payload.profile or {}
    user_profile.setdefault("gender", current_user.gender)
    user_profile.setdefault("style_preference", current_user.style_preference)
    user_profile.setdefault("budget_range", current_user.budget_range)

    # Run pipeline (rest stays the same)
    try:
        curated_state = await run_steps_1_to_3(
            user_message=payload.message,
            user_profile=user_profile
        )
        
        if len(curated_state["curated_outfits"]) >= 3:
            # Return curated outfits
            outfits = curated_state["curated_outfits"][:3]
            formatted_outfits = [
                {
                    "id": str(o["id"]),
                    "name": o["outfit_text"][:50],
                    "top": {"title": "See details", "price": o["budget_min"]},
                    "bottom": {"title": "See details", "price": o["budget_max"] - o["budget_min"]},
                    "shoe_note": f"Outfit: {o['outfit_text']}",
                    "note": f"Style: {', '.join(o.get('style_tags', []))}",
                    "source": "curated",
                }
                for o in outfits
            ]
            
            ai_response = {
                "message": f"Perfect! I found {len(formatted_outfits)} curated outfits.",
                "outfits": formatted_outfits,
                "source": "curated_database",
            }
        else:
            ai_response = await run_outfit_pipeline(
                user_input=payload.message,
                conversation_history=history,
                user_profile=user_profile,
            )
            ai_response["source"] = "ai_fallback"
    
    except Exception as e:
        logger.warning(f"Curated pipeline error: {e}. Using AI fallback.")
        ai_response = await run_outfit_pipeline(
            user_input=payload.message,
            conversation_history=history,
            user_profile=user_profile,
        )
        ai_response["source"] = "ai_fallback"

    response_json = json.dumps(ai_response)

    ai_message = await repo.add_message(
        session_id=session.id, role="assistant",
        content=response_json, outfit_data=ai_response,
    )

    if session.message_count <= 2:
        await repo.update_session_title(
            session.id,
            payload.message[:60] + ("…" if len(payload.message) > 60 else ""),
        )

    cache_key = RedisCache.session_key(str(session.id))
    await RedisCache.set(cache_key, {"session_id": str(session.id)}, ttl=3600)

    return ChatResponse(
        session_id=str(session.id),
        message_id=str(ai_message.id),
        response=response_json,
        outfit_data=ai_response,
    )


# ═══════════════════════════════════════════════════════════════
# NEW ENDPOINT: Query curated outfits only (steps 1-3)
# ═══════════════════════════════════════════════════════════════

@router.post("/query-curated", response_model=QueryOutfitsResponse)
async def query_curated_outfits(
    request: QueryOutfitsRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Query 10k curated outfits database (steps 1-3 only).
    
    This endpoint does NOT call the AI pipeline further.
    Use this to:
    - Debug the curated database queries
    - Get raw outfit data without AI formatting
    - Test the hybrid pipeline in isolation
    
    Returns:
    - intent: What the AI understood from the message
    - query_params: The structured query (occasion, gender, skin_tone, budget)
    - curated_outfits: List of matching outfits from database
    """
    try:
        # Use user profile from account if not overridden
        user_profile = request.profile or {}
        user_profile.setdefault("gender", current_user.gender)
        user_profile.setdefault("skin_tone", current_user.skin_tone)

        # Run steps 1-3
        state = await run_steps_1_to_3(
            user_message=request.message,
            user_profile=user_profile
        )

        logger.info(
            f"Curated query for user {current_user.id}: "
            f"occasion={state['query_params'].get('occasion')}, "
            f"found {len(state['curated_outfits'])} outfits"
        )

        return QueryOutfitsResponse(
            success=len(state["curated_outfits"]) > 0,
            intent=state["intent"],
            query_params=state["query_params"],
            curated_outfits=state["curated_outfits"],
            count=len(state["curated_outfits"]),
        )

    except Exception as e:
        logger.error(f"Error in query_curated_outfits for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query curated outfits: {str(e)}"
        )
