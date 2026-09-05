from fastapi import FastAPI
from fastapi.testclient import TestClient

from clearing_ingest.refs import RefClient, router


def test_fx_converts_gbp():
    rate, as_of = RefClient().fx_to_usd("GBP", as_of="2026-09-04")
    assert rate == 1.27
    assert as_of == "2026-09-04"


def test_bin_lookup_known_and_unknown():
    client = RefClient()
    known = client.bin("541275")
    assert known["product"] == "World Elite"
    unknown = client.bin("000000")
    assert unknown["product"] == "Unknown"


def test_refs_http_surface():
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    assert http.get("/refs/fx", params={"ccy": "EUR"}).json()["rates"]["EUR"] == 1.08
    assert http.get("/refs/bins/541275").status_code == 200
    assert http.get("/refs/bins/000000").status_code == 404
