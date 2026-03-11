"""Format event recommendations for WhatsApp messages."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def format_recommendations_text(ranked_events: list[dict]) -> list[str]:
    """Format ranked events into WhatsApp-friendly text messages.

    Returns a list of message strings (one per event).
    """
    messages = []

    for i, item in enumerate(ranked_events[:4]):
        event = item.get("event", {})
        reason = item.get("reason", "")

        title = event.get("title", "Event")
        lines = [f"*{i + 1}. {title}*"]

        if reason:
            lines.append(f"_{reason}_")

        # Date & Time
        date_str = event.get("start_date", "")
        time_str = event.get("start_time", "")
        if date_str:
            dt_line = f"Date: {date_str}"
            if time_str:
                dt_line += f" at {time_str}"
            lines.append(dt_line)

        # Duration
        if event.get("duration_minutes"):
            hours = event["duration_minutes"] // 60
            mins = event["duration_minutes"] % 60
            dur = f"{hours}h" if hours else ""
            if mins:
                dur += f" {mins}min" if dur else f"{mins} min"
            lines.append(f"Duration: {dur.strip()}")

        # Age
        age_fit = item.get("age_fit", "")
        if age_fit:
            lines.append(f"Ages: {age_fit}")
        elif event.get("age_min") is not None:
            age_line = f"Ages: {event.get('age_min', 0)}"
            if event.get("age_max") and event["age_max"] < 100:
                age_line += f"-{event['age_max']}"
            else:
                age_line += "+"
            lines.append(age_line)

        # Price
        if event.get("price_display"):
            lines.append(f"Price: {event['price_display']}")
        elif event.get("is_free"):
            lines.append("Price: Free")
        elif event.get("price_cents") is not None:
            price_dollars = event["price_cents"] / 100
            lines.append(f"Price: ${price_dollars:.0f}")

        # Location
        venue = event.get("venue_name", "")
        area = event.get("district", "") or event.get("city", "")
        if venue:
            loc_line = f"Location: {venue}"
            if area:
                loc_line += f", {area}"
            lines.append(loc_line)

        # Subway
        if event.get("subway_info"):
            lines.append(f"Transit: {event['subway_info']}")

        # Accessibility
        access_parts = []
        if event.get("stroller_friendly"):
            access_parts.append("Stroller-friendly")
        if event.get("wheelchair_accessible"):
            access_parts.append("Wheelchair accessible")
        if access_parts:
            lines.append(" | ".join(access_parts))

        # What to expect (from includes or highlights)
        highlights = item.get("highlights", [])
        includes = event.get("includes_json", [])
        if highlights:
            lines.append("\nWhat to expect:")
            for h in highlights[:3]:
                lines.append(f"  - {h}")
        elif includes and isinstance(includes, list):
            lines.append("\nIncludes:")
            for inc in includes[:3]:
                lines.append(f"  - {inc}")

        # Link
        if event.get("url") or event.get("ticket_url"):
            link = event.get("ticket_url") or event.get("url")
            lines.append(f"\n{link}")

        messages.append("\n".join(lines))

    return messages
