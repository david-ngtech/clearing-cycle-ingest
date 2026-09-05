from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from clearing_ingest.config import DEADLETTER_DIR, INBOX_DIR
from clearing_ingest.store import Store
from clearing_ingest.validate import ContractError, parse_ndjson, validate_logical


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class Lander:
    def __init__(self, store: Store, inbox: Path = INBOX_DIR, dead: Path = DEADLETTER_DIR) -> None:
        self.store = store
        self.inbox = inbox
        self.dead = dead
        self.dead.mkdir(parents=True, exist_ok=True)

    def pending_paths(self) -> list[Path]:
        if not self.inbox.exists():
            return []
        return sorted(self.inbox.rglob("*.ndjson"))

    def _dead_dest(self, path: Path) -> Path:
        try:
            rel = path.relative_to(self.inbox)
        except ValueError:
            rel = Path(path.name)
        dest = self.dead / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def land_one(self, path: Path) -> dict:
        checksum = sha256_file(path)
        size = path.stat().st_size
        already = self.store.query("SELECT status, file_id FROM inbox_files WHERE sha256=?", (checksum,))
        if already:
            return {
                "status": "duplicate",
                "path": str(path),
                "prior": already[0]["status"],
                "file_id": already[0]["file_id"],
            }
        now = datetime.now(UTC).isoformat()
        logical = None
        try:
            logical = parse_ndjson(path)
            accepted = self.store.query(
                "SELECT status FROM inbox_files WHERE file_id=? AND status='accepted'",
                (logical.header.file_id,),
            )
            if accepted:
                return {
                    "status": "duplicate",
                    "path": str(path),
                    "prior": "accepted",
                    "file_id": logical.header.file_id,
                    "cycle_date": logical.header.cycle_date,
                    "cycle_no": logical.header.cycle_no,
                    "endpoint_id": logical.header.endpoint_id,
                }
            validate_logical(logical)
        except ContractError as exc:
            dest = self._dead_dest(path)
            shutil.copy2(path, dest)
            header = logical.header if logical is not None else None
            self.store.insert_dead_letter(
                str(dest),
                exc.reason,
                exc.evidence,
                now,
                cycle_date=header.cycle_date if header else None,
                cycle_no=header.cycle_no if header else None,
                endpoint_id=header.endpoint_id if header else None,
                file_id=header.file_id if header else None,
            )
            self.store.execute(
                """INSERT INTO inbox_files(path, sha256, status, reason, file_id, cycle_date, cycle_no, endpoint_id, bytes)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(path),
                    checksum,
                    "rejected",
                    exc.reason,
                    header.file_id if header else None,
                    header.cycle_date if header else None,
                    header.cycle_no if header else None,
                    header.endpoint_id if header else None,
                    size,
                ),
            )
            return {
                "status": "rejected",
                "path": str(path),
                "reason": exc.reason,
                "evidence": exc.evidence,
                "cycle_date": header.cycle_date if header else None,
                "cycle_no": header.cycle_no if header else None,
                "endpoint_id": header.endpoint_id if header else None,
            }

        header = logical.header
        self.store.execute(
            """INSERT INTO inbox_files(path, sha256, status, file_id, cycle_date, cycle_no, endpoint_id, bytes)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                str(path),
                checksum,
                "accepted",
                header.file_id,
                header.cycle_date,
                header.cycle_no,
                header.endpoint_id,
                size,
            ),
        )
        return {
            "status": "accepted",
            "path": str(path),
            "file_id": header.file_id,
            "cycle_date": header.cycle_date,
            "cycle_no": header.cycle_no,
            "endpoint_id": header.endpoint_id,
            "messages": [m.model_dump() for m in logical.messages],
            "logical": logical,
        }

    def land_all(self) -> list[dict]:
        return [self.land_one(p) for p in self.pending_paths()]
