"""Hard-filter events from the database based on criteria."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event

logger = logging.getLogger(__name__)

# Mapping from onboarding area IDs to boroughs/districts
AREA_TO_DISTRICTS = {
    "manhattan_upper": ["Upper West Side", "Upper East Side", "Harlem", "Washington Heights"],
    "manhattan_mid": ["Midtown", "Chelsea", "Flatiron", "Gramercy", "Murray Hill"],
    "manhattan_lower": ["Village", "FiDi", "Lower East Side", "SoHo", "TriBeCa", "Chinatown"],
    "brooklyn": ["Brooklyn"],
    "queens": ["Queens"],
    "bronx": ["Bronx", "The Bronx"],
    "staten_island": ["Staten Island"],
    "anywhere": [],
}

BUDGET_TO_CENTS = {
    "free": 0,
    "under_25": 2500,
    "under_50": 5000,
    "any": None,
}


@dataclass
class FilterCriteria:
    date_from: str | None = None
    date_to: str | None = None
    areas: list[str] = field(default_factory=list)
    max_price_cents: int | None = None
    category: str | None = None
    age: int | None = None
    is_free_only: bool = False
    keywords: list[str] = field(default_factory=list)
    limit: int = 30


def build_criteria_from_profile_and_payload(
    profile_dict: dict, payload: dict
) -> FilterCriteria:
    """Build filter criteria from user profile and search payload."""
    criteria = FilterCriteria()

    # Dates from payload
    criteria.date_from = payload.get("date_from")
    criteria.date_to = payload.get("date_to")

    # Areas from profile
    areas = profile_dict.get("neighborhoods_json", [])
    if areas and isinstance(areas, list):
        criteria.areas = areas

    # Budget from profile
    budget = profile_dict.get("budget_preference", "any")
    if budget == "free":
        criteria.is_free_only = True
    max_cents = BUDGET_TO_CENTS.get(budget)
    if max_cents is not None:
        criteria.max_price_cents = max_cents

    # Age from children
    children = profile_dict.get("children_json", {})
    if isinstance(children, dict) and children.get("raw_answer"):
        # We'll extract age in a future LLM step; for now skip
        pass

    # Intent keywords from payload
    intent = payload.get("intent", {})
    if isinstance(intent, dict):
        if intent.get("activity_type"):
            criteria.category = intent["activity_type"]
        if intent.get("keywords"):
            criteria.keywords = intent["keywords"]

    # User request as keyword fallback
    user_request = payload.get("user_request", "")
    if user_request and not criteria.keywords:
        criteria.keywords = user_request.lower().split()[:5]

    return criteria


async def filter_events(db: AsyncSession, criteria: FilterCriteria) -> list[dict]:
    """Filter events from DB based on hard criteria.

    Returns list of event dicts (up to criteria.limit).
    """
    query = select(Event).where(Event.is_active == True)

    # Date filter
    if criteria.date_from:
        query = query.where(Event.start_date >= criteria.date_from)
    if criteria.date_to:
        query = query.where(Event.start_date <= criteria.date_to)

    # Price filter
    if criteria.is_free_only:
        query = query.where(Event.is_free == True)
    elif criteria.max_price_cents is not None:
        query = query.where(
            (Event.price_cents <= criteria.max_price_cents) | (Event.is_free == True)
        )

    # Area filter
    if criteria.areas and "anywhere" not in criteria.areas:
        area_districts = []
        area_boroughs = []
        for area_id in criteria.areas:
            districts = AREA_TO_DISTRICTS.get(area_id, [])
            if districts:
                area_districts.extend(districts)
                area_boroughs.extend(districts)
            else:
                # Free text area
                area_districts.append(area_id)

        if area_districts:
            # Match on district, borough, or city
            query = query.where(
                Event.district.in_(area_districts)
                | Event.borough.in_(area_boroughs)
                | Event.city.in_(area_districts)
            )

    # Category filter (soft: only if specified)
    if criteria.category:
        query = query.where(Event.category.ilike(f"%{criteria.category}%"))

    # Order by date, then rating
    query = query.order_by(Event.start_date.asc(), Event.rating_avg.desc().nullslast())
    query = query.limit(criteria.limit)

    result = await db.execute(query)
    events = result.scalars().all()

    # Convert to dicts
    return [_event_to_dict(e) for e in events]


def _event_to_dict(event: Event) -> dict:
    """Convert Event ORM model to a plain dict."""
    return {
        "external_id": event.external_id,
        "title": event.title,
        "short_title": event.short_title,
        "description": event.description,
        "description_source": event.description_source,
        "tagline": event.tagline,
        "category": event.category,
        "tags_json": event.tags_json,
        "url": event.url,
        "ticket_url": event.ticket_url,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "duration_minutes": event.duration_minutes,
        "venue_name": event.venue_name,
        "venue_address": event.venue_address,
        "city": event.city,
        "district": event.district,
        "borough": event.borough,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "age_min": event.age_min,
        "age_max": event.age_max,
        "age_best_min": event.age_best_min,
        "age_best_max": event.age_best_max,
        "is_free": event.is_free,
        "price_cents": event.price_cents,
        "price_display": event.price_display,
        "main_image_url": event.main_image_url,
        "images_json": event.images_json,
        "venue_type": event.venue_type,
        "stroller_friendly": event.stroller_friendly,
        "wheelchair_accessible": event.wheelchair_accessible,
        "accessibility_notes": event.accessibility_notes,
        "subway_info": event.subway_info,
        "rating_avg": event.rating_avg,
        "rating_count": event.rating_count,
        "reviews_json": event.reviews_json,
        "includes_json": event.includes_json,
        "is_family_friendly": event.is_family_friendly,
    }
