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
