#!/usr/bin/env python3
"""Backfill historical high-signal events into the memory index.

Usage:
    python backfill.py [--dry-run]

Reads events from stdin (one JSON object per line) and processes them
through the full cold-path pipeline (redact → decide → embed → upsert).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

from dotenv import load_dotenv

load_dotenv()

from memory.ingestion.event_hubs_consumer import process_event


async def backfill(dry_run: bool = False) -> None:
    print("Reading events from stdin (one JSON per line)...")
    stored = 0
    skipped = 0
    errors = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            if dry_run:
                data = json.loads(line)
                print(f"  [dry-run] Would process event: {data.get('id', 'unknown')}")
                continue
            result = await process_event(line)
            status = result.get("status", "error")
            if status == "stored":
                stored += 1
            elif status == "skipped":
                skipped += 1
            else:
                errors += 1
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1

    print(f"\nBackfill complete: stored={stored} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    dr = "--dry-run" in sys.argv
    asyncio.run(backfill(dry_run=dr))
