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

## Onboarding Flow

The bot walks parents through a 5-step onboarding to build a family profile, then uses it to personalize event recommendations.

### State Machine

```
WELCOME → Q1 → Q2 → Q3 → Q4 → Q5 → READY → SEARCHING → OUTPUT → FOLLOW_UP
                                                 ↘ NO_RESULTS (broaden / new search)
```

### Q1 — Children (`Q1_CHILDREN`)

User describes their kids in free text or voice: *"a 6-year-old daughter and a 3-year-old son"*

- LLM extracts structured data: `{age, gender, name}` per child
- Gender inferred from keywords: daughter/son/girl/boy (EN + RU)
- Saved to `profile.children_json`

### Q2 — Interests (`Q2_INTERESTS`)

**Single child** — one set of multi-select buttons (Active, Creative, Educational, Shows & Performances, Outdoor/Nature, Fun & Play, Adventure, Books & Storytime, Social/Playdates).

**Multiple children** — per-child flow:
1. Asks interests for each child separately: *"What does your 6-year-old enjoy?"*
2. After all children done, shows summary with gender icons:
   ```
   👧 6yo → ⚽ Active, 🎭 Shows
   👦 3yo → 🎮 Fun Play
   ```
3. In summary phase, user can send text/voice to add notes (*"my daughter loves dancing"*)
4. `_enrich_children_from_notes()` uses LLM to distribute notes to specific children as short tags
5. Done button saves per-child interests + notes to profile

Multi-select pattern: clicking a button toggles a checkmark, inline keyboard updates in-place via `edit_inline_buttons`.

### Q3 — Neighborhoods (`Q3_NEIGHBORHOODS`)

Multi-select inline buttons: Upper Manhattan, Midtown, Lower Manhattan, Brooklyn, Queens, Bronx, Staten Island, Anywhere in NYC.

Area filter maps selections to districts and handles `city="New York"` as Manhattan via `NYC_CITY_ALIASES` (so events with city="New York" appear when any Manhattan neighborhood is selected).

### Q4 — Budget (`Q4_BUDGET`)

Single-select: Free only, Under $25, Under $50, Under $75, Under $100, Any budget. Saved as `budget_preference`.

### Q5 — Special Preferences (`Q5_PREFERENCES`)

Free text or voice for allergies, accessibility needs, indoor/outdoor preference. Skip button available. Saved as `special_needs_notes`.

### After Onboarding

**READY** — user sends a natural language query: *"Something fun this Saturday in Midtown"*
- LLM extracts intent: date range, activity type, location hints
- If date ambiguous → `ASK_DAY` state with quick-pick buttons

**SEARCHING** — filters events from DB by date, area, budget, age range, then LLM ranks top 5 by relevance to family profile (using `_format_children_for_llm()` for human-readable child context)

**OUTPUT** — renders event cards with:
- Image + title + personalized AI reason
- Date, duration, age fit, price, location, transit info
- "What to expect" highlights
- "Parent tips" derisk section (verdict, practical tips, who it's best for, tickets availability)
- Clickable `🎟 Tickets` link (URL hidden, no preview via `LinkPreviewOptions`)
- 1-5 star rating buttons per event

**NO_RESULTS** — offers to broaden search (relax date/area) or start new

**FOLLOW_UP** — Send as PDF, More options, That's all

### Universal Voice Transcription

Voice notes are transcribed at the dispatcher level (in `dispatch()`) before reaching any handler. This means voice input works at every step, not just Q5/READY. States that handle voice internally are skipped via `_SKIP_AUTO_TRANSCRIBE` to avoid double-processing.

### Profile Reset

Sending `restart` or `/start` calls `reset_profile()` — wipes children, interests, neighborhoods, budget, notes, and `onboarding_complete` flag. Clean slate for re-onboarding.

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
