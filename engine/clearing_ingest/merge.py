from __future__ import annotations

from datetime import UTC, datetime

from clearing_ingest.filespec import ClearingMessage
from clearing_ingest.refs import RefClient
from clearing_ingest.store import Store


def _usd_cents(amount_cents: int, rate: float) -> int:
    return int(round(amount_cents * rate))


class Merger:
    def __init__(self, store: Store, refs: RefClient) -> None:
        self.store = store
        self.refs = refs

    def merge_messages(
        self,
        *,
        cycle_date: str,
        cycle_no: int,
        endpoint_id: str,
        file_id: str,
        messages: list[ClearingMessage | dict],
        source_kind: str,
    ) -> int:
        inserted = 0
        as_of = cycle_date
        for raw in messages:
            msg = raw if isinstance(raw, ClearingMessage) else ClearingMessage.model_validate(raw)
            rate, fx_as_of = self.refs.fx_to_usd(msg.currency, as_of=as_of)
            bin_row = self.refs.bin(msg.card_bin)
            before = self.store.query(
                """SELECT COUNT(*) AS n FROM clearing_rows
                   WHERE cycle_date=? AND cycle_no=? AND endpoint_id=? AND file_id=? AND message_no=?""",
                (cycle_date, cycle_no, endpoint_id, file_id, msg.message_no),
            )[0]["n"]
            self.store.execute(
                """INSERT OR IGNORE INTO clearing_rows(
                     cycle_date, cycle_no, endpoint_id, file_id, message_no, txn_id,
                     card_bin, amount_cents, currency, usd_cents, merchant_id,
                     bin_product, bin_country, fx_as_of, source_kind
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cycle_date,
                    cycle_no,
                    endpoint_id,
                    file_id,
                    msg.message_no,
                    msg.txn_id,
                    msg.card_bin,
                    msg.amount_cents,
                    msg.currency,
                    _usd_cents(msg.amount_cents, rate),
                    msg.merchant_id,
                    bin_row.get("product"),
                    bin_row.get("country"),
                    fx_as_of,
                    source_kind,
                ),
            )
            after = self.store.query(
                """SELECT COUNT(*) AS n FROM clearing_rows
                   WHERE cycle_date=? AND cycle_no=? AND endpoint_id=? AND file_id=? AND message_no=?""",
                (cycle_date, cycle_no, endpoint_id, file_id, msg.message_no),
            )[0]["n"]
            if before == 0 and after == 1:
                inserted += 1
        now = datetime.now(UTC).isoformat()
        self.store.execute(
            """INSERT INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status, file_id, landed_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(cycle_date, cycle_no, endpoint_id) DO UPDATE SET
                 status='landed', file_id=excluded.file_id, landed_at=excluded.landed_at, reject_reason=NULL""",
            (cycle_date, cycle_no, endpoint_id, "landed", file_id, now),
        )
        return inserted

    def merge_parquet_rows(self, rows: list[dict]) -> int:
        inserted = 0
        grouped: dict[tuple, list[dict]] = {}
        for row in rows:
            key = (row["cycle_date"], int(row["cycle_no"]), row["endpoint_id"], row["file_id"])
            grouped.setdefault(key, []).append(row)
        for (cycle_date, cycle_no, endpoint_id, file_id), items in grouped.items():
            inserted += self.merge_messages(
                cycle_date=cycle_date,
                cycle_no=cycle_no,
                endpoint_id=endpoint_id,
                file_id=file_id,
                messages=items,
                source_kind="parquet_backfill",
            )
        return inserted
