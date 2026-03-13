"""Per-state handler functions for the conversation state machine."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from datetime import date, datetime, timedelta
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
    Q2_PER_CHILD_MSG,
    Q2_SUMMARY_MSG,
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
from app.db.queries import get_or_create_profile, reset_profile, save_event_rating, update_session_state
from app.telegram.client import TelegramClient
from app.telegram.schemas import TelegramMessage

logger = logging.getLogger(__name__)

HandlerFunc = Callable[..., Coroutine[Any, Any, None]]


def _check_restart(text: str | None) -> bool:
    """Check if user wants to restart the conversation."""
    if text and text.strip().lower() in RESTART_KEYWORDS:
        return True
    return False


# --------------- helpers ---------------

_INTEREST_EMOJI = {
    "active": "\u26bd",
    "creative": "\U0001f3a8",
    "educational": "\U0001f9ea",
    "shows": "\U0001f3ad",
    "outdoor": "\U0001f333",
    "fun_play": "\U0001f3ae",
    "adventure": "\U0001f680",
    "books": "\U0001f4da",
    "social": "\U0001f476",
}


async def _parse_children(raw_text: str) -> list[dict]:
    from app.llm.client import chat_completion_json
    result = await chat_completion_json(
        system_prompt=(
            'Extract children from the parent\'s text. Return JSON: '
            '{"children": [{"age": N, "gender": "boy"|"girl"|"unknown", "name": null}]}. '
            'Infer gender from words like daughter/son/girl/boy/девочка/мальчик/дочь/сын. '
            'If gender is not mentioned, use "unknown". '
            'If age is unclear, estimate. Always return at least 1 child.'
        ),
        user_prompt=raw_text,
    )
    return result.get("children", [{"age": None, "gender": "unknown", "name": None}])


def _build_interest_buttons(selected: list[str]) -> list[dict]:
    buttons = []
    for opt in Q2_INTERESTS_OPTIONS:
        title = opt["title"]
        if opt["id"] in selected:
            title = "\u2705 " + title
        buttons.append({"id": opt["id"], "title": title})
    buttons.append({"id": "q2_done", "title": "Done \u2705"})
    return buttons


def _build_neighborhood_buttons(selected: list[str]) -> list[dict]:
    buttons = []
    for opt in Q3_NEIGHBORHOODS_OPTIONS:
        title = opt["title"]
        if opt["id"] in selected:
            title = "\u2705 " + title
        buttons.append({"id": opt["id"], "title": title})
    buttons.append({"id": "q3_done", "title": "Done \u2705"})
    return buttons


_GENDER_EMOJI = {"girl": "\U0001f467", "boy": "\U0001f466", "unknown": "\U0001f9d2"}


def _build_per_child_summary(children: list[dict], per_child: dict) -> str:
    lines = []
    for idx, child in enumerate(children):
        age = child.get("age", "?")
        gender = child.get("gender", "unknown")
        name = child.get("name")
        emoji = _GENDER_EMOJI.get(gender, "\U0001f9d2")

        # Header: "\U0001f467 6yo" or "\U0001f466 Misha, 4yo"
        header = f"{emoji} "
        if name:
            header += f"{name}, "
        header += f"{age}yo"

        # Interests
        interests = per_child.get(str(idx), []) or child.get("interests", [])
        labels = []
        for iid in interests:
            ie = _INTEREST_EMOJI.get(iid, "")
            label = iid.replace("_", " ").title()
            labels.append(f"{ie} {label}".strip())
        joined = ", ".join(labels) if labels else "none yet"
        header += f" \u2192 {joined}"
        lines.append(header)

        # Notes (from voice/text enrichment)
        notes = child.get("notes", [])
        if notes:
            lines.append(f"   \U0001f4ac {'; '.join(notes)}")

    return "\n".join(lines)


async def _enrich_children_from_notes(
    children: list[dict], transcript: str
) -> list[dict]:
    """Use LLM to parse a parent\'s note and distribute info to each child."""
    import json as _json
    from app.llm.client import chat_completion_json

    result = await chat_completion_json(
        system_prompt=(
            "You have a list of children and a parent\'s note about them. "
            "Extract specific info about each child mentioned in the note. "
            "Return JSON: {\"children\": [{\"age\": N, \"gender\": \"...\", "
            "\"name\": \"...\" or null, \"notes\": [\"short note 1\", \"short note 2\"]}]}. "
            "Keep ALL existing fields (age, gender, name, interests) unchanged. "
            "Only ADD or UPDATE the \"notes\" array based on the transcript. "
            "Each note should be a SHORT phrase (3-6 words max), e.g. \"loves dancing\", \"likes building things\". "
            "If something doesn\'t clearly match a specific child, add it to the most likely one. "
            "If nothing relevant for a child, keep their notes as-is or empty."
        ),
        user_prompt=f"Children: {_json.dumps(children)}\n\nParent\'s note: {transcript}",
    )
    enriched = result.get("children", children)
    # Safety: preserve original structure, only merge notes
    for i, orig in enumerate(children):
        if i < len(enriched):
            orig["notes"] = enriched[i].get("notes", orig.get("notes", []))
            if enriched[i].get("name") and not orig.get("name"):
                orig["name"] = enriched[i]["name"]
            if enriched[i].get("gender") != "unknown" and orig.get("gender") == "unknown":
                orig["gender"] = enriched[i]["gender"]
    return children


