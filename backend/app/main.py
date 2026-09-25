import asyncio
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
