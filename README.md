# PulseUP Telegram Bot

AI-powered event concierge for NYC parents. Recommends kids activities based on family profile, interests, location, and budget.

## Features

- **Conversational onboarding** — per-child profiling with age, gender detection, and interest selection
- **Voice notes** — Whisper-based transcription at any conversation stage
- **Smart event search** — filters by date, area (Manhattan neighborhoods, boroughs), budget, and age fit
- **LLM-powered ranking** — GPT ranks and explains why each event matches the family
- **Parent tips (derisk)** — practical info: verdict, tips, best-for, ticket availability
- **PDF export** — styled recommendation cards as downloadable PDF
- **Telegram-native UX** — inline keyboards, multi-select toggles, image cards, clickable ticket links

## Tech Stack

- **Python 3.12**, aiogram 3.x (polling mode)
- **SQLAlchemy 2.0** async ORM + SQLite (aiosqlite)
- **OpenAI API** — GPT-4o-mini for intent parsing, child extraction, ranking; Whisper for STT
- **WeasyPrint** + Jinja2 for PDF generation
- **Docker Compose** on VPS

## Project Structure

```
app/
├── main.py                  # FastAPI + aiogram startup
├── config.py                # Pydantic settings (.env)
├── conversation/
│   ├── state_machine.py     # Dispatcher: state routing, universal voice transcription
│   ├── handlers.py          # State handlers: onboarding (Q1-Q5), search, rating
│   └── prompts.py           # System prompts for LLM calls
├── db/
│   ├── models.py            # SQLAlchemy models: UserProfile, Event, SessionState, EventRating
│   ├── queries.py           # DB queries: get/create profile, reset, save ratings
│   └── engine.py            # Async engine & session factory
├── events/
│   ├── importer.py          # CSV → DB event import with derisk JSON parsing
│   ├── filters.py           # Area/budget/date/age filtering with NYC aliases
│   └── search.py            # Orchestrates filter → LLM rank pipeline
├── llm/
│   ├── client.py            # chat_completion_json() — reusable structured LLM wrapper
│   ├── intent.py            # User intent & date extraction
│   ├── ranking.py           # LLM event ranking with per-child context
│   └── copywriting.py       # Event card formatting with derisk & ticket links
├── telegram/
│   ├── client.py            # Telegram send_text/send_photo with LinkPreviewOptions
│   ├── handlers.py          # aiogram router: messages, callbacks, commands
│   └── schemas.py           # Internal message/callback schemas
├── stt/
│   └── transcribe.py        # Whisper voice-to-text via OpenAI API
├── pdf/
│   └── generator.py         # WeasyPrint PDF generation from ranked events
└── utils/
    ├── dedup.py             # Event deduplication
    └── logging.py           # Logging setup
```

## Setup

```bash
cp .env.example .env
# Fill in: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY

docker compose up --build -d
```

## Event Data

Import events from CSV:

```bash
docker compose exec app python -c "
import asyncio
from app.db.engine import async_session
from app.events.importer import import_csv

async def run():
    async with async_session() as db:
        stats = await import_csv(db, '/app/event_ingest.csv')
        print(stats)

asyncio.run(run())
"
```

## Environment Variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `OPENAI_API_KEY` | OpenAI API key (GPT + Whisper) |
| `DATABASE_URL` | SQLite path (default: `sqlite+aiosqlite:///data/pulseup.db`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
