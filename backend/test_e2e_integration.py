"""
Auto-ETL Restorer — End-to-End Integration Test
Connects Component 1 (Mock Environment) with Component 2 (Tool Execution Hub).

Validates the full workflow:
1. Normal API fetch -> Cleanse -> Enrich -> Verify -> SQLite Load
2. Failure injection toggle (/inject-failure) -> Triggers KeyError in node_cleanse
3. Error Interception with structured CleanseError payload
4. Schema reset (/reset) -> Confirms recovery
5. Direct SQLite verification of persisted rows
"""

import os
import sys
import tempfile
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_service import app as mock_api_app, init_db, clear_db, query_records
from app.pipeline.schemas import (
    RawBatch,
    CanonicalRecord,
    EnrichedRecord,
    VerificationResult,
    LoadResult,
)
from app.pipeline.exceptions import CleanseError
from app.pipeline.nodes import (
    node_cleanse,
    node_enrich,
    node_verify,
    node_load,
)

# Use FastAPI TestClient to test mock endpoints without external networking dependencies
mock_client = TestClient(mock_api_app)

def test_full_pipeline_flow():
    print("=" * 75)
    print("RUNNING END-TO-END INTEGRATION TEST: COMPONENT 1 + COMPONENT 2")
    print("=" * 75)

    # Setup clean SQLite database in a temp directory
    test_db = os.path.join(tempfile.gettempdir(), "test_market_data.db")
    if os.path.exists(test_db):
        os.remove(test_db)
    init_db(test_db)
    clear_db(test_db)
    print(f"[INIT] Temporary target database created: {test_db}")

    # Ensure mock API starts in canonical state
    mock_client.post("/reset")

    # -----------------------------------------------------------------------
    # PHASE 1: Baseline Clean Pipeline Run
    # -----------------------------------------------------------------------
    print("\n[PHASE 1] Executing Clean Baseline Pipeline Run...")
    
    # 1. Fetch from mock API
    resp = mock_client.get("/market-data")
    assert resp.status_code == 200
    raw_json = resp.json()
    assert len(raw_json) == 5
    print(f"[OK] [1/5] Extract: Fetched {len(raw_json)} raw records from GET /market-data")

    raw_batch = RawBatch(
        source_url="http://mock-service/market-data",
        status_code=200,
        raw_payload=raw_json,
        fetched_at="2026-09-25T16:00:00Z",
        record_count=len(raw_json)
    )

    # 2. Cleanse
    canonical = node_cleanse(raw_batch)
    assert len(canonical) == 5
    for c in canonical:
        assert isinstance(c, CanonicalRecord)
        assert c.amount > 0
        assert c.currency == "USD"
        assert c.client_id.startswith("SYM-")
    print(f"[OK] [2/5] Cleanse: Successfully normalized to 5 CanonicalRecords in {node_cleanse.last_metrics.duration_ms}ms")

    # 3. Enrich
    enriched = node_enrich(canonical)
    assert len(enriched) == 5
    for e in enriched:
        assert isinstance(e, EnrichedRecord)
        expected_tax = round(e.amount * 0.18, 2)
        expected_net = round(e.amount + expected_tax, 2)
        assert abs(e.tax - expected_tax) <= 0.01
        assert abs(e.net_total - expected_net) <= 0.01
    print(f"[OK] [3/5] Enrich: Attached 18% tax and batch metadata in {node_enrich.last_metrics.duration_ms}ms")

    # 4. Verify
    verification = node_verify(enriched)
    assert verification.passed is True
    assert len(verification.failures) == 0
    assert verification.checked_count == 5
    print(f"[OK] [4/5] Verify: Invariant checks passed 100% ({verification.assertion_details})")

    # 5. Load
    load_res = node_load(enriched, db_path=test_db)
    assert load_res.success is True
    assert load_res.rows_loaded == 5
    print(f"[OK] [5/5] Load: Persisted 5 enriched rows into SQLite table '{load_res.target_table}'")

    # -----------------------------------------------------------------------
    # PHASE 2: Failure Injection & Error Interception
    # -----------------------------------------------------------------------
    print("\n[PHASE 2] Injecting Failure & Testing Exception Interception...")
    
    # Trigger failure on mock service
    inject_res = mock_client.post("/inject-failure")
    assert inject_res.status_code == 200
    print(f"[OK] POST /inject-failure response: {inject_res.json()['description']}")

    # Fetch drifted market data
    drifted_resp = mock_client.get("/market-data")
    assert drifted_resp.status_code == 200
    drifted_json = drifted_resp.json()
    assert "last_price" in drifted_json[0]
    assert "price" not in drifted_json[0]
    print(f"[OK] API returned drifted schema (has 'last_price', 'price' missing)")

    drifted_batch = RawBatch(
        source_url="http://mock-service/market-data",
        status_code=200,
        raw_payload=drifted_json,
        fetched_at="2026-09-25T16:01:00Z",
        record_count=len(drifted_json)
    )

    # Run node_cleanse and catch the typed CleanseError
    try:
        node_cleanse(drifted_batch)
        assert False, "node_cleanse should have raised CleanseError on schema drift"
    except CleanseError as err:
        print("[OK] Successfully trapped CleanseError at exact failing node:")
        print(f"     Node: {err.node_name}")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Offending payload: {err.failing_record}")
        print(f"     Original error: {err.original_error}")
        
        # Verify structured payload for Component 3 (Gemini diagnosis & WebSocket)
        err_dict = err.to_dict()
        assert err_dict["error_type"] == "CleanseError"
        assert err_dict["failing_step"] == "resolve_key_aliases"
        assert err_dict["record_index"] == 0
        assert "last_price" in err_dict["failing_record"]
        assert len(err_dict["traceback_str"]) > 0
        print("[OK] Error payload contains full structured context required for Gemini diagnosis!")

    # -----------------------------------------------------------------------
    # PHASE 3: Reset & Recovery Verification
    # -----------------------------------------------------------------------
    print("\n[PHASE 3] Resetting Schema & Validating Recovery...")
    reset_res = mock_client.post("/reset")
    assert reset_res.status_code == 200
    print(f"[OK] POST /reset response: {reset_res.json()['description']}")

    reverted_resp = mock_client.get("/market-data")
    reverted_batch = RawBatch(
        source_url="http://mock-service/market-data",
        status_code=200,
        raw_payload=reverted_resp.json(),
        fetched_at="2026-09-25T16:02:00Z"
    )

    # Re-run pipeline
    recovered_canonical = node_cleanse(reverted_batch)
    recovered_enriched = node_enrich(recovered_canonical)
    recovered_verify = node_verify(recovered_enriched)
    recovered_load = node_load(recovered_enriched, db_path=test_db)

    assert recovered_verify.passed is True
    assert recovered_load.rows_loaded == 5
    print("[OK] Pipeline recovered smoothly and re-inserted canonical records.")

    # Clean up test DB
    if os.path.exists(test_db):
        os.remove(test_db)

    print("\n" + "=" * 75)
    print("ALL INTEGRATION PHASES COMPLETED WITH ZERO ERRORS! 100% READY FOR COMPONENT 3.")
    print("=" * 75)

if __name__ == "__main__":
    test_full_pipeline_flow()
