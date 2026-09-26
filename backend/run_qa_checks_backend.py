import asyncio
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pipeline.engine import PipelineEngine
from app.pipeline.schemas import FailureType, RunPipelineRequest
from app.agent.sandbox import sandbox_test_patch, validate_ast_security

async def test_all():
    print("=" * 70)
    print("RUNNING COMPREHENSIVE QA CHECKS ON PIPELINE ENGINE & FALLBACK")
    print("=" * 70)

    engine = PipelineEngine()
    
    scenarios = [
        FailureType.NONE,
        FailureType.SCHEMA_DRIFT,
        FailureType.TYPE_MUTATION,
        FailureType.ENVELOPE_RELOCATION,
        FailureType.MISSING_NULL_FIELDS,
        FailureType.CORRUPT_TIMESTAMP
    ]

    # --- Part 1: Run all 6 scenarios with Gemini enabled ---
    print("\n>>> PART 1: Live Engine Run across all 6 scenarios (Gemini enabled)")
    for sc in scenarios:
        engine.reset_patches()
        captured_events = []
        captured_logs = []
        
        # Capture listener events
        class MockWS:
            async def send_json(self, msg):
                if msg.get("event") == "agent_log":
                    captured_logs.append(msg["data"])
                captured_events.append(msg)
        
        ws = MockWS()
        engine.add_listener(ws)

        req = RunPipelineRequest(
            failure_scenario=sc,
            use_cached_patches=False,
            custom_records_count=5
        )
        t0 = time.time()
        res = await engine.run_pipeline(req)
        dur = round((time.time() - t0) * 1000, 2)
        engine.remove_listener(ws)

        patch = engine.active_patch_records.get("node_cleanse")
        print(f"Scenario: {sc.value:<22} | Success: {res['success']} | Healed: {res.get('was_healed')} | Duration: {dur}ms | Patch ID: {patch.id if patch else 'None'}")
        if patch:
            print(f"   Diagnosis: {patch.root_cause[:80]}...")
            print(f"   Code Diff sample: {patch.python_code.splitlines()[0] if patch.python_code else 'None'}")
        assert res["success"] is True, f"Failed {sc.value}: {res.get('error')}"

    # --- Part 2: Fallback Path with GEMINI_API_KEY Unset / Invalid ---
    print("\n>>> PART 2: Offline / Fallback Healer Verification (Unset API Key)")
    fallback_engine = PipelineEngine()
    # Unset API key
    fallback_engine.agent.api_key = ""
    fallback_engine.agent.client = None

    for sc in scenarios:
        fallback_engine.reset_patches()
        req = RunPipelineRequest(
            failure_scenario=sc,
            use_cached_patches=False,
            custom_records_count=5,
            gemini_api_key=""
        )
        res = await fallback_engine.run_pipeline(req)
        patch = fallback_engine.active_patch_records.get("node_cleanse")
        src_label = "fallback" if patch and ("Fallback" in patch.explanation or "Resilient" in patch.explanation) else ("N/A" if sc == FailureType.NONE else "gemini")
        print(f"Fallback Scenario: {sc.value:<22} | Success: {res['success']} | Healed: {res.get('was_healed')} | Source: {src_label}")
        assert res["success"] is True, f"Fallback failed for {sc.value}"

    # --- Part 3: Guardrail & Sandbox Test ---
    print("\n>>> PART 3: Guardrail & AST Sandbox Checks")
    # Test unsafe code with os.system / exec
    unsafe_code = """
import os
def coerce_amount(raw_input):
    os.system('echo compromised')
    return float(raw_input)
"""
    passed, fn, msg = sandbox_test_patch(unsafe_code, "coerce_amount", 100.0)
    print(f"Sandbox Unsafe Code (import os): Passed={passed} | Detail={msg}")
    assert passed is False, "Sandbox should REJECT import os!"

    unsafe_dunder = """
def coerce_amount(raw_input):
    return float(raw_input.__class__.__name__)
"""
    passed2, fn2, msg2 = sandbox_test_patch(unsafe_dunder, "coerce_amount", 100.0)
    print(f"Sandbox Dunder Code (__class__): Passed={passed2} | Detail={msg2}")
    assert passed2 is False, "Sandbox should REJECT dunder access!"

    # Test wrong function name
    wrong_fn = """
def malicious_worker(raw_input):
    return float(raw_input)
"""
    passed3, fn3, msg3 = sandbox_test_patch(wrong_fn, "coerce_amount", 100.0)
    print(f"Sandbox Wrong Name: Passed={passed3} | Detail={msg3}")
    assert passed3 is False, "Sandbox should REJECT mismatched function name!"

    print("\n[OK] All Part 1, 2, and 3 QA Checks PASSED 100%!")

if __name__ == "__main__":
    asyncio.run(test_all())
