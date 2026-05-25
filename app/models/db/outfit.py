import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Numeric, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


# ── Liked Products ────────────────────────────
class LikedProduct(Base):
    __tablename__ = "liked_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Product details
    product_title: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    product_type: Mapped[str] = mapped_column(String(20), nullable=True)  # top|bottom|accessory
    color: Mapped[str] = mapped_column(String(20), nullable=True)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=True)

    # Source session/message
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    outfit_name: Mapped[str] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="liked_products")


# ── Orders ────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Order items (JSONB array of products)
    items: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending | confirmed | delivered | cancelled

    # Affiliate tracking
    affiliate_tag: Mapped[str] = mapped_column(String(50), nullable=True)

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    outfit_name: Mapped[str] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="orders")


# ── Feedback ──────────────────────────────────
class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)

    rating: Mapped[int] = mapped_column(Integer, nullable=True)       # 1-5
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=True)  # outfit|app|general
    comment: Mapped[str] = mapped_column(Text, nullable=True)

    # Which outfit was rated
    outfit_data: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="feedbacks")
