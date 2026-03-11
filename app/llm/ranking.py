"""LLM-based event ranking from pre-filtered candidates."""

from __future__ import annotations

import json
import logging

from app.llm.client import chat_completion_json

logger = logging.getLogger(__name__)

RANKING_SYSTEM_PROMPT = """You are an event recommendation assistant for NYC parents.

CRITICAL RULES:
1. You may ONLY rank and describe events from the PROVIDED list below.
2. Do NOT invent, fabricate, suggest, or reference any event not in this list.
3. If no events are a good fit, say so honestly. Do not make up alternatives.

Your task:
- Review the list of candidate events
- Rank the top 3 events that best match the user's profile and request
- For each event, explain WHY it's a good fit in 1-2 sentences

Return JSON with:
{
  "ranked_events": [
    {
      "event_id": <the external_id from the event>,
      "rank": 1,
      "reason": "Why this event is a great fit",
      "age_fit": "How it matches the child's age",
      "highlights": ["key highlight 1", "key highlight 2"]
    }
  ],
  "no_good_matches": false,
  "suggestion": null
}

If no events match well, set "no_good_matches": true and "suggestion" to advice for the user."""


def _event_to_summary(event: dict) -> str:
    """Convert event dict to a concise text summary for the LLM."""
    parts = [
        f"ID: {event.get('external_id', 'unknown')}",
        f"Title: {event.get('title', 'No title')}",
    ]
    if event.get("description"):
        parts.append(f"Description: {event['description'][:200]}")
    if event.get("category"):
        parts.append(f"Category: {event['category']}")
    if event.get("start_date"):
        parts.append(f"Date: {event['start_date']}")
    if event.get("start_time"):
        parts.append(f"Time: {event['start_time']}")
    if event.get("duration_minutes"):
        parts.append(f"Duration: {event['duration_minutes']} min")
    if event.get("venue_name"):
        parts.append(f"Venue: {event['venue_name']}")
    if event.get("district") or event.get("city"):
        parts.append(f"Area: {event.get('district', '')} {event.get('city', '')}".strip())
    if event.get("price_display"):
        parts.append(f"Price: {event['price_display']}")
    elif event.get("is_free"):
        parts.append("Price: Free")
    if event.get("age_min") is not None or event.get("age_max") is not None:
        age_str = f"Ages: {event.get('age_min', 0)}-{event.get('age_max', 'any')}"
        parts.append(age_str)
    if event.get("tags_json"):
        tags = event["tags_json"] if isinstance(event["tags_json"], list) else []
        if tags:
            parts.append(f"Tags: {', '.join(tags[:5])}")
    if event.get("stroller_friendly"):
        parts.append("Stroller-friendly: Yes")
    if event.get("rating_avg"):
        parts.append(f"Rating: {event['rating_avg']}/5")
    return " | ".join(parts)


async def rank_events(
    candidates: list[dict],
    user_profile: dict,
    user_request: str,
) -> list[dict]:
    """Rank candidate events using LLM.

    Args:
        candidates: List of event dicts from DB (pre-filtered)
        user_profile: User profile data
        user_request: Original user request text

    Returns:
        List of ranked event dicts with reasons
    """
    if not candidates:
        return []

    # Build events list for LLM
    events_text = "\n\n".join(
        f"Event {i + 1}:\n{_event_to_summary(e)}" for i, e in enumerate(candidates)
    )

    user_prompt = f"""User profile:
- Children: {json.dumps(user_profile.get('children_json', {}))}
- Interests: {json.dumps(user_profile.get('interests_json', []))}
- Area preference: {json.dumps(user_profile.get('neighborhoods_json', []))}
- Budget: {user_profile.get('budget_preference', 'any')}
- Special notes: {user_profile.get('special_needs_notes', 'none')}

User request: {user_request}

Available events:
{events_text}"""

    try:
        result = await chat_completion_json(
            system_prompt=RANKING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        if result.get("no_good_matches"):
            logger.info("LLM says no good matches")
            return []

        ranked = result.get("ranked_events", [])

        # Validate that all event_ids exist in candidates
        valid_ids = {e.get("external_id") for e in candidates}
        validated = []
        for r in ranked:
            if r.get("event_id") in valid_ids:
                # Attach the full event data
                event_data = next(
                    (e for e in candidates if e.get("external_id") == r["event_id"]), None
                )
                if event_data:
                    r["event"] = event_data
                    validated.append(r)
            else:
                logger.warning(f"LLM returned unknown event_id: {r.get('event_id')}")

        return validated

    except Exception:
        logger.exception("Failed to rank events")
        # Fallback: return first 3 candidates without LLM ranking
        return [
            {"event_id": e.get("external_id"), "rank": i + 1, "reason": "", "event": e}
            for i, e in enumerate(candidates[:3])
        ]
