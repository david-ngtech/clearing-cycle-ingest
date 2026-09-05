from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from pathlib import Path

from clearing_ingest.catalog import ENDPOINTS, MEMBERS
from clearing_ingest.config import INBOX_DIR
from clearing_ingest.filespec import ClearingMessage, FileHeader, FileTrailer, LogicalFile

CURRENCIES = {"US": "USD", "GB": "GBP", "DE": "EUR"}
BINS = ["541275", "222988", "414720", "526610", "454313", "510875"]


def _file_id(cycle_date: str, cycle_no: int, endpoint_id: str, retransmission: int = 1) -> str:
    base = f"IPM-{cycle_date.replace('-', '')}-C{cycle_no:02d}-{endpoint_id}"
    return f"{base}-R{retransmission}" if retransmission > 1 else base


def build_logical_file(
    *,
    cycle_date: str,
    cycle_no: int,
    endpoint_id: str,
    member_id: str,
    n_messages: int = 12,
    fault: str | None = None,
    retransmission: int = 1,
    rng: random.Random | None = None,
) -> LogicalFile:
    rng = rng or random.Random(f"{cycle_date}-{cycle_no}-{endpoint_id}-{retransmission}")
    member = next(m for m in MEMBERS if m.id == member_id)
    currency = CURRENCIES[member.country]
    file_id = _file_id(cycle_date, cycle_no, endpoint_id, retransmission)
    created = f"{cycle_date}T{cycle_no:02d}:{retransmission:02d}:00+00:00"
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
    retransmission: int = 1,
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
            retransmission=retransmission,
        )
        name = f"{endpoint.id}.ndjson" if retransmission == 1 else f"{endpoint.id}-R{retransmission}.ndjson"
        path = inbox / cycle_date / f"C{cycle_no:02d}" / name
        written.append(write_ndjson(logical, path))
    return written


def today_utc() -> str:
    return date.today().isoformat()


def seed_today_inbox(inbox: Path = INBOX_DIR) -> list[Path]:
    day = today_utc()
    paths: list[Path] = []
    # Cycle 1: complete. Cycle 2: skip one required endpoint (partial).
    # Cycle 3: one poison file. Cycle 4: not dropped yet (open).
    specs: list[tuple[int, set[str], dict[str, str]]] = [
        (1, set(), {}),
        (2, {"E-3310"}, {}),
        (3, set(), {"E-1102": "header_trailer_mismatch"}),
    ]
    for cycle_no, skip, faults in specs:
        dest = inbox / day / f"C{cycle_no:02d}"
        existing = sorted(dest.glob("*.ndjson")) if dest.exists() else []
        if existing:
            paths.extend(existing)
            continue
        paths += drop_cycle_inbox(
            day,
            cycle_no,
            skip_endpoints=skip,
            faults=faults,
            inbox=inbox,
        )
    return paths


def yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()
