"""
AegisFlow — Novel Failure Validation Suite
Tests 15 completely new, unscripted broken payloads against the live pipeline.
Evaluates:
- Node Exception triggering
- Gemini diagnosis / Fallback routing
- Sandbox verification
- Resulting final data accuracy
- Exact final outcome category
"""

import asyncio
import json
import os
import sys
import tempfile
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.pipeline.schemas import RawBatch, CanonicalRecord, EnrichedRecord
from app.agent.orchestrator import PipelineOrchestrator
import app.pipeline.nodes as pipeline_nodes
from mock_service import init_db, clear_db

# ---------------------------------------------------------------------------
# 15 NOVEL TEST PAYLOADS DEFINITION
# ---------------------------------------------------------------------------
NOVEL_TEST_CASES = [
    {
        "id": "TC-01",
        "name": "Combined Renamed Field + Corrupt Epoch Timestamp",
        "description": "Field renamed to 'gross_amount' AND timestamp is epoch millisecond integer.",
        "payload": [
            {
                "tx_id": "TX-COMB-101",
                "user_id": "USR-101",
                "gross_amount": 1250.00,
                "currency": "USD",
                "timestamp": 1790336893000,
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount", "timestamp"]
    },
    {
        "id": "TC-02",
        "name": "Zero-Semantic Obscure Key Renaming ('val_7')",
        "description": "amount -> 'val_7', tx_id -> 'k_99', user_id -> 'u_alpha'.",
        "payload": [
            {
                "k_99": "TX-OBSC-202",
                "u_alpha": "USR-102",
                "val_7": 450.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount", "tx_id", "user_id"]
    },
    {
        "id": "TC-03",
        "name": "New Data Type Mutation (Nested Object Amount)",
        "description": "amount returned as object {'value': 850.25, 'unit': 'USD'}.",
        "payload": [
            {
                "tx_id": "TX-NEST-303",
                "user_id": "USR-103",
                "amount": {"value": 850.25, "unit": "USD"},
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount"]
    },
    {
        "id": "TC-04",
        "name": "Deep 5-Level Nested Envelope",
        "description": "Payload buried inside meta.api_version.gateway.feed.records.",
        "payload": {
            "meta": {
                "api_version": "v3",
                "gateway": {
                    "feed": {
                        "records": [
                            {
                                "tx_id": "TX-DEEP-404",
                                "user_id": "USR-104",
                                "amount": 320.0,
                                "currency": "USD",
                                "timestamp": "2026-09-25T16:00:00Z",
                                "status": "completed"
                            }
                        ]
                    }
                }
            }
        },
        "expected_cleanse_keys": ["tx_id"]
    },
    {
        "id": "TC-05",
        "name": "Sibling Property Shadowing & Conflicting Fields",
        "description": "amount is None, but 'original_amount': 990.0 and 'amount_override': 1200.0 present.",
        "payload": [
            {
                "tx_id": "TX-SIBL-505",
                "user_id": "USR-105",
                "amount": None,
                "original_amount": 990.0,
                "amount_override": 1200.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount"]
    },
    {
        "id": "TC-06",
        "name": "Inconsistent Heterogeneous Schemas Within Same Batch",
        "description": "Record 0 is standard; Record 1 has renamed gross_amount; Record 2 has epoch timestamp.",
        "payload": [
            {
                "tx_id": "TX-HET-601",
                "user_id": "USR-106A",
                "amount": 100.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            },
            {
                "reference_id": "TX-HET-602",
                "client_id": "USR-106B",
                "gross_amount": 200.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            },
            {
                "tx_id": "TX-HET-603",
                "user_id": "USR-106C",
                "amount": 300.0,
                "currency": "USD",
                "timestamp": 1758816000000,
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount", "tx_id", "timestamp"]
    },
    {
        "id": "TC-07",
        "name": "Valid JSON but Semantically Nonsensical (Negative Amount & Fake Currency)",
        "description": "Keys present, but amount is -2500.0 and currency is 'XYZ123'.",
        "payload": [
            {
                "tx_id": "TX-NONS-707",
                "user_id": "USR-107",
                "amount": -2500.0,
                "currency": "XYZ123",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": []
    },
    {
        "id": "TC-08",
        "name": "Completely Empty Array Payload",
        "description": "Upstream API returns zero records: [].",
        "payload": [],
        "expected_cleanse_keys": []
    },
    {
        "id": "TC-09",
        "name": "Duplicate Primary Key tx_id Collision in Same Batch",
        "description": "Two distinct records share identical tx_id 'TX-DUP-999'.",
        "payload": [
            {
                "tx_id": "TX-DUP-999",
                "user_id": "USR-109A",
                "amount": 500.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            },
            {
                "tx_id": "TX-DUP-999",
                "user_id": "USR-109B",
                "amount": 750.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": []
    },
    {
        "id": "TC-10",
        "name": "Natural Language Relative Timestamp",
        "description": "Timestamp formatted as natural language string 'two days ago'.",
        "payload": [
            {
                "tx_id": "TX-TIME-1010",
                "user_id": "USR-110",
                "amount": 420.0,
                "currency": "USD",
                "timestamp": "two days ago",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["timestamp"]
    },
    {
        "id": "TC-11",
        "name": "Sequential Back-to-Back Novel Failures (Cross-Patch Interference)",
        "description": "Run Obscure Key (TC-02) then immediately run Nested Amount (TC-03) on hot-patched node.",
        "payload": [
            {
                "tx_id": "TX-SEQ-1111",
                "user_id": "USR-111",
                "amount": {"val": 600.0},
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["amount"]
    },
    {
        "id": "TC-12",
        "name": "Nested Array Type for String user_id Identifier",
        "description": "user_id is passed as array ['USR-1', 'PARENT-CORP'] instead of string.",
        "payload": [
            {
                "tx_id": "TX-ARR-1212",
                "user_id": ["USR-CORP-1", "DEPT-FINANCE"],
                "amount": 310.0,
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["user_id"]
    },
    {
        "id": "TC-13",
        "name": "Numeric ISO 4217 Currency Code (840 for USD)",
        "description": "currency is integer 840 instead of string 'USD'.",
        "payload": [
            {
                "tx_id": "TX-ISO-1313",
                "user_id": "USR-113",
                "amount": 150.0,
                "currency": 840,
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_cleanse_keys": ["currency"]
    },
    {
        "id": "TC-14",
        "name": "Corrupt Upstream Gateway HTML/Text String",
        "description": "Payload is raw HTML string '<html>502 Bad Gateway</html>' instead of list/dict.",
        "payload": "<html><head><title>502 Bad Gateway</title></head><body><h1>Bad Gateway</h1></body></html>",
        "expected_cleanse_keys": []
    },
    {
        "id": "TC-15",
        "name": "Extreme Missing Keys (Only tx_id Present)",
        "description": "Record has tx_id but user_id, amount, currency, timestamp, status are all missing.",
        "payload": [
            {
                "tx_id": "TX-BARE-1515"
            }
        ],
        "expected_cleanse_keys": ["amount", "user_id", "currency", "timestamp", "status"]
    }
]

async def execute_test_case(tc: Dict[str, Any], orchestrator: PipelineOrchestrator, test_db: str) -> Dict[str, Any]:
    # Reset node state before each independent test
    if tc["id"] != "TC-11":
        orchestrator.reset_patches()

    payload = tc["payload"]
    
    # Intercept node_extract to deliver the exact test payload
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
        "node_exception": "None",
        "diagnosis_correct": "N/A",
        "sandbox_passed": "N/A",
        "data_correct": "No",
        "final_outcome": "UNKNOWN",
        "notes": ""
    }

    try:
        run_res = await orchestrator.run_pipeline(
            source_url="mock://novel-test",
            db_path=test_db,
            allow_fallback=True
        )

        # Inspect events
        events = run_res.events
        states = [e.get("state") for e in events]
        diagnose_events = [e for e in events if e.get("state") == "DIAGNOSE"]
        sandbox_events = [e for e in events if e.get("state") == "SANDBOX_TEST"]
        patch_events = [e for e in events if e.get("state") == "HOT_PATCH"]
        failsafe_events = [e for e in events if e.get("state") == "FAIL_SAFE"]

        # 1. Check which node triggered an exception
        if "DIAGNOSE" in states:
            failing_step = diagnose_events[0].get("detail", {}).get("failing_step", "")
            orig_err = diagnose_events[0].get("detail", {}).get("original_error", "")
            result_record["node_exception"] = f"Cleanse ({failing_step}): {orig_err[:40]}..."
        elif any("node_verify" in str(e.get("node")) for e in failsafe_events):
            result_record["node_exception"] = "Verify (Invariants Failed)"
        elif any("node_extract" in str(e.get("node")) for e in failsafe_events):
            result_record["node_exception"] = "Extract (Malformed Input)"
        elif any("node_enrich" in str(e.get("node")) for e in failsafe_events):
            result_record["node_exception"] = "Enrich (Calculation Error)"
        elif not run_res.success:
            result_record["node_exception"] = run_res.error[:45] if run_res.error else "Unknown"

        # 2. Check Diagnosis
        if diagnose_events:
            diag_detail = diagnose_events[0].get("detail", {})
            f_step = diag_detail.get("failing_step", "")
            if any(k in f_step for k in ["alias", "amount", "timestamp", "envelope"]):
                result_record["diagnosis_correct"] = "Yes"
            else:
                result_record["diagnosis_correct"] = "Partial"

        # 3. Check Sandbox
        if sandbox_events:
            result_record["sandbox_passed"] = "Yes"
        elif patch_events:
            result_record["sandbox_passed"] = "Yes (Cached/Verified)"
        else:
            result_record["sandbox_passed"] = "N/A"

        # 4. Check Data Correctness & Outcome
        if run_res.success and run_res.state == "DONE":
            # Hand-check data correctness against semantic expectations
            import sqlite3
            db_conn = sqlite3.connect(test_db)
            cursor = db_conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS enriched_market_records (
                    tx_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    tax REAL NOT NULL,
                    net_total REAL NOT NULL,
                    currency TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    ledger_batch_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    loaded_at TEXT NOT NULL
                );
            """)
            cursor.execute("SELECT tx_id, client_id, amount, net_total, currency, timestamp FROM enriched_market_records ORDER BY loaded_at DESC LIMIT 5")
            rows = cursor.fetchall()
            db_conn.close()

            # Analyze correctness of rows
            is_data_accurate = True
            if not rows and tc["id"] != "TC-08":
                is_data_accurate = False
            
            for row in rows:
                tx_id, client_id, amt, net_tot, curr, ts = row
                # Check for semantic corruption
                if amt is None or amt <= 0:
                    is_data_accurate = False
                if not curr or len(str(curr)) != 3 or str(curr) == "XYZ123":
                    is_data_accurate = False
                if "val_7" in tc["description"] and amt == 0.0:
                    is_data_accurate = False
                if tc["id"] == "TC-03" and amt == 0.0:
                    is_data_accurate = False
                if tc["id"] == "TC-15" and (amt == 0.0 or client_id == "USR-DEFAULT"):
                    # Missing all fields was hallucinated/defaulted rather than properly extracted
                    is_data_accurate = False

            if is_data_accurate:
                result_record["data_correct"] = "Yes"
                if run_res.heal_source in ["fallback", "gemini"]:
                    result_record["final_outcome"] = "HEALED_CORRECTLY"
                    result_record["notes"] = f"Autonomously healed via {run_res.heal_source} in {run_res.mttr_ms}ms MTTR."
                elif run_res.heal_source == "cached":
                    result_record["final_outcome"] = "HEALED_CORRECTLY"
                    result_record["notes"] = "Reused cached patch with zero latency."
                else:
                    result_record["final_outcome"] = "HEALED_CORRECTLY"
                    result_record["notes"] = "Pipeline processed and loaded cleanly."
            else:
                result_record["data_correct"] = "No"
                result_record["final_outcome"] = "HEALED_BUT_WRONG_DATA"
                result_record["notes"] = "Healed without exception, but resulting rows contained synthetic 0.0/fallback values."

        elif run_res.state == "FAIL_SAFE":
            result_record["data_correct"] = "No (Stopped)"
            result_record["final_outcome"] = "FAIL_SAFE_TRIGGERED"
            result_record["notes"] = f"Guardrail stopped pipeline: {run_res.error[:60]}"

        else:
            result_record["data_correct"] = "No"
            result_record["final_outcome"] = "CRASHED"
            result_record["notes"] = f"Pipeline unhandled error: {run_res.error}"

    except Exception as exc:
        result_record["node_exception"] = f"Exception: {type(exc).__name__}"
        result_record["final_outcome"] = "CRASHED"
        result_record["notes"] = f"Uncaught exception: {str(exc)[:60]}"

    finally:
        pipeline_nodes.node_extract = orig_extract

    return result_record


async def main():
    print("=" * 80)
    print("AEGISFLOW NOVEL FAILURE VALIDATION SUITE (15 UNSCRIPTED EDGE CASES)")
    print("=" * 80)

    test_db = os.path.join(tempfile.gettempdir(), "test_novel_suite.db")
    init_db(test_db)
    clear_db(test_db)

    orchestrator = PipelineOrchestrator(api_key=None)

    results = []
    for tc in NOVEL_TEST_CASES:
        print(f"--> Running {tc['id']}: {tc['name']}...")
        rec = await execute_test_case(tc, orchestrator, test_db)
        results.append(rec)
        print(f"    Outcome: {rec['final_outcome']} | Data Correct: {rec['data_correct']} | {rec['notes']}")

    # Clean test db
    if os.path.exists(test_db):
        os.remove(test_db)

    print("\n" + "=" * 80)
    print("FINAL RESULTS TABLE")
    print("=" * 80)
    print(f"{'ID':<6} | {'Test Case':<32} | {'Exception Node':<24} | {'Outcome':<22} | {'Correct Data?'}")
    print("-" * 105)
    
    correctly_healed_count = 0
    for r in results:
        is_correct = r["data_correct"] == "Yes" and r["final_outcome"] in ["HEALED_CORRECTLY"]
        if is_correct:
            correctly_healed_count += 1
        print(f"{r['id']:<6} | {r['name'][:32]:<32} | {r['node_exception'][:24]:<24} | {r['final_outcome']:<22} | {r['data_correct']}")

    print("-" * 105)
    print(f"ACCURACY SCORE: {correctly_healed_count}/15 ({round((correctly_healed_count/15)*100, 1)}%) correctly healed with verified data.")
    
    # Dump JSON for report generation
    with open("novel_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
