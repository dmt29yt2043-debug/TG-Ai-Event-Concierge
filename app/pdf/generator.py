"""HTML -> PDF generation for event recommendations."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _dict_to_namespace(d: dict) -> SimpleNamespace:
    """Convert dict to SimpleNamespace for template dot notation."""
    return SimpleNamespace(**d)


def _generate_pdf_sync(events: list[dict], date_range: str) -> bytes:
    """Synchronous PDF generation (run in thread pool)."""
    from weasyprint import HTML

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("recommendations.html")

    # Prepare template data
    template_events = []
    for item in events:
        event_data = item.get("event", {})
        template_events.append({
            "event": _dict_to_namespace(event_data),
            "reason": item.get("reason", ""),
            "age_fit": item.get("age_fit", ""),
            "highlights": item.get("highlights", []),
        })

    html_string = template.render(
        events=template_events,
        date_range=date_range,
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )

    return HTML(string=html_string).write_pdf()


async def generate_pdf(events: list[dict], user_id: str) -> str | None:
    """Generate a PDF with event recommendations.

    Returns the filename (relative to static/) or None on failure.
    """
    if not events:
        return None

    try:
        # Build date range string
        dates = set()
        for item in events:
            event = item.get("event", {})
            if event.get("start_date"):
                dates.add(event["start_date"])
        date_range = " - ".join(sorted(dates)[:2]) if dates else "Upcoming"

        # Generate PDF in thread pool (WeasyPrint is sync/CPU-bound)
        pdf_bytes = await asyncio.to_thread(_generate_pdf_sync, events, date_range)

        # Save to static/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recs_{user_id}_{timestamp}.pdf"
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)

        filepath = static_dir / filename
        filepath.write_bytes(pdf_bytes)

        logger.info(f"Generated PDF: {filename} ({len(pdf_bytes)} bytes)")
        return filename

    except Exception:
        logger.exception("Failed to generate PDF")
        return None
