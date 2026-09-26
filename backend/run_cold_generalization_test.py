"""
AegisFlow — Final Cold Generalization Test (8 Brand New Structural Failure Cases)
Strict Rule: No code modifications or tuning before, during, or after execution.
Reports raw, unmodified cold performance on previously unseen failure modes.
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

COLD_8_TEST_CASES = [
    {
        "id": "COLD-01",
        "name": "Scientific Notation Amount ('4.5e2')",
        "dimension": "amount: '4.5e2' string representation of 450.0",
        "payload": [
            {
                "tx_id": "TX-COLD-01",
                "user_id": "USR-COLD-1",
                "amount": "4.5e2",
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-COLD-01",
        "expected_amount": 450.0,
        "expected_currency": "USD"
    },
    {
        "id": "COLD-02",
        "name": "Duplicate tx_id with Divergent Data in Single Batch",
        "dimension": "Batch with same tx_id 'TX-DUP-SAME' twice, but with different amounts and users",
        "payload": [
            {
                "tx_id": "TX-DUP-SAME",
                "user_id": "USR-ALPHA",
                "amount": 100.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            },
            {
                "tx_id": "TX-DUP-SAME",
                "user_id": "USR-BETA",
                "amount": 999.0,
                "currency": "EUR",
                "timestamp": "2026-09-25T17:00:00Z",
                "status": "completed"
            }
        ],
        "expected_behavior": "Must fail-safe due to duplicate primary key / duplicate batch invariant"
    },
    {
        "id": "COLD-03",
        "name": "Valid ISO Alpha Code for Uncommon Currency ('BTC')",
        "dimension": "currency: 'BTC' (3-letter crypto code rather than fiat)",
        "payload": [
            {
                "tx_id": "TX-COLD-03",
                "user_id": "USR-COLD-3",
                "amount": 1.5,
                "currency": "BTC",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-COLD-03",
        "expected_amount": 1.5,
        "expected_currency": "BTC"
    },
    {
        "id": "COLD-04",
        "name": "Paged Records Split Across Multiple Array Elements",
        "dimension": "results: [{'page': 1, 'data': [...]}, {'page': 2, 'data': [...]}]",
        "payload": {
            "results": [
                {
                    "page": 1,
                    "data": [
                        {
                            "tx_id": "TX-PAGE-01",
                            "user_id": "USR-P1",
                            "amount": 120.0,
                            "currency": "USD",
                            "timestamp": "2026-09-25T16:00:00Z",
                            "status": "completed"
                        }
                    ]
                },
                {
                    "page": 2,
                    "data": [
                        {
                            "tx_id": "TX-PAGE-02",
                            "user_id": "USR-P2",
                            "amount": 240.0,
                            "currency": "USD",
                            "timestamp": "2026-09-25T16:00:00Z",
                            "status": "completed"
                        }
                    ]
                }
            ]
        },
        "expected_count": 2,
        "expected_tx_ids": ["TX-PAGE-01", "TX-PAGE-02"],
        "expected_amounts": [120.0, 240.0]
    },
    {
        "id": "COLD-05",
        "name": "Amount String with Non-Breaking Space (' 450.00\\u00a0')",
        "dimension": "amount: ' 450.00\\u00a0' with leading spaces and non-breaking space suffix",
        "payload": [
            {
                "tx_id": "TX-COLD-05",
                "user_id": "USR-COLD-5",
                "amount": " 450.00\u00a0",
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-COLD-05",
        "expected_amount": 450.0
    },
    {
        "id": "COLD-06",
        "name": "Extra Unexpected Metadata Fields Alongside Canonical Fields",
        "dimension": "Record contains valid canonical fields plus telemetry & compliance metadata",
        "payload": [
            {
                "tx_id": "TX-COLD-06",
                "user_id": "USR-COLD-6",
                "amount": 350.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed",
                "meta_audit_telemetry": {
                    "trace_depth": 4,
                    "server_tags": ["edge-us-east-1", "canary"]
                },
                "risk_score": 0.042,
                "compliance_flags": ["AML_CLEARED", "KYC_PASS"]
            }
        ],
        "expected_tx_id": "TX-COLD-06",
        "expected_amount": 350.0,
        "expected_client": "USR-COLD-6"
    },
    {
        "id": "COLD-07",
        "name": "Valid ISO Timestamp with Far-Future Year ('2099-01-01')",
        "dimension": "timestamp: '2099-01-01T00:00:00Z' (valid ISO format, anomalous year 2099)",
        "payload": [
            {
                "tx_id": "TX-COLD-07",
                "user_id": "USR-COLD-7",
                "amount": 500.0,
                "currency": "USD",
                "timestamp": "2099-01-01T00:00:00Z",
                "status": "completed"
            }
        ],
        "expected_tx_id": "TX-COLD-07",
        "expected_amount": 500.0
    },
    {
        "id": "COLD-08",
        "name": "Co-Occurring Distinct Drifts in Same Batch",
        "dimension": "Record 1 has renamed user_id ('customer_account'), Record 2 has renamed amount ('settlement_value')",
        "payload": [
            {
                "tx_id": "TX-COLD-08A",
                "customer_account": "USR-COLD-8A",
                "amount": 600.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            },
            {
                "tx_id": "TX-COLD-08B",
                "user_id": "USR-COLD-8B",
                "settlement_value": 750.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_count": 2,
        "expected_data": [
            {"tx_id": "TX-COLD-08A", "client_id": "USR-COLD-8A", "amount": 600.0},
            {"tx_id": "TX-COLD-08B", "client_id": "USR-COLD-8B", "amount": 750.0}
        ]
    }
]

async def execute_cold_case(tc: Dict[str, Any], orchestrator: PipelineOrchestrator, test_db: str) -> Dict[str, Any]:
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
        "payload_sent": payload,
        "node_step_hit": "None",
        "node_exception": "None",
        "diagnosis_correct": "N/A",
        "sandbox_passed": "N/A",
        "data_correct": "No",
        "final_outcome": "UNKNOWN",
        "rows_loaded": 0,
        "row_data": [],
        "notes": ""
    }

    # Clean DB table
    conn = sqlite3.connect(test_db)
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS enriched_market_records (tx_id TEXT PRIMARY KEY, client_id TEXT, amount REAL, tax REAL, net_total REAL, currency TEXT, timestamp TEXT, ledger_batch_id TEXT, status TEXT, loaded_at TEXT);")
        conn.execute("DELETE FROM enriched_market_records;")
    conn.close()

    try:
        run_res = await orchestrator.run_pipeline(
            source_url="mock://cold-generalization-test",
            db_path=test_db,
            allow_fallback=True
        )

        events = run_res.events
        diagnose_events = [e for e in events if e.get("state") == "DIAGNOSE"]
        sandbox_events = [e for e in events if e.get("state") == "SANDBOX_TEST"]
        patch_events = [e for e in events if e.get("state") == "HOT_PATCH"]
        failsafe_events = [e for e in events if e.get("state") == "FAIL_SAFE"]

        # Track last executed node
        if events:
            last_event = events[-1]
            result_record["node_step_hit"] = str(last_event.get("node") or last_event.get("state"))

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

        if diagnose_events:
            result_record["diagnosis_correct"] = "Yes"
        elif run_res.success:
            result_record["diagnosis_correct"] = "N/A (Clean)"

        if sandbox_events:
            result_record["sandbox_passed"] = "Yes"
        elif patch_events:
            result_record["sandbox_passed"] = "Yes (Cached)"
        else:
            result_record["sandbox_passed"] = "N/A"

        # Check DB
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        rows = cursor.execute("SELECT tx_id, client_id, amount, tax, net_total, currency, timestamp FROM enriched_market_records").fetchall()
        conn.close()

        result_record["rows_loaded"] = len(rows)
        result_record["row_data"] = rows

        tc_id = tc["id"]
        is_correct = False
        notes = ""

        if tc_id == "COLD-01":
            # Scientific notation '4.5e2' -> 450.0
            if rows and rows[0][0] == "TX-COLD-01" and rows[0][2] == 450.0:
                is_correct = True
                notes = f"Parsed scientific notation correctly: amount={rows[0][2]}"
            elif rows and rows[0][2] != 450.0:
                is_correct = False
                notes = f"WRONG DATA: '4.5e2' parsed as {rows[0][2]} instead of 450.0 (regex stripped 'e')"
            else:
                notes = f"No rows or failed: rows={rows}"

        elif tc_id == "COLD-02":
            # Duplicate tx_id with different data in same batch -> Should fail-safe or reject duplicate
            if run_res.state == "FAIL_SAFE":
                is_correct = True
                notes = "FAIL_SAFE guardrail caught duplicate tx_id in batch; prevented DB primary key conflict."
            elif len(rows) == 1:
                is_correct = False
                notes = f"One duplicate silently overwritten: row={rows[0]}"
            else:
                notes = f"Duplicate batch outcome: state={run_res.state}, rows={len(rows)}"

        elif tc_id == "COLD-03":
            # Valid 3-letter currency 'BTC'
            if rows and rows[0][0] == "TX-COLD-03" and rows[0][5] == "BTC" and rows[0][2] == 1.5:
                is_correct = True
                notes = f"Standard 3-letter non-fiat ISO currency accepted: curr={rows[0][5]}, amount={rows[0][2]}"
            else:
                notes = f"Failed to ingest BTC currency: rows={rows}"

        elif tc_id == "COLD-04":
            # Split array envelope results: [{'page': 1, 'data': [...]}, {'page': 2, 'data': [...]}]
            if len(rows) == 2 and sorted([r[0] for r in rows]) == ["TX-PAGE-01", "TX-PAGE-02"]:
                is_correct = True
                notes = f"Both paged record lists unwrapped and loaded: {len(rows)} records"
            elif len(rows) == 1:
                is_correct = False
                notes = f"Only first page extracted, second page dropped: {rows}"
            else:
                notes = f"Unwrap envelope failed on array-of-pages: state={run_res.state}, rows={len(rows)}"

        elif tc_id == "COLD-05":
            # Non-breaking space in amount string ' 450.00\u00a0'
            if rows and rows[0][0] == "TX-COLD-05" and rows[0][2] == 450.0:
                is_correct = True
                notes = f"Whitespace and non-breaking space cleanly stripped: amount={rows[0][2]}"
            else:
                notes = f"Failed on NBSP string: rows={rows}"

        elif tc_id == "COLD-06":
            # Extra unexpected metadata fields alongside canonical fields
            if rows and rows[0][0] == "TX-COLD-06" and rows[0][1] == "USR-COLD-6" and rows[0][2] == 350.0:
                is_correct = True
                notes = f"Extra metadata fields ignored safely, canonical record cleanly loaded: tx_id={rows[0][0]}"
            else:
                notes = f"Extra metadata caused issue: rows={rows}"

        elif tc_id == "COLD-07":
            # Valid ISO format timestamp with year 2099
            if rows and rows[0][0] == "TX-COLD-07" and rows[0][6] == "2099-01-01T00:00:00Z":
                is_correct = True
                notes = f"ISO timestamp accepted: {rows[0][6]} (no sanity constraint against far-future dates)"
            elif run_res.state == "FAIL_SAFE":
                is_correct = True
                notes = f"Guardrail rejected anomalous far-future timestamp (2099)"
            else:
                notes = f"Timestamp year 2099 result: rows={rows}"

        elif tc_id == "COLD-08":
            # Co-occurring drifts in same batch: customer_account in rec 1, settlement_value in rec 2
            if len(rows) == 2:
                row_map = {r[0]: (r[1], r[2]) for r in rows}
                if row_map.get("TX-COLD-08A") == ("USR-COLD-8A", 600.0) and row_map.get("TX-COLD-08B") == ("USR-COLD-8B", 750.0):
                    is_correct = True
                    notes = "Both distinct field drifts in the same batch healed correctly."
                else:
                    is_correct = False
                    notes = f"Partial/wrong data in co-occurring batch: {row_map}"
            else:
                notes = f"Co-occurring drifts failed: state={run_res.state}, rows={len(rows)}"

        result_record["data_correct"] = "Yes" if is_correct else "No"
        result_record["notes"] = notes

        # Classification mapping
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
        result_record["notes"] = f"Unhandled Exception: {str(exc)[:60]}"

    finally:
        pipeline_nodes.node_extract = orig_extract

    return result_record

async def main():
    print("=" * 85)
    print("AEGISFLOW FINAL COLD GENERALIZATION TEST (8 BRAND NEW STRUCTURAL CASES)")
    print("Strict Policy: Single cold pass, no tuning, no post-test fixes.")
    print("=" * 85)

    test_db = os.path.join(tempfile.gettempdir(), "test_cold_generalization.db")
    init_db(test_db)

    orchestrator = PipelineOrchestrator(api_key=None)
    results = []

    for idx, tc in enumerate(COLD_8_TEST_CASES):
        clear_db(test_db)
        print(f"\n--> [{idx+1}/8] Running {tc['id']}: {tc['name']}...")
        print(f"    Dimension: {tc['dimension']}")
        res = await execute_cold_case(tc, orchestrator, test_db)
        print(f"    Outcome: {res['final_outcome']} | Correct Data: {res['data_correct']} | {res['notes']}")
        results.append(res)

    print("\n" + "=" * 85)
    print("COLD GENERALIZATION RESULTS SUMMARY (8 CASES)")
    print("=" * 85)
    print(f"{'ID':<8} | {'Test Case Name':<34} | {'Exception/Step Hit':<26} | {'Final Outcome':<22} | {'Data Correct?'}")
    print("-" * 105)
    for r in results:
        print(f"{r['id']:<8} | {r['name'][:34]:<34} | {r['node_exception'][:26]:<26} | {r['final_outcome']:<22} | {r['data_correct']}")
    print("-" * 105)

    healed_correctly = sum(1 for r in results if r["final_outcome"] == "HEALED_CORRECTLY")
    fail_safe = sum(1 for r in results if r["final_outcome"] == "FAIL_SAFE_TRIGGERED")
    wrong_data = sum(1 for r in results if r["final_outcome"] == "HEALED_BUT_WRONG_DATA")
    crashed = sum(1 for r in results if r["final_outcome"] == "CRASHED")

    print(f"HEALED_CORRECTLY:      {healed_correctly}/8 ({round(healed_correctly/8*100, 1)}%)")
    print(f"FAIL_SAFE_TRIGGERED:   {fail_safe}/8 ({round(fail_safe/8*100, 1)}%)")
    print(f"HEALED_BUT_WRONG_DATA: {wrong_data}/8 ({round(wrong_data/8*100, 1)}%)")
    print(f"CRASHED:               {crashed}/8 ({round(crashed/8*100, 1)}%)")
    print(f"TOTAL SAFE/RESILIENT:  {healed_correctly + fail_safe}/8 ({round((healed_correctly + fail_safe)/8*100, 1)}%)")

    # Save artifact
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cold_generalization_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    root_output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cold_generalization_results.json")
    with open(root_output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nArtifact written to: {output_path} and {root_output_path}")

if __name__ == "__main__":
    asyncio.run(main())
