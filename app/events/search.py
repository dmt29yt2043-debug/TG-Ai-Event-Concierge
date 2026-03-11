"""Event search orchestrator: intent extraction -> filter -> LLM rank -> return results."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserProfile
from app.events.filters import FilterCriteria, build_criteria_from_profile_and_payload, filter_events
from app.llm.intent import extract_intent
from app.llm.ranking import rank_events

logger = logging.getLogger(__name__)


async def search_events(
    db: AsyncSession,
    profile: UserProfile,
    payload: dict,
) -> list[dict]:
    """Search for events matching user profile and request.

    Steps:
    0. Extract structured intent from user request via LLM
    1. Build filter criteria from profile + payload + intent
    2. Hard-filter events from DB
    3. LLM rank the filtered candidates
    4. Return top results with reasons

    Returns list of ranked event dicts, or empty list.
    """
    # Step 0: Extract intent from user request (if available and not already extracted)
    user_request = payload.get("user_request", "")
    if user_request and "intent" not in payload:
        try:
            intent = await extract_intent(user_request)
            payload["intent"] = intent
            logger.info(f"Extracted intent: {intent}")
        except Exception:
            logger.warning("Intent extraction failed, continuing without it")

    # Build profile dict for criteria builder
    profile_dict = {
        "children_json": profile.children_json,
        "interests_json": profile.interests_json,
        "neighborhoods_json": profile.neighborhoods_json,
        "budget_preference": profile.budget_preference,
        "special_needs_notes": profile.special_needs_notes,
    }

    criteria = build_criteria_from_profile_and_payload(profile_dict, payload)
    logger.info(f"Search criteria: dates={criteria.date_from}-{criteria.date_to}, areas={criteria.areas}")

    # Step 1: Hard filter
    candidates = await filter_events(db, criteria)
    logger.info(f"Found {len(candidates)} candidate events after filtering")

    if not candidates:
        # Try broadening: remove area and category filters
        if criteria.areas or criteria.category:
            logger.info("No results, trying without area/category filter")
            broader = FilterCriteria(
                date_from=criteria.date_from,
                date_to=criteria.date_to,
                max_price_cents=criteria.max_price_cents,
                is_free_only=criteria.is_free_only,
                limit=criteria.limit,
            )
            candidates = await filter_events(db, broader)
            logger.info(f"Broader search found {len(candidates)} candidates")

    if not candidates:
        return []

    # Step 2: LLM ranking
    user_request = payload.get("user_request", "")
    ranked = await rank_events(
        candidates=candidates,
        user_profile=profile_dict,
        user_request=user_request,
    )

    logger.info(f"LLM ranked {len(ranked)} events")
    return ranked
