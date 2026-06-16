from fastapi import APIRouter
from app.api.v1.routes import auth, chat, sessions, users, feedback, saved_products

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)
api_router.include_router(feedback.router)
api_router.include_router(saved_products.router)