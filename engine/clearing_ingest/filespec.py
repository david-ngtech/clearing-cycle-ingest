from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileHeader(BaseModel):
    record_type: Literal["header"] = "header"
    file_id: str
    cycle_date: str
    cycle_no: int
    endpoint_id: str
    member_id: str
    created_at: str


class ClearingMessage(BaseModel):
    record_type: Literal["message"] = "message"
    message_no: int = Field(ge=1)
    txn_id: str
    card_bin: str
    amount_cents: int
    currency: str
    merchant_id: str
    auth_code: str | None = None


class FileTrailer(BaseModel):
    record_type: Literal["trailer"] = "trailer"
    file_id: str
    message_count: int
    hash_amount_cents: int


class LogicalFile(BaseModel):
    header: FileHeader
    messages: list[ClearingMessage]
    trailer: FileTrailer
