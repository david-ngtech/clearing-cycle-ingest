# Clearing Cycle Ingest

A local **clearing-cycle ingest fabric**. I built it to practice the file-protocol side of card-network data engineering: members drop cycle files, reference data arrives over APIs, yesterday lives in parquet, and a cycle is not closed until every required endpoint has landed.

Modeled on the public Mastercard GCMS / IPM file contract (header → messages → trailer, 4–6 cycles/day per endpoint). Synthetic data only. No PANs. No cluster.

```bash
make install && make dev
```

Engine: `http://127.0.0.1:18771` · Console: `http://127.0.0.1:43131`
