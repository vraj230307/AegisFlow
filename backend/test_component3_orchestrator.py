"""
Test suite for Auto-ETL Restorer — Component 3: Self-Healing Orchestrator
Tests:
1. Offline Fallback Healing across all 6 scenarios (with zero internet / no API key)
2. Zero-latency repeat execution via in-memory patch cache
3. Sandbox rejection of unsafe / invalid patch code
4. FAIL_SAFE guardrail when both Gemini and fallback are disabled
5. Structured event transitions {state, node, timestamp, detail}
"""

import asyncio
import os
import sys
import tempfile
from typing import List, Dict, Any

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pipeline.schemas import FailureType, RawBatch
from app.pipeline.failures import generate_base_transactions, inject_failure
from app.agent.orchestrator import PipelineOrchestrator
from app.agent.sandbox import sandbox_test_patch, validate_ast_security
from mock_service import init_db, clear_db

async def run_scenario_test(
    orchestrator: PipelineOrchestrator,
    failure_type: FailureType,
    test_db: str,
    scenario_name: str
):
    print(f"\n---> Testing Scenario: {scenario_name} ({failure_type.value})")
    clean_data = generate_base_transactions(5)
    mutated_payload = inject_failure(clean_data, failure_type)
    
    # We monkey-patch node_extract temporarily for this in-memory test run
    import app.pipeline.nodes as nodes
    orig_extract = nodes.node_extract
    nodes.node_extract = lambda url: RawBatch(
        source_url=url,
        status_code=200,
        raw_payload=mutated_payload,
        fetched_at="2026-09-25T16:00:00Z",
        record_count=len(mutated_payload) if isinstance(mutated_payload, list) else 1
    )

    try:
        # 1. First run: triggers self-healing
        res = await orchestrator.run_pipeline(
            source_url="mock://test",
            db_path=test_db,
            allow_fallback=True
        )
        assert res.success is True, f"Pipeline run failed: {res.error}"
        assert res.state == "DONE"
        if failure_type != FailureType.NONE:
            assert res.healed is True, f"Expected healed=True for {failure_type}"
            assert res.heal_source in ["fallback", "gemini"]
            assert res.mttr_ms > 0
            print(f"[OK] Run 1 (Healing): Successfully healed via {res.heal_source} in {res.mttr_ms}ms MTTR")
        else:
            print(f"[OK] Clean baseline executed cleanly in {res.duration_ms}ms")

        # 2. Second run: unpatch node to pristine, but keep patch_cache intact
        if failure_type != FailureType.NONE:
            orchestrator.unpatch_nodes_keep_cache()
            res_repeat = await orchestrator.run_pipeline(
                source_url="mock://test",
                db_path=test_db,
                allow_fallback=True
            )
            assert res_repeat.success is True
            assert res_repeat.heal_source == "cached", f"Expected heal_source='cached', got {res_repeat.heal_source}"
            print(f"[OK] Run 2 (Repeat): Reused cached patch with 0ms round-trip!")

            # 3. Third run: zero-overhead live execution (already hot-patched)
            res_live = await orchestrator.run_pipeline(
                source_url="mock://test",
                db_path=test_db,
                allow_fallback=True
            )
            assert res_live.success is True
            print(f"[OK] Run 3 (Hot-Patched In-Memory): Executed in {res_live.duration_ms}ms with 0 errors!")

    finally:
        nodes.node_extract = orig_extract


