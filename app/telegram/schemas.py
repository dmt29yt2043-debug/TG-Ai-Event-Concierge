"""Normalized message representation for the conversation state machine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TelegramMessage:
    """Adapter between aiogram native types and the state machine.

    Collapses WhatsApp's separate text/button_reply/list_reply
    into a unified structure using callback_data for all interactive replies.
    """

    id: str  # str(message_id) or str(callback_query.id)
    from_: str  # str(chat_id) — serves as user identifier
    type: str  # "text", "callback", "audio"
    text_body: str | None = None
    callback_data: str | None = None  # inline keyboard button ID
    callback_text: str | None = None  # inline keyboard button display text
    audio_file_id: str | None = None  # Telegram file_id for voice
    callback_message_id: int | None = None  # message_id of the message with inline keyboard
