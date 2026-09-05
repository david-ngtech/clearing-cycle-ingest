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

    def land_one(self, path: Path) -> dict:
        checksum = sha256_file(path)
        already = self.store.query("SELECT status, file_id FROM inbox_files WHERE sha256=?", (checksum,))
        if already:
            return {
                "status": "duplicate",
                "path": str(path),
                "prior": already[0]["status"],
                "file_id": already[0]["file_id"],
            }
        now = datetime.now(UTC).isoformat()
        try:
            logical = parse_ndjson(path)
            validate_logical(logical)
        except ContractError as exc:
            dest = self.dead / path.name
            shutil.copy2(path, dest)
            self.store.insert_dead_letter(str(dest), exc.reason, exc.evidence, now)
            self.store.execute(
                """INSERT INTO inbox_files(path, sha256, status, reason)
                   VALUES(?,?,?,?)""",
                (str(path), checksum, "rejected", exc.reason),
            )
            return {"status": "rejected", "path": str(path), "reason": exc.reason, "evidence": exc.evidence}

        header = logical.header
        self.store.execute(
            """INSERT INTO inbox_files(path, sha256, status, file_id, cycle_date, cycle_no, endpoint_id)
               VALUES(?,?,?,?,?,?,?)""",
            (str(path), checksum, "accepted", header.file_id, header.cycle_date, header.cycle_no, header.endpoint_id),
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
