import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Phone is the only required field ──────
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )  # E.164 format e.g. +919876543210

    # Optional profile fields (filled later)
    full_name: Mapped[str]  = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Styling profile
    style_preference: Mapped[str] = mapped_column(String(100), default="Minimalist / Modern")
    budget_range:     Mapped[str] = mapped_column(String(50),  default="$200 - $500")
    gender:           Mapped[str] = mapped_column(String(20),  nullable=True)
    plan:             Mapped[str] = mapped_column(String(20),  default="Free")

    # Stats
    total_likes:  Mapped[int] = mapped_column(Integer, default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    sessions:        Mapped[list["ChatSession"]]   = relationship("ChatSession",   back_populates="user", cascade="all, delete-orphan")
    liked_products:  Mapped[list["LikedProduct"]]  = relationship("LikedProduct",  back_populates="user", cascade="all, delete-orphan")
    orders:          Mapped[list["Order"]]          = relationship("Order",          back_populates="user", cascade="all, delete-orphan")
    feedbacks:       Mapped[list["Feedback"]]       = relationship("Feedback",       back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone}>"
