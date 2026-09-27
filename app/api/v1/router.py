from fastapi import APIRouter
from fastapi import APIRouter
from app.api.v1.routes import (
    auth,
    chat,
    chat_gpt_ans,
    chat_claude_ans,
    sessions,
    users,
    feedback,
    saved_products,
    outfits,
    outfits_v2,
    outfits_v3,
    outfits_v4, 
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(chat_gpt_ans.router)
# api_router.include_router(chat.router)
# api_router.include_router(chat_claude_ans.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)
api_router.include_router(feedback.router)
api_router.include_router(saved_products.router)
# api_router.include_router(outfits.router)
api_router.include_router(outfits_v2.router)
api_router.include_router(outfits_v3.router)
api_router.include_router(outfits_v4.router) 