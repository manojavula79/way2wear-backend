from fastapi import APIRouter
from app.api.v1.routes import auth, chat, sessions, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)
