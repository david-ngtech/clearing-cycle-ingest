from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from clearing_ingest.catalog import ENDPOINTS, MEMBERS, SOURCES
from clearing_ingest.config import DB_PATH


class Store:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()
        self.seed_catalog()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS members (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              country TEXT NOT NULL,
              ica TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS endpoints (
              id TEXT PRIMARY KEY,
              member_id TEXT NOT NULL,
              code TEXT NOT NULL,
              required INTEGER NOT NULL,
              city TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              cadence TEXT NOT NULL,
              contract TEXT NOT NULL,
              owner TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cycles (
              cycle_date TEXT NOT NULL,
              cycle_no INTEGER NOT NULL,
              status TEXT NOT NULL,
              opened_at TEXT,
              closed_at TEXT,
              PRIMARY KEY (cycle_date, cycle_no)
            );
            CREATE TABLE IF NOT EXISTS cycle_endpoints (
              cycle_date TEXT NOT NULL,
              cycle_no INTEGER NOT NULL,
              endpoint_id TEXT NOT NULL,
              status TEXT NOT NULL,
              file_id TEXT,
              landed_at TEXT,
              reject_reason TEXT,
              PRIMARY KEY (cycle_date, cycle_no, endpoint_id)
            );
            CREATE TABLE IF NOT EXISTS inbox_files (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              status TEXT NOT NULL,
              file_id TEXT,
              cycle_date TEXT,
              cycle_no INTEGER,
              endpoint_id TEXT,
              reason TEXT
            );
            CREATE TABLE IF NOT EXISTS dead_letters (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL,
              reason TEXT NOT NULL,
              evidence TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clearing_rows (
              cycle_date TEXT NOT NULL,
              cycle_no INTEGER NOT NULL,
              endpoint_id TEXT NOT NULL,
              file_id TEXT NOT NULL,
              message_no INTEGER NOT NULL,
              txn_id TEXT NOT NULL,
              card_bin TEXT,
              amount_cents INTEGER,
              currency TEXT,
              usd_cents INTEGER,
              merchant_id TEXT,
              bin_product TEXT,
              bin_country TEXT,
              fx_as_of TEXT,
              source_kind TEXT NOT NULL,
              PRIMARY KEY (cycle_date, cycle_no, endpoint_id, file_id, message_no)
            );
            """
        )
        self._conn.commit()

    def seed_catalog(self) -> None:
        with self._lock:
            for m in MEMBERS:
                self._conn.execute(
                    "INSERT OR REPLACE INTO members(id,name,country,ica) VALUES(?,?,?,?)",
                    (m.id, m.name, m.country, m.ica),
                )
            for e in ENDPOINTS:
                self._conn.execute(
                    "INSERT OR REPLACE INTO endpoints(id,member_id,code,required,city) VALUES(?,?,?,?,?)",
                    (e.id, e.member_id, e.code, int(e.required), e.city),
                )
            for s in SOURCES:
                self._conn.execute(
                    "INSERT OR REPLACE INTO sources(id,kind,name,cadence,contract,owner) VALUES(?,?,?,?,?,?)",
                    (s.id, s.kind, s.name, s.cadence, s.contract, s.owner),
                )
            self._conn.commit()

    def members(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM members ORDER BY id")

    def endpoints(self, required_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM endpoints"
        if required_only:
            sql += " WHERE required = 1"
        return self._rows(sql + " ORDER BY id")

    def sources(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM sources ORDER BY id")

    def required_endpoint_ids(self) -> list[str]:
        return [r["id"] for r in self.endpoints(required_only=True)]

    def _rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, args)
            self._conn.commit()

    def executescript(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)
            self._conn.commit()

    def query(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        return self._rows(sql, args)

    def insert_dead_letter(self, path: str, reason: str, evidence: dict, created_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO dead_letters(path, reason, evidence, created_at) VALUES(?,?,?,?)",
                (path, reason, json.dumps(evidence), created_at),
            )
            self._conn.commit()
