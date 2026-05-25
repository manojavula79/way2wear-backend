from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.db.user import User
from app.models.db.outfit import LikedProduct, Order, Feedback
from typing import Optional, List
import uuid


class UserRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: uuid.UUID, updates: dict) -> Optional[User]:
        await self.db.execute(update(User).where(User.id == user_id).values(**updates))
        return await self.get_by_id(user_id)

    async def add_liked_product(self, user_id: uuid.UUID, data: dict) -> LikedProduct:
        product = LikedProduct(user_id=user_id, **data)
        self.db.add(product)
        await self.db.execute(
            update(User).where(User.id == user_id).values(total_likes=User.total_likes + 1)
        )
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def remove_liked_product(self, user_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(LikedProduct).where(LikedProduct.id == product_id, LikedProduct.user_id == user_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return False
        await self.db.delete(product)
        await self.db.execute(
            update(User).where(User.id == user_id).values(total_likes=User.total_likes - 1)
        )
        return True

    async def get_liked_products(self, user_id: uuid.UUID) -> List[LikedProduct]:
        result = await self.db.execute(
            select(LikedProduct).where(LikedProduct.user_id == user_id).order_by(LikedProduct.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_order(self, user_id: uuid.UUID, data: dict) -> Order:
        order = Order(user_id=user_id, **data)
        self.db.add(order)
        await self.db.execute(
            update(User).where(User.id == user_id).values(total_orders=User.total_orders + 1)
        )
        await self.db.flush()
        await self.db.refresh(order)
        return order

    async def get_orders(self, user_id: uuid.UUID) -> List[Order]:
        result = await self.db.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_feedback(self, user_id: uuid.UUID, data: dict) -> Feedback:
        fb = Feedback(user_id=user_id, **data)
        self.db.add(fb)
        await self.db.flush()
        await self.db.refresh(fb)
        return fb
