"""
FastAPI orchestrator implementing steps 1-3 of the outfit pipeline:
1. UNDERSTAND INTENT (AI parses user prompt)
2. BUILD QUERY (AI + rules construct the query)
3. QUERY 10K DATABASE (simple SQL/JSON lookup)

Integration into your existing ai_orchestrator.py
"""

from typing import TypedDict, List, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import asyncpg
from dotenv import load_dotenv
import os
import json

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

llm = ChatOpenAI(api_key=OPENAI_API_KEY, model=OPENAI_MODEL, temperature=0.3)


class QueryParams(TypedDict):
    """Structured query parameters extracted from user intent."""
    occasion: str
    gender: str
    skin_tone: str
    budget: int


class IntentState(TypedDict):
    """State for the first 3 nodes."""
    user_message: str
    intent: dict  # raw intent from AI
    query_params: QueryParams
    curated_outfits: List[dict]  # results from 10k database


# ═══════════════════════════════════════════════════════════════
# NODE 1: UNDERSTAND INTENT
# ═══════════════════════════════════════════════════════════════

def node_understand_intent(state: IntentState) -> IntentState:
    """
    Step 1: Parse user prompt and extract raw intent.
    
    Example input: "I need a nice outfit for an office party, I'm a woman with fair skin, budget is 2000"
    Output: {
        "occasion": "office party",
        "gender": "female",
        "skin_tone": "fair",
        "budget": "2000",
        "mood": "professional",
        "description": "nice outfit, professional"
    }
    """
    
    prompt_template = ChatPromptTemplate.from_template("""
    Extract the fashion intent from this user message.
    Return ONLY valid JSON, no markdown or extra text.
    
    Valid occasions: casual, office, party, beach, wedding, date, gym, formal, festive, ethnic
    Valid genders: male, female, unisex
    Valid skin tones: fair, medium, dark
    
    User message: "{user_message}"
    
    Return JSON with keys:
    - occasion: string (pick closest match from valid list, or null)
    - gender: string (male/female/unisex, or null)
    - skin_tone: string (fair/medium/dark, or null)
    - budget: integer (in rupees, or null)
    - mood: string (casual description like "professional", "sporty", "romantic")
    - description: string (any additional style preferences mentioned)
    
    Example output:
    {{"occasion": "office party", "gender": "female", "skin_tone": "fair", "budget": 2000, "mood": "professional", "description": "elegant, formal"}}
    """)
    
    try:
        response = llm.invoke(prompt_template.format_prompt(user_message=state["user_message"]))
        intent_text = response.content.strip()
        
        # Clean markdown if present
        if intent_text.startswith("```"):
            intent_text = intent_text.split("```")[1]
            if intent_text.startswith("json"):
                intent_text = intent_text[4:]
            intent_text = intent_text.strip()
        
        state["intent"] = json.loads(intent_text)
        print(f"✅ Intent parsed: {state['intent']}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error in node_understand_intent: {e}")
        state["intent"] = {
            "occasion": None,
            "gender": None,
            "skin_tone": None,
            "budget": None,
            "mood": "",
            "description": ""
        }
    except Exception as e:
        print(f"❌ Error in node_understand_intent: {e}")
        state["intent"] = {}
    
    return state


# ═══════════════════════════════════════════════════════════════
# NODE 2: BUILD QUERY
# ═══════════════════════════════════════════════════════════════

def node_build_query(state: IntentState) -> IntentState:
    """
    Step 2: Build structured query params with fallback rules.
    
    - If intent had missing values, use profile defaults (from user account)
    - Validate all required fields before querying
    - Set sensible defaults: budget=5000, occasion=casual
    """
    
    intent = state.get("intent", {})
    
    # TODO: Fetch user profile from database for defaults
    # For now, using hardcoded defaults
    
    query_params: QueryParams = {
        "occasion": intent.get("occasion") or "casual",
        "gender": intent.get("gender") or "unisex",
        "skin_tone": intent.get("skin_tone") or "medium",
        "budget": int(intent.get("budget") or 5000),
    }
    
    # Validate: ensure all params are non-null and in expected ranges
    valid_occasions = ["casual", "office", "party", "beach", "wedding", "date", "gym", "formal", "festive", "ethnic"]
    valid_genders = ["male", "female", "unisex"]
    valid_tones = ["fair", "medium", "dark"]
    
    if query_params["occasion"] not in valid_occasions:
        print(f"⚠️  Invalid occasion '{query_params['occasion']}', using 'casual'")
        query_params["occasion"] = "casual"
    
    if query_params["gender"] not in valid_genders:
        print(f"⚠️  Invalid gender '{query_params['gender']}', using 'unisex'")
        query_params["gender"] = "unisex"
    
    if query_params["skin_tone"] not in valid_tones:
        print(f"⚠️  Invalid skin tone '{query_params['skin_tone']}', using 'medium'")
        query_params["skin_tone"] = "medium"
    
    if query_params["budget"] < 0 or query_params["budget"] > 50000:
        print(f"⚠️  Budget {query_params['budget']} out of range, clamping to 5000")
        query_params["budget"] = 5000
    
    state["query_params"] = query_params
    print(f"✅ Query built: {query_params}")
    
    return state


# ═══════════════════════════════════════════════════════════════
# NODE 3: QUERY 10K DATABASE
# ═══════════════════════════════════════════════════════════════

