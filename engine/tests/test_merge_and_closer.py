from clearing_ingest.closer import CycleCloser
from clearing_ingest.generator import build_logical_file
from clearing_ingest.merge import Merger
from clearing_ingest.refs import RefClient
from clearing_ingest.store import Store


def _merger(store: Store) -> Merger:
    return Merger(store, RefClient())


def test_merge_is_idempotent(tmp_path):
    store = Store(tmp_path / "t.db")
    merger = _merger(store)
    logical = build_logical_file(
        cycle_date="2026-09-04", cycle_no=1, endpoint_id="E-4821", member_id="M-NORTH"
    )
    first = merger.merge_messages(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        file_id=logical.header.file_id,
        messages=logical.messages,
        source_kind="cycle_file",
    )
    second = merger.merge_messages(
        cycle_date="2026-09-04",
        cycle_no=1,
        endpoint_id="E-4821",
        file_id=logical.header.file_id,
        messages=logical.messages,
        source_kind="parquet_backfill",
    )
    assert first == len(logical.messages)
    assert second == 0
    row = store.query("SELECT usd_cents, bin_product FROM clearing_rows LIMIT 1")[0]
    assert row["usd_cents"] is not None
    assert row["bin_product"]


def test_cycle_closes_only_when_required_endpoints_land(tmp_path):
    store = Store(tmp_path / "t.db")
    closer = CycleCloser(store)
    snap = closer.refresh("2026-09-04", 1)
    assert snap["status"] == "open"
    assert snap["missing"]

    store.execute(
        """INSERT INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status, file_id)
           VALUES('2026-09-04',1,'E-4821','landed','F1')
           ON CONFLICT DO UPDATE SET status='landed'"""
    )
    snap = closer.refresh("2026-09-04", 1)
    assert snap["status"] == "partial"

    for endpoint_id in store.required_endpoint_ids():
        store.execute(
            """INSERT INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status, file_id)
               VALUES(?,?,?, 'landed', 'F')
               ON CONFLICT DO UPDATE SET status='landed'""",
            ("2026-09-04", 1, endpoint_id),
        )
    snap = closer.refresh("2026-09-04", 1)
    assert snap["status"] == "closed"
    assert snap["missing"] == []

    closer.mark_late("2026-09-04", 1, "E-9407")
    assert store.query("SELECT status FROM cycles WHERE cycle_date='2026-09-04' AND cycle_no=1")[0]["status"] == "late"
