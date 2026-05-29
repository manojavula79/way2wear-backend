"""
WAY2WEAR — FEEDBACK
POST /feedback       → submit feedback (rating + message)
GET  /feedback/all   → admin: list all feedback (for showcasing)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db.user import User
from app.models.db.outfit import Feedback
from app.api.v1.middleware.auth import get_current_user

router = APIRouter(prefix="/feedback", tags=["Feedback"])
logger = logging.getLogger("way2wear")


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=0, le=5, default=0)
    message: str = Field(min_length=1, max_length=5000)


class FeedbackResponse(BaseModel):
    message: str


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    feedback = Feedback(
        user_id       = current_user.id,
        rating        = payload.rating or None,
        feedback_type = "app",
        comment       = payload.message.strip(),
    )
    db.add(feedback)
    await db.flush()
    logger.info(f"Feedback received from {current_user.phone}: {payload.rating}★")
    return FeedbackResponse(message="Thank you for your feedback!")


@router.get("/all")
async def list_feedback(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    Public list of feedback for showcasing.
    Returns rating + comment + date (no personal info).
    """
    result = await db.execute(
        select(Feedback)
        .where(Feedback.comment.isnot(None))
        .order_by(desc(Feedback.created_at))
        .limit(min(limit, 200))
    )
    rows = result.scalars().all()
    return [
        {
            "rating":     f.rating,
            "comment":    f.comment,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in rows
    ]
