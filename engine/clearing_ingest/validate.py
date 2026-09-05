from __future__ import annotations

import json
from pathlib import Path

from clearing_ingest.filespec import ClearingMessage, FileHeader, FileTrailer, LogicalFile


class ContractError(ValueError):
    def __init__(self, reason: str, evidence: dict) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


def parse_ndjson(path: Path) -> LogicalFile:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    if len(lines) < 3:
        raise ContractError("truncated_file", {"path": str(path), "lines": len(lines)})
    try:
        header = FileHeader.model_validate(json.loads(lines[0]))
        trailer = FileTrailer.model_validate(json.loads(lines[-1]))
        messages = [ClearingMessage.model_validate(json.loads(ln)) for ln in lines[1:-1]]
    except Exception as exc:  # noqa: BLE001
        raise ContractError("parse_error", {"path": str(path), "error": str(exc)}) from exc
    return LogicalFile(header=header, messages=messages, trailer=trailer)


def validate_logical(logical: LogicalFile) -> None:
    if logical.header.file_id != logical.trailer.file_id:
        raise ContractError(
            "header_trailer_mismatch",
            {"header": logical.header.file_id, "trailer": logical.trailer.file_id},
        )
    if logical.trailer.message_count != len(logical.messages):
        raise ContractError(
            "count_mismatch",
            {"trailer": logical.trailer.message_count, "actual": len(logical.messages)},
        )
    expected = list(range(1, len(logical.messages) + 1))
    got = [m.message_no for m in logical.messages]
    if got != expected:
        raise ContractError("de71_sequence", {"expected": expected, "got": got})
    hashed = sum(m.amount_cents for m in logical.messages)
    if hashed != logical.trailer.hash_amount_cents:
        raise ContractError(
            "hash_amount_mismatch",
            {"trailer": logical.trailer.hash_amount_cents, "actual": hashed},
        )
