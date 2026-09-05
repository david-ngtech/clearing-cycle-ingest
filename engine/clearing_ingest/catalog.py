from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Member(BaseModel):
    id: str
    name: str
    country: str
    ica: str


class Endpoint(BaseModel):
    id: str
    member_id: str
    code: str
    required: bool
    city: str


class Source(BaseModel):
    id: str
    kind: Literal["cycle_file", "fx_api", "bin_api", "member_db", "parquet_backfill"]
    name: str
    cadence: str
    contract: str
    owner: str


MEMBERS: list[Member] = [
    Member(id="M-NORTH", name="Northline Acquiring", country="US", ica="12345"),
    Member(id="M-HARBOR", name="Harbor Issuing", country="US", ica="22331"),
    Member(id="M-THAMES", name="Thames Payments", country="GB", ica="44550"),
    Member(id="M-RHINE", name="Rhine Card Services", country="DE", ica="55660"),
]

ENDPOINTS: list[Endpoint] = [
    Endpoint(id="E-4821", member_id="M-NORTH", code="4821", required=True, city="Arlington"),
    Endpoint(id="E-1102", member_id="M-NORTH", code="1102", required=True, city="Chicago"),
    Endpoint(id="E-7740", member_id="M-HARBOR", code="7740", required=True, city="Fairfax"),
    Endpoint(id="E-3310", member_id="M-THAMES", code="3310", required=True, city="London"),
    Endpoint(id="E-8902", member_id="M-RHINE", code="8902", required=True, city="Berlin"),
    Endpoint(id="E-9407", member_id="M-RHINE", code="9407", required=False, city="Frankfurt"),
]

SOURCES: list[Source] = [
    Source(
        id="SRC-CYCLE",
        kind="cycle_file",
        name="Member cycle drop",
        cadence="4 cycles/day per required endpoint",
        contract="IPM-like NDJSON: header, messages, trailer. file_id match, DE71 sequence.",
        owner="clearing-ops",
    ),
    Source(
        id="SRC-FX",
        kind="fx_api",
        name="FX mid rates",
        cadence="per cycle, as-of timestamp",
        contract="GET /refs/fx?ccy=&as_of=  → mid rate to USD",
        owner="treasury-ref",
    ),
    Source(
        id="SRC-BIN",
        kind="bin_api",
        name="Account-range lookup",
        cadence="on enrich",
        contract="GET /refs/bins/{bin} → product, country, region",
        owner="network-ref",
    ),
    Source(
        id="SRC-DB",
        kind="member_db",
        name="Member and endpoint registry",
        cadence="seed + rare updates",
        contract="Who must deliver cycle N; required vs optional endpoints",
        owner="member-ops",
    ),
    Source(
        id="SRC-PQ",
        kind="parquet_backfill",
        name="Historical lake partitions",
        cadence="on-demand backfill",
        contract="lake/cycle_date=YYYY-MM-DD/cycle_no=N/*.parquet",
        owner="lake-platform",
    ),
]
