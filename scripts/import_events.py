#!/usr/bin/env python3
"""CLI script to import events from CSV into the database."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.engine import async_session, engine
from app.db.models import Base
from app.events.importer import import_csv


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_events.py <csv_file> [source_name]")
        print("Example: python scripts/import_events.py data/events.csv event_ingest")
        sys.exit(1)

    csv_path = sys.argv[1]
    source_name = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(csv_path).exists():
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run import
    async with async_session() as db:
        async with db.begin():
            stats = await import_csv(db, csv_path, source_name)

    print(f"\nImport complete:")
    print(f"  Created:     {stats['created']}")
    print(f"  Updated:     {stats['updated']}")
    print(f"  Deactivated: {stats['deactivated']}")
    print(f"  Errors:      {stats['errors']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
