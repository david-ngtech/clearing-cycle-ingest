from pathlib import Path

from clearing_ingest.generator import build_logical_file, write_ndjson
from clearing_ingest.lander import Lander
from clearing_ingest.store import Store


def test_rejects_header_trailer_mismatch(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    inbox = tmp_path / "inbox"
    dead = tmp_path / "dead"
    logical = build_logical_file(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        member_id="M-NORTH",
        fault="header_trailer_mismatch",
    )
    path = write_ndjson(logical, inbox / "bad.ndjson")
    result = Lander(store, inbox=inbox, dead=dead).land_one(path)
    assert result["status"] == "rejected"
    assert result["reason"] == "header_trailer_mismatch"
    assert store.query("SELECT COUNT(*) AS n FROM dead_letters")[0]["n"] == 1


def test_accepts_clean_file(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    inbox = tmp_path / "inbox"
    logical = build_logical_file(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        member_id="M-NORTH",
    )
    path = write_ndjson(logical, inbox / "ok.ndjson")
    result = Lander(store, inbox=inbox, dead=tmp_path / "dead").land_one(path)
    assert result["status"] == "accepted"
    assert result["file_id"] == logical.header.file_id
