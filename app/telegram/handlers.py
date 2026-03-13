"""Aiogram message handlers — entry point replacing WhatsApp webhook routes."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery
from aiogram.types import Message as AiogramMessage

from app.db.engine import async_session
from app.db.queries import (
    create_session,
    get_active_session,
    get_or_create_user,
    save_message,
)
from app.telegram.client import TelegramClient
from app.telegram.schemas import TelegramMessage
from app.utils.dedup import is_duplicate

logger = logging.getLogger(__name__)

router = Router()

# Module-level client reference, set during startup
_tg_client: TelegramClient | None = None


def set_client(client: TelegramClient) -> None:
    global _tg_client
    _tg_client = client


@router.message(CommandStart())
async def on_start_command(message: AiogramMessage) -> None:
    """Handle /start command — treated as 'start' text to trigger WELCOME."""
    tg_msg = TelegramMessage(
        id=str(message.message_id),
        from_=str(message.chat.id),
        type="text",
        text_body="start",
    )
    await _process(tg_msg)


@router.message(F.text)
async def on_text_message(message: AiogramMessage) -> None:
    tg_msg = TelegramMessage(
        id=str(message.message_id),
        from_=str(message.chat.id),
        type="text",
        text_body=message.text,
    )
    await _process(tg_msg)


@router.message(F.voice)
async def on_voice_message(message: AiogramMessage) -> None:
    tg_msg = TelegramMessage(
        id=str(message.message_id),
        from_=str(message.chat.id),
        type="audio",
        audio_file_id=message.voice.file_id,
    )
    await _process(tg_msg)


@router.callback_query()
async def on_callback(callback: CallbackQuery) -> None:
    await callback.answer()  # Remove loading indicator
    tg_msg = TelegramMessage(
        id=str(callback.id),
        from_=str(callback.message.chat.id),
        type="callback",
        callback_data=callback.data,
        callback_text=callback.data,
        callback_message_id=callback.message.message_id,
    )
    await _process(tg_msg)


async def _process(tg_msg: TelegramMessage) -> None:
    """Process a normalized message through the state machine."""
    if is_duplicate(tg_msg.id):
        logger.debug(f"Duplicate message {tg_msg.id}, skipping")
        return

    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, tg_msg.from_)

            # Extract text content
            text = tg_msg.text_body or tg_msg.callback_data

            await save_message(
                db,
                user_id=user.id,
                direction="inbound",
                message_type=tg_msg.type,
                body=text,
                tg_message_id=tg_msg.id,
                media_url=tg_msg.audio_file_id,
            )

            session = await get_active_session(db, user.id)
            if session is None:
                session = await create_session(db, user.id)

            from app.conversation.state_machine import dispatch

            await dispatch(
                session=session,
                msg=tg_msg,
                text=text,
                db=db,
                client=_tg_client,
                user=user,
            )
