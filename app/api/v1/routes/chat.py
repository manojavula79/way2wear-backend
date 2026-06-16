from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.models.schemas.schemas import ChatRequest, ChatResponse
from app.repositories.session_repo import SessionRepository
from app.services.ai_orchestrator import run_outfit_pipeline
from app.redis_client import RedisCache
from app.config import settings
import json
import uuid

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def send_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
            detail=f"Rate limit exceeded. Max {settings.RATE_LIMIT_REQUESTS} requests per minute.",
        )

    # Save user message
    await repo.add_message(session_id=session.id, role="user", content=payload.message)

    # History
    recent = await repo.get_recent_messages(session.id, limit=8)
    history = [{"role": m.role, "content": m.content[:500]} for m in recent[:-1]]

    # Build profile: prefer the rich profile the frontend sends, fall back to DB columns
    user_profile = payload.profile or {}
    user_profile.setdefault("gender", current_user.gender)
    user_profile.setdefault("style_preference", current_user.style_preference)
    user_profile.setdefault("budget_range", current_user.budget_range)

    # Run pipeline
    ai_response = await run_outfit_pipeline(
        user_input=payload.message,
        conversation_history=history,
        user_profile=user_profile,
    )
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
