from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from clearing_ingest.catalog import ENDPOINTS
from clearing_ingest.closer import CycleCloser
from clearing_ingest.config import CYCLE_NOS, DEADLETTER_DIR, INBOX_DIR, LAKE_DIR
from clearing_ingest.generator import drop_cycle_inbox, seed_today_inbox, today_utc, yesterday
from clearing_ingest.lander import Lander
from clearing_ingest.merge import Merger
from clearing_ingest.parquet_backfill import read_partitions, seed_yesterday_lake
from clearing_ingest.refs import BIN_TABLE, RefClient
from clearing_ingest.store import Store

Listener = Callable[[dict[str, Any]], None]


class IngestPipeline:
    def __init__(
        self,
        store: Store,
        *,
        inbox: Path = INBOX_DIR,
        lake: Path = LAKE_DIR,
        dead: Path = DEADLETTER_DIR,
    ) -> None:
        self.store = store
        self.inbox = inbox
        self.lake = lake
        self.lander = Lander(store, inbox=inbox, dead=dead)
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
        files = seed_today_inbox(self.inbox)
        parquet_paths = seed_yesterday_lake(self.lake)
        day = today_utc()
        for n in CYCLE_NOS:
            self.closer.ensure_cycle(day, n)
        already = self.store.query("SELECT COUNT(*) AS n FROM clearing_rows")[0]["n"]
        if already == 0:
            yesterday_rows = read_partitions(self.lake, cycle_date=yesterday())
            backfilled = self.merger.merge_parquet_rows(yesterday_rows)
            seen: set[tuple[str, int]] = set()
            for row in yesterday_rows:
                key = (row["cycle_date"], int(row["cycle_no"]))
                if key not in seen:
                    self.closer.refresh(*key)
                    seen.add(key)
        else:
            backfilled = 0
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
        endpoint = next(e for e in ENDPOINTS if e.id == endpoint_id)
        existing = self.store.query(
            """SELECT COUNT(*) AS n FROM inbox_files
               WHERE cycle_date=? AND cycle_no=? AND endpoint_id=?""",
            (cycle_date, cycle_no, endpoint_id),
        )[0]["n"]
        paths = drop_cycle_inbox(
            cycle_date,
            cycle_no,
            skip_endpoints={e.id for e in ENDPOINTS if e.id != endpoint_id},
            retransmission=max(2, existing + 1),
            inbox=self.inbox,
        )
        return {"dropped": [str(p) for p in paths], "endpoint_id": endpoint.id}

    def replay_dead_letter(self, dead_id: int) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM dead_letters WHERE id=?", (dead_id,))
        if not rows:
            return {"status": "missing"}
        row = rows[0]
        cycle_date = row["cycle_date"]
        cycle_no = row["cycle_no"]
        endpoint_id = row["endpoint_id"]
        if not cycle_date or cycle_no is None or not endpoint_id:
            return {"status": "unreplayable", "reason": row["reason"], "path": row["path"]}
        paths = drop_cycle_inbox(
            cycle_date,
            int(cycle_no),
            skip_endpoints={e.id for e in ENDPOINTS if e.id != endpoint_id},
            inbox=self.inbox,
        )
        self.store.execute(
            "UPDATE dead_letters SET replayed_at=? WHERE id=?",
            (datetime.now(UTC).isoformat(), dead_id),
        )
        results = self.run_once()
        return {"status": "replayed", "path": str(paths[0]) if paths else row["path"], "results": results}

    def _source_stats(self) -> list[dict[str, Any]]:
        counts = {r["status"]: r["n"] for r in self.store.query("SELECT status, COUNT(*) AS n FROM inbox_files GROUP BY status")}
        accepted = int(counts.get("accepted", 0))
        rejected = int(counts.get("rejected", 0))
        total = accepted + rejected
        byte_row = self.store.query("SELECT COALESCE(SUM(bytes), 0) AS n FROM inbox_files")[0]
        last = self.store.query(
            """SELECT cycle_date, cycle_no FROM inbox_files
               WHERE status='accepted' AND cycle_date IS NOT NULL
               ORDER BY cycle_date DESC, cycle_no DESC LIMIT 1"""
        )
        pq = self.store.query(
            "SELECT MAX(cycle_date) AS d FROM clearing_rows WHERE source_kind='parquet_backfill'"
        )
        stats: dict[str, dict[str, Any]] = {
            "cycle_file": {
                "watermark": f"{last[0]['cycle_date']} C{last[0]['cycle_no']}" if last else None,
                "accepted": accepted,
                "rejected": rejected,
                "bytes": int(byte_row["n"]),
                "reject_rate": (rejected / total) if total else 0.0,
            },
            "fx_api": {"watermark": today_utc(), "accepted": 1, "rejected": 0, "bytes": 0, "reject_rate": 0.0},
            "bin_api": {
                "watermark": f"{len(BIN_TABLE)} ranges",
                "accepted": len(BIN_TABLE),
                "rejected": 0,
                "bytes": 0,
                "reject_rate": 0.0,
            },
            "member_db": {
                "watermark": f"{len(self.store.members())} members",
                "accepted": len(self.store.endpoints()),
                "rejected": 0,
                "bytes": 0,
                "reject_rate": 0.0,
            },
            "parquet_backfill": {
                "watermark": pq[0]["d"],
                "accepted": self.store.query(
                    "SELECT COUNT(*) AS n FROM clearing_rows WHERE source_kind='parquet_backfill'"
                )[0]["n"],
                "rejected": 0,
                "bytes": 0,
                "reject_rate": 0.0,
            },
        }
        return [{**source, **stats.get(source["kind"], {})} for source in self.store.sources()]

    def snapshot(self) -> dict[str, Any]:
        day = today_utc()
        inbox_stats = self.store.query(
            """SELECT
                 COUNT(*) AS files,
                 COALESCE(SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END), 0) AS rejected,
                 COALESCE(SUM(bytes), 0) AS bytes
               FROM inbox_files"""
        )[0]
        return {
            "as_of": datetime.now(UTC).isoformat(),
            "sources": self._source_stats(),
            "members": self.store.members(),
            "endpoints": self.store.endpoints(),
            "cycles": self.closer.board(day),
            "dead_letters": self.store.query("SELECT * FROM dead_letters ORDER BY id DESC LIMIT 50"),
            "inbox": self.store.query("SELECT * FROM inbox_files ORDER BY id DESC LIMIT 80"),
            "row_count": self.store.query("SELECT COUNT(*) AS n FROM clearing_rows")[0]["n"],
            "today": day,
            "inbox_files": inbox_stats["files"],
            "reject_count": inbox_stats["rejected"],
            "bytes_landed": inbox_stats["bytes"],
        }
