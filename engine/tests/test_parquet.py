from clearing_ingest.parquet_backfill import read_partitions, write_cycle_parquet


def test_parquet_round_trip(tmp_path):
    path = write_cycle_parquet("2026-09-03", 1, lake=tmp_path)
    assert path.exists()
    rows = read_partitions(tmp_path)
    assert rows
    assert {r["cycle_date"] for r in rows} == {"2026-09-03"}
    assert all(r["message_no"] >= 1 for r in rows)
