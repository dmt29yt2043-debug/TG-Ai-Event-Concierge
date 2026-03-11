"""CSV import/re-import pipeline for events.

Designed for the specific CSV format from the PulseUP scraper with
nested JSON in the `search_stats` column containing enriched event and venue data.
"""

from __future__ import annotations

import ast
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event

logger = logging.getLogger(__name__)


def _safe_json_parse(value: str | None) -> dict | list | None:
    """Try to parse a JSON string, falling back to ast.literal_eval for Python dicts."""
    if not value or value in ("", "None", "null"):
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None


def _safe_int(value, default=None):
    if value is None:
        return default
    try:
        v = float(value)
        return int(v)
    except (ValueError, TypeError):
        return default


def _safe_str(value, default=None):
    """Ensure value is a string or None. Converts dicts/lists to JSON strings."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_bool(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _price_to_cents(price_value) -> int | None:
    """Convert price value to cents."""
    if price_value is None:
        return None
    if isinstance(price_value, (int, float)):
        return int(price_value * 100)
    return None


def _extract_image_url(images_raw: str | None, merge_data: dict | None) -> str | None:
    """Extract the best image URL from available data."""
    # Try merge data first (usually higher quality)
    if merge_data:
        event_data = merge_data.get("event", {})
        img = event_data.get("main_image_url")
        if img:
            return img
        media = event_data.get("media", [])
        if media:
            return media[0]

    # Fallback to images_raw
    if images_raw:
        parsed = _safe_json_parse(images_raw)
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                return first.get("url")
            if isinstance(first, str):
                return first
    return None


def _parse_row(row: dict, source_csv: str) -> dict:
    """Parse a CSV row into Event model fields.

    Extracts data from both top-level columns and the nested
    `search_stats` JSON column which contains enriched data.
    """
    # Parse the enriched data from search_stats
    merge_data = None
    search_stats = _safe_json_parse(row.get("search_stats"))
    if isinstance(search_stats, dict):
        merge_data = search_stats.get("merge")

    event_enriched = {}
    venue_enriched = {}
    if merge_data:
        event_enriched = merge_data.get("event", {})
        venue_enriched = merge_data.get("venue", {})

    # Build external_id: prefer the enriched one, fallback to CSV column
    external_id = (
        event_enriched.get("external_id")
        or row.get("external_id")
        or row.get("url")
        or str(row.get("id", ""))
    )

    # Build venue address from enriched data
    venue_address = venue_enriched.get("address", "")
    if venue_enriched.get("city"):
        venue_address += f", {venue_enriched['city']}"
    if venue_enriched.get("state"):
        venue_address += f", {venue_enriched['state']}"
    if venue_enriched.get("zip"):
        venue_address += f" {venue_enriched['zip']}"
    if not venue_address.strip(", "):
        venue_address = row.get("venue_address", "")

    # Price handling
    price_val = event_enriched.get("price")
    is_free = _safe_bool(event_enriched.get("is_free") or row.get("is_free"))
    price_cents = _price_to_cents(price_val)
    if is_free:
        price_cents = 0

    price_display = event_enriched.get("price_note", "")
    if not price_display:
        if is_free:
            price_display = "Free"
        elif price_cents is not None:
            price_display = f"${price_cents / 100:.0f}"

    return {
        "external_id": str(external_id),
        "source_name": _safe_str(row.get("source_name"), ""),
        "title": _safe_str(event_enriched.get("title") or row.get("event_name"), "Untitled"),
        "short_title": _safe_str(event_enriched.get("short_title")),
        "description": _safe_str(event_enriched.get("description") or row.get("description"), ""),
        "description_source": _safe_str(event_enriched.get("description_source"), ""),
        "tagline": _safe_str(event_enriched.get("tagline")),
        "category": _safe_str(row.get("category"), ""),
        "tags_json": event_enriched.get("tags", []),
        "url": _safe_str(row.get("url"), ""),
        "ticket_url": _safe_str(event_enriched.get("ticket_url"), ""),
        # Dates
        "start_date": _safe_str(event_enriched.get("start_date") or (row.get("starts_at", "")[:10] if row.get("starts_at") else None)),
        "end_date": _safe_str(event_enriched.get("end_date") or (row.get("ends_at", "")[:10] if row.get("ends_at") else None)),
        "start_time": _safe_str(event_enriched.get("start_time"), ""),
        "end_time": _safe_str(event_enriched.get("end_time"), ""),
        "duration_minutes": _safe_int(event_enriched.get("duration_minutes")),
        "timezone": _safe_str(row.get("geo_timezone") or row.get("timezone"), ""),
        "schedule_raw": _safe_str(row.get("schedule_raw"), ""),
        # Location
        "venue_name": _safe_str(venue_enriched.get("name") or row.get("venue_name"), ""),
        "venue_address": venue_address.strip(", "),
        "city": _safe_str(row.get("geo_city") or row.get("city"), ""),
        "district": _safe_str(row.get("geo_district") or row.get("district"), ""),
        "borough": _safe_str(row.get("district"), ""),
        "state": _safe_str(row.get("geo_state") or row.get("state"), ""),
        "zip_code": _safe_str(venue_enriched.get("zip") or row.get("geo_zip"), ""),
        "latitude": _safe_float(row.get("geo_lat")),
        "longitude": _safe_float(row.get("geo_lon")),
        # Age
        "age_min": _safe_int(event_enriched.get("age_min")),
        "age_max": _safe_int(event_enriched.get("age_max")),
        "age_best_min": _safe_int(event_enriched.get("age_best_min")),
        "age_best_max": _safe_int(event_enriched.get("age_best_max")),
        # Price
        "is_free": is_free,
        "price_cents": price_cents,
        "price_min_cents": _price_to_cents(event_enriched.get("price_min")),
        "price_max_cents": _price_to_cents(event_enriched.get("price_max")),
        "price_display": _safe_str(price_display),
        # Media
        "main_image_url": _safe_str(_extract_image_url(row.get("images_raw"), merge_data)),
        "images_json": event_enriched.get("media", []),
        # Venue details
        "venue_type": _safe_str(venue_enriched.get("venue_type")),
        "stroller_friendly": _safe_bool(venue_enriched.get("stroller_friendly")),
        "wheelchair_accessible": _safe_bool(venue_enriched.get("wheelchair_accessible")),
        "accessibility_notes": _safe_str(venue_enriched.get("accessibility_notes")),
        "venue_phone": _safe_str(venue_enriched.get("phone")),
        "venue_website": _safe_str(venue_enriched.get("website")),
        # Reviews
        "rating_avg": _safe_float(event_enriched.get("rating_avg")),
        "rating_count": _safe_int(event_enriched.get("rating_count")),
        "reviews_json": event_enriched.get("reviews", []),
        # Extra
        "includes_json": event_enriched.get("includes", []),
        "is_family_friendly": _safe_bool(event_enriched.get("is_family_friendly")),
        "subway_info": _safe_str(event_enriched.get("subway")),
        # Import tracking
        "source_csv": source_csv,
        "is_active": True,
    }


async def import_csv(
    db: AsyncSession,
    file_path: str,
    source_name: str | None = None,
) -> dict:
    """Import events from CSV file.

    Uses upsert logic on external_id:
    - Existing events are updated
    - New events are inserted
    - Events not in the new CSV are marked inactive

    Returns: {"created": N, "updated": N, "deactivated": N, "errors": N}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    source_csv = source_name or path.name
    stats = {"created": 0, "updated": 0, "deactivated": 0, "errors": 0}
    seen_ids: set[str] = set()

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            try:
                parsed = _parse_row(row, source_csv)
                ext_id = parsed["external_id"]
                if not ext_id:
                    logger.warning(f"Row {row_num}: no external_id, skipping")
                    stats["errors"] += 1
                    continue

                seen_ids.add(ext_id)

                # Use savepoint so one row failure doesn't kill the transaction
                nested = await db.begin_nested()
                try:
                    result = await db.execute(
                        select(Event).where(Event.external_id == ext_id)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        for key, value in parsed.items():
                            if value is not None:
                                setattr(existing, key, value)
                        existing.updated_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                    else:
                        event = Event(**parsed)
                        db.add(event)
                        stats["created"] += 1

                    await nested.commit()
                except Exception:
                    await nested.rollback()
                    raise

            except Exception:
                logger.exception(f"Row {row_num}: failed to import")
                stats["errors"] += 1

    # Deactivate events not in this import (that share the same source_csv)
    result = await db.execute(
        select(Event).where(
            Event.source_csv == source_csv,
            Event.is_active == True,
            Event.external_id.notin_(seen_ids) if seen_ids else True,
        )
    )
    stale_events = result.scalars().all()
    for event in stale_events:
        event.is_active = False
        stats["deactivated"] += 1

    await db.flush()

    logger.info(
        f"Import complete: {stats['created']} created, {stats['updated']} updated, "
        f"{stats['deactivated']} deactivated, {stats['errors']} errors"
    )
    return stats
