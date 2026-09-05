from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from clearing_ingest.closer import CycleCloser
from clearing_ingest.config import CYCLE_NOS
from clearing_ingest.generator import drop_cycle_inbox, seed_today_inbox, today_utc
from clearing_ingest.lander import Lander
from clearing_ingest.merge import Merger
from clearing_ingest.parquet_backfill import read_partitions, seed_yesterday_lake
from clearing_ingest.refs import RefClient
from clearing_ingest.store import Store

Listener = Callable[[dict[str, Any]], None]


class IngestPipeline:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.lander = Lander(store)
        self.closer = CycleCloser(store)
        self.refs = RefClient()
        self.merger = Merger(store, self.refs)
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def _off() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _off

    def _emit(self, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            listener(payload)

    def bootstrap(self) -> dict[str, Any]:
        files = seed_today_inbox()
        parquet_paths = seed_yesterday_lake()
        day = today_utc()
        for n in CYCLE_NOS:
            self.closer.ensure_cycle(day, n)
        yesterday_rows = read_partitions()
        backfilled = self.merger.merge_parquet_rows(yesterday_rows)
        for row in yesterday_rows:
            self.closer.refresh(row["cycle_date"], int(row["cycle_no"]))
        landed = self.run_once()
        return {
            "inbox_files": len(files),
            "parquet_files": len(parquet_paths),
            "backfilled_rows": backfilled,
            "landed": landed,
        }

    def run_once(self) -> list[dict[str, Any]]:
        already_closed = {
            (row["cycle_date"], row["cycle_no"])
            for row in self.store.query("SELECT cycle_date, cycle_no, status FROM cycles")
            if row["status"] in {"closed", "late"}
        }
        results = []
        for result in self.lander.land_all():
            if result["status"] == "accepted":
                header_cycle = (result["cycle_date"], result["cycle_no"])
                was_closed = header_cycle in already_closed
                inserted = self.merger.merge_messages(
                    cycle_date=result["cycle_date"],
                    cycle_no=result["cycle_no"],
                    endpoint_id=result["endpoint_id"],
                    file_id=result["file_id"],
                    messages=result["messages"],
                    source_kind="cycle_file",
                )
                if was_closed:
                    self.closer.mark_late(result["cycle_date"], result["cycle_no"], result["endpoint_id"])
                snap = self.closer.refresh(result["cycle_date"], result["cycle_no"])
                result = {**result, "inserted": inserted, "cycle": snap}
                result.pop("logical", None)
            else:
                result.pop("logical", None)
            results.append(result)
            self._emit({"type": "land", **{k: v for k, v in result.items() if k != "messages"}})
        return results

    def drop_late_file(self, cycle_date: str, cycle_no: int, endpoint_id: str) -> dict[str, Any]:
        from clearing_ingest.catalog import ENDPOINTS

        endpoint = next(e for e in ENDPOINTS if e.id == endpoint_id)
        paths = drop_cycle_inbox(
            cycle_date,
            cycle_no,
            skip_endpoints={e.id for e in ENDPOINTS if e.id != endpoint_id},
        )
        return {"dropped": [str(p) for p in paths], "endpoint_id": endpoint.id}

    def replay_dead_letter(self, dead_id: int) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM dead_letters WHERE id=?", (dead_id,))
        if not rows:
            return {"status": "missing"}
        return {"status": "queued", "path": rows[0]["path"], "reason": rows[0]["reason"]}

    def snapshot(self) -> dict[str, Any]:
        day = today_utc()
        return {
            "as_of": datetime.now(UTC).isoformat(),
            "sources": self.store.sources(),
            "members": self.store.members(),
            "endpoints": self.store.endpoints(),
            "cycles": self.closer.board(day),
            "dead_letters": self.store.query("SELECT * FROM dead_letters ORDER BY id DESC LIMIT 50"),
            "inbox": self.store.query("SELECT * FROM inbox_files ORDER BY id DESC LIMIT 80"),
            "row_count": self.store.query("SELECT COUNT(*) AS n FROM clearing_rows")[0]["n"],
            "today": day,
        }
