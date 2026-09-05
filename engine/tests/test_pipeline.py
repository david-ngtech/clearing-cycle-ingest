from clearing_ingest.closer import CycleCloser
from clearing_ingest.generator import today_utc
from clearing_ingest.pipeline import IngestPipeline
from clearing_ingest.store import Store


def _pipeline(tmp_path) -> IngestPipeline:
    store = Store(tmp_path / "t.db")
    return IngestPipeline(
        store,
        inbox=tmp_path / "inbox",
        lake=tmp_path / "lake",
        dead=tmp_path / "dead",
    )


def test_bootstrap_closes_complete_cycle_and_stays_closed(tmp_path):
    pipe = _pipeline(tmp_path)
    pipe.bootstrap()
    day = today_utc()
    by_no = {c["cycle_no"]: c for c in pipe.closer.board(day)}
    assert by_no[1]["status"] == "closed"
    assert by_no[1]["missing"] == []
    assert by_no[2]["status"] == "partial"
    assert "E-3310" in by_no[2]["missing"]
    assert by_no[3]["status"] == "partial"
    assert "E-1102" in by_no[3]["missing"]
    assert by_no[4]["status"] == "open"

    pipe.bootstrap()
    again = {c["cycle_no"]: c for c in pipe.closer.board(day)}
    assert again[1]["status"] == "closed"
    assert again[2]["status"] == "partial"
    assert again[3]["status"] == "partial"
    assert again[4]["status"] == "open"


def test_late_retransmission_marks_closed_cycle_late(tmp_path):
    pipe = _pipeline(tmp_path)
    pipe.bootstrap()
    day = today_utc()
    assert pipe.closer.board(day)[0]["status"] == "closed"
    pipe.drop_late_file(day, 1, "E-9407")
    pipe.run_once()
    assert pipe.store.query("SELECT status FROM cycles WHERE cycle_date=? AND cycle_no=1", (day,))[0][
        "status"
    ] == "late"


def test_replay_repairs_poison_file(tmp_path):
    pipe = _pipeline(tmp_path)
    pipe.bootstrap()
    dead = pipe.store.query("SELECT id FROM dead_letters")
    assert dead
    result = pipe.replay_dead_letter(dead[0]["id"])
    assert result["status"] == "replayed"
    day = today_utc()
    c3 = next(c for c in pipe.closer.board(day) if c["cycle_no"] == 3)
    assert c3["status"] == "closed"
    assert "E-1102" not in c3["missing"]


def test_optional_endpoint_after_required_close_is_not_late(tmp_path):
    store = Store(tmp_path / "t.db")
    closer = CycleCloser(store)
    closer.ensure_cycle("2026-09-04", 1)
    for endpoint_id in store.required_endpoint_ids():
        store.execute(
            """INSERT INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status, file_id)
               VALUES(?,?,?,'landed','F')
               ON CONFLICT DO UPDATE SET status='landed'""",
            ("2026-09-04", 1, endpoint_id),
        )
    snap = closer.refresh("2026-09-04", 1)
    assert snap["status"] == "closed"
    store.execute(
        """INSERT INTO cycle_endpoints(cycle_date, cycle_no, endpoint_id, status, file_id)
           VALUES('2026-09-04',1,'E-9407','landed','F-OPT')
           ON CONFLICT DO UPDATE SET status='landed'"""
    )
    snap = closer.refresh("2026-09-04", 1)
    assert snap["status"] == "closed"
