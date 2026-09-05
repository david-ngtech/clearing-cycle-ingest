from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from clearing_ingest.config import LAKE_DIR
from clearing_ingest.generator import build_logical_file, yesterday
from clearing_ingest.catalog import ENDPOINTS


COLUMNS = [
    "cycle_date",
    "cycle_no",
    "endpoint_id",
    "file_id",
    "message_no",
    "txn_id",
    "card_bin",
    "amount_cents",
    "currency",
    "merchant_id",
]


def partition_dir(cycle_date: str, cycle_no: int, lake: Path = LAKE_DIR) -> Path:
    return lake / f"cycle_date={cycle_date}" / f"cycle_no={cycle_no}"


def write_cycle_parquet(cycle_date: str, cycle_no: int, lake: Path = LAKE_DIR) -> Path:
    rows = {col: [] for col in COLUMNS}
    for endpoint in ENDPOINTS:
        logical = build_logical_file(
            cycle_date=cycle_date,
            cycle_no=cycle_no,
            endpoint_id=endpoint.id,
            member_id=endpoint.member_id,
            n_messages=8,
        )
        for msg in logical.messages:
            rows["cycle_date"].append(cycle_date)
            rows["cycle_no"].append(cycle_no)
            rows["endpoint_id"].append(endpoint.id)
            rows["file_id"].append(logical.header.file_id)
            rows["message_no"].append(msg.message_no)
            rows["txn_id"].append(msg.txn_id)
            rows["card_bin"].append(msg.card_bin)
            rows["amount_cents"].append(msg.amount_cents)
            rows["currency"].append(msg.currency)
            rows["merchant_id"].append(msg.merchant_id)
    table = pa.table(rows)
    dest_dir = partition_dir(cycle_date, cycle_no, lake)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "part-000.parquet"
    pq.write_table(table, dest)
    return dest


def seed_yesterday_lake(lake: Path = LAKE_DIR) -> list[Path]:
    day = yesterday()
    return [write_cycle_parquet(day, cycle_no, lake) for cycle_no in (1, 2, 3, 4)]


def read_partitions(lake: Path = LAKE_DIR) -> list[dict]:
    if not lake.exists():
        return []
    rows: list[dict] = []
    for path in sorted(lake.rglob("*.parquet")):
        table = pq.read_table(path)
        rows.extend(table.to_pylist())
    return rows
