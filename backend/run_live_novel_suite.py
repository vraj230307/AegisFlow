"""
AegisFlow — Novel Failure Validation Suite (Live API Execution)
Runs 15 unscripted, novel broken payloads through the live pipeline via direct API calls
(bypassing dashboard buttons) against the live FastAPI backend on port 8000.
"""

import asyncio
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import httpx

# ---------------------------------------------------------------------------
# 15 NOVEL TEST PAYLOADS DEFINITION
# ---------------------------------------------------------------------------
NOVEL_TEST_CASES = [
    {
        "id": "TC-01",
        "name": "Combined Renamed Field + Corrupt Epoch Timestamp",
        "dimension": "Two failure types in SAME payload (renamed field + corrupt timestamp)",
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
        "expected_exception_node": "node_cleanse (resolve_key_aliases)",
        "expected_amount": 1250.00,
        "expected_client": "USR-101"
    },
    {
        "id": "TC-02",
        "name": "Zero-Semantic Obscure Key Renaming ('val_7')",
        "dimension": "No obvious semantic similarity (amount->val_7, tx_id->k_99, user_id->u_alpha)",
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
        "expected_exception_node": "node_cleanse (resolve_key_aliases)",
        "expected_amount": 450.0,
        "expected_client": "USR-102"
    },
    {
        "id": "TC-03",
        "name": "New Data Type Mutation (Nested Object Amount)",
        "dimension": "Amount as nested object {'value': 850.25, 'currency': 'USD'}",
        "payload": [
            {
                "tx_id": "TX-NEST-303",
                "user_id": "USR-103",
                "amount": {"value": 850.25, "currency": "USD"},
                "currency": "USD",
                "timestamp": "2026-09-25T16:00:00Z",
                "status": "completed"
            }
        ],
        "expected_exception_node": "node_cleanse (coerce_amount)",
        "expected_amount": 850.25,
        "expected_client": "USR-103"
    },
    {
        "id": "TC-04",
        "name": "Deep 5-Level Nested Envelope",
        "dimension": "Envelope nesting 5 levels deep (meta.api_version.gateway.feed.records)",
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
        "expected_exception_node": "node_cleanse (unwrap_envelope)",
        "expected_amount": 320.0,
        "expected_client": "USR-104"
    },
    {
        "id": "TC-05",
        "name": "Sibling Property Shadowing & Conflicting Fields",
        "dimension": "Field present but unexpected extra property alongside it (amount is None, original_amount=990.0)",
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
        "expected_exception_node": "node_cleanse (coerce_amount / resolve_key_aliases)",
        "expected_amount": 990.0,
        "expected_client": "USR-105"
    },
    {
        "id": "TC-06",
        "name": "Inconsistent Heterogeneous Schemas in Same Batch",
        "dimension": "Array where records have inconsistent schemas from each other in same batch",
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
        "expected_exception_node": "node_cleanse (resolve_key_aliases / normalize_timestamp)",
        "expected_amount": 600.0,
        "expected_client": "USR-106A"
    },
    {
        "id": "TC-07",
        "name": "Valid JSON but Semantically Nonsensical",
        "dimension": "All required fields present, but negative amount (-2500.0) & currency 'XYZ123'",
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
        "expected_exception_node": "node_enrich (EnrichError: invalid amount)",
        "expected_amount": None,
        "expected_client": None
    },
    {
        "id": "TC-08",
        "name": "Completely Empty Array Payload",
        "dimension": "Empty array [] returned by upstream",
        "payload": [],
        "expected_exception_node": "None (No exception)",
        "expected_amount": None,
        "expected_client": None
    },
    {
        "id": "TC-09",
        "name": "Duplicate Primary Key tx_id Collision in Same Batch",
        "dimension": "Duplicate tx_id 'TX-DUP-999' within the same batch",
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
        "expected_exception_node": "node_verify (Duplicate tx_id invariant)",
        "expected_amount": None,
        "expected_client": None
    },
    {
        "id": "TC-10",
        "name": "Natural Language Relative Timestamp",
        "dimension": "Timestamp format not covered by existing fixture ('two days ago')",
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
        "expected_exception_node": "node_cleanse (normalize_timestamp)",
        "expected_amount": 420.0,
        "expected_client": "USR-110"
    },
    {
        "id": "TC-11",
        "name": "Sequential Back-to-Back Failures (Cross-Patch Interference)",
        "dimension": "Two novel failures back to back in sequence without patch reset",
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
        "expected_exception_node": "node_cleanse (coerce_amount)",
        "expected_amount": 600.0,
        "expected_client": "USR-111"
    },
    {
        "id": "TC-12",
        "name": "Nested Array Type for String user_id Identifier",
        "dimension": "Field right name but wrong type (user_id as ['USR-CORP-1', 'DEPT-FINANCE'])",
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
        "expected_exception_node": "None / node_cleanse",
        "expected_amount": 310.0,
        "expected_client": "USR-CORP-1"
    },
    {
        "id": "TC-13",
        "name": "Numeric ISO 4217 Currency Code (840 for USD)",
        "dimension": "Currency code provided as numeric integer 840 instead of string 'USD'",
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
        "expected_exception_node": "None / node_cleanse",
        "expected_amount": 150.0,
        "expected_client": "USR-113"
    },
    {
        "id": "TC-14",
        "name": "Corrupt Upstream Gateway HTML/Text String",
        "dimension": "Payload is raw HTML 502 Bad Gateway string instead of JSON array/dict",
        "payload": "<html><head><title>502 Bad Gateway</title></head><body><h1>Bad Gateway</h1></body></html>",
        "expected_exception_node": "node_cleanse (unwrap_envelope)",
        "expected_amount": None,
        "expected_client": None
    },
    {
        "id": "TC-15",
        "name": "Extreme Missing Keys (Only tx_id Present)",
        "dimension": "Only tx_id present; amount, user_id, currency, timestamp, status missing",
        "payload": [
            {
                "tx_id": "TX-BARE-1515"
            }
        ],
        "expected_exception_node": "node_cleanse (resolve_key_aliases)",
        "expected_amount": None,
        "expected_client": None
    }
]

