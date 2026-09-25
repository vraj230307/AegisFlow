"""
Test suite for Auto-ETL Restorer — Component 2: Tool Execution Hub
Tests node_extract and node_cleanse across all 6 scenarios:
1. Clean Baseline (passes through with no errors)
2. Schema Drift (raises CleanseError at resolve_key_aliases)
3. Type Mutation (raises CleanseError at coerce_amount)
4. Envelope Relocation (raises CleanseError at unwrap_envelope)
5. Missing/Null Fields (raises CleanseError at resolve_key_aliases)
6. Corrupt Timestamps (raises CleanseError at normalize_timestamp)
Plus:
- node_extract network/HTTP error handling (raises ExtractError)
- Pydantic model serialization and timing wrapper verification
"""

import sys
import os
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pipeline.schemas import (
    RawBatch,
    CanonicalRecord,
    FailureType,
    ExtractErrorPayload,
    CleanseErrorPayload,
)
from app.pipeline.exceptions import ExtractError, CleanseError
from app.pipeline.failures import generate_base_transactions, inject_failure
from app.pipeline.nodes import node_extract, node_cleanse

def test_component2_nodes():
    print("=" * 70)
    print("TESTING COMPONENT 2: TOOL EXECUTION HUB (node_extract & node_cleanse)")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # TEST 1: node_extract with Connection Error
    # -----------------------------------------------------------------------
    print("\n[TEST 1/7] Testing node_extract exception handling on invalid host...")
    try:
        node_extract("http://127.0.0.1:9999/non-existent-endpoint", timeout=0.5)
        assert False, "node_extract should have raised ExtractError for unavailable endpoint"
    except ExtractError as err:
        print("[OK] Caught expected ExtractError:")
        print(f"     Message: {err.message}")
        print(f"     Source URL: {err.source_url}")
        print(f"     Original Error: {err.original_error}")
        assert err.node_name == "node_extract"
        assert err.source_url == "http://127.0.0.1:9999/non-existent-endpoint"
        assert len(err.traceback_str) > 0
        assert isinstance(err.to_dict(), dict)

    # -----------------------------------------------------------------------
    # TEST 2: Scenario 1 — Clean Baseline
    # -----------------------------------------------------------------------
    print("\n[TEST 2/7] Testing Scenario 1: Clean Baseline through node_cleanse...")
    clean_data = generate_base_transactions(count=5)
    raw_clean = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=clean_data,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        record_count=len(clean_data)
    )

    canonical_records = node_cleanse(raw_clean)
    assert len(canonical_records) == 5, f"Expected 5 records, got {len(canonical_records)}"
    for idx, r in enumerate(canonical_records):
        assert isinstance(r, CanonicalRecord)
        assert r.tx_id.startswith("TX-")
        assert isinstance(r.amount, float)
        assert r.amount > 0
        assert r.currency in ["USD", "EUR", "GBP", "JPY", "INR"]
        assert r.client_id.startswith("USR-")
        assert r.timestamp.endswith("Z")

    # Check timing decorator stats
    assert node_cleanse.last_metrics is not None
    assert node_cleanse.last_metrics.success is True
    assert node_cleanse.last_metrics.duration_ms >= 0
    print(f"[OK] Clean baseline passed 100% (5 records parsed in {node_cleanse.last_metrics.duration_ms}ms).")
    print(f"     Sample CanonicalRecord: {canonical_records[0].model_dump()}")

    # -----------------------------------------------------------------------
    # TEST 3: Scenario 2 — Schema Drift (tx_id -> reference_id, amount -> gross_amount)
    # -----------------------------------------------------------------------
    print("\n[TEST 3/7] Testing Scenario 2: Schema Drift...")
    drifted_data = inject_failure(clean_data, FailureType.SCHEMA_DRIFT)
    raw_drifted = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=drifted_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        node_cleanse(raw_drifted)
        assert False, "node_cleanse should have raised CleanseError on schema drift"
    except CleanseError as err:
        print("[OK] Caught expected CleanseError on Schema Drift:")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Original error: {err.original_error}")
        assert err.failing_step == "resolve_key_aliases", f"Expected resolve_key_aliases, got {err.failing_step}"
        assert err.record_index == 0
        assert "reference_id" in err.failing_record
        assert "gross_amount" in err.failing_record
        assert "tx_id" in err.original_error or "KeyError" in err.original_error
        assert len(err.traceback_str) > 0

    # -----------------------------------------------------------------------
    # TEST 4: Scenario 3 — Type Mutation (price string formatted with symbol)
    # -----------------------------------------------------------------------
    print("\n[TEST 4/7] Testing Scenario 3: Type Mutation (amount as formatted currency string)...")
    mutated_data = inject_failure(clean_data, FailureType.TYPE_MUTATION)
    raw_mutated = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=mutated_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        node_cleanse(raw_mutated)
        assert False, "node_cleanse should have raised CleanseError on type mutation"
    except CleanseError as err:
        print("[OK] Caught expected CleanseError on Type Mutation:")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Original error: {err.original_error}")
        assert err.failing_step == "coerce_amount", f"Expected coerce_amount, got {err.failing_step}"
        assert err.record_index == 0
        assert isinstance(err.failing_record["amount"], str)
        assert "ValueError" in err.original_error
        assert len(err.traceback_str) > 0

    # -----------------------------------------------------------------------
    # TEST 5: Scenario 4 — Envelope Relocation (nested inside response_payload.items)
    # -----------------------------------------------------------------------
    print("\n[TEST 5/7] Testing Scenario 4: Envelope Relocation...")
    nested_data = inject_failure(clean_data, FailureType.ENVELOPE_RELOCATION)
    raw_nested = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=nested_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        node_cleanse(raw_nested)
        assert False, "node_cleanse should have raised CleanseError on envelope relocation"
    except CleanseError as err:
        print("[OK] Caught expected CleanseError on Envelope Relocation:")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Original error: {err.original_error}")
        assert err.failing_step == "unwrap_envelope", f"Expected unwrap_envelope, got {err.failing_step}"
        assert err.record_index is None
        assert isinstance(err.failing_record, dict)
        assert "response_payload" in err.failing_record
        assert "TypeError" in err.original_error
        assert len(err.traceback_str) > 0

    # -----------------------------------------------------------------------
    # TEST 6: Scenario 5 — Missing / Null Fields (missing currency, user_id=None)
    # -----------------------------------------------------------------------
    print("\n[TEST 6/7] Testing Scenario 5: Missing / Null Fields...")
    missing_data = inject_failure(clean_data, FailureType.MISSING_NULL_FIELDS)
    raw_missing = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=missing_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        node_cleanse(raw_missing)
        assert False, "node_cleanse should have raised CleanseError on missing/null fields"
    except CleanseError as err:
        print("[OK] Caught expected CleanseError on Missing/Null Fields:")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Original error: {err.original_error}")
        assert err.failing_step == "resolve_key_aliases", f"Expected resolve_key_aliases, got {err.failing_step}"
        assert "ValueError" in err.original_error
        assert len(err.traceback_str) > 0

    # -----------------------------------------------------------------------
    # TEST 7: Scenario 6 — Corrupt Timestamps (epoch ms int / slash format)
    # -----------------------------------------------------------------------
    print("\n[TEST 7/7] Testing Scenario 6: Corrupt Timestamps...")
    corrupt_ts_data = inject_failure(clean_data, FailureType.CORRUPT_TIMESTAMP)
    raw_corrupt = RawBatch(
        source_url="http://mock-api/market-data",
        status_code=200,
        raw_payload=corrupt_ts_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        node_cleanse(raw_corrupt)
        assert False, "node_cleanse should have raised CleanseError on corrupt timestamp"
    except CleanseError as err:
        print("[OK] Caught expected CleanseError on Corrupt Timestamps:")
        print(f"     Failing step: {err.failing_step}")
        print(f"     Record index: {err.record_index}")
        print(f"     Original error: {err.original_error}")
        assert err.failing_step == "normalize_timestamp", f"Expected normalize_timestamp, got {err.failing_step}"
        assert ("TypeError" in err.original_error) or ("ValueError" in err.original_error)
        assert len(err.traceback_str) > 0

    print("\n" + "=" * 70)
    print("ALL 7 COMPONENT 2 TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    test_component2_nodes()
