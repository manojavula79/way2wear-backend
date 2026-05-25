from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from sqlalchemy.orm import selectinload
from app.models.db.session import ChatSession, Message
from app.models.db.user import User
from app.config import settings
from typing import List, Optional
import uuid


class SessionRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Get all sessions for user ─────────────
    async def get_user_sessions(self, user_id: uuid.UUID) -> List[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.is_active == True)
            .order_by(ChatSession.updated_at.desc())
        )
        return list(result.scalars().all())

    # ── Get session with messages ─────────────
    async def get_session_with_messages(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ── Create session (enforces 10-session limit) ──
    async def create_session(self, user_id: uuid.UUID, title: str = "New Style Session") -> ChatSession:
        # Count current sessions
        count_result = await self.db.execute(
            select(func.count(ChatSession.id))
            .where(ChatSession.user_id == user_id, ChatSession.is_active == True)
        )
        count = count_result.scalar() or 0

        # ── AUTO-DELETE oldest if >= MAX_SESSIONS ──
        if count >= settings.MAX_SESSIONS_PER_USER:
            oldest = await self.db.execute(
                select(ChatSession.id)
                .where(ChatSession.user_id == user_id, ChatSession.is_active == True)
                .order_by(ChatSession.updated_at.asc())
                .limit(count - settings.MAX_SESSIONS_PER_USER + 1)
            )
            old_ids = [row[0] for row in oldest.fetchall()]
            if old_ids:
                # Delete messages first (cascade should handle, but being explicit)
                await self.db.execute(
                    delete(Message).where(Message.session_id.in_(old_ids))
                )
                await self.db.execute(
                    delete(ChatSession).where(ChatSession.id.in_(old_ids))
                )
                await self.db.flush()

        # Create new session
        session = ChatSession(user_id=user_id, title=title)
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    # ── Update session title ──────────────────
    async def update_session_title(self, session_id: uuid.UUID, title: str):
        await self.db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(title=title[:100])
        )

    # ── Delete session ────────────────────────
    async def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return False
        await self.db.delete(session)
        return True

    # ── Add message to session ────────────────
    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        outfit_data: Optional[dict] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
    ) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            outfit_data=outfit_data,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self.db.add(msg)

        # Update session message count and updated_at
        await self.db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(message_count=ChatSession.message_count + 1)
        )

        await self.db.flush()
        await self.db.refresh(msg)
        return msg

    # ── Get last N messages for context ───────
    async def get_recent_messages(
        self, session_id: uuid.UUID, limit: int = 10
    ) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()  # chronological order
        return messages
