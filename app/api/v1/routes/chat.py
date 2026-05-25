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
    import uuid, json

    # ── Run AI pipeline (works without DB) ───
    user_profile = {
        "style_preference": current_user.style_preference,
        "budget_range":     current_user.budget_range,
        "gender":           current_user.gender,
    }
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in (payload.history or [])[-8:]
    ]

    ai_response = await run_outfit_pipeline(
        user_input=payload.message,
        conversation_history=history,
        user_profile=user_profile,
    )

    # ── Try saving to DB — skip silently if DB is down ──
    session_id = payload.session_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    try:
        repo = SessionRepository(db)

        # Get or create session
        if payload.session_id:
            try:
                sid = uuid.UUID(payload.session_id)
                session = await repo.get_session_with_messages(sid, current_user.id)
                if not session:
                    session = await repo.create_session(current_user.id, payload.message[:50])
            except Exception:
                session = await repo.create_session(current_user.id, payload.message[:50])
        else:
            session = await repo.create_session(current_user.id, payload.message[:50])

        session_id = str(session.id)

        # Save messages
        await repo.add_message(session.id, "user", payload.message)
        msg = await repo.add_message(
            session.id, "assistant",
            json.dumps(ai_response), ai_response
        )
        message_id = str(msg.id)

        # Update title
        if session.message_count <= 2:
            await repo.update_session_title(session.id, payload.message[:60])

    except Exception as e:
        logger.warning(f"DB save skipped (DB unavailable): {e}")

    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        response=json.dumps(ai_response),
        outfit_data=ai_response,
    )
    """
    Main chat endpoint — runs the 11-node LangGraph pipeline
    and saves messages to PostgreSQL
    """
    repo = SessionRepository(db)

    # ── Get or create session ────────────────
    session_id = payload.session_id
    session = None

    if session_id:
        try:
            sid = uuid.UUID(session_id)
            session = await repo.get_session_with_messages(sid, current_user.id)
        except ValueError:
            pass

    if not session:
        # Create new session — auto-enforces 10-session limit
        session = await repo.create_session(
            user_id=current_user.id,
            title=payload.message[:50],
        )

    # ── Rate limit check (Redis) ─────────────
    rate_key = RedisCache.rate_limit_key(str(current_user.id))
    count = await RedisCache.increment(rate_key, ttl=settings.RATE_LIMIT_WINDOW)
    if count > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {settings.RATE_LIMIT_REQUESTS} requests per minute.",
        )

    # ── Save user message ────────────────────
    await repo.add_message(
        session_id=session.id,
        role="user",
        content=payload.message,
    )

    # ── Build conversation history for AI ────
    recent_messages = await repo.get_recent_messages(session.id, limit=8)
    history = [
        {"role": m.role, "content": m.content[:500]}
        for m in recent_messages[:-1]  # exclude the message we just added
    ]

    # ── User profile context ─────────────────
    user_profile = {
        "style_preference": current_user.style_preference,
        "budget_range": current_user.budget_range,
        "gender": current_user.gender,
    }

    # ── Run LangGraph 11-node pipeline ───────
    ai_response = await run_outfit_pipeline(
        user_input=payload.message,
        conversation_history=history,
        user_profile=user_profile,
    )

    response_json = json.dumps(ai_response)

    # ── Save AI response to DB ───────────────
    ai_message = await repo.add_message(
        session_id=session.id,
        role="assistant",
        content=response_json,
        outfit_data=ai_response,
    )

    # ── Update session title on first message ─
    if session.message_count <= 2:
        await repo.update_session_title(
            session.id,
            payload.message[:60] + ("…" if len(payload.message) > 60 else ""),
        )

    # ── Cache session in Redis (1hr) ─────────
    cache_key = RedisCache.session_key(str(session.id))
    await RedisCache.set(cache_key, {"session_id": str(session.id)}, ttl=3600)

    return ChatResponse(
        session_id=str(session.id),
        message_id=str(ai_message.id),
        response=response_json,
        outfit_data=ai_response,
    )
