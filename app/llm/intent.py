"""Extract user intent from text (typed or transcribed voice note)."""

import logging

from app.llm.client import chat_completion_json

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You are an intent extraction assistant for a kids event finder in NYC.
Given a parent's request about children's activities, extract structured information.

Return JSON with these fields:
- activity_type: string or null (e.g. "arts", "sports", "music", "nature", "STEM", "storytime", "food", "social", "general")
- age_group: string or null (e.g. "toddler", "preschool", "school-age", "teen", or specific like "4-6")
- date_hint: string or null (e.g. "this saturday", "weekend", "march 15", "today")
- location_hint: string or null (e.g. "brooklyn", "upper west side", "central park")
- budget_hint: string or null (e.g. "free", "cheap", "under 20")
- indoor_outdoor: string or null ("indoor", "outdoor", "either")
- keywords: list of strings (important words from the request)
- mood: string or null (e.g. "active", "calm", "educational", "fun", "social")

If a field is not mentioned, set it to null.
Extract as much as you can from the text. Be precise."""


async def extract_intent(text: str) -> dict:
    """Extract structured intent from user's event request."""
    try:
        result = await chat_completion_json(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=f"Parent's request: {text}",
        )
        logger.info(f"Extracted intent: {result}")
        return result
    except Exception:
        logger.exception("Failed to extract intent")
        return {"keywords": [text], "activity_type": None}
