"""OpenAI GPT-4o client wrapper with retry logic."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o",
    json_mode: bool = False,
    temperature: float = 0.3,
) -> str:
    """Call OpenAI chat completion with retry."""
    client = get_openai_client()

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    logger.debug(f"LLM response ({model}): {content[:200]}")
    return content


async def chat_completion_json(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o",
    temperature: float = 0.3,
) -> dict:
    """Call OpenAI and parse JSON response."""
    content = await chat_completion(
        system_prompt, user_prompt, model=model, json_mode=True, temperature=temperature
    )
    return json.loads(content)
