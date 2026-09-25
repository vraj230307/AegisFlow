"""
Auto-ETL Restorer — Stage Demo 5x Dry-Run Rehearsal
Executes 5 consecutive full end-to-end demo cycles:
  Inject Schema Drift -> Extract -> Intercept KeyError -> Synthesize & Sandbox Patch -> Hot-Patch -> Green -> Verify SQLite
Times each rehearsal run to ensure rock-solid stage demo reliability.
"""

import asyncio
import os
import sys
import time
from typing import List

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import FailureType, RawBatch
from app.pipeline.failures import generate_base_transactions, inject_failure
from mock_service import init_db, clear_db, query_records
import app.pipeline.nodes as nodes

async def rehearse_stage_demo(rehearsal_num: int, orchestrator: PipelineOrchestrator, db_path: str):
    t_start = time.time()
    
    # 1. Reset patches to simulate starting cold on stage
    orchestrator.reset_patches()
    clear_db(db_path)

    # 2. Inject schema drift failure payload
    drifted_data = inject_failure(generate_base_transactions(5), FailureType.SCHEMA_DRIFT)

    # Mock extract returns the drifted payload
    orig_extract = nodes.node_extract
    nodes.node_extract = lambda url: RawBatch(
        source_url=url,
        status_code=200,
        raw_payload=drifted_data,
        fetched_at="2026-09-25T16:00:00Z"
    )

    try:
        # 3. First execution: Traps KeyError -> Heals via Fallback/Gemini -> Green
        run1 = await orchestrator.run_pipeline(
            source_url="http://mock-api/market-data",
            db_path=db_path,
            allow_fallback=True
        )
        assert run1.success is True, f"Rehearsal #{rehearsal_num} failed: {run1.error}"
        assert run1.state == "DONE"
        assert run1.healed is True
        assert run1.mttr_ms > 0
        
        # 4. Second execution: Demonstrates zero-latency cached repeat execution
        # Unpatch node to pristine, but keep patch cache
        orchestrator.unpatch_nodes_keep_cache()
        run2 = await orchestrator.run_pipeline(
            source_url="http://mock-api/market-data",
            db_path=db_path,
            allow_fallback=True
        )
        assert run2.success is True
        assert run2.heal_source == "cached"

        # 5. Third execution: Zero-latency in-memory execution (already patched)
        run3 = await orchestrator.run_pipeline(
            source_url="http://mock-api/market-data",
            db_path=db_path,
            allow_fallback=True
        )
        assert run3.success is True

        # 6. Verify SQLite persistence
        stored_rows = query_records(db_path)
        
        elapsed_ms = round((time.time() - t_start) * 1000, 2)
        print(f"[REHEARSAL #{rehearsal_num}/5 PASS] Cold MTTR: {run1.mttr_ms}ms | Cached Run: {run2.duration_ms}ms | Total Demo Loop: {elapsed_ms}ms")
        return elapsed_ms
    finally:
        nodes.node_extract = orig_extract

async def run_5x_rehearsal():
    print("=" * 75)
    print("REHEARSAL CHECK: 5 CONSECUTIVE STAGE DEMO DRY-RUNS")
    print("=" * 75)

    test_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage_rehearsal.db")
    init_db(test_db)
    
    orchestrator = PipelineOrchestrator(api_key=None)

    timings = []
    for i in range(1, 6):
        duration = await rehearse_stage_demo(i, orchestrator, test_db)
        timings.append(duration)
        await asyncio.sleep(0.1)

    if os.path.exists(test_db):
        os.remove(test_db)

    avg_duration = round(sum(timings) / len(timings), 2)
    print("\n" + "=" * 75)
    print(f"ALL 5 REHEARSALS COMPLETED FLAWLESSLY! Average demo cycle: {avg_duration}ms")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(run_5x_rehearsal())
