"""
WAY2WEAR BACKEND — FastAPI Application
Production-ready AI Fashion Stylist API
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import logging

from app.config import settings
from app.database import create_tables
from app.redis_client import get_redis, close_redis
from app.api.v1.router import api_router

# ── Logging ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("way2wear")


# ── Lifespan (startup / shutdown) ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Way2Wear API starting up...")

    # ── Database (non-fatal) ──────────────────
    try:
        await create_tables()
        logger.info("✅ Database tables ready")
    except Exception as e:
        logger.warning(f"⚠️  Database unavailable: {e}")
        logger.warning("⚠️  Continuing without DB — AI chat still works")

    # ── Redis (non-fatal) ─────────────────────
    try:
        r = await get_redis()
        await r.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable: {e}")

    logger.info("✅ Way2Wear API ready")
    yield

    await close_redis()
    logger.info("👋 Way2Wear shutting down")

# ── FastAPI App ───────────────────────────────
app = FastAPI(
    title="Way2Wear API",
    description="AI-powered fashion stylist backend with LangGraph orchestration",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
# origins = settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS else ["*"]
origins = [
    "http://localhost:4200",
    "http://localhost:8100",
    "https://way2wear-ai.vercel.app",
    "https://www.way2wear-ai.vercel.app",
    "https://way2wear.in",
    "https://www.way2wear.in"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ── Request logging middleware ─────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration}ms)")
    return response


# ── Global exception handler ──────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routes ────────────────────────────────────
app.include_router(api_router)


# ── Health check ──────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Way2Wear API — From idea to outfit in seconds 🔥",
        "docs": "/docs",
        "version": settings.APP_VERSION,
    }


# ── Run (dev only) ────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
