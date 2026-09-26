import asyncio
import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.config import settings
from app.pipeline.schemas import RunPipelineRequest, PipelineMetrics
from app.pipeline.engine import pipeline_engine
from app.agent.planner import PipelinePlanner
from app.agent.orchestrator import PipelineOrchestrator
from mock_service import (
    get_market_data,
    inject_failure as mock_inject_failure,
    reset_schema as mock_reset_schema,
    get_status as mock_get_status,
    get_database_records as mock_get_db_records,
    reset_database as mock_reset_db
)

orchestrator = PipelineOrchestrator()

# Wire orchestrator transitions into the WebSocket broadcast stream
orchestrator.add_event_listener(
    lambda event: asyncio.create_task(pipeline_engine.broadcast("orchestrator_event", event))
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Agentic Self-Healing Pipeline for HACK-O-OCTO 4.0 (PS01)"
)

# Enable CORS for Next.js / Vite React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "track": settings.TRACK,
        "status": "online",
        "version": settings.VERSION,
        "docs": "/docs",
        "ws_endpoint": "/ws/pipeline"
    }

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "gemini_model": settings.DEFAULT_MODEL,
        "has_api_key": bool(pipeline_engine.agent.api_key),
        "active_patches": len(pipeline_engine.active_patch_records),
        "is_pipeline_busy": pipeline_engine.is_running
    }

@app.get("/api/plan")
def get_plan():
    return {
        "nodes": [n.model_dump() for n in PipelinePlanner.get_default_plan()]
    }

@app.get("/api/metrics")
def get_metrics():
    return pipeline_engine.get_metrics().model_dump()

@app.get("/api/patches")
def get_patches():
    return {
        "patches": [p.model_dump() for p in pipeline_engine.active_patch_records.values()]
    }

@app.post("/api/reset-patches")
async def reset_patches():
    pipeline_engine.reset_patches()
    await pipeline_engine.broadcast("patches_cleared", {"message": "All hot-patches purged from memory."})
    return {"status": "success", "message": "Patches cleared successfully"}

class ApiKeyUpdate(BaseModel):
    api_key: str

@app.post("/api/config/key")
def update_api_key(req: ApiKeyUpdate):
    pipeline_engine.agent.update_key(req.api_key)
    return {"status": "success", "has_key": bool(pipeline_engine.agent.api_key)}

# ===========================================================================
# Component 1: Mock Market Environment Endpoints
# ===========================================================================
@app.get("/market-data")
def api_market_data(fail: Optional[bool] = Query(None)):
    return get_market_data(fail=fail)

@app.post("/inject-failure")
def api_inject_failure():
    return mock_inject_failure()

@app.post("/reset")
def api_reset():
    return mock_reset_schema()

@app.get("/status")
def api_mock_status():
    return mock_get_status()

@app.get("/db/records")
def api_db_records():
    return mock_get_db_records()

@app.post("/db/reset")
def api_db_reset():
    return mock_reset_db()

# ===========================================================================
# Component 3: Autonomous Orchestrator Endpoints
# ===========================================================================
class OrchestratorRunRequest(BaseModel):
    source_url: str = "http://127.0.0.1:8000/market-data"
    allow_fallback: bool = True
    gemini_api_key: Optional[str] = None

@app.post("/api/orchestrator/run")
async def trigger_orchestrator(req: OrchestratorRunRequest):
    if req.gemini_api_key:
        orchestrator.gemini_healer.update_key(req.gemini_api_key)
    result = await orchestrator.run_pipeline(
        source_url=req.source_url,
        allow_fallback=req.allow_fallback
    )
    return result.model_dump()

@app.post("/api/orchestrator/reset")
def reset_orchestrator():
    orchestrator.reset_patches()
    return {"status": "success", "message": "Orchestrator patches and cache purged."}

# ===========================================================================
# Benchmark & Invariant Verification Suite Endpoints
# ===========================================================================
@app.get("/api/benchmark")
def get_benchmark_results():
    import json
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "master_33_validation_results.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "master_33_validation_results.json")
    
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            cases = json.load(f)
    else:
        cases = []

    suites = ["Original 15", "Fresh 10", "Cold 8"]
    summary_by_suite = {}
    for s in suites:
        s_cases = [c for c in cases if c.get("suite") == s]
        healed = sum(1 for c in s_cases if c.get("outcome") == "HEALED_CORRECTLY")
        failsafe = sum(1 for c in s_cases if c.get("outcome") == "FAIL_SAFE_TRIGGERED")
        wrong = sum(1 for c in s_cases if c.get("outcome") == "HEALED_BUT_WRONG_DATA")
        crashed = sum(1 for c in s_cases if c.get("outcome") == "CRASHED")
        total = len(s_cases)
        summary_by_suite[s] = {
            "total": total,
            "healed": healed,
            "failsafe": failsafe,
            "wrong": wrong,
            "crashed": crashed,
            "rate": round((healed + failsafe) / total * 100, 1) if total > 0 else 0
        }

    total_healed = sum(1 for c in cases if c.get("outcome") == "HEALED_CORRECTLY")
    total_failsafe = sum(1 for c in cases if c.get("outcome") == "FAIL_SAFE_TRIGGERED")
    total_wrong = sum(1 for c in cases if c.get("outcome") == "HEALED_BUT_WRONG_DATA")
    total_crashed = sum(1 for c in cases if c.get("outcome") == "CRASHED")
    total = len(cases)

    return {
        "status": "success",
        "summary": {
            "total": total,
            "healed": total_healed,
            "failsafe": total_failsafe,
            "wrong_data": total_wrong,
            "crashed": total_crashed,
            "safe_resilient_rate": round((total_healed + total_failsafe) / total * 100, 1) if total > 0 else 100.0
        },
        "by_suite": summary_by_suite,
        "cases": cases
    }

@app.post("/api/benchmark/run")
async def run_benchmark_live():
    from run_master_33_benchmark import run_master_benchmark

    async def broadcast_progress(current, total, rec):
        pct = round(current / total * 100)
        await pipeline_engine.broadcast("benchmark_progress", {
            "current": current,
            "total": total,
            "percent": pct,
            "case": rec
        })

    # Run in background or directly
    asyncio.create_task(run_master_benchmark(progress_callback=broadcast_progress))
    return {"status": "started", "message": "Master 33-Case Benchmark suite initiated."}

@app.post("/api/run")
async def trigger_run(request: RunPipelineRequest):
    result = await pipeline_engine.run_pipeline(request)
    return result

@app.websocket("/ws/pipeline")
async def websocket_pipeline(websocket: WebSocket):
    await websocket.accept()
    pipeline_engine.add_listener(websocket)
    # Send initial state immediately
    await websocket.send_json({
        "event": "connected",
        "data": {
            "message": "Connected to AegisFlow Agentic WebSocket Stream",
            "metrics": pipeline_engine.get_metrics().model_dump(),
            "patches": [p.model_dump() for p in pipeline_engine.active_patch_records.values()],
            "has_api_key": bool(pipeline_engine.agent.api_key)
        }
    })
    try:
        while True:
            # Handle incoming client messages (e.g. ping/pong or triggering runs)
            data = await websocket.receive_json()
            if data.get("action") == "run":
                req = RunPipelineRequest(**data.get("params", {}))
                await pipeline_engine.run_pipeline(req)
            elif data.get("action") == "reset":
                pipeline_engine.reset_patches()
                await pipeline_engine.broadcast("patches_cleared", {})
    except WebSocketDisconnect:
        pipeline_engine.remove_listener(websocket)
    except Exception:
        pipeline_engine.remove_listener(websocket)
