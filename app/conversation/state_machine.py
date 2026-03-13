"""Conversation state machine — dispatches incoming messages to handlers."""

from __future__ import annotations

import logging
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session, User
from app.telegram.client import TelegramClient
from app.telegram.schemas import TelegramMessage

logger = logging.getLogger(__name__)


class State(str, Enum):
    WELCOME = "WELCOME"
    Q1_CHILDREN = "Q1_CHILDREN"
    Q2_INTERESTS = "Q2_INTERESTS"
    Q3_NEIGHBORHOODS = "Q3_NEIGHBORHOODS"
    Q4_BUDGET = "Q4_BUDGET"
    Q5_PREFERENCES = "Q5_PREFERENCES"
    READY = "READY"
    TRANSCRIBING = "TRANSCRIBING"
    ASK_DAY = "ASK_DAY"
    SEARCHING = "SEARCHING"
    OUTPUT = "OUTPUT"
    NO_RESULTS = "NO_RESULTS"
    FOLLOW_UP = "FOLLOW_UP"


async def dispatch(
    session: Session,
    msg: TelegramMessage,
    text: str | None,
    db: AsyncSession,
    client: TelegramClient,
    user: User,
) -> None:
    """Dispatch an incoming message to the appropriate state handler."""
    from app.conversation.handlers import HANDLERS

    state = session.state
    handler = HANDLERS.get(state)

    if handler is None:
        logger.error(f"No handler for state {state}, resetting to WELCOME")
        state = State.WELCOME
        handler = HANDLERS[state]

    logger.info(f"Dispatching: user={user.tg_id} state={state} msg_type={msg.type}")

    # ---- Universal voice transcription ----
    # If the message is a voice note, transcribe it before passing to handler.
    # Skip for states that already handle transcription internally (READY, ASK_DAY, Q5)
    # or if state is TRANSCRIBING (avoid loops).
    _SKIP_AUTO_TRANSCRIBE = {
        State.TRANSCRIBING,
        State.READY,
        State.ASK_DAY,
        State.Q5_PREFERENCES,
    }
    if (
        msg.type == "audio"
        and msg.audio_file_id
        and state not in _SKIP_AUTO_TRANSCRIBE
        and text is None
    ):
        from app.stt.transcribe import transcribe_voice_note

        await client.send_text(user.tg_id, "\U0001f399\ufe0f Transcribing your voice note...")
        try:
            transcript = await transcribe_voice_note(client, msg.audio_file_id)
        except Exception:
            logger.exception("Voice transcription failed")
            transcript = None

        if transcript:
            text = transcript
            await client.send_text(user.tg_id, f'I heard: "{transcript}"')
            logger.info(f"Auto-transcribed voice to: {transcript[:80]}")
        else:
            await client.send_text(
                user.tg_id,
                "Sorry, I couldn\u2019t understand that voice note. Could you try typing instead?",
            )
            return

    try:
        await handler(
            session=session,
            msg=msg,
            text=text,
            db=db,
            client=client,
            user=user,
        )
    except Exception:
        logger.exception(f"Error in handler for state {state}")
        await client.send_text(
            user.tg_id,
            "Sorry, something went wrong. Please try again or send 'start' to restart.",
        )
