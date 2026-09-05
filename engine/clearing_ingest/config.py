from __future__ import annotations

from pathlib import Path

ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 18771

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "ingest.db"
INBOX_DIR = ROOT / "inbox"
LAKE_DIR = ROOT / "lake"
DEADLETTER_DIR = ROOT / "deadletter"

CYCLES_PER_DAY = 4
SEED_CYCLE_DATE_OFFSET_DAYS = 0

# Public GCMS analog: members take at least four clearing cycles per endpoint per day.
CYCLE_NOS = (1, 2, 3, 4)
