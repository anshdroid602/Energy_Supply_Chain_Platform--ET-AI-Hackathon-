"""FastAPI endpoints that serve the agent pipeline to the frontend.

Mounted onto the main read API (api/main.py) as a router, so the dashboard
talks to one server:

  GET /pipeline/run     -> full PipelineResult JSON (one shot)
  GET /pipeline/stream  -> Server-Sent Events, one per agent as it finishes,
                           then a final `done` event with the whole result
                           (this powers the live step-by-step demo + latency timer)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from . import config
from .orchestrator import Orchestrator
from .schemas import PipelineResult

router = APIRouter(prefix="/pipeline", tags=["agents"])


def _params(max_risk: float, threshold: Optional[float]) -> dict:
    p: dict = {"max_risk": max_risk}
    if threshold is not None:
        p["threshold"] = threshold
    return p


@router.get("/run", response_model=PipelineResult)
def run_pipeline(
    corridor: str = Query("Strait of Hormuz"),
    refinery: str = Query(config.DEFAULT_REFINERY),
    max_risk: float = Query(0.5, ge=0, le=1),
    threshold: Optional[float] = Query(None, ge=0, le=1,
                                       description="override the fire threshold"),
):
    """Run all five agents and return the assembled recommendation."""
    orch = Orchestrator(params=_params(max_risk, threshold))
    try:
        return orch.run(corridor, refinery)
    finally:
        orch.ds.close()


@router.get("/stream")
def stream_pipeline(
    corridor: str = Query("Strait of Hormuz"),
    refinery: str = Query(config.DEFAULT_REFINERY),
    max_risk: float = Query(0.5, ge=0, le=1),
    threshold: Optional[float] = Query(None, ge=0, le=1),
):
    """Stream each agent step as SSE, then a final `done` event with the full
    PipelineResult. The frontend renders steps live and reads latency off `done`."""
    orch = Orchestrator(params=_params(max_risk, threshold))

    def gen():
        start = time.time()
        try:
            for step_name, slice_obj in orch.iter_steps(corridor, refinery):
                payload = {
                    "step": step_name,
                    "elapsed_s": round(time.time() - start, 2),
                    "result": slice_obj.model_dump(mode="json") if slice_obj is not None else None,
                }
                yield f"event: step\ndata: {json.dumps(payload, default=str)}\n\n"

            latency = time.time() - start
            result = orch._assemble(corridor, refinery, orch._final_state, latency)
            yield f"event: done\ndata: {result.model_dump_json()}\n\n"
        except Exception as e:  # surface failures to the client instead of hanging
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            orch.ds.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