async def _resolve_date_hint(date_hint: str) -> tuple[date, date]:
    """Convert a date_hint string to date_from, date_to."""
    today = date.today()
    hint = date_hint.strip().lower()
    if hint in ("this weekend", "weekend"):
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0:
            days_until_sat = 7
        date_from = today + timedelta(days=days_until_sat)
        return date_from, date_from + timedelta(days=1)
    elif hint in ("today",):
        return today, today
    elif hint in ("tomorrow",):
        return today + timedelta(days=1), today + timedelta(days=1)
    elif hint in ("this saturday", "saturday"):
        days = (5 - today.weekday()) % 7
        if days == 0:
            days = 7
        d = today + timedelta(days=days)
        return d, d
    elif hint in ("this sunday", "sunday"):
        days = (6 - today.weekday()) % 7
        if days == 0:
            days = 7
        d = today + timedelta(days=days)
        return d, d
    else:
        parsed = _parse_flexible_date(hint)
        if parsed:
            return parsed, parsed
        return today, today + timedelta(days=7)


async def _do_search_and_output(
    session: Session,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
    payload: dict,
) -> None:
    """Shared search + output logic used by handle_ask_day and handle_ready."""
    from app.events.search import search_events

    profile = await get_or_create_profile(db, user.id)
    results = await search_events(db, profile, payload)

    if results and len(results) > 0:
        await update_session_state(
            db, session, State.OUTPUT, {**payload, "results": results}
        )
        from app.llm.copywriting import format_recommendations_text

        formatted = format_recommendations_text(results)
        for i, event_text in enumerate(formatted):
            event_data = results[i].get("event", {}) if i < len(results) else {}
            image_url = event_data.get("main_image_url")
            if image_url:
                try:
                    if len(event_text) <= 1024:
                        await client.send_image(user.tg_id, image_url, caption=event_text)
                    else:
                        await client.send_image(user.tg_id, image_url)
                        await client.send_text(user.tg_id, event_text)
                except Exception:
                    logger.warning("Failed to send image for event, sending text only")
                    await client.send_text(user.tg_id, event_text)
            else:
                await client.send_text(user.tg_id, event_text)

            rating_buttons = [
                {"id": f"rate_{i}_1", "title": "1 \u2b50"},
                {"id": f"rate_{i}_2", "title": "2 \u2b50\u2b50"},
                {"id": f"rate_{i}_3", "title": "3 \u2b50\u2b50\u2b50"},
                {"id": f"rate_{i}_4", "title": "4 \u2b50\u2b50\u2b50\u2b50"},
                {"id": f"rate_{i}_5", "title": "5 \u2b50\u2b50\u2b50\u2b50\u2b50"},
            ]
            await client.send_inline_row(
                user.tg_id, "Rate this suggestion:", rating_buttons
            )

        await client.send_interactive_buttons(
            user.tg_id,
            "*What would you like to do next?*",
            PDF_OFFER_BUTTONS,
        )
    else:
        await update_session_state(db, session, State.NO_RESULTS, payload)
        await client.send_interactive_buttons(
            user.tg_id, NO_RESULTS_MSG, NO_RESULTS_BUTTONS
        )


