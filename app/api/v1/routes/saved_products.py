"""
WAY2WEAR — SAVED & LIKED PRODUCTS
POST   /products/save      → save an outfit/product
DELETE /products/save/{id} → unsave
GET    /products/saved     → list saved
POST   /products/like      → like a product
DELETE /products/like/{id} → unlike
GET    /products/liked     → list liked
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.api.v1.middleware.auth import get_current_user
from app.models.db.user import User
from app.models.db.outfit import LikedProduct  # existing model

router = APIRouter(prefix="/products", tags=["Saved & Liked"])


class SaveItemRequest(BaseModel):
    kind: str = "save"          # "save" or "like"
    product_title: str
    brand: Optional[str] = None
    price: Optional[float] = None
    product_type: Optional[str] = None
    color: Optional[str] = None
    image: Optional[str] = None
    affiliate_url: Optional[str] = None
    outfit_name: Optional[str] = None


async def _add(payload: SaveItemRequest, kind: str, user: User, db: AsyncSession):
    row = LikedProduct(
        user_id=user.id,
        product_title=payload.product_title,
        brand=payload.brand,
        price=payload.price,
        product_type=kind,                 # reuse to mark save vs like
        color=payload.color,
        affiliate_url=payload.affiliate_url,
        outfit_name=payload.outfit_name,
    )
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "message": f"{kind} saved"}


async def _list(kind: str, user: User, db: AsyncSession):
    res = await db.execute(
        select(LikedProduct)
        .where(LikedProduct.user_id == user.id, LikedProduct.product_type == kind)
        .order_by(desc(LikedProduct.created_at))
    )
    rows = res.scalars().all()
    return [{
        "id": str(r.id),
        "product_title": r.product_title,
        "brand": r.brand,
        "price": r.price,
        "color": r.color,
        "affiliate_url": r.affiliate_url,
        "outfit_name": r.outfit_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


async def _remove(item_id: str, user: User, db: AsyncSession):
    try:
        rid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    await db.execute(
        delete(LikedProduct).where(LikedProduct.id == rid, LikedProduct.user_id == user.id)
    )
    return {"message": "removed"}


@router.post("/save")
async def save_item(payload: SaveItemRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _add(payload, "save", user, db)


@router.get("/saved")
async def list_saved(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _list("save", user, db)


@router.delete("/save/{item_id}")
async def unsave(item_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _remove(item_id, user, db)


@router.post("/like")
async def like_item(payload: SaveItemRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _add(payload, "like", user, db)


@router.get("/liked")
async def list_liked(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _list("like", user, db)


@router.delete("/like/{item_id}")
async def unlike(item_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _remove(item_id, user, db)
