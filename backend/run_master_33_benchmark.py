"""
AegisFlow — Master 33-Case Precision Benchmark Suite
Runs all 33 distinct test cases:
- 15 Original Novel Cases (TC-01 to TC-15)
- 10 Fresh Novel Cases (TC-16 to TC-25)
- 8 Structural Cold Cases (COLD-01 to COLD-08)
Verifies exact SQLite rows, invariant enforcement, and zero silent data corruption.
"""

import asyncio
import json
import os
import sys
import tempfile
import sqlite3
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_novel_validation_suite import NOVEL_TEST_CASES, execute_test_case
from run_fresh_novel_suite import FRESH_10_TEST_CASES, execute_case as execute_fresh_case
from run_cold_generalization_test import COLD_8_TEST_CASES, execute_cold_case
from app.agent.orchestrator import PipelineOrchestrator
from mock_service import init_db, clear_db

async def run_master_benchmark(progress_callback=None):
    print("=" * 95)
    print("AEGISFLOW MASTER 33-CASE PRECISION BENCHMARK SUITE")
    print("Evaluating Invariant Enforcement, Healing Accuracy, and Safe Refusals Across All Scenarios")
    print("=" * 95)

    test_db = os.path.join(tempfile.gettempdir(), "test_master_benchmark.db")
    init_db(test_db)
    orchestrator = PipelineOrchestrator(api_key=None)

    all_results = []
    total_cases = len(NOVEL_TEST_CASES) + len(FRESH_10_TEST_CASES) + len(COLD_8_TEST_CASES)
    current_idx = 0

    # 1. Original 15 Cases
    print("\n--- PHASE 1: Original 15 Novel Failure Cases (TC-01 to TC-15) ---")
    for idx, tc in enumerate(NOVEL_TEST_CASES):
        current_idx += 1
        clear_db(test_db)
        res = await execute_test_case(tc, orchestrator, test_db)
        print(f"[{current_idx:02d}/33] {tc['id']}: {res['final_outcome']} | Correct: {res['data_correct']} | {tc['name']}")
        rec = {
            "suite": "Original 15",
            "id": tc["id"],
            "name": tc["name"],
            "dimension": tc.get("desc") or tc.get("dimension") or tc["name"],
            "outcome": res["final_outcome"],
            "data_correct": res["data_correct"],
            "node_exception": res.get("node_exception", "None"),
            "payload": tc["payload"],
            "row_data": res.get("row_data", []),
            "notes": res["notes"]
        }
        all_results.append(rec)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(current_idx, total_cases, rec)
            else:
                progress_callback(current_idx, total_cases, rec)

    # 2. Fresh 10 Cases
    print("\n--- PHASE 2: Fresh 10 Structural Cases (TC-16 to TC-25) ---")
    for idx, tc in enumerate(FRESH_10_TEST_CASES):
        current_idx += 1
        clear_db(test_db)
        res = await execute_fresh_case(tc, orchestrator, test_db)
        print(f"[{current_idx:02d}/33] {tc['id']}: {res['final_outcome']} | Correct: {res['data_correct']} | {tc['name']}")
        rec = {
            "suite": "Fresh 10",
            "id": tc["id"],
            "name": tc["name"],
            "dimension": tc.get("dimension") or tc["name"],
            "outcome": res["final_outcome"],
            "data_correct": res["data_correct"],
            "node_exception": res.get("node_exception", "None"),
            "payload": tc["payload"],
            "row_data": res.get("row_data", []),
            "notes": res["notes"]
        }
        all_results.append(rec)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(current_idx, total_cases, rec)
            else:
                progress_callback(current_idx, total_cases, rec)

    # 3. Cold 8 Cases
    print("\n--- PHASE 3: Cold 8 Structural Cases (COLD-01 to COLD-08) ---")
    for idx, tc in enumerate(COLD_8_TEST_CASES):
        current_idx += 1
        clear_db(test_db)
        res = await execute_cold_case(tc, orchestrator, test_db)
        print(f"[{current_idx:02d}/33] {tc['id']}: {res['final_outcome']} | Correct: {res['data_correct']} | {tc['name']}")
        rec = {
            "suite": "Cold 8",
            "id": tc["id"],
            "name": tc["name"],
            "dimension": tc.get("dimension") or tc["name"],
            "outcome": res["final_outcome"],
            "data_correct": res["data_correct"],
            "node_exception": res.get("node_exception", "None"),
            "payload": tc["payload"],
            "row_data": res.get("row_data", []),
            "notes": res["notes"]
        }
        all_results.append(rec)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(current_idx, total_cases, rec)
            else:
                progress_callback(current_idx, total_cases, rec)

    print("\n" + "=" * 95)
    print("MASTER 33-CASE BENCHMARK SUMMARY")
    print("=" * 95)

    suites = ["Original 15", "Fresh 10", "Cold 8"]
    summary_by_suite = {}

    for s in suites:
        s_cases = [r for r in all_results if r["suite"] == s]
        healed = sum(1 for r in s_cases if r["outcome"] == "HEALED_CORRECTLY")
        failsafe = sum(1 for r in s_cases if r["outcome"] == "FAIL_SAFE_TRIGGERED")
        wrong = sum(1 for r in s_cases if r["outcome"] == "HEALED_BUT_WRONG_DATA")
        crashed = sum(1 for r in s_cases if r["outcome"] == "CRASHED")
        total = len(s_cases)
        resilient = healed + failsafe
        summary_by_suite[s] = {
            "total": total,
            "healed": healed,
            "failsafe": failsafe,
            "wrong": wrong,
            "crashed": crashed,
            "resilient": resilient,
            "resilient_pct": round(resilient / total * 100, 1),
            "healed_pct": round(healed / total * 100, 1)
        }

    total_healed = sum(1 for r in all_results if r["outcome"] == "HEALED_CORRECTLY")
    total_failsafe = sum(1 for r in all_results if r["outcome"] == "FAIL_SAFE_TRIGGERED")
    total_wrong = sum(1 for r in all_results if r["outcome"] == "HEALED_BUT_WRONG_DATA")
    total_crashed = sum(1 for r in all_results if r["outcome"] == "CRASHED")
    total_resilient = total_healed + total_failsafe

    print(f"{'Suite':<14} | {'Total':<6} | {'Healed':<8} | {'Fail-Safe':<10} | {'Wrong Data':<11} | {'Crashed':<8} | {'Safe/Resilient Rate'}")
    print("-" * 95)
    for s in suites:
        info = summary_by_suite[s]
        print(f"{s:<14} | {info['total']:<6} | {info['healed']:<8} | {info['failsafe']:<10} | {info['wrong']:<11} | {info['crashed']:<8} | {info['resilient']}/{info['total']} ({info['resilient_pct']}%)")
    print("-" * 95)
    print(f"{'OVERALL (33)':<14} | {33:<6} | {total_healed:<8} | {total_failsafe:<10} | {total_wrong:<11} | {total_crashed:<8} | {total_resilient}/33 ({round(total_resilient/33*100, 1)}%)")
    print("=" * 95)

    # Save artifacts
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_33_validation_results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    root_out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "master_33_validation_results.json")
    with open(root_out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nArtifact saved to: {out_path} and {root_out_path}")

if __name__ == "__main__":
    asyncio.run(run_master_benchmark())
