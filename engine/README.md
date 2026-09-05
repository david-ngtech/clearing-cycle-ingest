# Clearing Cycle Ingest engine

Python ingest fabric. See the repository root README for architecture.

```bash
uv sync --extra dev
uv run uvicorn clearing_ingest.api:app --host 127.0.0.1 --port 18771
```