async def test_component3():
    print("=" * 75)
    print("TESTING COMPONENT 3: ERROR INTERCEPTOR & FALLBACK/GEMINI SELF-HEALER")
    print("=" * 75)

    test_db = os.path.join(tempfile.gettempdir(), "test_orchestrator.db")
    init_db(test_db)
    clear_db(test_db)

    orchestrator = PipelineOrchestrator(api_key=None)  # Explicitly offline

    # Captured events logger
    captured_events: List[Dict[str, Any]] = []
    orchestrator.add_event_listener(lambda e: captured_events.append(e))

    # -----------------------------------------------------------------------
    # TEST 1: All 6 Scenarios via Deterministic Fallback Healer (Offline Demo Insurance)
    # -----------------------------------------------------------------------
    scenarios = [
        (FailureType.NONE, "1. Clean Baseline"),
        (FailureType.SCHEMA_DRIFT, "2. Schema Drift"),
        (FailureType.TYPE_MUTATION, "3. Type Mutation"),
        (FailureType.ENVELOPE_RELOCATION, "4. Envelope Relocation"),
        (FailureType.MISSING_NULL_FIELDS, "5. Missing/Null Fields"),
        (FailureType.CORRUPT_TIMESTAMP, "6. Corrupt Timestamp"),
    ]

    for f_type, s_name in scenarios:
        orchestrator.reset_patches()
        await run_scenario_test(orchestrator, f_type, test_db, s_name)

    print("\n[OK] All 6 scenarios reached DONE via FALLBACK_HEAL with zero internet / API key!")

    # -----------------------------------------------------------------------
    # TEST 2: Sandbox Security Validation Rejection Tests
    # -----------------------------------------------------------------------
    print("\n---> Testing Sandbox Security Checks (Rejecting Unsafe Patches)...")
    
    # Test A: Malicious import
    bad_code_1 = """import os
def resolve_key_aliases(raw_record):
    os.system("echo hacked")
    return raw_record
"""
    passed, _, err = sandbox_test_patch(bad_code_1, "resolve_key_aliases", {"id": 1})
    assert passed is False
    assert "Forbidden module import: 'os'" in err
    print(f"[OK] Sandbox successfully rejected unauthorized import: {err}")

    # Test B: Dangerous builtin call (open)
    bad_code_2 = """def resolve_key_aliases(raw_record):
    open("test.txt", "w").write("leak")
    return raw_record
"""
    passed, _, err = sandbox_test_patch(bad_code_2, "resolve_key_aliases", {"id": 1})
    assert passed is False
    assert "Forbidden function call: 'open()'" in err
    print(f"[OK] Sandbox successfully rejected dangerous call: {err}")

    # Test C: Wrong function name
    bad_code_3 = """def wrong_function_name(raw_record):
    return raw_record
"""
    passed, _, err = sandbox_test_patch(bad_code_3, "resolve_key_aliases", {"id": 1})
    assert passed is False
    assert "does not match expected helper" in err
    print(f"[OK] Sandbox rejected mismatching function signature: {err}")

    # -----------------------------------------------------------------------
    # TEST 3: Guardrail FAIL_SAFE Verification
    # -----------------------------------------------------------------------
    print("\n---> Testing FAIL_SAFE Guardrail (Hard Cap)...")
    orchestrator.reset_patches()
    
    # Run schema drift with fallback disabled and no Gemini client
    drift_data = inject_failure(generate_base_transactions(5), FailureType.SCHEMA_DRIFT)
    import app.pipeline.nodes as nodes
    orig_extract = nodes.node_extract
    nodes.node_extract = lambda url: RawBatch(
        source_url=url,
        status_code=200,
        raw_payload=drift_data,
        fetched_at="2026-09-25T16:00:00Z"
    )

    try:
        failsafe_res = await orchestrator.run_pipeline(
            source_url="mock://test",
            db_path=test_db,
            allow_fallback=False
        )
        assert failsafe_res.success is False
        assert failsafe_res.state == "FAIL_SAFE"
        print(f"[OK] FAIL_SAFE triggered correctly as expected: {failsafe_res.error}")
    finally:
        nodes.node_extract = orig_extract

    # -----------------------------------------------------------------------
    # TEST 4: Structured Events Verification
    # -----------------------------------------------------------------------
    print("\n---> Verifying Structured Event Stream for WebSocket Telemetry...")
    states_emitted = [e["state"] for e in captured_events]
    for required_state in ["PLAN", "EXTRACT", "CLEANSE", "DIAGNOSE", "FALLBACK_HEAL", "HOT_PATCH", "ENRICH", "VERIFY", "LOAD", "DONE", "FAIL_SAFE"]:
        assert required_state in states_emitted, f"Missing expected state event: {required_state}"
    print(f"[OK] Successfully verified stream of {len(captured_events)} structured events across transitions!")

    # Cleanup test db
    if os.path.exists(test_db):
        os.remove(test_db)

    print("\n" + "=" * 75)
    print("ALL COMPONENT 3 TESTS PASSED SUCCESSFULLY! 100% READY FOR LIVE DEMO.")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(test_component3())
