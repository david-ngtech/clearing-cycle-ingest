from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/refs", tags=["reference-apis"])

FX_TO_USD = {
    "USD": 1.0,
    "GBP": 1.27,
    "EUR": 1.08,
    "JPY": 0.0067,
    "CAD": 0.73,
}

BIN_TABLE = {
    "541275": {"product": "World Elite", "country": "US", "region": "NA", "network": "Mastercard"},
    "222988": {"product": "Debit", "country": "US", "region": "NA", "network": "Mastercard"},
    "414720": {"product": "Traditional", "country": "US", "region": "NA", "network": "Visa"},
    "526610": {"product": "Platinum", "country": "CA", "region": "NA", "network": "Mastercard"},
    "454313": {"product": "Business", "country": "GB", "region": "EU", "network": "Visa"},
    "510875": {"product": "World", "country": "DE", "region": "EU", "network": "Mastercard"},
}


def lookup_fx(ccy: str | None = None, as_of: str | None = None) -> dict:
    stamp = as_of or datetime.now(UTC).date().isoformat()
    if ccy:
        if ccy not in FX_TO_USD:
            raise KeyError(ccy)
        return {"as_of": stamp, "base": "USD", "rates": {ccy: FX_TO_USD[ccy]}}
    return {"as_of": stamp, "base": "USD", "rates": dict(FX_TO_USD)}


def lookup_bin(card_bin: str) -> dict | None:
    row = BIN_TABLE.get(card_bin)
    if not row:
        return None
    return {"bin": card_bin, **row}


@router.get("/fx")
def fx_rates(ccy: str | None = None, as_of: str | None = Query(default=None)) -> dict:
    try:
        return lookup_fx(ccy, as_of)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown currency {exc.args[0]}") from exc


@router.get("/bins/{bin}")
def bin_lookup(bin: str) -> dict:
    row = lookup_bin(bin)
    if not row:
        raise HTTPException(status_code=404, detail=f"unknown bin {bin}")
    return row


class RefClient:
    """Client used at merge time. Talks the same contract as GET /refs/*."""

    def fx_to_usd(self, ccy: str, as_of: str | None = None) -> tuple[float, str]:
        body = lookup_fx(ccy, as_of)
        return float(body["rates"][ccy]), body["as_of"]

    def bin(self, card_bin: str) -> dict:
        row = lookup_bin(card_bin)
        if not row:
            return {"product": "Unknown", "country": "??", "region": "??", "network": "Unknown"}
        return row
