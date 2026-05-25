"""
WAY2WEAR — PHONE OTP AUTHENTICATION
Two endpoints:
  POST /auth/send-otp    → generate & send OTP via SMS
  POST /auth/verify-otp  → verify OTP, create/login user, return JWT
  POST /auth/refresh     → refresh access token
"""
import random
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.redis_client import RedisCache
from app.models.db.user import User
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.config import settings
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])

# OTP expires in 5 minutes
OTP_TTL_SECONDS = 300
OTP_KEY_PREFIX  = "otp:"
OTP_ATTEMPTS    = "otp_attempts:"


# ── Schemas ───────────────────────────────────
class SendOtpRequest(BaseModel):
    phone: str


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Helper: normalize phone ───────────────────
def normalize_phone(phone: str) -> str:
    """Strip everything except digits and leading +"""
    cleaned = re.sub(r"[^\d+]", "", phone)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def validate_phone(phone: str) -> bool:
    """Basic E.164 format check: +[country][number] 10-15 digits total"""
    pattern = r"^\+\d{10,15}$"
    return bool(re.match(pattern, phone))


# ── Helper: send SMS via Twilio ───────────────
async def send_sms(phone: str, otp: str) -> bool:
    """
    Send OTP via Twilio. Falls back to dev mode if not configured.
    Install: pip install twilio
    """
    twilio_sid   = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    twilio_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    twilio_from  = getattr(settings, "TWILIO_FROM_NUMBER", None)

    if not all([twilio_sid, twilio_token, twilio_from]):
        # DEV MODE — just log the OTP (no SMS sent)
        print(f"\n{'='*40}")
        print(f"  📱 DEV MODE OTP for {phone}: {otp}")
        print(f"{'='*40}\n")
        return True

    try:
        from twilio.rest import Client
        client = Client(twilio_sid, twilio_token)
        client.messages.create(
            body=f"Your Way2Wear OTP is {otp}. Valid for 5 minutes. Do not share this code.",
            from_=twilio_from,
            to=phone,
        )
        return True
    except Exception as e:
        print(f"Twilio error: {e}")
        return False


# ═════════════════════════════════════════════
# ENDPOINT 1 — SEND OTP
# ═════════════════════════════════════════════
@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest):
    phone = normalize_phone(payload.phone)

    if not validate_phone(phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Use format: +91XXXXXXXXXX",
        )

    # Rate limit: max 3 OTPs per phone per 10 minutes
    rate_key = f"otp_rate:{phone}"
    attempts = await RedisCache.increment(rate_key, ttl=600)
    if attempts > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please wait 10 minutes.",
        )

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Store OTP in Redis with 5-minute TTL
    otp_key = f"{OTP_KEY_PREFIX}{phone}"
    await RedisCache.set(otp_key, {"otp": otp, "attempts": 0}, ttl=OTP_TTL_SECONDS)

    # Send SMS
    sent = await send_sms(phone, otp)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send OTP. Please try again.",
        )

    response = {"message": f"OTP sent to {phone}"}

    # Return OTP in dev mode (no Twilio configured)
    twilio_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    if not twilio_sid:
        response["dev_otp"] = otp  # visible in frontend dev mode

    return response


# ═════════════════════════════════════════════
# ENDPOINT 2 — VERIFY OTP → LOGIN / REGISTER
# ═════════════════════════════════════════════
@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(payload.phone)
    entered_otp = payload.otp.strip()

    if not validate_phone(phone):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    if not re.match(r"^\d{6}$", entered_otp):
        raise HTTPException(status_code=400, detail="OTP must be 6 digits")

    # Fetch stored OTP from Redis
    otp_key = f"{OTP_KEY_PREFIX}{phone}"
    stored  = await RedisCache.get(otp_key)

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found. Please request a new one.",
        )

    # Max 5 wrong attempts → invalidate
    attempts = stored.get("attempts", 0)
    if attempts >= 5:
        await RedisCache.delete(otp_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many wrong attempts. Please request a new OTP.",
        )

    # Verify OTP
    if stored["otp"] != entered_otp:
        # Increment attempts
        stored["attempts"] = attempts + 1
        await RedisCache.set(otp_key, stored, ttl=OTP_TTL_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect OTP. {4 - attempts} attempts remaining.",
        )

    # ✅ OTP is correct — delete it
    await RedisCache.delete(otp_key)

    # ── Get or create user ────────────────────
    result = await db.execute(select(User).where(User.phone == phone))
    user   = result.scalar_one_or_none()

    if not user:
        # First time login → auto register
        user = User(phone=phone, is_active=True)
        db.add(user)
        await db.flush()
        await db.refresh(user)

    # ── Issue JWT tokens ──────────────────────
    token_data = {"sub": str(user.id)}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ═════════════════════════════════════════════
# ENDPOINT 3 — REFRESH TOKEN
# ═════════════════════════════════════════════
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id = data.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    import uuid
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