# ---------------------------------------------------------------------------
# MOCK HTTP SERVER SERVING TEST CASES ON PORT 8005
# ---------------------------------------------------------------------------
PAYLOAD_MAP = {tc["id"]: tc["payload"] for tc in NOVEL_TEST_CASES}

class MockPayloadHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Path format: /tc/<id>
        tc_id = self.path.strip("/").split("/")[-1]
        if tc_id in PAYLOAD_MAP:
            data = PAYLOAD_MAP[tc_id]
            body = json.dumps(data).encode("utf-8") if not isinstance(data, str) else data.encode("utf-8")
            self.send_response(200)
            if isinstance(data, str):
                self.send_header("Content-Type", "text/html; charset=utf-8")
            else:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        pass  # Quiet logging

def start_mock_server(port: int = 8005) -> http.server.HTTPServer:
    server = socketserver.TCPServer(("127.0.0.1", port), MockPayloadHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server

# ---------------------------------------------------------------------------
# TEST RUNNER ENGINE
# ---------------------------------------------------------------------------
async def run_suite():
    print("=" * 85)
    print("AEGISFLOW NOVEL FAILURE VALIDATION SUITE — 15 UNSCRIPTED CASES")
    print("=" * 85)

    # 1. Start Mock Payload Server
    mock_server = start_mock_server(8005)
    print("[INIT] Mock Payload HTTP server running on http://127.0.0.1:8005")

    api_base = "http://127.0.0.1:8000"
    db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data.db")

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check backend health
        try:
            h_resp = await client.get(f"{api_base}/api/health")
            print(f"[INIT] Live Backend Health: {h_resp.json()}")
        except Exception as e:
            print(f"[FATAL] Backend not reachable at {api_base}: {e}")
            mock_server.shutdown()
            return

        for idx, tc in enumerate(NOVEL_TEST_CASES):
            tc_id = tc["id"]
            tc_name = tc["name"]
            source_url = f"http://127.0.0.1:8005/tc/{tc_id}"

            print(f"\n[{idx+1}/15] Executing {tc_id}: {tc_name}...")
            print(f"      Dimension: {tc['dimension']}")

            # Reset patches unless this is TC-11 (interference test)
            if tc_id != "TC-11":
                await client.post(f"{api_base}/api/orchestrator/reset")

            # Reset database table for fresh record verification
            try:
                conn = sqlite3.connect(db_file)
                with conn:
                    conn.execute("DELETE FROM enriched_market_records;")
                conn.close()
            except Exception:
                pass

            record_res = {
                "id": tc_id,
                "name": tc_name,
                "dimension": tc["dimension"],
                "payload_sample": tc["payload"] if not isinstance(tc["payload"], str) else tc["payload"][:80],
                "node_exception": "None",
                "gemini_called": False,
                "gemini_diagnosis": "N/A",
                "diagnosis_correct": "N/A",
                "sandbox_passed": "N/A",
                "heal_source": None,
                "rows_loaded": 0,
                "data_correct": "No",
                "final_outcome": "UNKNOWN",
                "hand_check_details": "",
                "mttr_ms": 0.0
            }

            try:
                t0 = time.time()
                res = await client.post(
                    f"{api_base}/api/orchestrator/run",
                    json={
                        "source_url": source_url,
                        "allow_fallback": True
                    }
                )
                duration_ms = round((time.time() - t0) * 1000, 2)
                res_data = res.json()

                events = res_data.get("events", [])
                states = [e.get("state") for e in events]
                diag_events = [e for e in events if e.get("state") == "DIAGNOSE"]
                synth_events = [e for e in events if e.get("state") == "SYNTHESIZE"]
                sb_events = [e for e in events if e.get("state") == "SANDBOX_TEST"]
                patch_events = [e for e in events if e.get("state") == "HOT_PATCH"]
                fallback_events = [e for e in events if e.get("state") == "FALLBACK_HEAL"]
                failsafe_events = [e for e in events if e.get("state") == "FAIL_SAFE"]

                record_res["mttr_ms"] = res_data.get("mttr_ms", 0.0)
                record_res["heal_source"] = res_data.get("heal_source")

                # 1. Identify Node Exception Triggered
                if diag_events:
                    step = diag_events[0].get("detail", {}).get("failing_step", "")
                    err = diag_events[0].get("detail", {}).get("original_error", "")
                    record_res["node_exception"] = f"node_cleanse ({step}): {err[:45]}"
                elif any("node_enrich" in str(e.get("node")) for e in failsafe_events):
                    record_res["node_exception"] = "node_enrich (EnrichError: invalid amount / math)"
                elif any("node_verify" in str(e.get("node")) for e in failsafe_events):
                    record_res["node_exception"] = "node_verify (VerificationResult invariants failed)"
                elif any("node_extract" in str(e.get("node")) for e in failsafe_events):
                    record_res["node_exception"] = "node_extract (ExtractError: HTTP / Parse failure)"
                elif not res_data.get("success", False):
                    record_res["node_exception"] = res_data.get("error", "Unknown Error")[:50]

                # 2. Check Gemini diagnosis
                if synth_events:
                    record_res["gemini_called"] = True
                if patch_events and res_data.get("heal_source") == "gemini":
                    g_diag = patch_events[0].get("detail", {}).get("diagnosis", "")
                    record_res["gemini_diagnosis"] = g_diag
                    # Substantive correctness check: did it mention the actual field/type?
                    keywords = [
                        "amount", "gross_amount", "val_7", "value", "timestamp", "epoch",
                        "envelope", "dict", "type", "alias", "missing", "user_id"
                    ]
                    if any(k in g_diag.lower() for k in keywords):
                        record_res["diagnosis_correct"] = "Yes"
                    else:
                        record_res["diagnosis_correct"] = "Partial"
                elif diag_events:
                    record_res["diagnosis_correct"] = "No (Gemini failed/retried)"

                # 3. Check Sandbox Validation
                if sb_events:
                    # Check if sandbox rejected any Gemini patch
                    sb_diagnose = [e for e in diag_events if "sandbox" in str(e.get("node"))]
                    if sb_diagnose:
                        record_res["sandbox_passed"] = "Rejected"
                    else:
                        record_res["sandbox_passed"] = "Yes"
                elif patch_events and res_data.get("heal_source") == "cached":
                    record_res["sandbox_passed"] = "Yes (Cached)"
                else:
                    record_res["sandbox_passed"] = "N/A"

                # 4. Check Database Persisted Rows & Hand-Verify Data
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS enriched_market_records (
                        tx_id TEXT PRIMARY KEY, client_id TEXT, amount REAL, tax REAL,
                        net_total REAL, currency TEXT, timestamp TEXT, ledger_batch_id TEXT,
                        status TEXT, loaded_at TEXT
                    )
                """)
                cursor.execute("SELECT tx_id, client_id, amount, tax, net_total, currency, timestamp FROM enriched_market_records")
                rows = cursor.fetchall()
                conn.close()

                record_res["rows_loaded"] = len(rows)

                # HAND CHECK DATA AGAINST SPECIFIC EXPECTATION
                is_correct = False
                hand_notes = ""

                if tc_id == "TC-01":
                    # Combined gross_amount (1250.0) + epoch timestamp
                    if rows and rows[0][2] == 1250.00 and rows[0][6].endswith("Z"):
                        is_correct = True
                        hand_notes = f"Row verified: tx_id={rows[0][0]}, amount=${rows[0][2]}, ts={rows[0][6]}"
                    else:
                        hand_notes = f"Data mismatch: rows={rows}"

                elif tc_id == "TC-02":
                    # val_7 (450.0), k_99, u_alpha
                    if rows and rows[0][2] == 450.0 and rows[0][0] == "TX-OBSC-202":
                        is_correct = True
                        hand_notes = f"Row verified: val_7 correctly mapped to amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Zero-semantic renaming failed: amount={rows[0][2] if rows else 'None'}"

                elif tc_id == "TC-03":
                    # nested object amount: {'value': 850.25}
                    if rows and rows[0][2] == 850.25:
                        is_correct = True
                        hand_notes = f"Row verified: nested object unpacked to amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Nested amount failed: amount={rows[0][2] if rows else 'None'} (expected 850.25)"

                elif tc_id == "TC-04":
                    # 5-level deep envelope
                    if rows and rows[0][2] == 320.0 and rows[0][0] == "TX-DEEP-404":
                        is_correct = True
                        hand_notes = f"Row verified: 5-level envelope unwrapped, amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Deep unwrapping failed: rows={rows}"

                elif tc_id == "TC-05":
                    # Sibling shadowing: amount is None, original_amount=990.0
                    if rows and rows[0][2] in [990.0, 1200.0]:
                        is_correct = True
                        hand_notes = f"Row verified: picked sibling amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Sibling extraction failed: amount={rows[0][2] if rows else 'None'}"

                elif tc_id == "TC-06":
                    # Inconsistent batch: 3 records with different drift
                    if len(rows) == 3 and {r[2] for r in rows} == {100.0, 200.0, 300.0}:
                        is_correct = True
                        hand_notes = f"All 3 heterogeneous rows healed & loaded: amounts={[r[2] for r in rows]}"
                    else:
                        hand_notes = f"Batch mismatch: len={len(rows)}, amounts={[r[2] for r in rows]}"

                elif tc_id == "TC-07":
                    # Nonsensical: negative amount -2500.0. MUST FAIL_SAFE!
                    if res_data.get("state") == "FAIL_SAFE" and len(rows) == 0:
                        is_correct = True
                        hand_notes = "Guardrail correctly triggered: negative amount stopped at enrich node."
                    else:
                        hand_notes = f"Security violation: nonsensical record was permitted! state={res_data.get('state')}"

                elif tc_id == "TC-08":
                    # Empty array: []
                    if len(rows) == 0 and res_data.get("success"):
                        is_correct = True
                        hand_notes = "Empty payload handled gracefully: 0 rows loaded without exception."
                    else:
                        hand_notes = f"Unexpected state for empty array: {res_data.get('state')}"

                elif tc_id == "TC-09":
                    # Duplicate tx_id: MUST FAIL_SAFE at verify node!
                    if res_data.get("state") == "FAIL_SAFE" and len(rows) == 0:
                        is_correct = True
                        hand_notes = "Guardrail correctly triggered: duplicate primary key stopped at verify node."
                    else:
                        hand_notes = f"Integrity violation: duplicate tx_id was loaded into ledger!"

                elif tc_id == "TC-10":
                    # 'two days ago' timestamp
                    if rows and rows[0][2] == 420.0 and rows[0][6].endswith("Z"):
                        is_correct = True
                        hand_notes = f"Timestamp normalized to ISO 8601: {rows[0][6]}"
                    else:
                        hand_notes = f"Timestamp normalization failed: ts={rows[0][6] if rows else 'None'}"

                elif tc_id == "TC-11":
                    # Sequential back-to-back cross-patch test
                    if rows and rows[0][2] == 600.0:
                        is_correct = True
                        hand_notes = f"Row verified: amount=${rows[0][2]} without cross-patch interference."
                    else:
                        hand_notes = f"Sequential failure: amount={rows[0][2] if rows else 'None'} (expected 600.0)"

                elif tc_id == "TC-12":
                    # user_id as array ['USR-CORP-1', 'DEPT-FINANCE']
                    if rows and rows[0][2] == 310.0 and "USR-CORP-1" in str(rows[0][1]):
                        is_correct = True
                        hand_notes = f"Array client_id handled cleanly: client_id='{rows[0][1]}', amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Array user_id failed: client_id='{rows[0][1] if rows else 'None'}'"

                elif tc_id == "TC-13":
                    # Currency 840 (ISO numeric for USD)
                    if rows and rows[0][2] == 150.0 and str(rows[0][5]) in ["840", "USD"]:
                        is_correct = True
                        hand_notes = f"Numeric currency handled cleanly: currency='{rows[0][5]}', amount=${rows[0][2]}"
                    else:
                        hand_notes = f"Numeric currency failed: curr='{rows[0][5] if rows else 'None'}'"

                elif tc_id == "TC-14":
                    # Corrupt 502 HTML: MUST FAIL_SAFE!
                    if res_data.get("state") == "FAIL_SAFE":
                        is_correct = True
                        hand_notes = "Guardrail correctly triggered: corrupt HTML safely rejected after retry cap."
                    else:
                        hand_notes = f"Unexpected state for corrupt HTML: {res_data.get('state')}"

                elif tc_id == "TC-15":
                    # Bare tx_id only: Missing all critical fields.
                    # Correct behavior is either FAIL_SAFE (rejected) or if healed with wrong data.
                    if res_data.get("state") == "FAIL_SAFE":
                        is_correct = True
                        hand_notes = "Guardrail correctly stopped record missing all financial data."
                    else:
                        is_correct = False
                        hand_notes = f"Healed via fallback defaults: synthetic amount={rows[0][2] if rows else 'None'}, guest user."

                record_res["data_correct"] = "Yes" if is_correct else "No"
                record_res["hand_check_details"] = hand_notes

                # 5. Determine Final Outcome Category
                state = res_data.get("state")
                heal_source = res_data.get("heal_source")
                sb_passed = record_res["sandbox_passed"]

                if state == "DONE" and is_correct:
                    if heal_source in ["gemini", "cached"]:
                        record_res["final_outcome"] = "HEALED_CORRECTLY"
                    elif heal_source == "fallback":
                        record_res["final_outcome"] = "FALLBACK_USED"
                    else:
                        record_res["final_outcome"] = "HEALED_CORRECTLY"

                elif state == "DONE" and not is_correct:
                    record_res["final_outcome"] = "HEALED_BUT_WRONG_DATA"

                elif sb_passed == "Rejected":
                    record_res["final_outcome"] = "SANDBOX_REJECTED"

                elif state == "FAIL_SAFE":
                    record_res["final_outcome"] = "FAIL_SAFE_TRIGGERED"

                elif heal_source == "fallback" and not is_correct:
                    record_res["final_outcome"] = "FALLBACK_USED"

                else:
                    record_res["final_outcome"] = "CRASHED"

            except Exception as exc:
                record_res["node_exception"] = f"Exception: {type(exc).__name__}"
                record_res["final_outcome"] = "CRASHED"
                record_res["hand_check_details"] = f"Runner exception: {str(exc)[:60]}"

            print(f"      Outcome: {record_res['final_outcome']} | Correct Data: {record_res['data_correct']} | {record_res['hand_check_details']}")
            results.append(record_res)

    mock_server.shutdown()

    # Save complete JSON artifact
    with open("novel_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Print Markdown Deliverable
    print("\n" + "=" * 85)
    print("DELIVERABLE TABLE: AEGISFLOW NOVEL FAILURE VALIDATION SUITE (15 RUNS)")
    print("=" * 85)
    correct_count = sum(1 for r in results if r["data_correct"] == "Yes")
    print(f"ACCURACY SCORE: {correct_count}/15 ({round((correct_count/15)*100, 1)}%) correctly healed / safely handled with verified data.\n")

if __name__ == "__main__":
    asyncio.run(run_suite())