# --------------- state handlers ---------------


async def handle_welcome(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    # Wipe profile on restart for clean testing
    await reset_profile(db, user.id)
    await client.send_text(user.tg_id, WELCOME_MSG)
    await client.send_text(user.tg_id, Q1_CHILDREN_MSG)
    await update_session_state(db, session, State.Q1_CHILDREN)


# --- Change 2: handle_q1_children with per-child parsing ---

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
        await client.send_text(user.tg_id, "Please tell me about your kids \u2014 ages and how many.")
        return

    # Parse children with LLM
    parsed_children = await _parse_children(text)

    profile = await get_or_create_profile(db, user.id)
    profile.children_json = {"raw_answer": text, "children": parsed_children}
    await db.flush()

    # Build Q2 buttons
    buttons = _build_interest_buttons([])

    if len(parsed_children) <= 1:
        # Single child: normal Q2
        result = await client.send_interactive_buttons(user.tg_id, Q2_INTERESTS_MSG, buttons)
        await update_session_state(
            db, session, State.Q2_INTERESTS,
            payload={"selected": [], "msg_id": result.get("message_id")},
        )
    else:
        # Multiple children: per-child flow
        first_child = parsed_children[0]
        age = first_child.get("age", "?")
        msg_text = Q2_PER_CHILD_MSG.format(age=age)
        result = await client.send_interactive_buttons(user.tg_id, msg_text, buttons)
        await update_session_state(
            db, session, State.Q2_INTERESTS,
            payload={
                "children": parsed_children,
                "current_child": 0,
                "per_child": {},
                "selected": [],
                "msg_id": result.get("message_id"),
                "phase": "selecting",
            },
        )


# --- Change 3: handle_q2_interests with per-child flow ---

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

    payload = session.state_payload_json or {}
    selected: list[str] = payload.get("selected", [])
    msg_id: int | None = payload.get("msg_id")
    children: list[dict] | None = payload.get("children")
    phase: str = payload.get("phase", "selecting")
    current_child: int = payload.get("current_child", 0)
    per_child: dict = payload.get("per_child", {})

    cb = msg.callback_data

    # --- Legacy / single-child: no "children" key in payload ---
    if children is None:
        # Original behavior
        if not cb:
            profile = await get_or_create_profile(db, user.id)
            profile.interests_json = [text.strip().lower()] if text else []
            await db.flush()
        else:
            if cb == "q2_done":
                if not selected:
                    await client.send_text(user.tg_id, "Please pick at least one activity type first.")
                    return
                profile = await get_or_create_profile(db, user.id)
                profile.interests_json = selected
                await db.flush()
            else:
                # Toggle
                if cb in selected:
                    selected.remove(cb)
                else:
                    selected.append(cb)
                buttons = _build_interest_buttons(selected)
                target_msg = msg_id or msg.callback_message_id
                if target_msg:
                    await client.edit_inline_buttons(user.tg_id, target_msg, buttons)
                await update_session_state(
                    db, session, State.Q2_INTERESTS,
                    payload={"selected": selected, "msg_id": target_msg},
                )
                return

        # Advance to Q3 (multi-select neighborhoods)
        await _send_q3_multiselect(session, db, client, user)
        return

    # --- Multi-child flow ---

    if phase == "summary":
        # In summary phase: "q2_done" finalizes, text/voice adds notes
        if cb == "q2_done":
            # Save everything to profile
            profile = await get_or_create_profile(db, user.id)
            # Union of all interests
            all_interests: list[str] = []
            for idx_str, ints in per_child.items():
                for i in ints:
                    if i not in all_interests:
                        all_interests.append(i)
            profile.interests_json = all_interests

            # Store per-child interests in children_json
            cj = profile.children_json or {}
            cj_children = cj.get("children", children)
            for idx_str, ints in per_child.items():
                idx = int(idx_str)
                if idx < len(cj_children):
                    cj_children[idx]["interests"] = ints
            cj["children"] = cj_children
            profile.children_json = cj
            await db.flush()

            # Advance to Q3
            await _send_q3_multiselect(session, db, client, user)
            return

        # Text or voice in summary phase -> enrich children with structured notes
        # (Voice is already transcribed by the dispatcher, so text is set)
        if text:
            # Use LLM to distribute notes to specific children
            await client.send_text(user.tg_id, "\U0001f4ad Processing your notes...")
            enriched = await _enrich_children_from_notes(children, text)
            payload["children"] = enriched

            # Update profile with enriched children data
            profile = await get_or_create_profile(db, user.id)
            cj = profile.children_json or {}
            cj["children"] = enriched
            profile.children_json = cj
            await db.flush()

            summary = _build_per_child_summary(enriched, per_child)
            summary_msg = Q2_SUMMARY_MSG.format(summary=summary)
            done_buttons = [{"id": "q2_done", "title": "Done \u2705"}]
            result = await client.send_interactive_buttons(user.tg_id, summary_msg, done_buttons)
            payload["msg_id"] = result.get("message_id")
            await update_session_state(db, session, State.Q2_INTERESTS, payload=payload)
            return

        return

    # --- Selecting phase (per child) ---

    if not cb:
        # User typed text instead of clicking
        profile = await get_or_create_profile(db, user.id)
        profile.interests_json = [text.strip().lower()] if text else []
        await db.flush()
        await _send_q3_multiselect(session, db, client, user)
        return

    if cb == "q2_done":
        if not selected:
            await client.send_text(user.tg_id, "Please pick at least one activity type first.")
            return

        # Save current child's selections
        per_child[str(current_child)] = list(selected)

        if current_child + 1 < len(children):
            # More children: move to next
            next_child = current_child + 1
            next_age = children[next_child].get("age", "?")
            next_msg = Q2_PER_CHILD_MSG.format(age=next_age)
            buttons = _build_interest_buttons([])
            result = await client.send_interactive_buttons(user.tg_id, next_msg, buttons)
            await update_session_state(
                db, session, State.Q2_INTERESTS,
                payload={
                    "children": children,
                    "current_child": next_child,
                    "per_child": per_child,
                    "selected": [],
                    "msg_id": result.get("message_id"),
                    "phase": "selecting",
                },
            )
        else:
            # Last child done: show summary
            summary = _build_per_child_summary(children, per_child)
            summary_msg = Q2_SUMMARY_MSG.format(summary=summary)
            done_buttons = [{"id": "q2_done", "title": "Done \u2705"}]
            result = await client.send_interactive_buttons(user.tg_id, summary_msg, done_buttons)
            await update_session_state(
                db, session, State.Q2_INTERESTS,
                payload={
                    "children": children,
                    "current_child": current_child,
                    "per_child": per_child,
                    "selected": [],
                    "msg_id": result.get("message_id"),
                    "phase": "summary",
                },
            )
        return

    # Toggle interest
    if cb in selected:
        selected.remove(cb)
    else:
        selected.append(cb)

    buttons = _build_interest_buttons(selected)
    target_msg = msg_id or msg.callback_message_id
    if target_msg:
        await client.edit_inline_buttons(user.tg_id, target_msg, buttons)

    payload["selected"] = selected
    payload["msg_id"] = target_msg
    await update_session_state(db, session, State.Q2_INTERESTS, payload=payload)


# --- Change 4: Q3 neighborhoods multi-select ---

async def _send_q3_multiselect(
    session: Session,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """Send Q3 as multi-select inline buttons (like Q2)."""
    buttons = _build_neighborhood_buttons([])
    result = await client.send_interactive_buttons(user.tg_id, Q3_NEIGHBORHOODS_MSG, buttons)
    await update_session_state(
        db, session, State.Q3_NEIGHBORHOODS,
        payload={"selected": [], "msg_id": result.get("message_id")},
    )


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

    payload = session.state_payload_json or {}
    selected: list[str] = payload.get("selected", [])
    msg_id: int | None = payload.get("msg_id")

    cb = msg.callback_data

    if not cb:
        # User typed text
        if not text:
            await client.send_text(user.tg_id, "Please select an area or type it out.")
            return
        profile = await get_or_create_profile(db, user.id)
        profile.neighborhoods_json = [text.strip().lower()]
        await db.flush()
        await client.send_interactive_buttons(user.tg_id, Q4_BUDGET_MSG, Q4_BUDGET_BUTTONS)
        await update_session_state(db, session, State.Q4_BUDGET)
        return

    # "anywhere" auto-advances
    if cb == "anywhere":
        profile = await get_or_create_profile(db, user.id)
        profile.neighborhoods_json = ["anywhere"]
        await db.flush()
        await client.send_interactive_buttons(user.tg_id, Q4_BUDGET_MSG, Q4_BUDGET_BUTTONS)
        await update_session_state(db, session, State.Q4_BUDGET)
        return

    # Done
    if cb == "q3_done":
        if not selected:
            await client.send_text(user.tg_id, "Please pick at least one area first.")
            return
        profile = await get_or_create_profile(db, user.id)
        profile.neighborhoods_json = selected
        await db.flush()
        await client.send_interactive_buttons(user.tg_id, Q4_BUDGET_MSG, Q4_BUDGET_BUTTONS)
        await update_session_state(db, session, State.Q4_BUDGET)
        return

    # Toggle
    if cb in selected:
        selected.remove(cb)
    else:
        selected.append(cb)

    buttons = _build_neighborhood_buttons(selected)
    target_msg = msg_id or msg.callback_message_id
    if target_msg:
        await client.edit_inline_buttons(user.tg_id, target_msg, buttons)

    await update_session_state(
        db, session, State.Q3_NEIGHBORHOODS,
        payload={"selected": selected, "msg_id": target_msg},
    )


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

    await client.send_interactive_buttons(user.tg_id, Q5_PREFERENCES_MSG, Q5_SKIP_BUTTON)
    await update_session_state(db, session, State.Q5_PREFERENCES)


# --- Change 5: handle_q5_preferences with voice support ---

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

    # Handle voice notes
    if msg.type == "audio" and msg.audio_file_id:
        from app.stt.transcribe import transcribe_voice_note
        await client.send_text(user.tg_id, "\U0001f399\ufe0f Got your voice note! Transcribing...")
        transcript = await transcribe_voice_note(client, msg.audio_file_id)
        if transcript:
            text = transcript
            await client.send_text(user.tg_id, f'I heard: "{transcript}"')
        else:
            await client.send_text(user.tg_id, "Sorry, couldn't understand. Try again or tap Skip.")
            return

    profile = await get_or_create_profile(db, user.id)
    skip = msg.callback_data == "skip"

    if not skip and text:
        profile.special_needs_notes = text

    profile.onboarding_complete = True
    await db.flush()

    await client.send_text(user.tg_id, ONBOARDING_COMPLETE_MSG)
    await update_session_state(db, session, State.READY)


# --- Change 6: handle_ready with smart ASK_DAY skip ---

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
        await client.send_text(user.tg_id, "\U0001f399\ufe0f Got your voice note! Transcribing...")
        await update_session_state(
            db, session, State.TRANSCRIBING, {"media_id": msg.audio_file_id}
        )
        from app.stt.transcribe import transcribe_voice_note

        transcript = await transcribe_voice_note(client, msg.audio_file_id)
        if transcript:
            await client.send_text(user.tg_id, f'I heard: "{transcript}"')
            text = transcript
            # Fall through to intent extraction below
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

    # Extract intent to check for date_hint
    from app.llm.intent import extract_intent
    intent = await extract_intent(text)

    if intent.get("date_hint"):
        # Smart skip: resolve dates and go straight to search
        date_from, date_to = await _resolve_date_hint(intent["date_hint"])
        payload = {
            "user_request": text,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
        await client.send_text(user.tg_id, SEARCHING_MSG)
        await update_session_state(db, session, State.SEARCHING, payload)
        await _do_search_and_output(session, db, client, user, payload)
    else:
        # No date hint: ask for day
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

    # Handle voice notes in ASK_DAY state
    if msg.type == "audio" and msg.audio_file_id:
        from app.stt.transcribe import transcribe_voice_note

        await client.send_text(user.tg_id, "\U0001f399\ufe0f Got your voice note! Transcribing...")
        transcript = await transcribe_voice_note(client, msg.audio_file_id)
        if transcript:
            text = transcript
            await client.send_text(user.tg_id, f'I heard: "{transcript}"')
        else:
            await client.send_text(
                user.tg_id,
                "Sorry, I couldn't understand that. Please pick a day or type a date.",
            )
            return

    # Handle "Other date" button
    if msg.callback_data == "other_date":
        await client.send_text(
            user.tg_id,
            "Type a date \u2014 for example:\n"
            "\u2022 March 15\n\u2022 03/15\n\u2022 next Friday\n\u2022 \u0437\u0430\u0432\u0442\u0440\u0430\n\u2022 20 \u043c\u0430\u0440\u0442\u0430",
        )
        return

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

    if day_choice in ("today",):
        date_from = today
        date_to = today
    elif day_choice in ("tomorrow",):
        date_from = today + timedelta(days=1)
        date_to = date_from
    elif day_choice in ("this_weekend", "this weekend", "weekend"):
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0:
            days_until_sat = 7
        date_from = today + timedelta(days=days_until_sat)
        date_to = date_from + timedelta(days=1)
    else:
        parsed_date = _parse_flexible_date(day_choice)
        if parsed_date:
            date_from = parsed_date
            date_to = parsed_date
        else:
            await client.send_text(
                user.tg_id,
                "I couldn\u2019t understand that date. Try something like:\n"
                "\u2022 March 15\n\u2022 03/15\n\u2022 next Friday\n\u2022 20 \u043c\u0430\u0440\u0442\u0430",
            )
            return

    payload = session.state_payload_json or {}
    payload["date_from"] = date_from.isoformat()
    payload["date_to"] = date_to.isoformat()

    await client.send_text(user.tg_id, SEARCHING_MSG)
    await update_session_state(db, session, State.SEARCHING, payload)

    # Use shared search + output
    await _do_search_and_output(session, db, client, user, payload)


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

    # Handle rating callbacks (rate_0_1, rate_1_3, etc.)
    if msg.callback_data and msg.callback_data.startswith("rate_"):
        parts = msg.callback_data.split("_")
        if len(parts) == 3:
            event_idx = int(parts[1])
            stars = int(parts[2])
            payload = session.state_payload_json or {}
            results = payload.get("results", [])
            event_title = None
            event_ext_id = "unknown"
            if event_idx < len(results):
                ev = results[event_idx].get("event", {})
                event_title = ev.get("title")
                event_ext_id = ev.get("external_id", str(event_idx))
            await save_event_rating(
                db, user.id, event_ext_id, event_title, stars,
                search_query=payload.get("user_request"),
            )
            star_str = "\u2b50" * stars
            await client.send_text(
                user.tg_id, f"Thanks! You rated *{event_title or 'this event'}* {star_str}"
            )
            return

    button_id = msg.callback_data

    if button_id == "send_pdf" or (text and "pdf" in text.lower()):
        await client.send_text(user.tg_id, "Generating your PDF summary...")
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
            "Tell me what you're looking for \u2014 type a message or send a voice note.",
        )
        await update_session_state(db, session, State.READY)

    elif button_id == "done":
        await client.send_text(user.tg_id, FOLLOW_UP_MSG)
        await update_session_state(db, session, State.FOLLOW_UP)

    else:
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
        payload = session.state_payload_json or {}
        date_from = payload.get("date_from", date.today().isoformat())
        payload["date_from"] = date_from
        payload["date_to"] = (
            date.fromisoformat(date_from) + timedelta(days=14)
        ).isoformat()
        payload["broadened"] = True

        await client.send_text(user.tg_id, SEARCHING_MSG)
        await update_session_state(db, session, State.SEARCHING, payload)

        await _do_search_and_output(session, db, client, user, payload)

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

    await update_session_state(db, session, State.READY)
    await handle_ready(session, msg, text, db, client, user)


# --- Flexible date parsing ---

_RU_MONTHS = {
    "\u044f\u043d\u0432\u0430\u0440\u044f": 1, "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2, "\u043c\u0430\u0440\u0442\u0430": 3, "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
    "\u043c\u0430\u044f": 5, "\u0438\u044e\u043d\u044f": 6, "\u0438\u044e\u043b\u044f": 7, "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
    "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9, "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10, "\u043d\u043e\u044f\u0431\u0440\u044f": 11, "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
    "\u044f\u043d\u0432\u0430\u0440\u044c": 1, "\u0444\u0435\u0432\u0440\u0430\u043b\u044c": 2, "\u043c\u0430\u0440\u0442": 3, "\u0430\u043f\u0440\u0435\u043b\u044c": 4,
    "\u043c\u0430\u0439": 5, "\u0438\u044e\u043d\u044c": 6, "\u0438\u044e\u043b\u044c": 7, "\u0430\u0432\u0433\u0443\u0441\u0442": 8,
    "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044c": 9, "\u043e\u043a\u0442\u044f\u0431\u0440\u044c": 10, "\u043d\u043e\u044f\u0431\u0440\u044c": 11, "\u0434\u0435\u043a\u0430\u0431\u0440\u044c": 12,
}

_RU_RELATIVE = {
    "\u0441\u0435\u0433\u043e\u0434\u043d\u044f": 0, "\u0437\u0430\u0432\u0442\u0440\u0430": 1, "\u043f\u043e\u0441\u043b\u0435\u0437\u0430\u0432\u0442\u0440\u0430": 2,
    "today": 0, "tomorrow": 1,
}

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "\u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a": 0, "\u0432\u0442\u043e\u0440\u043d\u0438\u043a": 1,
    "\u0441\u0440\u0435\u0434\u0430": 2, "\u0441\u0440\u0435\u0434\u0443": 2,
    "\u0447\u0435\u0442\u0432\u0435\u0440\u0433": 3,
    "\u043f\u044f\u0442\u043d\u0438\u0446\u0430": 4, "\u043f\u044f\u0442\u043d\u0438\u0446\u0443": 4,
    "\u0441\u0443\u0431\u0431\u043e\u0442\u0430": 5, "\u0441\u0443\u0431\u0431\u043e\u0442\u0443": 5,
    "\u0432\u043e\u0441\u043a\u0440\u0435\u0441\u0435\u043d\u044c\u0435": 6,
}


def _parse_flexible_date(text: str) -> date | None:
    """Parse a date from free-form text (EN/RU). Returns date or None."""
    import re
    text = text.strip().lower()
    today = date.today()

    # Relative dates
    for word, delta in _RU_RELATIVE.items():
        if word in text:
            return today + timedelta(days=delta)

    # "next <weekday>" in English
    if "next" in text:
        for wd_name, wd_num in _WEEKDAYS.items():
            if wd_name in text:
                days_ahead = (wd_num - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                return today + timedelta(days=days_ahead)

    # Weekday names (EN and RU)
    for wd_name, wd_num in _WEEKDAYS.items():
        if wd_name in text:
            days_ahead = (wd_num - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    # Russian: "15 \u043c\u0430\u0440\u0442\u0430", "20 \u044f\u043d\u0432\u0430\u0440\u044f 2026"
    ru_match = re.search(r"(\d{1,2})\s+([\u0430-\u044f\u0451]+)(?:\s+(\d{4}))?", text)
    if ru_match:
        day_num = int(ru_match.group(1))
        month_name = ru_match.group(2)
        year = int(ru_match.group(3)) if ru_match.group(3) else today.year
        month = _RU_MONTHS.get(month_name)
        if month:
            try:
                d = date(year, month, day_num)
                if d < today:
                    d = date(year + 1, month, day_num)
                return d
            except ValueError:
                pass

    # Try python-dateutil
    try:
        from dateutil import parser as dateutil_parser
        parsed = dateutil_parser.parse(text, dayfirst=False, fuzzy=True)
        d = parsed.date()
        if d < today:
            d = d.replace(year=d.year + 1)
        return d
    except (ValueError, OverflowError):
        pass

    return None


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