async def node_query_curated_database(state: IntentState) -> IntentState:
    """
    Step 3: Query the 10k curated outfits database.
    
    SQL: SELECT * FROM curated_outfits 
         WHERE occasion = ? AND gender IN (?, 'unisex')
         AND skin_tone = ? AND budget_max >= ? 
         ORDER BY RANDOM() LIMIT 10
    """
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        state["curated_outfits"] = []
        return state
    
    try:
        params = state["query_params"]
        
        # Query: find outfits matching occasion/gender/skin_tone/budget
        query = """
        SELECT id, outfit_text, occasion, gender, skin_tone, budget_min, budget_max, style_tags
        FROM curated_outfits
        WHERE 
            occasion = $1
            AND gender IN ($2, 'unisex')
            AND skin_tone = $3
            AND budget_max >= $4
        ORDER BY RANDOM()
        LIMIT 10;
        """
        
        rows = await conn.fetch(
            query,
            params["occasion"],
            params["gender"],
            params["skin_tone"],
            params["budget"],
        )
        
        outfits = [dict(row) for row in rows]
        state["curated_outfits"] = outfits
        
        print(f"✅ DB query returned {len(outfits)} outfits")
        print(f"   Occasion: {params['occasion']}")
        print(f"   Gender: {params['gender']} (+ unisex)")
        print(f"   Skin tone: {params['skin_tone']}")
        print(f"   Budget: ≤ {params['budget']} rupees")
        
        for i, outfit in enumerate(outfits[:3], 1):
            print(f"   {i}. {outfit['outfit_text']}")
        
    except Exception as e:
        print(f"❌ Query error: {e}")
        state["curated_outfits"] = []
    finally:
        await conn.close()
    
    return state


# ═══════════════════════════════════════════════════════════════
# INTEGRATION: Run steps 1-3 in sequence
# ═══════════════════════════════════════════════════════════════

async def run_steps_1_to_3(user_message: str, user_profile: dict = None) -> IntentState:
    """
    Execute nodes 1-3 and return state with curated outfits.
    
    Args:
        user_message: The user's fashion request
        user_profile: Optional user profile for defaults (gender, skin_tone from account settings)
    
    Returns:
        IntentState with curated_outfits populated
    """
    
    state: IntentState = {
        "user_message": user_message,
        "intent": {},
        "query_params": {},
        "curated_outfits": [],
    }
    
    # Step 1: Understand intent
    print("\n🔍 Step 1: Parsing intent...")
    state = node_understand_intent(state)
    
    # Step 2: Build query
    print("\n🔨 Step 2: Building query...")
    state = node_build_query(state)
    
    # Override with user profile if available (gender + skin_tone from account)
    if user_profile:
        if user_profile.get("gender"):
            state["query_params"]["gender"] = user_profile["gender"]
        if user_profile.get("skin_tone"):
            state["query_params"]["skin_tone"] = user_profile["skin_tone"]
    
    # Step 3: Query database
    print("\n📊 Step 3: Querying curated database...")
    state = await node_query_curated_database(state)
    
    return state

def detect_person_context(message: str) -> dict:
    """
    Detect if asking about outfit for someone else.
    
    Returns: {
        "is_for_someone_else": bool,
        "person_type": "brother" | "sister" | "son" | "daughter" | "friend" | "self"
    }
    """
    message_lower = message.lower()
    
    # Keywords for different person types
    patterns = {
        "brother": ["my brother", "brother's", "bro"],
        "sister": ["my sister", "sister's"],
        "son": ["my son", "son he", "8 year old"],
        "daughter": ["my daughter", "daughter she", "sister's daughter"],
        "friend": ["my friend", "friend's", "my bff"],
        "wife": ["my wife", "wife's"],
        "husband": ["my husband", "husband's"],
        "mom": ["my mom", "my mother", "mom's"],
        "dad": ["my dad", "my father", "dad's"],
        "cousin": ["my cousin", "cousin's"],
    }
    
    person_type = "self"
    for ptype, keywords in patterns.items():
        if any(k in message_lower for k in keywords):
            person_type = ptype
            break
    
    is_for_someone_else = person_type != "self"
    
    return {
        "is_for_someone_else": is_for_someone_else,
        "person_type": person_type,
    }


def check_profile_form_needed(intent: dict, is_for_someone_else: bool) -> bool:
    """
    Check if we need to show profile form.
    
    Show form if:
    - Asking about someone else
    - AND no gender provided in message
    
    Don't show if:
    - Own outfit
    - OR gender already mentioned in message
    """
    
    # No form needed if asking about self
    if not is_for_someone_else:
        return False
    
    # No form needed if gender already in message
    if intent.get("gender"):
        return False
    
    # Need form if no gender provided
    return True

# ═══════════════════════════════════════════════════════════════
# FastAPI endpoint example
# ═══════════════════════════════════════════════════════════════

"""
ADD THIS TO YOUR app/routes/chat.py:

@router.post("/api/v1/outfits/query")
async def query_outfits(request: QueryOutfitsRequest):
    '''Query curated outfits based on user message.'''
    
    user_profile = None
    if request.user_id:
        # Fetch user profile for defaults (gender, skin_tone)
        user_profile = await get_user_profile(request.user_id)
    
    state = await run_steps_1_to_3(
        user_message=request.message,
        user_profile=user_profile
    )
    
    return {
        "intent": state["intent"],
        "query_params": state["query_params"],
        "curated_outfits": state["curated_outfits"],
        "count": len(state["curated_outfits"]),
    }
"""


# ═══════════════════════════════════════════════════════════════
# Test
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    # Test message
    test_message = "I need a nice outfit for an office party. I'm a woman with fair skin. My budget is 2000 rupees."
    
    print(f"Testing with message: {test_message}\n")
    
    # Simulate user profile
    user_profile = {
        "gender": "female",
        "skin_tone": "fair",
    }
    
    # Run
    result = asyncio.run(run_steps_1_to_3(test_message, user_profile))
    
    print("\n" + "="*60)
    print("FINAL STATE:")
    print("="*60)
    print(json.dumps(result, indent=2, default=str))
