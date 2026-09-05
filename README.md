# Clearing Cycle Ingest

A local **clearing-cycle ingest fabric**. I built it to stay sharp on the file-protocol side of card-network data engineering: members drop cycle files, reference data arrives over APIs, yesterday lives in parquet, and a cycle is not closed until every required endpoint has landed.

It is modeled on the **public** Mastercard GCMS / IPM file contract — header, messages, trailer; four to six cycles per day per endpoint — not on any internal Mastercard system. Synthetic data only. Six-digit BINs, never a PAN.

```bash
make install && make dev
```

- Engine: `http://127.0.0.1:18771/health`
- Console: `http://127.0.0.1:43131`

## Why this exists

Authorization is a stream. Clearing is a **file protocol**. Networks still take member files on a cycle clock, validate header/trailer contracts, convert currency, and refuse to call a cycle closed until every required delivery destination has shown up. That is a different senior problem than scoring a live auth feed.

I wanted one repo that practices that ingest problem end to end, locally, without a cluster.

## Architecture

```
inbox/*.ndjson          GET /refs/fx          GET /refs/bins/{bin}
 (IPM-like packs)        (mid to USD)          (account range)
         │                     │                      │
         ▼                     │                      │
   land + fingerprint          │                      │
   header/trailer/DE71         │                      │
         │                     ▼                      ▼
         └──────────►  enrich + INSERT OR IGNORE  ◄───┘
                       natural key:
                       (cycle_date, cycle_no, endpoint_id, file_id, message_no)
                                  │
                     member DB ───┤  who is required for cycle N
                     parquet   ───┤  yesterday's partitions, same key
                                  ▼
                           cycle closer
                           open → partial → closed
                           (a file after close is late)
                                  │
                                  ▼
                         FastAPI + SSE  →  Next.js board
```

| Source | Public analog | Here |
| --- | --- | --- |
| Cycle drop | Member IPM logical file (header / messages / trailer). File IDs must match; `DE 71` increments from 1. | `inbox/YYYY-MM-DD/C0N/*.ndjson` |
| FX API | GCMS currency conversion tables | `GET /refs/fx?ccy=&as_of=` |
| BIN API | Network account-range lookup | `GET /refs/bins/{bin}` |
| Member DB | Endpoint registry and settlement calendar | SQLite `members` / `endpoints` — who must deliver cycle N |
| Historical parquet | Lake backfill / Hadoop → cloud | `lake/cycle_date=/cycle_no=/*.parquet` |

## What the fabric actually does

1. **Catalog** — five sources with contract, cadence, owner. Required endpoints come from the member registry, not from whatever happened to land.
2. **Land** — fingerprint the pack (`sha256`). Parse NDJSON. Reject to dead-letter when header/trailer `file_id` diverge, trailer count is wrong, `DE 71` has a gap, or the amount hash fails.
3. **Merge** — insert with `INSERT OR IGNORE` on `(cycle_date, cycle_no, endpoint_id, file_id, message_no)`. Re-drops and parquet backfills do not double the lake. FX and BIN stamp USD cents and product as-of the cycle date.
4. **Close** — `open` until something lands, `partial` while a required endpoint is missing, `closed` only when every required endpoint has a valid file. A pack after close is `late`.
5. **Board** — the console shows the cycle burn-down, the source catalog, inbox accepts/rejects, and dead letters.

Seed on boot: today’s cycles 1–3 in the inbox (one complete, one missing an endpoint, one poison file), cycle 4 not dropped, and all four of yesterday’s cycles as parquet.

## Layout

```
engine/clearing_ingest/   catalog, filespec, lander, refs, merge, closer, API
engine/tests/             contract, merge, closer, parquet tests
web/                      Next.js cycle board
inbox/                    generated drops (gitignored)
lake/                     generated parquet (gitignored)
```

## Running it

Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make install
make dev
```

```bash
make test
```

**Run inbox** on the board re-walks leftover drops. **Drop late file** writes one more pack after a cycle has already moved, so you can see `late` instead of a silent overwrite.

## Data

Every file is invented. No primary account numbers. The IPM-like NDJSON is a teaching stand-in for the public GCMS header/trailer rules, not a wire-format codec.

Public background: [GCMS / IPM reference (customer-generated files)](https://pismoassets.pismo.io/pismo-docs/mc_gcms_rm.pdf).
