"""PulseUP Telegram Assistant — FastAPI + aiogram in a single process."""

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.engine import engine
from app.db.models import Base
from app.telegram.client import TelegramClient
from app.telegram.handlers import router as tg_router, set_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize aiogram bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(tg_router)

    # Create and register TelegramClient wrapper
    tg_client = TelegramClient(bot)
    set_client(tg_client)

    # Start polling in background task
    polling_task = asyncio.create_task(dp.start_polling(bot))

    yield

    # Cleanup
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    await engine.dispose()


logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseUP Telegram Assistant", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}
