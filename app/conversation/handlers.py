"""Per-state handler functions for the conversation state machine."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversation.prompts import (
    ASK_DAY_BUTTONS,
    ASK_DAY_MSG,
    FOLLOW_UP_MSG,
    NO_RESULTS_BUTTONS,
    NO_RESULTS_MSG,
    ONBOARDING_COMPLETE_MSG,
    PDF_OFFER_BUTTONS,
    Q1_CHILDREN_MSG,
    Q2_INTERESTS_MSG,
    Q2_INTERESTS_OPTIONS,
    Q3_NEIGHBORHOODS_MSG,
    Q3_NEIGHBORHOODS_OPTIONS,
    Q4_BUDGET_BUTTONS,
    Q4_BUDGET_MSG,
    Q5_PREFERENCES_MSG,
    Q5_SKIP_BUTTON,
    RESTART_KEYWORDS,
    SEARCHING_MSG,
    WELCOME_MSG,
)
from app.conversation.state_machine import State
from app.db.models import Session, User
from app.db.queries import get_or_create_profile, update_session_state
from app.telegram.client import TelegramClient
from app.telegram.schemas import TelegramMessage

logger = logging.getLogger(__name__)

HandlerFunc = Callable[..., Coroutine[Any, Any, None]]


def _check_restart(text: str | None) -> bool:
    """Check if user wants to restart the conversation."""
    if text and text.strip().lower() in RESTART_KEYWORDS:
        return True
    return False


async def handle_welcome(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    await client.send_text(user.tg_id, WELCOME_MSG)
    await client.send_text(user.tg_id, Q1_CHILDREN_MSG)
    await update_session_state(db, session, State.Q1_CHILDREN)


async def handle_q1_children(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    if not text:
        await client.send_text(user.tg_id, "Please tell me about your kids — ages and how many.")
        return

    # Store raw answer, parse later with LLM if needed
    profile = await get_or_create_profile(db, user.id)
    profile.children_json = {"raw_answer": text}
    await db.flush()

    # Send Q2 as interactive list
    sections = [
        {
            "title": "Choose activities",
            "rows": [
                {"id": opt["id"], "title": opt["title"]}
                for opt in Q2_INTERESTS_OPTIONS
            ],
        }
    ]
    await client.send_interactive_list(
        user.tg_id, Q2_INTERESTS_MSG, "Pick interests", sections
    )
    await update_session_state(db, session, State.Q2_INTERESTS)


async def handle_q2_interests(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    if not text:
        await client.send_text(user.tg_id, "Please select an interest or type it out.")
        return

    # Store interest
    profile = await get_or_create_profile(db, user.id)
    interest_id = msg.callback_data if msg.callback_data else None
    interests = [interest_id] if interest_id else [text.strip().lower()]
    profile.interests_json = interests
    await db.flush()

    # Send Q3 as interactive list
    sections = [
        {
            "title": "Choose area",
            "rows": [
                {"id": opt["id"], "title": opt["title"], "description": opt.get("description", "")}
                for opt in Q3_NEIGHBORHOODS_OPTIONS
            ],
        }
    ]
    await client.send_interactive_list(
        user.tg_id, Q3_NEIGHBORHOODS_MSG, "Pick area", sections
    )
    await update_session_state(db, session, State.Q3_NEIGHBORHOODS)


async def handle_q3_neighborhoods(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    if not text:
        await client.send_text(user.tg_id, "Please select an area or type it out.")
        return

    profile = await get_or_create_profile(db, user.id)
    area_id = msg.callback_data if msg.callback_data else None
    profile.neighborhoods_json = [area_id] if area_id else [text.strip().lower()]
    await db.flush()

    # Send Q4 as buttons
    await client.send_interactive_buttons(user.tg_id, Q4_BUDGET_MSG, Q4_BUDGET_BUTTONS)
    await update_session_state(db, session, State.Q4_BUDGET)


async def handle_q4_budget(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    if not text:
        await client.send_text(user.tg_id, "Please pick a budget or type it out.")
        return

    profile = await get_or_create_profile(db, user.id)
    budget_id = msg.callback_data if msg.callback_data else None
    profile.budget_preference = budget_id or text.strip().lower()
    await db.flush()

    # Send Q5 with skip button
    await client.send_interactive_buttons(user.tg_id, Q5_PREFERENCES_MSG, Q5_SKIP_BUTTON)
    await update_session_state(db, session, State.Q5_PREFERENCES)


async def handle_q5_preferences(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    profile = await get_or_create_profile(db, user.id)
    skip = msg.callback_data == "skip"

    if not skip and text:
        profile.special_needs_notes = text

    profile.onboarding_complete = True
    await db.flush()

    await client.send_text(user.tg_id, ONBOARDING_COMPLETE_MSG)
    await update_session_state(db, session, State.READY)


async def handle_ready(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """User is onboarded and sending a request for events."""
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    # If audio message -> transcribe first
    if msg.type == "audio" and msg.audio_file_id:
        await client.send_text(user.tg_id, "Got your voice note! Transcribing...")
        await update_session_state(
            db, session, State.TRANSCRIBING, {"media_id": msg.audio_file_id}
        )
        # Trigger transcription
        from app.stt.transcribe import transcribe_voice_note

        transcript = await transcribe_voice_note(client, msg.audio_file_id)
        if transcript:
            # Store transcript and move to ASK_DAY
            await update_session_state(
                db, session, State.ASK_DAY, {"user_request": transcript}
            )
            await client.send_text(user.tg_id, f"I heard: \"{transcript}\"")
            await client.send_interactive_buttons(user.tg_id, ASK_DAY_MSG, ASK_DAY_BUTTONS)
        else:
            await client.send_text(
                user.tg_id,
                "Sorry, I couldn't understand that voice note. Could you try again or type your request?",
            )
            await update_session_state(db, session, State.READY)
        return

    if not text:
        await client.send_text(
            user.tg_id,
            "Send me a message or voice note about what kind of event you're looking for!",
        )
        return

    # Text message -> store as request and ask for day
    await update_session_state(db, session, State.ASK_DAY, {"user_request": text})
    await client.send_interactive_buttons(user.tg_id, ASK_DAY_MSG, ASK_DAY_BUTTONS)


async def handle_transcribing(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """User sent another message while we're transcribing. Just acknowledge."""
    await client.send_text(user.tg_id, "Still working on your voice note, one moment...")


