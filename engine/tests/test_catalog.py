from clearing_ingest.catalog import ENDPOINTS, SOURCES
from clearing_ingest.store import Store


def test_required_endpoints_match_gcms_style_minimum():
    required = [e for e in ENDPOINTS if e.required]
    assert len(required) >= 4
    assert any(s.kind == "cycle_file" for s in SOURCES)


def test_store_seeds_member_catalog(tmp_path):
    store = Store(tmp_path / "t.db")
    assert len(store.members()) == 4
    assert len(store.required_endpoint_ids()) == 5
    kinds = {s["kind"] for s in store.sources()}
    assert kinds == {"cycle_file", "fx_api", "bin_api", "member_db", "parquet_backfill"}
