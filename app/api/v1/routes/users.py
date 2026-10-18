from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.models.schemas.schemas import (
    UserProfileResponse, UserProfileUpdate,
    LikeProductRequest, LikedProductResponse,
    CreateOrderRequest, OrderResponse,
    FeedbackRequest,
)
from app.repositories.user_repo import UserRepository
from typing import List
import uuid
from fastapi import UploadFile, File, Request
from pathlib import Path

router = APIRouter(prefix="/users", tags=["Users"])
AVATAR_DIR = Path("static/avatars")
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


# ── Profile ───────────────────────────────────
@router.get("/me", response_model=UserProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return current_user
    updated = await repo.update_profile(current_user.id, updates)
    return updated


# ── Liked Products ────────────────────────────
@router.post("/me/likes", response_model=LikedProductResponse, status_code=201)
async def like_product(
    payload: LikeProductRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    data = payload.model_dump()
    if data.get("session_id"):
        try:
            data["session_id"] = uuid.UUID(data["session_id"])
        except ValueError:
            data["session_id"] = None
    product = await repo.add_liked_product(current_user.id, data)
    return product


@router.get("/me/likes", response_model=List[LikedProductResponse])
async def get_liked_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    return await repo.get_liked_products(current_user.id)


@router.delete("/me/likes/{product_id}", status_code=204)
async def unlike_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    deleted = await repo.remove_liked_product(current_user.id, pid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Liked product not found")


# ── Orders ────────────────────────────────────
@router.post("/me/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    data = payload.model_dump()
    if data.get("session_id"):
        try:
            data["session_id"] = uuid.UUID(data["session_id"])
        except ValueError:
            data["session_id"] = None
    order = await repo.create_order(current_user.id, data)
    return order


@router.get("/me/orders", response_model=List[OrderResponse])
async def get_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    return await repo.get_orders(current_user.id)


# ── Feedback ──────────────────────────────────
@router.post("/me/feedback", status_code=201)
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    data = payload.model_dump()
    for key in ["session_id", "message_id"]:
        if data.get(key):
            try:
                data[key] = uuid.UUID(data[key])
            except ValueError:
                data[key] = None
    await repo.create_feedback(current_user.id, data)
    return {"status": "feedback_received"}

@router.post("/me/avatar", response_model=UserProfileResponse)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = ALLOWED_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(status_code=415, detail="Use a JPEG, PNG or WebP image")

    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Image must be under 2MB")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{current_user.id}-{uuid.uuid4().hex[:8]}{ext}"
    (AVATAR_DIR / filename).write_bytes(data)

    url = f"{str(request.base_url).rstrip('/')}/static/avatars/{filename}"
    repo = UserRepository(db)
    return await repo.update_profile(current_user.id, {"avatar_url": url})