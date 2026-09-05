from __future__ import annotations

from datetime import UTC, datetime

from clearing_ingest.config import CYCLE_NOS
from clearing_ingest.store import Store

# open → partial → closed; a file after closed becomes late.
STATUSES = ("open", "partial", "closed", "late")


class CycleCloser:
    def __init__(self, store: Store) -> None:
        self.store = store

    def ensure_cycle(self, cycle_date: str, cycle_no: int) -> None:
        self.store.execute(
            """INSERT OR IGNORE INTO cycles(cycle_date, cycle_no, status, opened_at)
               VALUES(?,?,?,?)""",
            (cycle_date, cycle_no, "open", datetime.now(UTC).isoformat()),
        )
        for endpoint_id in self.store.required_endpoint_ids():
            self.store.execute(
                """INSERT OR IGNORE INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status)
                   VALUES(?,?,?,?)""",
                (cycle_date, cycle_no, endpoint_id, "missing"),
            )

    def refresh(self, cycle_date: str, cycle_no: int) -> dict:
        self.ensure_cycle(cycle_date, cycle_no)
        required = set(self.store.required_endpoint_ids())
        rows = self.store.query(
            """SELECT endpoint_id, status, file_id FROM cycle_endpoints
               WHERE cycle_date=? AND cycle_no=?""",
            (cycle_date, cycle_no),
        )
        landed = {r["endpoint_id"] for r in rows if r["status"] in {"landed", "late"}}
        missing = sorted(required - landed)
        prior = self.store.query(
            "SELECT status FROM cycles WHERE cycle_date=? AND cycle_no=?",
            (cycle_date, cycle_no),
        )
        prior_status = prior[0]["status"] if prior else "open"

        if not landed:
            status = "open"
        elif missing:
            status = "partial"
        elif prior_status in {"closed", "late"}:
            status = "late" if prior_status == "late" else "closed"
        else:
            status = "closed"

        closed_at = datetime.now(UTC).isoformat() if status in {"closed", "late"} else None
        if status == "closed" and prior_status != "closed":
            self.store.execute(
                "UPDATE cycles SET status=?, closed_at=? WHERE cycle_date=? AND cycle_no=?",
                (status, closed_at, cycle_date, cycle_no),
            )
        else:
            self.store.execute(
                "UPDATE cycles SET status=? WHERE cycle_date=? AND cycle_no=?",
                (status, cycle_date, cycle_no),
            )
        by_id = {r["endpoint_id"]: r for r in rows}
        endpoints = []
        for ep in self.store.endpoints():
            row = by_id.get(ep["id"])
            endpoints.append(
                {
                    "id": ep["id"],
                    "required": bool(ep["required"]),
                    "status": row["status"] if row else "missing",
                    "file_id": row["file_id"] if row else None,
                }
            )
        return {
            "cycle_date": cycle_date,
            "cycle_no": cycle_no,
            "status": status,
            "required": sorted(required),
            "landed": sorted(landed),
            "missing": missing,
            "endpoints": endpoints,
        }

    def mark_late(self, cycle_date: str, cycle_no: int, endpoint_id: str) -> None:
        current = self.store.query(
            "SELECT status FROM cycles WHERE cycle_date=? AND cycle_no=?",
            (cycle_date, cycle_no),
        )
        if current and current[0]["status"] in {"closed", "late"}:
            self.store.execute(
                """UPDATE cycle_endpoints SET status='late'
                   WHERE cycle_date=? AND cycle_no=? AND endpoint_id=?""",
                (cycle_date, cycle_no, endpoint_id),
            )
            self.store.execute(
                "UPDATE cycles SET status='late' WHERE cycle_date=? AND cycle_no=?",
                (cycle_date, cycle_no),
            )

    def board(self, cycle_date: str) -> list[dict]:
        return [self.refresh(cycle_date, n) for n in CYCLE_NOS]
