from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.models.schemas.schemas import SessionSchema, SessionDetailSchema
from app.repositories.session_repo import SessionRepository
from typing import List
import uuid

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("", response_model=List[SessionSchema])
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all chat sessions for the current user (max 10)"""
    repo = SessionRepository(db)
    sessions = await repo.get_user_sessions(current_user.id)
    return sessions


@router.get("/{session_id}", response_model=SessionDetailSchema)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific session with all its messages"""
    repo = SessionRepository(db)
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await repo.get_session_with_messages(sid, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session"""
    repo = SessionRepository(db)
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    deleted = await repo.delete_session(sid, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("", response_model=SessionSchema, status_code=201)
async def create_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new empty session (auto-deletes oldest if >10 exist)"""
    repo = SessionRepository(db)
    session = await repo.create_session(current_user.id)
    return session