async def handle_ask_day(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    if not text:
        await client.send_text(user.tg_id, "Please pick a day or type a date.")
        return

    # Parse day choice
    today = date.today()
    day_choice = text.strip().lower()
    if msg.callback_data:
        day_choice = msg.callback_data

    date_from = today
    date_to = today + timedelta(days=7)

    if day_choice in ("this_saturday", "this saturday", "saturday"):
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0:
            days_until_sat = 7
        date_from = today + timedelta(days=days_until_sat)
        date_to = date_from
    elif day_choice in ("this_sunday", "this sunday", "sunday"):
        days_until_sun = (6 - today.weekday()) % 7
        if days_until_sun == 0:
            days_until_sun = 7
        date_from = today + timedelta(days=days_until_sun)
        date_to = date_from
    elif day_choice in ("this_weekend", "this weekend", "weekend"):
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0:
            days_until_sat = 7
        date_from = today + timedelta(days=days_until_sat)
        date_to = date_from + timedelta(days=1)

    # Store day info and search
    payload = session.state_payload_json or {}
    payload["date_from"] = date_from.isoformat()
    payload["date_to"] = date_to.isoformat()

    await client.send_text(user.tg_id, SEARCHING_MSG)
    await update_session_state(db, session, State.SEARCHING, payload)

    # Trigger search
    from app.events.search import search_events

    profile = await get_or_create_profile(db, user.id)
    results = await search_events(db, profile, payload)

    if results and len(results) > 0:
        await update_session_state(
            db, session, State.OUTPUT, {**payload, "results": results}
        )
        # Format and send results
        from app.llm.copywriting import format_recommendations_text

        for event_text in format_recommendations_text(results):
            await client.send_text(user.tg_id, event_text)

        # Offer PDF and follow-up
        await client.send_interactive_buttons(
            user.tg_id,
            "What would you like to do next?",
            PDF_OFFER_BUTTONS,
        )
    else:
        await update_session_state(db, session, State.NO_RESULTS, payload)
        await client.send_interactive_buttons(
            user.tg_id, NO_RESULTS_MSG, NO_RESULTS_BUTTONS
        )


async def handle_searching(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """User sent a message while searching. Acknowledge."""
    await client.send_text(user.tg_id, "Still searching for the best events...")


async def handle_output(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """User responded after receiving recommendations."""
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    button_id = msg.callback_data

    if button_id == "send_pdf" or (text and "pdf" in text.lower()):
        await client.send_text(user.tg_id, "Generating your PDF summary...")
        # Generate and send PDF
        from app.pdf.generator import generate_pdf

        payload = session.state_payload_json or {}
        results = payload.get("results", [])
        pdf_path = await generate_pdf(results, user.tg_id)
        if pdf_path:
            pdf_file_path = f"static/{pdf_path}"
            await client.send_document(
                user.tg_id, pdf_file_path, "Your event recommendations", "PulseUP_Events.pdf"
            )
        await client.send_text(user.tg_id, FOLLOW_UP_MSG)
        await update_session_state(db, session, State.FOLLOW_UP)

    elif button_id == "more_options" or (text and "more" in text.lower()):
        await client.send_text(
            user.tg_id,
            "Tell me what you're looking for — type a message or send a voice note.",
        )
        await update_session_state(db, session, State.READY)

    elif button_id == "done":
        await client.send_text(user.tg_id, FOLLOW_UP_MSG)
        await update_session_state(db, session, State.FOLLOW_UP)

    else:
        # Treat as a new request
        await update_session_state(db, session, State.READY)
        await handle_ready(session, msg, text, db, client, user)


async def handle_no_results(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    button_id = msg.callback_data

    if button_id == "broaden":
        # Broaden search: extend date range, remove some filters
        payload = session.state_payload_json or {}
        date_from = payload.get("date_from", date.today().isoformat())
        payload["date_from"] = date_from
        payload["date_to"] = (
            date.fromisoformat(date_from) + timedelta(days=14)
        ).isoformat()
        payload["broadened"] = True

        await client.send_text(user.tg_id, SEARCHING_MSG)
        await update_session_state(db, session, State.SEARCHING, payload)

        from app.events.search import search_events

        profile = await get_or_create_profile(db, user.id)
        results = await search_events(db, profile, payload)

        if results:
            await update_session_state(
                db, session, State.OUTPUT, {**payload, "results": results}
            )
            from app.llm.copywriting import format_recommendations_text

            for event_text in format_recommendations_text(results):
                await client.send_text(user.tg_id, event_text)
            await client.send_interactive_buttons(
                user.tg_id, "What would you like to do next?", PDF_OFFER_BUTTONS
            )
        else:
            await client.send_text(
                user.tg_id,
                "Still no matches. Try telling me something different you're looking for!",
            )
            await update_session_state(db, session, State.READY)

    elif button_id == "new_search":
        await client.send_text(
            user.tg_id,
            "Sure! Tell me what kind of event you're looking for.",
        )
        await update_session_state(db, session, State.READY)

    else:
        await client.send_text(
            user.tg_id,
            "Tell me what you're looking for, or tap a button above.",
        )


async def handle_follow_up(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """User sends a new message after completing a flow. Treat as new request."""
    if _check_restart(text):
        await update_session_state(db, session, State.WELCOME)
        return await handle_welcome(session, msg, text, db, client, user)

    # Any message here starts a new search flow
    await update_session_state(db, session, State.READY)
    await handle_ready(session, msg, text, db, client, user)


# Map states to handlers
HANDLERS: dict[str, HandlerFunc] = {
    State.WELCOME: handle_welcome,
    State.Q1_CHILDREN: handle_q1_children,
    State.Q2_INTERESTS: handle_q2_interests,
    State.Q3_NEIGHBORHOODS: handle_q3_neighborhoods,
    State.Q4_BUDGET: handle_q4_budget,
    State.Q5_PREFERENCES: handle_q5_preferences,
    State.READY: handle_ready,
    State.TRANSCRIBING: handle_transcribing,
    State.ASK_DAY: handle_ask_day,
    State.SEARCHING: handle_searching,
    State.OUTPUT: handle_output,
    State.NO_RESULTS: handle_no_results,
    State.FOLLOW_UP: handle_follow_up,
}
