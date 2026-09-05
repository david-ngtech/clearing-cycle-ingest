from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from clearing_ingest.catalog import ENDPOINTS, MEMBERS
from clearing_ingest.config import CYCLE_NOS, INBOX_DIR
from clearing_ingest.filespec import ClearingMessage, FileHeader, FileTrailer, LogicalFile

CURRENCIES = {"US": "USD", "GB": "GBP", "DE": "EUR"}
BINS = ["541275", "222988", "414720", "526610", "454313", "510875"]


def _file_id(cycle_date: str, cycle_no: int, endpoint_id: str) -> str:
    return f"IPM-{cycle_date.replace('-', '')}-C{cycle_no:02d}-{endpoint_id}"


def build_logical_file(
    *,
    cycle_date: str,
    cycle_no: int,
    endpoint_id: str,
    member_id: str,
    n_messages: int = 12,
    fault: str | None = None,
    rng: random.Random | None = None,
) -> LogicalFile:
    rng = rng or random.Random(f"{cycle_date}-{cycle_no}-{endpoint_id}")
    member = next(m for m in MEMBERS if m.id == member_id)
    currency = CURRENCIES[member.country]
    file_id = _file_id(cycle_date, cycle_no, endpoint_id)
    created = datetime.now(UTC).isoformat()
    messages: list[ClearingMessage] = []
    for i in range(1, n_messages + 1):
        messages.append(
            ClearingMessage(
                message_no=i,
                txn_id=str(uuid.UUID(int=rng.getrandbits(128))),
                card_bin=rng.choice(BINS),
                amount_cents=rng.randint(250, 18_000),
                currency=currency,
                merchant_id=f"MER-{rng.randint(1000, 9999)}",
                auth_code=f"{rng.randint(100000, 999999)}",
            )
        )
    header = FileHeader(
        file_id=file_id,
        cycle_date=cycle_date,
        cycle_no=cycle_no,
        endpoint_id=endpoint_id,
        member_id=member_id,
        created_at=created,
    )
    trailer = FileTrailer(
        file_id=file_id,
        message_count=len(messages),
        hash_amount_cents=sum(m.amount_cents for m in messages),
    )
    if fault == "header_trailer_mismatch":
        trailer.file_id = file_id + "-X"
    elif fault == "count_mismatch":
        trailer.message_count = len(messages) + 3
    elif fault == "gap_de71":
        messages[2].message_no = 9
    return LogicalFile(header=header, messages=messages, trailer=trailer)


def write_ndjson(logical: LogicalFile, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        logical.header.model_dump_json(),
        *[m.model_dump_json() for m in logical.messages],
        logical.trailer.model_dump_json(),
    ]
    dest.write_text("\n".join(lines) + "\n")
    return dest


def drop_cycle_inbox(
    cycle_date: str,
    cycle_no: int,
    *,
    skip_endpoints: set[str] | None = None,
    faults: dict[str, str] | None = None,
    inbox: Path = INBOX_DIR,
) -> list[Path]:
    skip_endpoints = skip_endpoints or set()
    faults = faults or {}
    written: list[Path] = []
    for endpoint in ENDPOINTS:
        if endpoint.id in skip_endpoints:
            continue
        logical = build_logical_file(
            cycle_date=cycle_date,
            cycle_no=cycle_no,
            endpoint_id=endpoint.id,
            member_id=endpoint.member_id,
            fault=faults.get(endpoint.id),
        )
        path = inbox / cycle_date / f"C{cycle_no:02d}" / f"{endpoint.id}.ndjson"
        written.append(write_ndjson(logical, path))
    return written


def today_utc() -> str:
    return date.today().isoformat()


def seed_today_inbox() -> list[Path]:
    day = today_utc()
    paths: list[Path] = []
    # Cycle 1: complete. Cycle 2: skip one required endpoint (partial).
    # Cycle 3: one poison file. Cycle 4: not dropped yet (open).
    paths += drop_cycle_inbox(day, 1)
    paths += drop_cycle_inbox(day, 2, skip_endpoints={"E-3310"})
    paths += drop_cycle_inbox(day, 3, faults={"E-1102": "header_trailer_mismatch"})
    return paths


def yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()
