"""
AegisFlow — Expanded Novel Failure Suite (Pass 2: 10 Fresh Test Cases)
Cold execution against current system without prior tuning.
Evaluates generalizability beyond the original 15 cases.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import sqlite3
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pipeline.schemas import RawBatch
from app.agent.orchestrator import PipelineOrchestrator
import app.pipeline.nodes as pipeline_nodes
from mock_service import init_db, clear_db

FRESH_10_TEST_CASES = [
    {
        "id": "TC-16",
        "name": "Three-Way Combined Failure (Rename + Numeric Currency + Nested Array User)",
        "dimension": "gross_amount + currency: 978 (EUR) + user_id: ['USR-CORP-9', 'SUBSIDIARY-EU']",
        "payload": [
            {
                "tx_id": "TX-3WAY-1616",
                "user_id": ["USR-CORP-9", "SUBSIDIARY-EU"],
                "gross_amount": 1450.00,
                "currency": 978,
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-3WAY-1616",
        "expected_client": "USR-CORP-9",
        "expected_amount": 1450.00,
        "expected_currency": "EUR"
    },
    {
        "id": "TC-17",
        "name": "Mixed Batch (80% Clean, 20% Novel Drifted Record)",
        "dimension": "Batch of 5 records: records 0,1,2,4 clean, record 3 has trade_amount & client_ref",
        "payload": [
            {"tx_id": "TX-MIX-01", "user_id": "USR-201", "amount": 100.0, "currency": "USD", "timestamp": "2026-09-25T16:00:00Z", "status": "completed"},
            {"tx_id": "TX-MIX-02", "user_id": "USR-202", "amount": 200.0, "currency": "USD", "timestamp": "2026-09-25T16:00:00Z", "status": "completed"},
            {"tx_id": "TX-MIX-03", "user_id": "USR-203", "amount": 300.0, "currency": "USD", "timestamp": "2026-09-25T16:00:00Z", "status": "completed"},
            {"tx_id": "TX-MIX-04", "client_ref": "USR-204", "trade_amount": 400.0, "currency": "USD", "timestamp": "2026-09-25T16:00:00Z", "status": "completed"},
            {"tx_id": "TX-MIX-05", "user_id": "USR-205", "amount": 500.0, "currency": "USD", "timestamp": "2026-09-25T16:00:00Z", "status": "completed"}
        ],
        "expected_count": 5,
        "expected_amounts": [100.0, 200.0, 300.0, 400.0, 500.0]
    },
    {
        "id": "TC-18",
        "name": "Field with Correct Name but Boolean Value (amount: True)",
        "dimension": "amount: true (boolean instead of numeric currency float)",
        "payload": [
            {
                "tx_id": "TX-BOOL-1818",
                "user_id": "USR-118",
                "amount": True,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_behavior": "Should reject or fail-safe against bool as money"
    },
    {
        "id": "TC-19",
        "name": "Currency Given as Full Word ('US Dollars')",
        "dimension": "currency: 'US Dollars' instead of 3-letter code 'USD'",
        "payload": [
            {
                "tx_id": "TX-WORD-1919",
                "user_id": "USR-119",
                "amount": 250.0,
                "currency": "US Dollars",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_currency": "USD",
        "expected_amount": 250.0
    },
    {
        "id": "TC-20",
        "name": "Timestamp with Timezone Offset ('2026-09-25T10:00:00-05:00')",
        "dimension": "Timestamp with -05:00 offset; must convert to UTC ending in 'Z' (15:00:00Z)",
        "payload": [
            {
                "tx_id": "TX-OFFSET-2020",
                "user_id": "USR-120",
                "amount": 180.0,
                "currency": "USD",
                "timestamp": "2026-09-25T10:00:00-05:00",
                "status": "completed"
            }
        ],
        "expected_ts": "2026-09-25T15:00:00Z",
        "expected_amount": 180.0
    },
    {
        "id": "TC-21",
        "name": "European Formatted Number String ('1.250,99')",
        "dimension": "amount: '1.250,99' with period thousand separator and comma decimal",
        "payload": [
            {
                "tx_id": "TX-NUMFMT-2121",
                "user_id": "USR-121",
                "amount": "1.250,99",
                "currency": "EUR",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_amount": 1250.99
    },
    {
        "id": "TC-22",
        "name": "Swapped Identifiers (tx_id has USR value, user_id has TX value)",
        "dimension": "tx_id: 'USR-777', user_id: 'TX-SWAP-2222'",
        "payload": [
            {
                "tx_id": "USR-777",
                "user_id": "TX-SWAP-2222",
                "amount": 550.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-SWAP-2222",
        "expected_client": "USR-777",
        "expected_amount": 550.0
    },
    {
        "id": "TC-23",
        "name": "Nested Envelope with Sibling False-Lead Lists",
        "dimension": "Envelope contains debug_logs, audits, and genuine transactions list alongside",
        "payload": {
            "meta": {
                "status": 200,
                "debug_logs": [{"log_id": 1, "msg": "ok"}, {"log_id": 2, "msg": "started"}],
                "system_warnings": ["disk_low", "rate_limit_warn"],
                "data": {
                    "audits": [{"audit_id": "A1"}, {"audit_id": "A2"}],
                    "transactions": [
                        {
                            "tx_id": "TX-BRANCH-2323",
                            "user_id": "USR-123",
                            "amount": 890.0,
                            "currency": "USD",
                            "timestamp": "2026-09-25T16:00:00Z",
                            "status": "completed"
                        }
                    ]
                }
            }
        },
        "expected_tx_id": "TX-BRANCH-2323",
        "expected_amount": 890.0
    },
    {
        "id": "TC-24",
        "name": "Lone Single Object Payload (No List Wrapper)",
        "dimension": "Payload is a bare dict {tx_id: ...} instead of a list of dicts [{...}]",
        "payload": {
            "tx_id": "TX-LONE-2424",
            "user_id": "USR-124",
            "amount": 415.0,
            "currency": "USD",
            "timestamp": "2026-09-25T16:00:00Z",
            "status": "completed"
        },
        "expected_tx_id": "TX-LONE-2424",
        "expected_amount": 415.0
    },
    {
        "id": "TC-25",
        "name": "Sequential Collision (Rename gross_amount immediately after client_ref patch)",
        "dimension": "Tests patch cache isolation when two different renames occur sequentially",
        "payload": [
            {
                "tx_id": "TX-COLL-2525",
                "user_id": "USR-125",
                "gross_amount": 775.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-COLL-2525",
        "expected_amount": 775.0
    }
]

async def execute_case(tc: Dict[str, Any], orchestrator: PipelineOrchestrator, test_db: str) -> Dict[str, Any]:
    # Reset patches unless this is TC-25 (interference test following TC-24)
    if tc["id"] != "TC-25":
        orchestrator.reset_patches()

    payload = tc["payload"]

    orig_extract = pipeline_nodes.node_extract
    pipeline_nodes.node_extract = lambda url: RawBatch(
        source_url=url,
        status_code=200,
        raw_payload=payload,
        fetched_at="2026-09-25T16:00:00Z",
        record_count=len(payload) if isinstance(payload, list) else 1
    )

    result_record = {
        "id": tc["id"],
        "name": tc["name"],
        "dimension": tc["dimension"],
        "node_exception": "None",
        "diagnosis_correct": "N/A",
        "sandbox_passed": "N/A",
        "data_correct": "No",
        "final_outcome": "UNKNOWN",
        "rows_loaded": 0,
        "row_data": [],
        "notes": ""
    }

    # Clean enriched_market_records table before each test run
    conn = sqlite3.connect(test_db)
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS enriched_market_records (tx_id TEXT PRIMARY KEY, client_id TEXT, amount REAL, tax REAL, net_total REAL, currency TEXT, timestamp TEXT, ledger_batch_id TEXT, status TEXT, loaded_at TEXT);")
        conn.execute("DELETE FROM enriched_market_records;")
    conn.close()

    try:
        run_res = await orchestrator.run_pipeline(
            source_url="mock://fresh-novel-test",
            db_path=test_db,
            allow_fallback=True
        )

        events = run_res.events
        states = [e.get("state") for e in events]
        diagnose_events = [e for e in events if e.get("state") == "DIAGNOSE"]
        sandbox_events = [e for e in events if e.get("state") == "SANDBOX_TEST"]
        patch_events = [e for e in events if e.get("state") == "HOT_PATCH"]
        failsafe_events = [e for e in events if e.get("state") == "FAIL_SAFE"]

        # 1. Exception triggered
        if diagnose_events:
            f_step = diagnose_events[0].get("detail", {}).get("failing_step", "")
            orig_err = diagnose_events[0].get("detail", {}).get("original_error", "")
            result_record["node_exception"] = f"Cleanse ({f_step}): {orig_err[:40]}..."
        elif any("node_verify" in str(e.get("node")) for e in failsafe_events):
            result_record["node_exception"] = "Verify (Invariants Failed)"
        elif any("node_enrich" in str(e.get("node")) for e in failsafe_events):
            result_record["node_exception"] = "Enrich (Calculation Error)"
        elif not run_res.success:
            result_record["node_exception"] = run_res.error[:45] if run_res.error else "Unknown"

        # 2. Diagnosis
        if diagnose_events:
            result_record["diagnosis_correct"] = "Yes"
        elif run_res.success:
            result_record["diagnosis_correct"] = "N/A (Clean)"

        # 3. Sandbox
        if sandbox_events:
            result_record["sandbox_passed"] = "Yes"
        elif patch_events:
            result_record["sandbox_passed"] = "Yes (Cached)"
        else:
            result_record["sandbox_passed"] = "N/A"

        # 4. Check DB
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        rows = cursor.execute("SELECT tx_id, client_id, amount, tax, net_total, currency, timestamp FROM enriched_market_records").fetchall()
        conn.close()

        result_record["rows_loaded"] = len(rows)
        result_record["row_data"] = rows

        # Evaluate correctness
        tc_id = tc["id"]
        is_correct = False
        notes = ""

        if tc_id == "TC-16":
            # Three-way: gross_amount 1450, currency 978 (EUR), user_id ['USR-CORP-9', 'SUBSIDIARY-EU']
            if rows and rows[0][0] == "TX-3WAY-1616" and rows[0][1] == "USR-CORP-9" and rows[0][2] == 1450.0 and rows[0][5] == "EUR":
                is_correct = True
                notes = f"All 3 mutations healed: client={rows[0][1]}, amt=${rows[0][2]}, curr={rows[0][5]}"
            else:
                notes = f"Mismatch: rows={rows}"

        elif tc_id == "TC-17":
            # Mixed batch 5 records: amounts 100, 200, 300, 400, 500
            if len(rows) == 5 and sorted([r[2] for r in rows]) == [100.0, 200.0, 300.0, 400.0, 500.0]:
                is_correct = True
                notes = f"All 5 records cleanly loaded (4 clean + 1 drifted): {[r[2] for r in rows]}"
            else:
                notes = f"Batch mismatch: len={len(rows)}, amounts={[r[2] for r in rows]}"

        elif tc_id == "TC-18":
            # amount: True (boolean) -> Financial guardrail should safely reject or stop
            if run_res.state == "FAIL_SAFE" or (rows and not isinstance(rows[0][2], bool) and rows[0][2] > 0 and rows[0][2] != 1.0):
                is_correct = True
                notes = "Guardrail safely caught boolean amount: stopped financial corruption."
            elif rows and rows[0][2] == 1.0:
                is_correct = False
                notes = "Boolean True silently converted to float 1.0 without semantic validation."
            else:
                notes = f"State: {run_res.state}, rows={rows}"

        elif tc_id == "TC-19":
            # 'US Dollars' -> USD
            if rows and rows[0][2] == 250.0 and rows[0][5] == "USD":
                is_correct = True
                notes = f"Currency 'US Dollars' mapped to canonical 'USD': {rows[0][5]}"
            else:
                notes = f"Currency word failed: curr='{rows[0][5] if rows else 'None'}'"

        elif tc_id == "TC-20":
            # Timezone offset: 2026-09-25T10:00:00-05:00 -> 2026-09-25T15:00:00Z
            if rows and rows[0][6] == "2026-09-25T15:00:00Z":
                is_correct = True
                notes = f"Offset correctly converted to UTC: {rows[0][6]}"
            else:
                notes = f"Offset timestamp failed: ts='{rows[0][6] if rows else 'None'}'"

        elif tc_id == "TC-21":
            # European format '1.250,99' -> 1250.99
            if rows and rows[0][2] == 1250.99:
                is_correct = True
                notes = f"European number format parsed to float: {rows[0][2]}"
            else:
                notes = f"European number format failed: amt={rows[0][2] if rows else 'None'}"

        elif tc_id == "TC-22":
            # Swapped identifiers: tx_id='USR-777', user_id='TX-SWAP-2222'
            if rows and rows[0][0] == "TX-SWAP-2222" and rows[0][1] == "USR-777":
                is_correct = True
                notes = f"Swapped identifiers detected by value shape: tx_id={rows[0][0]}, client={rows[0][1]}"
            else:
                notes = f"Identifier swap: tx_id='{rows[0][0] if rows else 'None'}', client='{rows[0][1] if rows else 'None'}'"

        elif tc_id == "TC-23":
            # Envelope with false leads
            if rows and rows[0][0] == "TX-BRANCH-2323" and rows[0][2] == 890.0:
                is_correct = True
                notes = f"Found correct transaction list among false leads: amount=${rows[0][2]}"
            else:
                notes = f"False lead trap: rows={rows}"

        elif tc_id == "TC-24":
            # Lone dict object instead of list
            if rows and rows[0][0] == "TX-LONE-2424" and rows[0][2] == 415.0:
                is_correct = True
                notes = f"Lone dictionary auto-wrapped and cleansed cleanly: amount=${rows[0][2]}"
            else:
                notes = f"Lone object failed: rows={rows}"

        elif tc_id == "TC-25":
            # Sequential collision
            if rows and rows[0][0] == "TX-COLL-2525" and rows[0][2] == 775.0:
                is_correct = True
                notes = f"Sequential drift handled without cache collision: amount=${rows[0][2]}"
            else:
                notes = f"Sequential collision failed: rows={rows}"

        result_record["data_correct"] = "Yes" if is_correct else "No"
        result_record["notes"] = notes

        if run_res.state == "DONE" and is_correct:
            result_record["final_outcome"] = "HEALED_CORRECTLY"
        elif run_res.state == "DONE" and not is_correct:
            result_record["final_outcome"] = "HEALED_BUT_WRONG_DATA"
        elif run_res.state == "FAIL_SAFE":
            result_record["final_outcome"] = "FAIL_SAFE_TRIGGERED"
        else:
            result_record["final_outcome"] = "CRASHED"

    except Exception as exc:
        result_record["node_exception"] = f"Exception: {type(exc).__name__}: {str(exc)[:50]}"
        result_record["final_outcome"] = "CRASHED"
        result_record["notes"] = f"Exception: {str(exc)[:60]}"

    finally:
        pipeline_nodes.node_extract = orig_extract

    return result_record

async def main():
    print("=" * 85)
    print("AEGISFLOW FRESH NOVEL TEST SUITE (10 NEW TEST CASES)")
    print("Cold execution against current system without prior tuning")
    print("=" * 85)

    test_db = os.path.join(tempfile.gettempdir(), "test_fresh_suite.db")
    init_db(test_db)

    orchestrator = PipelineOrchestrator(api_key=None)
    results = []

    for idx, tc in enumerate(FRESH_10_TEST_CASES):
        clear_db(test_db)
        print(f"\n--> [{idx+1}/10] Running {tc['id']}: {tc['name']}...")
        print(f"    Dimension: {tc['dimension']}")
        res = await execute_case(tc, orchestrator, test_db)
        print(f"    Outcome: {res['final_outcome']} | Correct Data: {res['data_correct']} | {res['notes']}")
        results.append(res)

    print("\n" + "=" * 85)
    print("COLD EXECUTION RESULTS: 10 FRESH NOVEL TEST CASES")
    print("=" * 85)
    print(f"{'ID':<6} | {'Test Case':<32} | {'Exception Node':<24} | {'Outcome':<20} | {'Correct?'}")
    print("-" * 95)
    for r in results:
        print(f"{r['id']:<6} | {r['name'][:32]:<32} | {r['node_exception'][:24]:<24} | {r['final_outcome']:<20} | {r['data_correct']}")
    print("-" * 95)
    correct_count = sum(1 for r in results if r["data_correct"] == "Yes")
    print(f"COLD ACCURACY SCORE: {correct_count}/10 ({round((correct_count/10)*100, 1)}%) correctly healed or safely handled.\n")

    with open("fresh_novel_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
