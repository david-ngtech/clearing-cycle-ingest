from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from clearing_ingest.config import ENGINE_HOST, ENGINE_PORT
from clearing_ingest.pipeline import IngestPipeline
from clearing_ingest.refs import router as refs_router
from clearing_ingest.store import Store

store = Store()
pipeline = IngestPipeline(store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.bootstrap()
    yield


app = FastAPI(
    title="Clearing Cycle Ingest",
    description="IPM-like cycle ingest fabric with FX/BIN APIs, member catalog, and parquet backfill.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(refs_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LateBody(BaseModel):
    cycle_date: str
    cycle_no: int
    endpoint_id: str


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "clearing-cycle-ingest"}


@app.get("/catalog")
def catalog() -> dict[str, Any]:
    snap = pipeline.snapshot()
    return {
        "sources": snap["sources"],
        "members": snap["members"],
        "endpoints": snap["endpoints"],
    }


@app.get("/cycles")
def cycles() -> dict[str, Any]:
    snap = pipeline.snapshot()
    return {"today": snap["today"], "cycles": snap["cycles"]}


@app.get("/inbox")
def inbox() -> dict[str, Any]:
    snap = pipeline.snapshot()
    return {"items": snap["inbox"], "dead_letters": snap["dead_letters"]}


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    return pipeline.snapshot()


@app.post("/run")
def run() -> dict[str, Any]:
    results = pipeline.run_once()
    return {"results": results, "cycles": pipeline.snapshot()["cycles"]}


@app.post("/late")
def drop_late(body: LateBody) -> dict[str, Any]:
    dropped = pipeline.drop_late_file(body.cycle_date, body.cycle_no, body.endpoint_id)
    results = pipeline.run_once()
    return {"dropped": dropped, "results": results, "cycles": pipeline.snapshot()["cycles"]}


@app.post("/replay/{dead_id}")
def replay(dead_id: int) -> dict[str, Any]:
    result = pipeline.replay_dead_letter(dead_id)
    if result["status"] == "missing":
        raise HTTPException(status_code=404, detail="Dead letter not found")
    return result


@app.get("/stream")
async def stream() -> StreamingResponse:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    loop = asyncio.get_running_loop()

    def on_event(payload: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    off = pipeline.subscribe(on_event)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'hello', **pipeline.snapshot()}, default=str)}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=8)
                    yield f"data: {json.dumps(item, default=str)}\n\n"
                except TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            off()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def run() -> None:
    import uvicorn

    uvicorn.run("clearing_ingest.api:app", host=ENGINE_HOST, port=ENGINE_PORT)


if __name__ == "__main__":
    run()
