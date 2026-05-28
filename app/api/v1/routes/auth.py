"""
WAY2WEAR — FIREBASE PHONE AUTH
POST /auth/firebase-verify  → verify Firebase ID token, return JWT
POST /auth/refresh          → refresh access token
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import httpx, json

from app.database import get_db
from app.models.db.user import User
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger("way2wear")


# ── Schemas ───────────────────────────────────
class FirebaseVerifyRequest(BaseModel):
    id_token: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int


# ── Verify Firebase ID token (no service account needed) ──
async def verify_firebase_id_token(id_token: str) -> dict:
    """
    Verifies Firebase ID token using Google's public keys.
    No service account or credentials required.
    """
    from jose import jwt, JWTError
    import time

    project_id = settings.FIREBASE_PROJECT_ID

    # Get Firebase public keys
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://www.googleapis.com/robot/v1/metadata/x509/"
            "securetoken@system.gserviceaccount.com"
        )
        public_keys = resp.json()

    # Get key ID from token header
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")

    if kid not in public_keys:
        raise ValueError("Invalid Firebase token key ID")

    public_key = public_keys[kid]

    # Decode and verify
    decoded = jwt.decode(
        id_token,
        public_key,
        algorithms=["RS256"],
        audience=project_id,
        issuer=f"https://securetoken.google.com/{project_id}",
        options={"verify_exp": True},
    )

    # Must have phone_number claim
    if not decoded.get("phone_number"):
        raise ValueError("Token does not contain phone_number claim")

    return decoded


# ═════════════════════════════════════════════
# POST /auth/firebase-verify
# Frontend sends Firebase ID token → we return our JWT
# ═════════════════════════════════════════════
@router.post("/firebase-verify", response_model=TokenResponse)
async def firebase_verify(
    payload: FirebaseVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify Firebase token
    try:
        decoded = await verify_firebase_id_token(payload.id_token)
        phone   = decoded["phone_number"]
    except Exception as e:
        logger.error(f"Firebase token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    # Get or create user
    result = await db.execute(select(User).where(User.phone == phone))
    user   = result.scalar_one_or_none()

    if not user:
        # First time — auto register
        user = User(phone=phone, is_active=True)
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info(f"New user registered: {phone}")
    else:
        logger.info(f"User logged in: {phone}")

    # Issue JWT tokens
    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token  = create_access_token(token_data),
        refresh_token = create_refresh_token(token_data),
        token_type    = "bearer",
        expires_in    = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ═════════════════════════════════════════════
# POST /auth/refresh
# ═════════════════════════════════════════════
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        data    = decode_token(payload.refresh_token)
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
        access_token  = create_access_token(token_data),
        refresh_token = create_refresh_token(token_data),
        token_type    = "bearer",
        expires_in    = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
