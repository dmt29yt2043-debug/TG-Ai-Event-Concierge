"""Telegram client wrapping aiogram Bot — matches WhatsAppClient interface."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions

logger = logging.getLogger(__name__)

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096


class TelegramClient:
    """Wraps aiogram.Bot with the same method signatures as WhatsAppClient."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(self, to: str, text: str, parse_mode: str | None = "Markdown") -> dict:
        """Send a text message, splitting if over 4096 chars."""
        chat_id = int(to)
        chunks = _split_text(text)
        last_msg = None
        for chunk in chunks:
            try:
                last_msg = await self._bot.send_message(chat_id, chunk, parse_mode=parse_mode, link_preview_options=LinkPreviewOptions(is_disabled=True))
            except TelegramBadRequest as e:
                logger.warning(f"Markdown parse failed for send_text, falling back: {e}")
                last_msg = await self._bot.send_message(chat_id, chunk)
        return {"message_id": last_msg.message_id if last_msg else None}

    async def send_interactive_buttons(
        self, to: str, body_text: str, buttons: list[dict]
    ) -> dict:
        """Send text with inline keyboard buttons.

        buttons format: [{"id": "xxx", "title": "Label"}, ...]
        """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=b["title"], callback_data=b["id"])]
                for b in buttons
            ]
        )
        chat_id = int(to)
        try:
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard, parse_mode="Markdown")
        except TelegramBadRequest as e:
            logger.warning(f"Markdown parse failed for buttons, falling back: {e}")
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard)
        return {"message_id": msg.message_id}

    async def send_interactive_list(
        self, to: str, body_text: str, button_text: str, sections: list[dict]
    ) -> dict:
        """Send text with inline keyboard (Telegram has no native list widget).

        Flattens WhatsApp-style sections into rows of inline buttons.
        """
        rows = []
        for section in sections:
            for row in section.get("rows", []):
                rows.append(
                    [InlineKeyboardButton(text=row["title"], callback_data=row["id"])]
                )
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        chat_id = int(to)
        try:
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard, parse_mode="Markdown")
        except TelegramBadRequest as e:
            logger.warning(f"Markdown parse failed for list, falling back: {e}")
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard)
        return {"message_id": msg.message_id}

    async def send_document(
        self, to: str, document_path: str, caption: str, filename: str
    ) -> dict:
        """Send a document from local file path."""
        chat_id = int(to)
        file_bytes = Path(document_path).read_bytes()
        doc = BufferedInputFile(file_bytes, filename=filename)
        msg = await self._bot.send_document(chat_id, doc, caption=caption)
        return {"message_id": msg.message_id}

    async def send_image(
        self, to: str, image_url: str, caption: str | None = None
    ) -> dict:
        """Send an image by URL."""
        chat_id = int(to)
        try:
            msg = await self._bot.send_photo(chat_id, image_url, caption=caption, parse_mode="Markdown" if caption else None)
        except TelegramBadRequest as e:
            logger.warning(f"Markdown parse failed for image caption, falling back: {e}")
            msg = await self._bot.send_photo(chat_id, image_url, caption=caption)
        return {"message_id": msg.message_id}

    async def download_media(self, file_id: str) -> bytes:
        """Download a file from Telegram by file_id."""
        file = await self._bot.get_file(file_id)
        buf = io.BytesIO()
        await self._bot.download_file(file.file_path, buf)
        return buf.getvalue()


    async def send_inline_row(
        self, to: str, body_text: str, buttons: list[dict]
    ) -> dict:
        """Send text with buttons in a single horizontal row."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=b["title"], callback_data=b["id"]) for b in buttons]
            ]
        )
        chat_id = int(to)
        try:
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard, parse_mode="Markdown")
        except TelegramBadRequest as e:
            logger.warning(f"Markdown parse failed for inline_row, falling back: {e}")
            msg = await self._bot.send_message(chat_id, body_text, reply_markup=keyboard)
        return {"message_id": msg.message_id}


    async def edit_inline_buttons(
        self, chat_id: str, message_id: int, buttons: list[dict]
    ) -> None:
        """Edit the inline keyboard of an existing message.

        buttons format: [{"id": "xxx", "title": "Label"}, ...]
        Each button gets its own row.
        """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=b["title"], callback_data=b["id"])]
                for b in buttons
            ]
        )
        try:
            await self._bot.edit_message_reply_markup(
                chat_id=int(chat_id),
                message_id=message_id,
                reply_markup=keyboard,
            )
        except TelegramBadRequest as e:
            logger.warning(f"Failed to edit inline buttons: {e}")

    async def mark_read(self, message_id: str) -> None:
        """No-op for Telegram (no read receipts API)."""


def _split_text(text: str) -> list[str]:
    """Split text into chunks that fit Telegram's 4096-char limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break
        # Try to split at last newline within limit
        split_at = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
