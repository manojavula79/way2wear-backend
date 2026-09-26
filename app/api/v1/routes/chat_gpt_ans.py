from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from app.api.v1.middleware.auth import (
    get_current_user,
)

from app.models.db.user import User

from app.models.schemas.schemas import (
    ChatRequest,
    ChatResponse,
    QueryOutfitsRequest,
    QueryOutfitsResponse,
)

from app.repositories.session_repo import (
    SessionRepository,
)

from app.services.orchestrator_v8_gpt_backup import (
    run_outfit_pipeline,
    run_steps_1_to_3,
    detect_person_context,
    check_profile_form_needed,
    node_understand_intent,
)

from app.redis_client import RedisCache

from app.config import settings

import json
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

# ============================================================
# CHAT
# ============================================================

@router.post(
    "",
    response_model=ChatResponse,
)
async def send_message(
    payload: ChatRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: AsyncSession = Depends(
        get_db
    ),
):
    repo = SessionRepository(db)
    session = None
    # --------------------------------------------------------
    # GET EXISTING SESSION
    # --------------------------------------------------------
    if payload.session_id:
        try:
            sid = uuid.UUID(
                payload.session_id
            )
            session = (
                await repo.get_session_with_messages(
                    sid,
                    current_user.id,
                )
            )
        except ValueError:
            session = None
    # --------------------------------------------------------
    # CREATE SESSION
    # --------------------------------------------------------
    if not session:
        session = await repo.create_session(
            user_id=current_user.id,
            title=payload.message[:50],
        )
    # --------------------------------------------------------
    # RATE LIMIT
    # --------------------------------------------------------
    rate_key = (
        RedisCache.rate_limit_key(
            str(current_user.id)
        )
    )

    count = await RedisCache.increment(
        rate_key,
        ttl=settings.RATE_LIMIT_WINDOW,
    )

    if count > settings.RATE_LIMIT_REQUESTS:

        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),

            detail=(
                "Rate limit exceeded."
            ),
        )

    # --------------------------------------------------------
    # PERSON CONTEXT
    # --------------------------------------------------------

    person_context = (
        detect_person_context(
            payload.message
        )
    )

    # --------------------------------------------------------
    # PROFILE
    # --------------------------------------------------------

    user_profile = (
        payload.profile.copy()
        if payload.profile
        else {}
    )

    # Fill missing values from account
    # without overwriting values explicitly
    # sent by frontend.

    if not user_profile.get(
        "gender"
    ):
        user_profile["gender"] = (
            current_user.gender
        )

    if not user_profile.get(
        "stylePreference"
    ):

        user_profile[
            "stylePreference"
        ] = current_user.style_preference

    if not user_profile.get(
        "budgetRange"
    ):

        user_profile[
            "budgetRange"
        ] = current_user.budget_range

    # Add remaining account fields
    # only when available.

    if not user_profile.get(
        "skinTone"
    ):

        user_profile[
            "skinTone"
        ] = getattr(
            current_user,
            "skin_tone",
            None,
        )

    # --------------------------------------------------------
    # PERSON-OTHER FORM
    # --------------------------------------------------------

    if person_context[
        "is_for_someone_else"
    ]:

        intent_state = {

            "user_message":
                payload.message,

            "intent": {},

            "is_for_someone_else":
                True,

            "needs_profile_form":
                False,

            "query_params": {},

            "curated_outfits": [],

            "user_profile":
                user_profile,
        }

        try:

            intent_state = (
                await node_understand_intent(
                    intent_state
                )
            )

        except Exception as e:

            logger.warning(
                "Could not understand "
                "person context: %s",
                e,
            )

        intent = (
            intent_state.get(
                "intent",
                {},
            )
        )

        needs_form = (
            check_profile_form_needed(
                intent,
                True,
            )
        )

        if needs_form:

            await repo.add_message(
                session_id=session.id,
                role="user",
                content=payload.message,
            )

            form_response = {

                "needs_form": True,

                "message": (
                    "To give you the best "
                    f"recommendations for your "
                    f"{person_context['person_type']}, "
                    "please tell me their gender "
                    "and skin tone preference."
                ),

                "form_fields": {

                    "gender": {
                        "type": "buttons",

                        "options": [
                            "Male",
                            "Female",
                            "Unisex",
                        ],

                        "required": True,
                    },

                    "skin_tone": {
                        "type": "buttons",

                        "options": [
                            "Fair",
                            "Medium",
                            "Dark",
                        ],

                        "required": False,
                    },

                    "size": {
                        "type": "dropdown",

                        "options": [
                            "XS",
                            "S",
                            "M",
                            "L",
                            "XL",
                            "XXL",
                        ],

                        "required": False,
                    },
                },
            }

            await repo.add_message(
                session_id=session.id,
                role="assistant",
                content=json.dumps(
                    form_response
                ),
            )

            return ChatResponse(

                session_id=str(
                    session.id
                ),

                message_id=str(
                    uuid.uuid4()
                ),

                response=json.dumps(
                    form_response
                ),

                outfit_data=form_response,
            )

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    await repo.add_message(
        session_id=session.id,
        role="user",
        content=payload.message,
    )

    # --------------------------------------------------------
    # CONVERSATION HISTORY
    # --------------------------------------------------------

    recent = await repo.get_recent_messages(
        session.id,
        limit=8,
    )

    history = [
        {
            "role": message.role,
            "content": (
                message.content[:500]
                if message.content
                else ""
            ),
        }

        for message in recent[:-1]
    ]

    # --------------------------------------------------------
    # AI OUTFIT PIPELINE
    # --------------------------------------------------------

    try:

        ai_response = (
            await run_outfit_pipeline(

                user_input=payload.message,

                conversation_history=history,

                user_profile=user_profile,
            )
        )

        ai_response[
            "source"
        ] = "ai_product_matching"

    except Exception as e:

        logger.exception(
            "AI outfit pipeline failed"
        )

        ai_response = {

            "message": (
                "I couldn't generate "
                "your outfit right now."
            ),

            "tip": (
                "Please try again."
            ),

            "outfits": [],

            "source": "error",

            "error": str(e),
        }

    # --------------------------------------------------------
    # SAVE AI MESSAGE
    # --------------------------------------------------------

    response_json = json.dumps(
        ai_response,
        ensure_ascii=False,
    )

    ai_message = await repo.add_message(

        session_id=session.id,

        role="assistant",

        content=response_json,

        outfit_data=ai_response,
    )

    # --------------------------------------------------------
    # SESSION TITLE
    # --------------------------------------------------------

    if session.message_count <= 2:

        await repo.update_session_title(

            session.id,

            payload.message[:60]
            + (
                "…"
                if len(payload.message) > 60
                else ""
            ),
        )

    # --------------------------------------------------------
    # SESSION CACHE
    # --------------------------------------------------------

    cache_key = (
        RedisCache.session_key(
            str(session.id)
        )
    )

    await RedisCache.set(

        cache_key,

        {
            "session_id":
                str(session.id)
        },

        ttl=3600,
    )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return ChatResponse(

        session_id=str(
            session.id
        ),

        message_id=str(
            ai_message.id
        ),

        response=response_json,

        outfit_data=ai_response,
    )


