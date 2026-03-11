"""Speech-to-text using OpenAI Whisper API."""

from __future__ import annotations

import logging

from app.llm.client import get_openai_client

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes) -> str | None:
    """Transcribe audio bytes using OpenAI Whisper API.

    Telegram voice notes are OGG/Opus. Whisper accepts .ogg files.
    """
    if not audio_bytes:
        return None

    client = get_openai_client()

    try:
        result = await client.audio.transcriptions.create(
            model="whisper-1",
            file=("voice_note.ogg", audio_bytes, "audio/ogg"),
            language="en",
        )
        transcript = result.text.strip()
        logger.info(f"Transcribed: {transcript[:100]}")
        return transcript
    except Exception:
        logger.exception("Failed to transcribe audio")
        return None


async def transcribe_voice_note(client, file_id: str) -> str | None:
    """Download and transcribe a voice note.

    Accepts any client with a download_media(file_id) method
    (TelegramClient or MockClient).
    """
    try:
        audio_bytes = await client.download_media(file_id)
        if not audio_bytes:
            logger.warning("Empty audio data from media download")
            return None
        return await transcribe_audio(audio_bytes)
    except Exception:
        logger.exception(f"Failed to download/transcribe media {file_id}")
        return None