# ============================================================
# LEGACY / QUERY CURATED
# ============================================================

@router.post(
    "/query-curated",
    response_model=QueryOutfitsResponse,
)
async def query_curated_outfits(

    request: QueryOutfitsRequest,

    current_user: User = Depends(
        get_current_user
    ),
):

    try:

        user_profile = (
            request.profile.copy()
            if request.profile
            else {}
        )

        if not user_profile.get(
            "gender"
        ):

            user_profile[
                "gender"
            ] = current_user.gender

        if not user_profile.get(
            "skinTone"
        ):

            user_profile[
                "skinTone"
            ] = getattr(
                current_user,
                "skin_tone",
                None,
            )

        state = (
            await run_steps_1_to_3(

                user_message=request.message,

                user_profile=user_profile,
            )
        )

        logger.info(

            "Catalog query for user %s: "
            "occasion=%s, found=%s",

            current_user.id,

            state[
                "query_params"
            ].get(
                "occasion"
            ),

            len(
                state[
                    "curated_outfits"
                ]
            ),
        )

        return QueryOutfitsResponse(

            success=(
                len(
                    state[
                        "curated_outfits"
                    ]
                ) > 0
            ),

            intent=state[
                "intent"
            ],

            query_params=state[
                "query_params"
            ],

            curated_outfits=state[
                "curated_outfits"
            ],

            count=len(
                state[
                    "curated_outfits"
                ]
            ),
        )

    except Exception as e:

        logger.exception(
            "Error in query_curated_outfits "
            "for user %s",
            current_user.id,
        )

        raise HTTPException(

            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),

            detail=(
                "Failed to query outfits: "
                f"{str(e)}"
            ),
        )